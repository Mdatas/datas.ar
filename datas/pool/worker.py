"""Run this device as a pool worker (ggml-rpc-server + mDNS advert)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable

from datas import __version__
from datas.config import Config
from datas.hardware.detect import DeviceSpec
from datas.pool.discovery import advertise
from datas.recommend.engine import budget_for
from datas.runtime import llamacpp


def worker_command(
    cfg: Config, spec: DeviceSpec, port: int | None = None, host: str = "127.0.0.1"
) -> list[str]:
    exe = llamacpp.binary(cfg, "rpc-server")
    b = budget_for(spec, cfg.headroom, cfg.headroom_min_gib)
    cmd = [str(exe), "-H", host, "-p", str(port or cfg.rpc_port), "-t", str(b.threads), "-c"]
    return cmd


def run_worker(
    cfg: Config,
    spec: DeviceSpec,
    port: int | None = None,
    host: str = "127.0.0.1",
    log: Callable[[str], None] = print,
) -> int:
    """Blocks until Ctrl-C. Returns the rpc-server exit code."""
    port = port or cfg.rpc_port
    cmd = worker_command(cfg, spec, port, host)
    b = budget_for(spec, cfg.headroom, cfg.headroom_min_gib)
    env = os.environ.copy()
    exe_dir = os.path.dirname(cmd[0])
    if sys.platform.startswith("linux"):
        env["LD_LIBRARY_PATH"] = exe_dir + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    elif sys.platform == "darwin":
        env["DYLD_LIBRARY_PATH"] = exe_dir + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
    log(f"Starting pool worker: {' '.join(cmd)}")
    log(
        f"Offering ≈{b.ram_budget / 2**30:.1f} GiB RAM"
        + (f" + {b.vram_budget / 2**30:.1f} GiB VRAM" if b.vram_budget else "")
        + f" ({b.backend}), llama.cpp {cfg.llamacpp_tag}"
    )
    local_only = host in ("127.0.0.1", "localhost")
    log(
        "Reachable from this device only (use it through your own tunnel). Ctrl-C to stop."
        if local_only
        else "This worker accepts unencrypted, unauthenticated connections — use only on a "
        "network you fully trust. Ctrl-C to stop."
    )
    proc = subprocess.Popen(cmd, env=env, cwd=exe_dir)
    zc = info = None
    if not local_only:
        zc, info = advertise(
            port, cfg.llamacpp_tag, b.backend, b.ram_budget, b.vram_budget, __version__
        )

    def _stop(*_):
        proc.terminate()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        while proc.poll() is None:
            time.sleep(0.5)
    finally:
        try:
            if zc is not None:
                zc.unregister_service(info)
                zc.close()
        except Exception:
            pass
        if proc.poll() is None:
            proc.kill()
    return proc.returncode or 0
