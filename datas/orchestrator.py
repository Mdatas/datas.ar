"""The Datas orchestrator: detect → recommend → install → run, shared by CLI and server.

This is the "minimal local AI that sets you up" — except it is not an AI at all, it is a
small deterministic program. It reads the device, picks a model, fetches llama.cpp and
the weights, starts the server with safe flags, and keeps the handles.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from datas import __version__
from datas.catalog import Catalog, CatalogModel, ModelFile
from datas.catalog import load as load_catalog
from datas.config import Config, home, models_dir
from datas.hardware.detect import DeviceSpec, detect
from datas.pool.discovery import Node, discover, parse_manual
from datas.recommend.engine import (
    Budget,
    Candidate,
    Recommendation,
    budget_for,
    evaluate,
    llama_server_args,
    pool_budget,
    recommend,
)
from datas.runtime import downloader, gguf_meta, llamacpp
from datas.runtime.process import LlamaServer, bench

GiB = 2**30


# ---------------------------------------------------------------------------
# Jobs (long-running work the UI polls)
# ---------------------------------------------------------------------------


@dataclass
class Job:
    id: str
    kind: str  # runtime | model | run | bench
    title: str
    state: str = "queued"  # queued | running | done | error
    phase: str = ""
    done: int = 0
    total: int | None = None
    started: float = field(default_factory=time.time)
    finished: float | None = None
    error: str | None = None
    result: dict | None = None
    log: list[str] = field(default_factory=list)

    def progress(self, done: int, total: int | None) -> None:
        self.done, self.total = done, total

    def say(self, msg: str) -> None:
        self.log.append(msg)
        self.log = self.log[-200:]

    def to_dict(self) -> dict:
        pct = (self.done / self.total * 100) if self.total else None
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "state": self.state,
            "phase": self.phase,
            "done": self.done,
            "total": self.total,
            "percent": round(pct, 1) if pct is not None else None,
            "started": self.started,
            "finished": self.finished,
            "error": self.error,
            "result": self.result,
            "log": self.log[-30:],
        }


# ---------------------------------------------------------------------------


class Datas:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config.load()
        self.server = LlamaServer(self.cfg)
        self.jobs: dict[str, Job] = {}
        self._spec: DeviceSpec | None = None
        self._spec_at = 0.0
        self._pool_nodes: list[Node] = []
        self._lock = threading.Lock()

    # ---- device -----------------------------------------------------------
    def spec(self, refresh: bool = False) -> DeviceSpec:
        if refresh or self._spec is None or time.time() - self._spec_at > 60:
            self._spec = detect()
            self._spec_at = time.time()
        return self._spec

    def budget(self, headroom: float | None = None) -> Budget:
        return budget_for(
            self.spec(),
            headroom if headroom is not None else self.cfg.headroom,
            self.cfg.headroom_min_gib,
        )

    # ---- catalog / recommendation ----------------------------------------
    @property
    def catalog(self) -> Catalog:
        return load_catalog()

    def recommendation(
        self,
        headroom: float | None = None,
        context: int | None = None,
        kv_bits: int = 16,
        want: list[str] | None = None,
        role: str = "general",
        pool_nodes: list[Node] | None = None,
    ) -> Recommendation:
        ctx = context or self.cfg.context
        hr = headroom if headroom is not None else self.cfg.headroom
        if pool_nodes:
            local = budget_for(self.spec(), hr, self.cfg.headroom_min_gib)
            remote = [
                Budget(
                    ram_total=n.ram_budget,
                    ram_budget=n.ram_budget,
                    ram_headroom=0,
                    vram_total=n.vram_budget,
                    vram_budget=n.vram_budget,
                    unified=False,
                    backend=n.backend or "cpu",
                    disk_free=0,
                    threads=1,
                )
                for n in pool_nodes
            ]
            b = pool_budget([local, *remote])
            return recommend(
                self.spec(), budget=b, context=ctx, kv_bits=kv_bits, want=want, role=role, pool=True
            )
        return recommend(
            self.spec(),
            headroom=hr,
            headroom_min_gib=self.cfg.headroom_min_gib,
            context=ctx,
            kv_bits=kv_bits,
            want=want,
            role=role,
        )

    def candidate(
        self,
        model_id: str,
        quant: str | None = None,
        context: int | None = None,
        kv_bits: int = 16,
        pool_nodes: list[Node] | None = None,
    ) -> tuple[CatalogModel, ModelFile, Candidate]:
        m = self.catalog.get(model_id)
        f = m.file(quant) if quant else m.smallest()
        rec = self.recommendation(context=context, kv_bits=kv_bits, pool_nodes=pool_nodes)
        c = evaluate(m, f, rec.budget, context or self.cfg.context, kv_bits, pool=bool(pool_nodes))
        return m, f, c

    # ---- jobs --------------------------------------------------------------
    def _job(self, kind: str, title: str) -> Job:
        j = Job(id=uuid.uuid4().hex[:10], kind=kind, title=title)
        self.jobs[j.id] = j
        return j

    def _run_job(self, job: Job, fn: Callable[[Job], dict | None]) -> Job:
        def body():
            job.state = "running"
            try:
                job.result = fn(job) or {}
                job.state = "done"
            except Exception as e:  # noqa: BLE001 — surfaced to the UI
                job.state = "error"
                job.error = f"{type(e).__name__}: {e}"
                job.say(job.error)
            finally:
                job.finished = time.time()

        threading.Thread(target=body, daemon=True).start()
        return job

    # ---- runtime -----------------------------------------------------------
    def runtime_installed(self) -> bool:
        return llamacpp.installed_dir(self.cfg) is not None

    def ensure_runtime(self, job: Job | None = None) -> Path:
        say = job.say if job else print
        prog = job.progress if job else None
        if job:
            job.phase = "runtime"
        return llamacpp.install(self.spec(), self.cfg, progress=prog, log=say)

    # ---- model -------------------------------------------------------------
    def ensure_model(
        self, model_id: str, quant: str, job: Job | None = None, with_vision: bool = False
    ) -> Path:
        m = self.catalog.get(model_id)
        f = m.file(quant)
        say = job.say if job else print
        if job:
            job.phase = "model"
            job.total = f.bytes
        if downloader.is_downloaded(m, f):
            say(f"Model already on disk: {f.path}")
            if job:
                job.done = f.bytes
            return downloader.local_path(m, f)
        say(f"Downloading {m.name} {f.quant} ({f.bytes / GiB:.1f} GiB) from {m.hf_url}")
        return downloader.download_model(
            m, f, progress=(job.progress if job else None), with_vision=with_vision, log=say
        )

    def refine(self, c: Candidate, path: Path, budget: Budget) -> tuple[Candidate, list[str]]:
        """Replace the KV estimate with the GGUF header's exact values; shrink ctx if needed."""
        notes: list[str] = []
        try:
            facts = gguf_meta.read(path)
        except Exception as e:  # unreadable header → keep the estimate
            return c, [f"Could not read GGUF header ({e}); keeping the estimate."]
        hint = facts.kv_hint()
        if not hint:
            return c, notes
        m = self.catalog.get(c.model_id)
        m2 = m.model_copy(update={"kv": hint})
        f = m.file(c.quant)
        ctx = c.need.context
        if facts.context_train and ctx > facts.context_train:
            notes.append(f"Context capped at the model's trained length ({facts.context_train}).")
            ctx = facts.context_train
        new = evaluate(m2, f, budget, ctx, c.need.kv_bits, pool=(c.placement == "pool"))
        while not new.fits and ctx > 2048:
            ctx //= 2
            new = evaluate(m2, f, budget, ctx, c.need.kv_bits, pool=(c.placement == "pool"))
        if ctx != c.need.context:
            notes.append(f"Context reduced to {ctx} so the exact KV cache fits the budget.")
        if new.need.kv_cache != c.need.kv_cache:
            notes.append(
                f"Exact KV cache: {new.need.kv_cache / GiB:.2f} GiB at {ctx} tokens (estimate was {c.need.kv_cache / GiB:.2f})."
            )
        return new, notes

    # ---- run ---------------------------------------------------------------
    def run(
        self,
        model_id: str,
        quant: str,
        context: int | None = None,
        kv_bits: int = 16,
        pool_nodes: list[Node] | None = None,
        job: Job | None = None,
        exact_layers: bool = False,
        with_vision: bool = False,
    ) -> dict:
        say = job.say if job else print
        self.ensure_runtime(job)
        path = self.ensure_model(model_id, quant, job, with_vision=with_vision)
        m, f, c = self.candidate(model_id, quant, context, kv_bits, pool_nodes)
        rec_budget = self.recommendation(
            context=context, kv_bits=kv_bits, pool_nodes=pool_nodes
        ).budget
        c, notes = self.refine(c, path, rec_budget)
        for n in notes:
            say(n)
        if not c.fits:
            say(
                "Warning: this model does not fit the budget; starting anyway because you asked. "
                "llama-server --fit will shrink what it can; expect swapping or a failed load."
            )
        rpc = [n.endpoint for n in pool_nodes] if pool_nodes else None
        if pool_nodes:
            for n in pool_nodes:
                if n.tag and n.tag != self.cfg.llamacpp_tag:
                    say(
                        f"Warning: worker {n.host} runs llama.cpp {n.tag}, this node runs {self.cfg.llamacpp_tag}. "
                        "RPC needs identical builds — run `datas runtime pin` on both."
                    )
        mmproj = None
        if with_vision and "mmproj" in m.extras:
            mp = downloader.local_path(m, m.extras["mmproj"].path)
            mmproj = str(mp) if mp.exists() else None
        args = llama_server_args(
            c,
            rec_budget,
            str(path),
            self.cfg.llama_port,
            rpc=rpc,
            mmproj_path=mmproj,
            exact_layers=exact_layers,
        )
        if job:
            job.phase = "starting"
        say("Starting llama-server: " + " ".join(args))
        state = self.server.start(args, str(path), model_id, quant, rpc=rpc)
        self.cfg.model_id, self.cfg.quant = model_id, quant
        self.cfg.provider = "pool" if rpc else "local"
        self.cfg.save()
        say(f"Ready at {self.server.base_url()}/v1 (OpenAI-compatible).")
        return {"server": state.to_dict(), "candidate": c.to_dict(), "notes": notes}

    def run_custom(
        self,
        path: str | Path,
        context: int | None = None,
        kv_bits: int = 16,
        ngl: str = "auto",
        job: Job | None = None,
    ) -> dict:
        """Run a GGUF the user already has. Memory check uses the file's real header."""
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(p)
        self.ensure_runtime(job)
        b = self.budget()
        facts = gguf_meta.read(p)
        ctx = min(context or self.cfg.context, facts.context_train or 10**9)
        hint = facts.kv_hint()
        kv = hint.bytes_per_token(kv_bits) * ctx if hint else 0
        need = p.stat().st_size + kv + int(0.08 * p.stat().st_size) + 512 * 2**20
        say = job.say if job else print
        if need > b.total_budget:
            say(
                f"Warning: {p.name} needs ≈{need / GiB:.1f} GiB, budget is {b.total_budget / GiB:.1f} GiB."
            )
        args = [
            "-m",
            str(p),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.cfg.llama_port),
            "-c",
            str(ctx),
            "-t",
            str(b.threads),
            "--jinja",
            "-fa",
            "auto",
            "--fit",
            "on",
            "--fit-target",
            str(max(256, b.ram_headroom // 2**20)),
            "-ngl",
            str(ngl),
        ]
        if kv_bits == 8:
            args += ["-ctk", "q8_0", "-ctv", "q8_0"]
        state = self.server.start(
            args, str(p), f"custom:{p.name}", facts.file_type and str(facts.file_type) or ""
        )
        self.cfg.model_id, self.cfg.quant, self.cfg.provider = f"custom:{p}", "", "local"
        self.cfg.save()
        return {
            "server": state.to_dict(),
            "facts": facts.to_dict(),
            "needed_gib": round(need / GiB, 2),
        }

    def stop(self) -> None:
        self.server.stop()

    def bench(self, model_path: str | None = None, ngl: int = 99) -> dict:
        path = (
            model_path
            or self.server.state.model_path
            or self._path_for(self.cfg.model_id, self.cfg.quant)
        )
        if not path:
            raise RuntimeError("No model to benchmark. Run or install one first.")
        was_running = self.server.running()
        if was_running:
            self.server.stop()  # the GPU/RAM must be free for a fair number
        b = self.budget()
        return bench(
            self.cfg, str(path), ngl=ngl if b.vram_budget or b.unified else 0, threads=b.threads
        )

    def _path_for(self, model_id: str, quant: str) -> Path | None:
        if not model_id or model_id.startswith("custom:"):
            return Path(model_id[7:]) if model_id.startswith("custom:") else None
        try:
            m = self.catalog.get(model_id)
            return downloader.local_path(m, m.file(quant))
        except KeyError:
            return None

    # ---- async wrappers for the server -------------------------------------
    def start_install_job(self, model_id: str, quant: str, with_vision: bool = False) -> Job:
        job = self._job("model", f"Install {model_id} {quant}")
        return self._run_job(
            job,
            lambda j: {
                "path": str(self.ensure_model(model_id, quant, j, with_vision)),
                "runtime": str(self.ensure_runtime(j)),
            },
        )

    def start_run_job(
        self,
        model_id: str,
        quant: str,
        context: int | None = None,
        kv_bits: int = 16,
        pool: bool = False,
        with_vision: bool = False,
    ) -> Job:
        job = self._job("run", f"Run {model_id} {quant}")
        nodes = self.pool_nodes() if pool else None
        return self._run_job(
            job,
            lambda j: self.run(
                model_id, quant, context, kv_bits, nodes, j, with_vision=with_vision
            ),
        )

    def start_bench_job(self) -> Job:
        job = self._job("bench", "Benchmark")
        return self._run_job(job, lambda j: self.bench())

    # ---- pool ---------------------------------------------------------------
    def pool_nodes(self, refresh: bool = False, seconds: float = 3.0) -> list[Node]:
        manual = getattr(self.cfg, "pool_nodes", "")
        if refresh or not self._pool_nodes:
            found = discover(seconds)
            if manual:
                known = {n.endpoint for n in found}
                found += [n for n in parse_manual(manual) if n.endpoint not in known]
            self._pool_nodes = found
        return self._pool_nodes

    # ---- status -------------------------------------------------------------
    def status(self) -> dict:
        return {
            "version": __version__,
            "home": str(home()),
            "models_dir": str(models_dir()),
            "runtime": {
                "installed": self.runtime_installed(),
                "tag": self.cfg.llamacpp_tag,
                "version": llamacpp.version_string(self.cfg) if self.runtime_installed() else None,
            },
            "server": self.server.state.to_dict(),
            "provider": self.cfg.provider,
            "model_id": self.cfg.model_id,
            "quant": self.cfg.quant,
            "headroom": self.cfg.headroom,
            "context": self.cfg.context,
            "installed_models": downloader.installed_models(),
            "pool_nodes": [n.to_dict() for n in self._pool_nodes],
        }
