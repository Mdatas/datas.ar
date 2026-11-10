"""A real Datas for a phone app's tests to link to.

Starts a Datas on this machine (its own data folder, its own free ports, the link switched
on), asks it for a one-time pairing code, and runs a command that is given the address and
the code in its environment:

    DATAS_LINK_HOST  DATAS_LINK_PORT  DATAS_LINK_CODE  DATAS_LINK_NAME

Afterwards it checks, at the computer, that a phone with that name is now linked — so the
command cannot "pass" without really having paired. Used by .github/workflows/ios.yml:

    python scripts/phone_target.py --name "Mac test" --run "swift test --package-path ios/DatasLink"
    python scripts/phone_target.py --prefix TEST_RUNNER_ --run "xcodebuild test … -destination 'id={sim}'"

``{sim}`` in the command becomes the identifier of an iPhone simulator that is available
here. ``--prefix TEST_RUNNER_`` is how Xcode hands environment values on to tests.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def simulator() -> str:
    """The identifier of an iPhone simulator that can be used on this Mac."""
    out = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "available", "-j"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    phones = []
    for runtime, devices in json.loads(out)["devices"].items():
        if "iOS" not in runtime:
            continue
        for d in devices:
            if d.get("isAvailable", True) and d["name"].startswith("iPhone"):
                phones.append((runtime, d["name"], d["udid"]))
    if not phones:
        raise SystemExit("no iPhone simulator is available on this Mac")
    runtime, name, udid = sorted(phones)[-1]  # the newest system, the last model by name
    print(f"simulator: {name} ({runtime.rsplit('.', 1)[-1]})", flush=True)
    return udid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, help="the command to run with the address and code")
    ap.add_argument("--name", default="Test phone", help="the name the phone should link under")
    ap.add_argument("--prefix", default="", help="put this before each environment name")
    a = ap.parse_args()

    home = Path(tempfile.mkdtemp(prefix="datas-phone-target-"))
    ui, link = free_port(), free_port()
    (home / "config.json").write_text(
        json.dumps(
            {
                "ui_port": ui,
                "link_port": link,
                "llama_port": free_port(),
                "rpc_port": free_port(),
                "memory_mode": "remember",
                "onboarded": True,
                "device_name": "Test computer",
            }
        ),
        encoding="utf-8",
    )
    code = (
        "import uvicorn\n"
        "from datas.server.app import app, set_http_port\n"
        f"set_http_port({ui})\n"
        f"uvicorn.run(app, host='127.0.0.1', port={ui}, log_level='error')\n"
    )
    datas = subprocess.Popen(
        [sys.executable, "-c", code], env=dict(os.environ, DATAS_HOME=str(home)), cwd=str(ROOT)
    )
    http = httpx.Client(base_url=f"http://127.0.0.1:{ui}", trust_env=False, timeout=60)
    try:
        for _ in range(150):
            try:
                if http.get("/api/privacy").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            raise SystemExit("the test Datas did not start")
        pairing = http.post("/api/link/pairing").json()["pairing"]
        env = dict(os.environ)
        for key, value in (
            ("DATAS_LINK_HOST", "127.0.0.1"),
            ("DATAS_LINK_PORT", str(link)),
            ("DATAS_LINK_CODE", pairing["code"]),
            ("DATAS_LINK_NAME", a.name),
        ):
            env[a.prefix + key] = value
        command = a.run.replace("{sim}", simulator()) if "{sim}" in a.run else a.run
        print(f"test Datas: link on 127.0.0.1:{link}; running: {command}", flush=True)
        done = subprocess.run(shlex.split(command), env=env, cwd=str(ROOT))
        peers = http.get("/api/link").json()["peers"]
        linked = [p["name"] for p in peers if p.get("kind") == "app"]
        print(f"phones linked at the computer afterwards: {linked}", flush=True)
        if done.returncode != 0:
            return done.returncode
        if a.name not in linked:
            print(f"the command passed, but no phone called {a.name!r} was linked", flush=True)
            return 1
        return 0
    finally:
        http.close()
        datas.terminate()
        try:
            datas.wait(10)
        except subprocess.TimeoutExpired:
            datas.kill()


if __name__ == "__main__":
    sys.exit(main())
