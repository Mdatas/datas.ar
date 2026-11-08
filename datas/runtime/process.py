"""llama-server lifecycle: start, health, stop, bench.

llama-server (from llama.cpp) exposes an OpenAI-compatible API on localhost. Datas
starts it with the flags the recommender computed, waits for /health, and keeps the
handle so the UI/CLI can stop or swap models. Logs go to the Datas logs dir.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from datas.config import Config, logs_dir
from datas.runtime import llamacpp


@dataclass
class ServerState:
    pid: int | None = None
    port: int | None = None
    model_path: str | None = None
    model_id: str | None = None
    quant: str | None = None
    args: list[str] = field(default_factory=list)
    started_at: float | None = None
    log_path: str | None = None
    rpc: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__ | {"running": self.pid is not None}


class LlamaServer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self.state = ServerState()
        self._log_fh = None

    # ---- lifecycle -------------------------------------------------------
    def start(
        self,
        args: list[str],
        model_path: str,
        model_id: str = "",
        quant: str = "",
        port: int | None = None,
        rpc: list[str] | None = None,
        timeout: float = 600.0,
    ) -> ServerState:
        if self.proc and self.proc.poll() is None:
            self.stop()
        exe = llamacpp.binary(self.cfg, "llama-server")
        port = port or self.cfg.llama_port
        log_path = logs_dir() / "llama-server.log"
        self._log_fh = log_path.open("ab")
        env = os.environ.copy()
        # make sure sibling shared libs are found (linux tarballs ship them next to the binary)
        libdir = str(exe.parent)
        if sys.platform.startswith("linux"):
            env["LD_LIBRARY_PATH"] = libdir + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        elif sys.platform == "darwin":
            env["DYLD_LIBRARY_PATH"] = libdir + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
        cmd = [str(exe), *args]
        self._log_fh.write(
            f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} starting: {' '.join(cmd)}\n".encode()
        )
        self._log_fh.flush()
        creation = {}
        if sys.platform == "win32":
            creation["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        self.proc = subprocess.Popen(
            cmd,
            stdout=self._log_fh,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(exe.parent),
            **creation,
        )
        self.state = ServerState(
            pid=self.proc.pid,
            port=port,
            model_path=model_path,
            model_id=model_id,
            quant=quant,
            args=args,
            started_at=time.time(),
            log_path=str(log_path),
            rpc=rpc or [],
        )
        self.wait_healthy(timeout)
        return self.state

    def wait_healthy(self, timeout: float) -> None:
        deadline = time.time() + timeout
        url = f"http://127.0.0.1:{self.state.port}/health"
        last = ""
        with httpx.Client(timeout=5) as c:
            while time.time() < deadline:
                if self.proc and self.proc.poll() is not None:
                    tail = self.log_tail(40)
                    self._clear()
                    raise RuntimeError(
                        f"llama-server exited early (code {self.proc.returncode}).\n{tail}"
                    )
                try:
                    r = c.get(url)
                    if r.status_code == 200:
                        return
                    last = r.text[:200]
                except httpx.HTTPError as e:
                    last = str(e)
                time.sleep(0.5)
        self.stop()
        raise TimeoutError(f"llama-server did not become healthy in {timeout:.0f}s ({last})")

    def stop(self, grace: float = 10.0) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                if sys.platform == "win32":
                    self.proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    self.proc.terminate()
                self.proc.wait(grace)
            except Exception:
                self.proc.kill()
        self._clear()

    def _clear(self) -> None:
        if self._log_fh:
            try:
                self._log_fh.close()
            except Exception:
                pass
            self._log_fh = None
        self.state = ServerState()
        self.proc = None

    # ---- info ------------------------------------------------------------
    def running(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.state.port or self.cfg.llama_port}"

    def props(self) -> dict | None:
        if not self.running():
            return None
        try:
            return httpx.get(self.base_url() + "/props", timeout=5).json()
        except Exception:
            return None

    def log_tail(self, lines: int = 60) -> str:
        p = Path(self.state.log_path) if self.state.log_path else logs_dir() / "llama-server.log"
        if not p.exists():
            return ""
        data = p.read_bytes()[-65536:]
        return "\n".join(data.decode("utf-8", errors="replace").splitlines()[-lines:])


def bench(
    cfg: Config,
    model_path: str,
    ngl: int = 99,
    threads: int | None = None,
    prompt: int = 128,
    gen: int = 64,
) -> dict:
    """Measure prompt-processing and generation tokens/s with llama-bench (JSON output)."""
    exe = llamacpp.binary(cfg, "llama-bench")
    cmd = [
        str(exe),
        "-m",
        model_path,
        "-p",
        str(prompt),
        "-n",
        str(gen),
        "-ngl",
        str(ngl),
        "-o",
        "json",
    ]
    if threads:
        cmd += ["-t", str(threads)]
    env = os.environ.copy()
    if sys.platform.startswith("linux"):
        env["LD_LIBRARY_PATH"] = str(exe.parent) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    out = subprocess.run(
        cmd, capture_output=True, text=True, timeout=1800, env=env, cwd=str(exe.parent)
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-2000:])
    rows = json.loads(out.stdout)
    result = {"model": Path(model_path).name, "ngl": ngl}
    for r in rows:
        kind = "prompt_tps" if r.get("n_prompt") else "gen_tps"
        result[kind] = round(float(r.get("avg_ts", 0)), 1)
        result["backend"] = r.get("backends") or r.get("backend")
    return result
