"""The Datas orchestrator: detect → recommend → install → run, shared by CLI and server.

This is the "minimal local AI that sets you up" — except it is not an AI at all, it is a
small deterministic program. It reads the device, picks a model, fetches llama.cpp and
the weights, starts the server with safe flags, and keeps the handles.
"""

from __future__ import annotations

import base64
import subprocess
import sys
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
from datas.engines import images as image_engine
from datas.engines import voice as voice_engine
from datas.hardware.detect import DeviceSpec, detect
from datas.pool.discovery import Node, parse_manual
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


STARTER_ID, STARTER_QUANT = "qwen3-0.6b", "Q4_0"  # 409 MB: chat within a minute of the first Run


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
        self.recorder = voice_engine.Recorder()
        image_engine.set_tag(self.cfg.sd_tag)
        self.sd = image_engine.SdServer(self.cfg)
        from datas.apps import AppManager

        self.apps = AppManager(self.cfg, self.spec)
        self.starter_active = (
            False  # the small helper AI is answering while the chosen one downloads
        )
        self.granted_folders: list[str] = []  # agent folders allowed for this session
        self.scheduler = None  # started by the server (datas.server.app)
        self.approvals: dict[str, dict] = {}  # pending "may I?" questions from a running agent
        self.agent_stop = threading.Event()
        self._spec: DeviceSpec | None = None
        self._spec_at = 0.0
        self._pool_nodes: list[Node] = []
        self.http_port = self.cfg.ui_port  # where the local API listens (set by the server)
        self._agent_windows: list[subprocess.Popen] = []
        self._lock = threading.Lock()
        # ---- sleeping when idle, waking on the next message ----
        self.last_activity = time.time()
        self.asleep = False
        self.agent_busy = 0  # agents running right now (they keep the AI awake)
        self._wake_lock = threading.Lock()
        self._watch: threading.Thread | None = None
        self.notice: dict | None = None  # one thing the window should tell the user (shown once)
        self.link = None  # datas.link.LinkManager, created on first use

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
        self.check_disk(f.bytes, downloader.local_path(m, f), m.name)
        say(f"Downloading {m.name} {f.quant} ({f.bytes / GiB:.1f} GiB) from {m.hf_url}")
        return downloader.download_model(
            m, f, progress=(job.progress if job else None), with_vision=with_vision, log=say
        )

    @staticmethod
    def check_disk(need_bytes: int, dest: Path, what: str = "this download") -> None:
        """Stop before a download that cannot fit, with a sentence the user can act on."""
        import shutil

        folder = dest.parent
        folder.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        already = part.stat().st_size if part.exists() else 0
        free = shutil.disk_usage(folder).free
        margin = 1 * GiB  # never fill the disk to the brim
        if free < need_bytes - already + margin:
            raise RuntimeError(
                f"Not enough free space for {what}: it needs {(need_bytes - already) / GiB:.1f} GB "
                f"more and the disk has {free / GiB:.1f} GB free. Free some space (or remove an AI "
                "you no longer use in My AIs) and try again."
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
        with_voice: bool = False,
    ) -> dict:
        say = job.say if job else print
        self.ensure_runtime(job)
        path = self.ensure_model(model_id, quant, job, with_vision=with_vision)
        if with_voice:
            self.ensure_voice(job)
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
        if model_id != STARTER_ID or not self.starter_active:
            self.cfg.last_run = {
                "model_id": model_id,
                "quant": quant,
                "context": c.need.context,
                "kv_bits": kv_bits,
                "with_vision": bool(mmproj),
                "pool": bool(rpc),
            }
        self.cfg.save()
        self.asleep = False
        self.touch()
        try:
            from datas import library

            library.touch(model_id, quant)
        except Exception:
            pass
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
        self.cfg.last_run = {"custom": str(p), "context": ctx, "kv_bits": kv_bits}
        self.cfg.save()
        self.asleep = False
        self.touch()
        return {
            "server": state.to_dict(),
            "facts": facts.to_dict(),
            "needed_gib": round(need / GiB, 2),
        }

    def stop(self) -> None:
        """The user stopped the AI: it stays stopped until they start one again."""
        self.asleep = False
        self.cfg.last_run = {}
        self.server.stop()

    # ---- sleeping when idle ------------------------------------------------------
    def touch(self) -> None:
        self.last_activity = time.time()

    def can_wake(self) -> bool:
        """True when no AI is running but we know which one to bring back and it is on disk."""
        lr = self.cfg.last_run or {}
        if self.server.running() or self.cfg.provider not in ("local", "pool") or not lr:
            return False
        if lr.get("custom"):
            return Path(lr["custom"]).exists()
        try:
            m = self.catalog.get(lr["model_id"])
            return downloader.is_downloaded(m, m.file(lr["quant"]))
        except (KeyError, TypeError):
            return False

    def wake(self) -> None:
        """Start the AI again exactly as it was last started (after sleep or an app restart)."""
        with self._wake_lock:
            if self.server.running():
                return
            lr = dict(self.cfg.last_run or {})
            if lr.get("custom"):
                self.run_custom(lr["custom"], lr.get("context"), lr.get("kv_bits", 16))
            else:
                nodes = self.pool_nodes(refresh=True) if lr.get("pool") else None
                self.run(
                    lr["model_id"],
                    lr["quant"],
                    lr.get("context"),
                    lr.get("kv_bits", 16),
                    nodes or None,
                    with_vision=bool(lr.get("with_vision")),
                )
            self.asleep = False
            self.touch()

    def sleep(self) -> None:
        """Give the memory back; ``last_run`` stays so the next message wakes the same AI."""
        if self.server.running():
            self.server.stop()
            self.asleep = True

    def busy(self) -> bool:
        return self.agent_busy > 0 or any(
            j.state in ("queued", "running") and j.kind in ("run", "bench", "model")
            for j in self.jobs.values()
        )

    def start_watch(self) -> None:
        """One small background loop: idle sleep, and noticing an engine that died."""
        if self._watch and self._watch.is_alive():
            return

        def loop() -> None:
            while True:
                time.sleep(20)
                try:
                    self._tick()
                except Exception:  # noqa: BLE001 - the watcher must outlive any single failure
                    pass

        self._watch = threading.Thread(target=loop, daemon=True, name="datas-watch")
        self._watch.start()

    def _tick(self) -> None:
        mins = self.cfg.idle_sleep_min
        if self.busy():
            self.touch()
            return
        if (
            mins > 0
            and self.server.running()
            and time.time() - self.last_activity > mins * 60
            and not self.starter_active
        ):
            self.sleep()
        elif self.server.proc is not None and not self.server.running():
            # the engine process ended on its own (crash, killed by the system for memory)
            tail = self.server.log_tail(8)
            pooled = bool(self.server.state.rpc)
            self.server._clear()  # noqa: SLF001
            if pooled:
                self.fallback_local()
                return
            self.asleep = True
            self.notice = {
                "kind": "engine_stopped",
                "text": "The AI stopped unexpectedly (often: the computer ran short of memory). "
                "It will start again with your next message.",
                "detail": tail,
            }

    def chat_saved(self, chat_id: str) -> None:
        """A chat changed on this device: let linked devices know (if any)."""
        link = self.link
        if link is not None:
            try:
                link.chats_changed()
            except Exception:  # noqa: BLE001
                pass

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
        with_voice: bool = False,
        starter: bool = True,
    ) -> Job:
        job = self._job("run", f"Run {model_id} {quant}")
        nodes = self.pool_nodes() if pool else None

        def with_starter(j: Job) -> dict:
            # Nothing running and a real download ahead → bring up the small helper first, so the
            # user can already chat (and ask the guide) while the chosen AI downloads.
            try:
                m = self.catalog.get(model_id)
                need_download = not downloader.is_downloaded(m, m.file(quant))
                sm = self.catalog.get(STARTER_ID)
                big = m.file(quant).bytes > 3 * sm.file(STARTER_QUANT).bytes
                if need_download and big and not self.server.running() and model_id != STARTER_ID:
                    j.say(
                        "Starting a small helper AI first so you can chat while the big one downloads…"
                    )
                    self.run(STARTER_ID, STARTER_QUANT, 8192, 16, None, j)
                    self.starter_active = True
                    j.phase = "model"
                    j.say("Helper ready — you can chat now. Downloading your AI…")
            except Exception as e:  # noqa: BLE001 - the helper is a convenience, never a blocker
                j.say(f"(helper AI skipped: {e})")
            try:
                return self.run(
                    model_id,
                    quant,
                    context,
                    kv_bits,
                    nodes,
                    j,
                    with_vision=with_vision,
                    with_voice=with_voice,
                )
            finally:
                self.starter_active = False

        if starter:
            return self._run_job(job, with_starter)
        return self._run_job(
            job,
            lambda j: self.run(
                model_id,
                quant,
                context,
                kv_bits,
                nodes,
                j,
                with_vision=with_vision,
                with_voice=with_voice,
            ),
        )

    # ---- agent: approvals ("may I?") ---------------------------------------------
    def ask_user(self, text: str, timeout: float = 900) -> bool:
        """Blocks the agent until the window answers (or 15 min pass → denied)."""
        aid = uuid.uuid4().hex[:8]
        ev = threading.Event()
        self.approvals[aid] = {
            "id": aid,
            "text": text,
            "event": ev,
            "answer": None,
            "asked": time.time(),
        }
        try:
            ev.wait(timeout)
            return bool(self.approvals[aid]["answer"])
        finally:
            self.approvals.pop(aid, None)

    def answer(self, aid: str, ok: bool) -> bool:
        a = self.approvals.get(aid)
        if not a:
            return False
        a["answer"] = ok
        a["event"].set()
        return True

    # ---- agent: scheduled tasks ------------------------------------------------
    def start_scheduler(self):
        from datas.agents.schedule import Scheduler

        if self.scheduler is None:
            self.scheduler = Scheduler(self.run_scheduled_task)
            self.scheduler.start()
        return self.scheduler

    def run_scheduled_task(self, t) -> tuple[str, str, str]:  # noqa: ANN001
        """Runs one scheduled task through the agent; returns (state, summary, result path)."""
        import time as _t

        from datas.agents import AgentConfig, run_agent
        from datas.agents.schedule import results_dir

        if not self.server.running() and self.can_wake():
            try:
                self.wake()
            except Exception as e:  # noqa: BLE001
                return "error", f"The AI could not be started for this task: {e}", ""
        if not self.server.running() and self.cfg.provider in ("local", "pool"):
            return "error", "No AI was running when the task came due.", ""
        acfg = AgentConfig(
            base_url=f"http://127.0.0.1:{self.http_port}/v1",
            roots=[Path(f) for f in t.folders],
            allow_shell=t.allow_shell,
            allow_network=t.internet,
            lang=self.cfg.lang,
            allow_local=self.cfg.allow_local_fetch,
        )
        lines, final, state = [], "", "done"
        self.agent_busy += 1
        try:
            for ev in run_agent(t.task, acfg):
                self.touch()
                if ev["type"] == "tool_call":
                    lines.append(f"- {ev['name']} {str(ev.get('arguments', ''))[:160]}")
                elif ev["type"] == "final":
                    final = ev.get("content", "")
                elif ev["type"] == "error":
                    state, final = "error", ev.get("error", "")
        finally:
            self.agent_busy -= 1
        stamp = _t.strftime("%Y-%m-%d_%H-%M")
        out = results_dir() / f"{t.id}-{stamp}.md"
        out.write_text(
            f"# {t.title}\n\n{_t.strftime('%Y-%m-%d %H:%M')} — {state}\n\n{final}\n\n"
            f"## Steps\n" + "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        return state, final, str(out)

    # ---- images and video (stable-diffusion.cpp) ---------------------------------
    def media_choice(self, kind: str = "image") -> image_engine.ImageChoice:
        if kind == "video":
            return image_engine.choose_video(self.spec(), self.cfg)
        return image_engine.choose(self.spec(), self.cfg)

    def image_choice(self) -> image_engine.ImageChoice:
        return self.media_choice("image")

    def image_status(self, kind: str = "image") -> dict:
        ch = self.media_choice(kind)
        files = image_engine.installed_files(ch)
        running = self.sd.running() and self.sd.state.recipe == ch.recipe
        return {
            "kind": kind,
            "engine_installed": image_engine.installed_dir() is not None,
            "models": files,
            "ready": files["ready"] and image_engine.installed_dir() is not None,
            "server": self.sd.state.to_dict() | {"running": running},
            "choice": {
                "recipe": ch.recipe,
                "backend": ch.backend,
                "device": ch.device,
                "offload": ch.offload,
                "quant": ch.diffusion["quant"],
                "total_bytes": ch.total_bytes,
                "need_gib": ch.need_gib,
                "speed": ch.speed,
                "fits": ch.fits,
                "reasons": ch.reasons,
                "plain": ch.plain(self.cfg.lang),
                "files": [
                    {"file": f["file"], "bytes": f["bytes"], "repo": f["repo"]} for f in ch.files()
                ],
            },
        }

    def start_images_job(self, kind: str = "image") -> Job:
        """Download the engine and the model files if needed, then (re)start sd-server with them.
        Never refused: a device that is too small gets a warning in the log and tries anyway."""
        job = self._job("images", f"Set up making {kind}s")

        def body(j: Job) -> dict:
            ch = self.media_choice(kind)
            if not ch.fits:
                j.say(
                    "Warning: this device is below what this needs; trying anyway. "
                    + " ".join(ch.reasons)
                )
            exe = image_engine.ensure_runtime(self.spec(), self.cfg, j)
            image_engine.ensure_models(ch, j)
            j.phase = "starting"
            j.say(f"Starting the engine (loading ~{ch.total_bytes / GiB:.1f} GB)…")
            st = self.sd.start(exe, ch, self.spec(), self.cfg.sd_port)
            return {"server": st.to_dict(), "kind": kind}

        return self._run_job(job, body)

    def stop_images(self) -> None:
        self.sd.stop()

    def _save_media(self, data: bytes, ext: str) -> dict:
        if self.cfg.forget:
            return {"b64": [base64.b64encode(data).decode()], "ext": ext}
        name = f"{time.strftime('%Y-%m-%d_%H-%M-%S')}_{uuid.uuid4().hex[:6]}.{ext}"
        (image_engine.images_dir() / name).write_bytes(data)
        return {"files": [name], "ext": ext}

    def start_generate_job(
        self, prompt: str, negative: str, width: int, height: int, steps: int | None, seed: int
    ) -> Job:
        job = self._job("image", prompt[:60])

        def body(j: Job) -> dict:
            ch = self.media_choice("image")
            if not self.sd.running() or self.sd.state.recipe != ch.recipe:
                raise RuntimeError(
                    "The image engine is not running. Start it from the Images screen."
                )
            r = image_engine.recipe_of(ch)
            j.phase = "generating"
            pngs = self.sd.generate(
                prompt,
                negative,
                width,
                height,
                steps or r["steps"],
                r["cfg_scale"],
                seed,
                progress=j.progress,
            )
            return self._save_media(pngs[0], "png")

        return self._run_job(job, body)

    def start_video_job(
        self,
        prompt: str,
        negative: str,
        seconds: float | None,
        width: int | None,
        height: int | None,
        seed: int,
        init_image_b64: str | None = None,
    ) -> Job:
        job = self._job("video", prompt[:60])

        def body(j: Job) -> dict:
            ch = self.media_choice("video")
            if not self.sd.running() or self.sd.state.recipe != ch.recipe:
                raise RuntimeError(
                    "The video engine is not running. Start it from the Images & video screen."
                )
            r = image_engine.recipe_of(ch)
            fps = r["fps"]
            frames = r["frames"] if not seconds else max(5, int(seconds * fps) // 4 * 4 + 1)
            j.phase = "generating"
            data, mime = self.sd.generate_video(
                prompt,
                negative,
                width or r["width"],
                height or r["height"],
                frames,
                fps,
                r["steps"],
                r["cfg_scale"],
                r["flow_shift"],
                seed,
                init_image_b64,
                progress=j.progress,
            )
            return self._save_media(
                data, "webm" if "webm" in mime else ("avi" if "msvideo" in mime else "webp")
            )

        return self._run_job(job, body)

    # ---- voice (hearing + speaking) -----------------------------------------
    def voice_choice(self) -> voice_engine.VoiceChoice:
        return voice_engine.choose(self.spec(), self.cfg)

    def ensure_voice(self, job: Job | None = None) -> dict:
        avail = voice_engine.available()
        if not (avail["stt"] and avail["tts"]):
            raise RuntimeError(
                "Voice packages are not installed on this copy of Datas "
                f"(missing: {', '.join(avail['missing'])}). Reinstall Datas or run: pip install 'datas[voice]'"
            )
        return voice_engine.ensure(self.voice_choice(), job)

    def start_voice_install_job(self) -> Job:
        job = self._job("voice", "Install voice (hearing + speaking)")
        return self._run_job(job, lambda j: self.ensure_voice(j))

    def voice_status(self) -> dict:
        avail = voice_engine.available()
        out = {"available": avail, "installed": voice_engine.installed(self.cfg, self.spec())}
        if avail["stt"] and avail["tts"]:
            ch = self.voice_choice()
            out["choice"] = {
                "stt_model": ch.stt_model,
                "total_bytes": ch.total_bytes,
                "ram_gib": ch.ram_gib,
                "reasons": ch.reasons,
                "plain": ch.plain(self.cfg.lang),
            }
        out["recording"] = self.recorder.recording
        out["speak_answers"] = self.cfg.voice_speak_answers
        return out

    def hear(self, pcm16k, language: str | None) -> str:  # noqa: ANN001
        model = voice_engine.installed(self.cfg, self.spec())
        mid = model.get("stt_model") or (model["stt_models"][0] if model["stt_models"] else None)
        if not mid or mid not in model["stt_models"]:
            # the auto choice is not downloaded yet but another size is: use what we have
            if model["stt_models"]:
                mid = model["stt_models"][-1]
            else:
                raise RuntimeError("No hearing model installed yet.")
        threads = max(1, min(8, (self.spec().cpu_cores_logical or 4) - 1))
        return voice_engine.transcribe(pcm16k, language, mid, threads=threads)

    def start_bench_job(self) -> Job:
        job = self._job("bench", "Benchmark")
        return self._run_job(job, lambda j: self.bench())

    # ---- pool ---------------------------------------------------------------
    def link_manager(self):  # noqa: ANN201 - datas.link.LinkManager
        """The encrypted link to the user's other devices (created on first use)."""
        with self._lock:
            if self.link is None:
                from datas.link import LinkManager

                self.link = LinkManager(self)
            return self.link

    def pool_nodes(self, refresh: bool = False, seconds: float = 3.0) -> list[Node]:
        """Devices whose memory can be added to this one: the user's linked devices, reached
        through the encrypted link. (Experts can also list raw llama.cpp workers by hand with
        ``datas pool nodes --set`` — those connections are not encrypted by Datas.)"""
        nodes: list[Node] = []
        if self.link is not None or self.cfg.link_enabled:
            try:
                nodes = self.link_manager().pool_nodes(refresh=refresh)
            except Exception:  # noqa: BLE001 - a link problem must not break a local run
                nodes = []
        manual = getattr(self.cfg, "pool_nodes", "")
        if manual:
            known = {n.endpoint for n in nodes}
            nodes += [n for n in parse_manual(manual) if n.endpoint not in known]
        self._pool_nodes = nodes
        return self._pool_nodes

    def fallback_local(self, lost: str = "") -> dict:
        """A device this AI was spread over went away (or the link dropped): carry on with the
        best installed AI that fits this device alone, and tell the user."""
        from datas import library

        with self._wake_lock:
            was = self.model_name(
                self.server.state.model_id or (self.cfg.last_run or {}).get("model_id")
            )
            self.server.stop()
            rec = self.recommendation(pool_nodes=None)
            have = {i["model_id"] for i in library.installed() if not i["custom"]}
            pick = None
            for c in rec.fits:
                if c.model_id not in have or c.role != "general":
                    continue
                m = self.catalog.get(c.model_id)
                if downloader.is_downloaded(m, m.file(c.quant)):
                    pick = c
                    break
            if pick is None:
                self.cfg.last_run = {}
                self.cfg.provider = "local"
                self.cfg.save()
                self.notice = {
                    "kind": "fallback_none",
                    "lost": lost,
                    "was": was,
                    "text": f"{lost or 'A linked device'} went offline, and none of the AIs installed "
                    "here fits this device alone. Open My AIs to add a lighter one.",
                }
                return self.notice
            self.run(pick.model_id, pick.quant)
            self.notice = {
                "kind": "fallback",
                "lost": lost,
                "was": was,
                "now": pick.name,
                "text": f"{lost or 'A linked device'} went offline. The chat continues on this "
                f"device with {pick.name}.",
            }
            return self.notice

    # ---- background helpers ---------------------------------------------------
    def _self_cmd(self) -> list[str]:
        """How to start another Datas process (frozen exe or python -m datas)."""
        if getattr(sys, "frozen", False):
            return [sys.executable]
        return [sys.executable, "-m", "datas"]

    def worker_running(self) -> bool:
        return bool(self.cfg.link_enabled and self.cfg.link_share_memory)

    def set_pool_offer(self, on: bool) -> dict:
        """Offer this device's memory to the user's linked devices (through the encrypted link;
        the open, unencrypted worker of earlier versions is gone)."""
        self.cfg.link_share_memory = on
        self.cfg.pool_offer = on
        self.cfg.save()
        return {"offering": self.worker_running()}

    def open_url_window(self, url: str, title: str) -> dict:
        p = subprocess.Popen(self._self_cmd() + ["open-url", url, "--title", title])
        self._agent_windows.append(p)
        return {"pid": p.pid}

    def start_app_job(self, app_id: str, install_only: bool = False) -> Job:
        a = self.apps.recipe(app_id)
        job = self._job("app", a["name"])

        def body(j: Job) -> dict:
            if install_only:
                return self.apps.install(app_id, j)
            r = self.apps.start(app_id, j)
            self.open_url_window(r["url"], f"{a['name']} — Datas.ar")
            return r

        return self._run_job(job, body)

    def open_agent_window(self) -> dict:
        """The agent runs in its own window *and* its own process, as requested."""
        p = subprocess.Popen(self._self_cmd() + ["agent-window"])
        self._agent_windows.append(p)
        return {"pid": p.pid}

    def shutdown(self) -> None:
        self.server.stop()  # not stop(): the next start wakes the same AI on the first message
        self.sd.stop()
        if self.link is not None:
            try:
                self.link.stop()
            except Exception:  # noqa: BLE001
                pass
        self.apps.stop_all()
        for p in self._agent_windows:
            if p.poll() is None:
                p.terminate()

    def model_name(self, model_id: str | None) -> str:
        if not model_id:
            return ""
        try:
            return self.catalog.get(model_id).name
        except Exception:  # noqa: BLE001
            return (
                Path(model_id.split(":", 1)[-1]).stem
                if model_id.startswith("custom:")
                else model_id
            )

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
            "server": self.server.state.to_dict()
            | {
                "model_name": self.model_name(self.server.state.model_id),
                "vision": "--mmproj" in (self.server.state.args or []),
            },
            "asleep": self.asleep and not self.server.running(),
            "can_wake": self.can_wake(),
            "last_model_name": self.model_name((self.cfg.last_run or {}).get("model_id"))
            or Path((self.cfg.last_run or {}).get("custom", "")).stem,
            "idle_sleep_min": self.cfg.idle_sleep_min,
            "theme": self.cfg.theme,
            "provider": self.cfg.provider,
            "model_id": self.cfg.model_id,
            "quant": self.cfg.quant,
            "headroom": self.cfg.headroom,
            "context": self.cfg.context,
            "installed_models": downloader.installed_models(),
            "pool_nodes": [n.to_dict() for n in self._pool_nodes],
            "pool_offering": self.worker_running(),
            "privacy": {
                "memory_mode": self.cfg.memory_mode,
                "keep_logs": self.cfg.keep_logs,
                "internet_default": self.cfg.internet_default,
                "onboarded": self.cfg.onboarded,
            },
            "lang": self.cfg.lang,
            "use_cases": self.cfg.use_cases,
            "resource_mode": self.cfg.resource_mode,
            "voice": {
                "available": voice_engine.available(),
                "installed": voice_engine.installed(self.cfg),
                "speak_answers": self.cfg.voice_speak_answers,
            },
            "images": {
                "engine_installed": image_engine.installed_dir() is not None,
                "running": self.sd.running(),
                "recipe": self.sd.state.recipe,
            },
            "starter_active": self.starter_active,
        }
