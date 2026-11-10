from __future__ import annotations

import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import zipfile
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from datas.config import Config, home, logs_dir
from datas.hardware.detect import DeviceSpec

if TYPE_CHECKING:
    from datas.orchestrator import Job

GiB = 2**30
UV_TAG = "0.13.5"  # asset names verified on the release page
UV_URL = "https://github.com/astral-sh/uv/releases/download/{tag}/{asset}"


def uv_asset(spec: DeviceSpec) -> str:
    arm = spec.arch in ("arm64", "aarch64")
    if spec.os == "windows":
        return "uv-x86_64-pc-windows-msvc.zip"
    if spec.os == "darwin":
        return "uv-aarch64-apple-darwin.tar.gz" if arm else "uv-x86_64-apple-darwin.tar.gz"
    return "uv-aarch64-unknown-linux-gnu.tar.gz" if arm else "uv-x86_64-unknown-linux-gnu.tar.gz"


def accel_keys(spec: DeviceSpec) -> list[str]:
    """Most specific first; recipes pick the first key they define."""
    vendors = {g.vendor for g in spec.gpus}
    keys: list[str] = []
    if spec.os == "darwin":
        keys.append("mac")
    if "nvidia" in vendors:
        keys.append("nvidia")
    if "amd" in vendors and spec.os == "linux":
        keys.append("amd-linux")
    if spec.os == "windows" and vendors - {"unknown"}:
        keys.append("windows-gpu")
    keys.append("cpu")
    return keys


def _pick(table: dict, keys: list[str]):  # noqa: ANN202
    for k in keys:
        if k in table:
            return k, table[k]
    return "cpu", table.get("cpu")


def tools_dir() -> Path:
    d = home() / "tools"
    d.mkdir(parents=True, exist_ok=True)
    return d


def apps_root() -> Path:
    d = home() / "apps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_recipes() -> list[dict]:
    with resources.files("datas.apps").joinpath("apps.json").open("r", encoding="utf-8") as fh:
        apps = json.load(fh)["apps"]
    extra = home() / "apps.d"
    if extra.is_dir():
        for f in sorted(extra.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for a in data.get("apps", [data] if "id" in data else []):
                    a["user_recipe"] = str(f)
                    apps = [x for x in apps if x["id"] != a["id"]] + [a]
            except (ValueError, OSError):
                continue
    return apps


def _download(url: str, dest: Path, job: Job | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        timeout=httpx.Timeout(60, read=600),
        follow_redirects=True,
        headers={"User-Agent": "datas.ar"},
    ) as c:
        with c.stream("GET", url) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0)) or None
            done = 0
            with dest.open("wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
                    done += len(chunk)
                    if job:
                        job.progress(done, total)
    return dest


def ensure_uv(spec: DeviceSpec, job: Job | None = None) -> Path:
    exe_name = "uv.exe" if spec.os == "windows" else "uv"
    d = tools_dir() / "uv" / UV_TAG
    for cand in d.rglob(exe_name):
        return cand
    say = job.say if job else print
    asset = uv_asset(spec)
    say(f"Downloading uv {UV_TAG} (the tool that sets up Python environments)")
    arc = _download(UV_URL.format(tag=UV_TAG, asset=asset), d / asset, job)
    if asset.endswith(".zip"):
        with zipfile.ZipFile(arc) as z:
            z.extractall(d)
    else:
        with tarfile.open(arc, "r:gz") as t:
            t.extractall(d, filter="data")
    arc.unlink(missing_ok=True)
    for cand in d.rglob(exe_name):
        if spec.os != "windows":
            cand.chmod(cand.stat().st_mode | 0o111)
        return cand
    raise RuntimeError("uv was not found in its release archive")


class AppManager:
    def __init__(self, cfg: Config, spec_fn) -> None:  # noqa: ANN001
        self.cfg = cfg
        self.spec_fn = spec_fn
        self.procs: dict[str, subprocess.Popen] = {}
        self.ports: dict[str, int] = {}
        self._logs: dict[str, object] = {}

    # ---- info -----------------------------------------------------------------
    def recipe(self, app_id: str) -> dict:
        for a in load_recipes():
            if a["id"] == app_id:
                return a
        raise KeyError(app_id)

    def dir(self, app_id: str) -> Path:
        return apps_root() / app_id

    def py(self, app_id: str) -> Path:
        v = self.dir(app_id) / "venv"
        return v / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    def installed_tag(self, app_id: str) -> str | None:
        m = self.dir(app_id) / ".datas-installed"
        return m.read_text().strip() if m.exists() else None

    def running(self, app_id: str) -> bool:
        p = self.procs.get(app_id)
        return p is not None and p.poll() is None

    def verdict(self, a: dict) -> dict:
        """Guidance only — never blocks. yes | slow | no (+ why)."""
        spec = self.spec_fn()
        g = a.get("guide") or {}
        vram = spec.dedicated_vram_total / GiB
        unified = any(x.unified for x in spec.gpus)
        ram = spec.ram_total / GiB
        has_gpu = vram >= g.get("vram_gib", 0) or (unified and ram >= g.get("ram_gib", 0) + 8)
        if ram < g.get("ram_gib", 0) and not has_gpu:
            return {
                "verdict": "no",
                "why": f"Made for {g.get('ram_gib')} GB+ of memory"
                + (f" and a graphics card with {g.get('vram_gib')} GB+" if g.get("gpu") else "")
                + "; you can still try.",
            }
        if g.get("gpu") and not has_gpu:
            return {
                "verdict": "slow",
                "why": f"Works best with a graphics card of {g.get('vram_gib')} GB+; on this device expect it to be very slow.",
            }
        if not has_gpu:
            return {"verdict": "slow", "why": "Runs on the processor here: it works, slowly."}
        return {"verdict": "yes", "why": "This device meets what it asks for."}

    def list(self) -> list[dict]:
        out = []
        for a in load_recipes():
            tag = self.installed_tag(a["id"])
            out.append(
                {
                    **{
                        k: a.get(k)
                        for k in (
                            "id",
                            "name",
                            "maker",
                            "license",
                            "url",
                            "docs",
                            "tasks",
                            "plain_en",
                            "plain_es",
                            "supports",
                        )
                    },
                    "tag": a["source"]["tag"],
                    "installed": tag is not None,
                    "installed_tag": tag,
                    "running": self.running(a["id"]),
                    "port": self.ports.get(a["id"]),
                    "user_recipe": a.get("user_recipe"),
                    **self.verdict(a),
                }
            )
        return out

    # ---- install ----------------------------------------------------------------
    def _run(self, cmd: list[str], cwd: Path, job: Job | None, env: dict | None = None) -> None:
        say = job.say if job else print
        say("$ " + " ".join(str(c) for c in cmd)[:300])
        p = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            env=env,
        )
        tail: list[str] = []
        assert p.stdout is not None
        for line in p.stdout:
            line = line.rstrip()
            if line:
                tail = (tail + [line])[-15:]
                say(line[:300])
        if p.wait() != 0:
            raise RuntimeError(
                f"step failed ({' '.join(str(c) for c in cmd[:4])}…): " + " | ".join(tail[-4:])
            )

    def _env(self, app_id: str, extra: dict | None = None) -> dict:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["UV_CACHE_DIR"] = str(tools_dir() / "uv-cache")
        env["UV_PYTHON_INSTALL_DIR"] = str(tools_dir() / "python")
        venv = self.dir(app_id) / "venv"
        bins = [str(self.py(app_id).parent)]
        ff = self.dir(app_id) / ".ffmpeg-dir"
        if ff.exists():
            bins.append(ff.read_text().strip())
        env["VIRTUAL_ENV"] = str(venv)
        env["PATH"] = os.pathsep.join(bins) + os.pathsep + env.get("PATH", "")
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        # a frozen (PyInstaller) parent must not leak its library path into the child
        for k in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            orig = env.pop(k + "_ORIG", None)
            if orig is not None:
                env[k] = orig
            elif getattr(sys, "frozen", False):
                env.pop(k, None)
        env.update(extra or {})
        return env

    def install(self, app_id: str, job: Job | None = None) -> dict:
        a = self.recipe(app_id)
        spec = self.spec_fn()
        say = job.say if job else print
        keys = accel_keys(spec)
        d = self.dir(app_id)
        src = d / "src"
        if job:
            job.phase = "app-download"
        uv = ensure_uv(spec, job)
        repo, tag = a["source"]["repo"], a["source"]["tag"]
        if not (src / ".datas-tag").exists() or (src / ".datas-tag").read_text().strip() != tag:
            say(f"Downloading {a['name']} {tag} from github.com/{repo}")
            data = _download(
                f"https://github.com/{repo}/archive/refs/tags/{tag}.zip", d / "src.zip", job
            )
            tmp = d / "src.tmp"
            shutil.rmtree(tmp, ignore_errors=True)
            with zipfile.ZipFile(io.BytesIO(data.read_bytes())) as z:
                z.extractall(tmp)
            top = next(p for p in tmp.iterdir() if p.is_dir())
            # keep the user's models/outputs when upgrading: copy new code over the old tree
            src.mkdir(parents=True, exist_ok=True)
            shutil.copytree(top, src, dirs_exist_ok=True)
            shutil.rmtree(tmp, ignore_errors=True)
            data.unlink(missing_ok=True)
            (src / ".datas-tag").write_text(tag)
        if job:
            job.phase = "app-install"
            job.done, job.total = 0, None
        env = self._env(app_id)
        if not self.py(app_id).exists():
            self._run(
                [str(uv), "venv", "--python", a.get("python", "3.12"), "--seed", str(d / "venv")],
                d,
                job,
                env,
            )
        py = str(self.py(app_id))
        for step in a.get("install", []):
            if "pip" in step:
                _, extra = _pick(step.get("extra_by_accel", {"cpu": []}), keys)
                self._run(
                    [str(uv), "pip", "install", "--python", py, *step["pip"], *(extra or [])],
                    src,
                    job,
                    env,
                )
            elif "pip_requirements" in step:
                self._run(
                    [str(uv), "pip", "install", "--python", py, "-r", step["pip_requirements"]],
                    src,
                    job,
                    env,
                )
            elif "python" in step:
                _, vars_ = _pick(step.get("vars_by_accel", {"cpu": {}}), keys)
                args = [x.format(**(vars_ or {})) for x in step["python"]]
                self._run([py, *args], src, job, env)
        if a.get("needs_ffmpeg") and not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
            # the same checked copy the rest of Datas uses (datas.programs.fetch_ffmpeg)
            from datas import programs

            say("Adding FFmpeg (video reading/writing) for this app")
            try:
                exe = programs.fetch_ffmpeg(job.progress if job else None)
                (d / ".ffmpeg-dir").write_text(str(Path(exe).parent))
            except RuntimeError as e:
                say(f"FFmpeg was not added: {e}")
        (d / ".datas-installed").write_text(tag)
        say(f"{a['name']} installed.")
        return {"id": app_id, "tag": tag}

    # ---- run ----------------------------------------------------------------------
    def start(self, app_id: str, job: Job | None = None, timeout: float = 600) -> dict:
        a = self.recipe(app_id)
        if self.running(app_id):
            return {"id": app_id, "port": self.ports[app_id], "url": self.url(app_id)}
        if not self.installed_tag(app_id):
            self.install(app_id, job)
        say = job.say if job else print
        if job:
            job.phase = "app-start"
        keys = accel_keys(self.spec_fn())
        port = int(a.get("port", 8600))
        la = a["launch"]
        _, extra_args = (
            _pick(la.get("args_by_accel", {}), keys) if la.get("args_by_accel") else ("", [])
        )
        args = [x.format(port=port) for x in [*la["args"], *(extra_args or [])]]
        env = self._env(app_id, {k: v.format(port=port) for k, v in (la.get("env") or {}).items()})
        quiet = self.cfg.forget or not self.cfg.keep_logs
        log = open(os.devnull, "ab") if quiet else (logs_dir() / f"app-{app_id}.log").open("ab")
        creation = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if sys.platform == "win32"
            else {}
        )
        say(f"Starting {a['name']} on port {port}")
        p = subprocess.Popen(
            [str(self.py(app_id)), *args],
            cwd=str(self.dir(app_id) / "src"),
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            **creation,
        )
        self.procs[app_id], self.ports[app_id], self._logs[app_id] = p, port, log
        deadline = time.time() + timeout
        with httpx.Client(timeout=5, trust_env=False) as c:
            while time.time() < deadline:
                if p.poll() is not None:
                    raise RuntimeError(
                        f"{a['name']} stopped right after starting (exit code {p.returncode}); see logs/app-{app_id}.log"
                    )
                try:
                    if c.get(self.url(app_id)).status_code < 500:
                        return {"id": app_id, "port": port, "url": self.url(app_id)}
                except httpx.HTTPError:
                    pass
                time.sleep(1)
        raise TimeoutError(f"{a['name']} did not answer on port {port} within {timeout:.0f}s")

    def url(self, app_id: str) -> str:
        return f"http://127.0.0.1:{self.ports.get(app_id, self.recipe(app_id).get('port'))}/"

    def stop(self, app_id: str) -> None:
        p = self.procs.pop(app_id, None)
        if p and p.poll() is None:
            try:
                if sys.platform == "win32":
                    p.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    p.terminate()
                p.wait(10)
            except Exception:  # noqa: BLE001
                p.kill()
        log = self._logs.pop(app_id, None)
        if log:
            try:
                log.close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        self.ports.pop(app_id, None)

    def stop_all(self) -> None:
        for app_id in list(self.procs):
            self.stop(app_id)

    def remove(self, app_id: str, keep_models: bool = False) -> bool:
        self.stop(app_id)
        d = self.dir(app_id)
        if not d.exists():
            return False
        if keep_models:
            shutil.rmtree(d / "venv", ignore_errors=True)
            (d / ".datas-installed").unlink(missing_ok=True)
        else:
            shutil.rmtree(d, ignore_errors=True)
        return True
