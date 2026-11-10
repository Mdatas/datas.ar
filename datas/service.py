"""Datas without a window: start with the computer and keep running.

For a Raspberry Pi, a NAS or a home server that has no screen — you then use it from the
phone app or from another computer of yours, through the encrypted link — and for a desktop
whose scheduled tasks should run while the window is closed.

Linux only for now, as a *user* service of systemd (the part of Linux that starts programs):
it runs as you, not as the administrator, and touches nothing outside your own folders.
The file is ``~/.config/systemd/user/datas.service``. See docs/SMALL_COMPUTERS.md.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from datas.words import Problem

NAME = "datas.service"

UNIT = """[Unit]
Description=Datas - your own AI on this computer
Documentation=https://github.com/Mdatas/datas.ar
After=network-online.target
Wants=network-online.target

[Service]
ExecStart={command}
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
{environment}
[Install]
WantedBy=default.target
"""


def command() -> list[str]:
    """How this copy of Datas is started without a window."""
    if getattr(sys, "frozen", False):  # the installed app: the command-line program beside it
        cli = Path(sys.executable).with_name("datas-cli")
        return [str(cli if cli.exists() else Path(sys.executable)), "serve", "--no-browser"]
    return [sys.executable, "-m", "datas", "serve", "--no-browser"]


def _quote(arg: str) -> str:
    """One argument as systemd reads it: % doubled, quoted when it has spaces."""
    arg = arg.replace("%", "%%")
    if any(ch.isspace() for ch in arg) or '"' in arg or "\\" in arg:
        return '"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return arg


def unit_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "systemd" / "user" / NAME


def unit_text(cmd: list[str] | None = None) -> str:
    env = ""
    if os.environ.get("DATAS_HOME"):  # a copy that keeps its data in a folder of its own
        env = f"Environment={_quote('DATAS_HOME=' + os.environ['DATAS_HOME'])}\n"
    return UNIT.format(command=" ".join(_quote(a) for a in (cmd or command())), environment=env)


def supported() -> None:
    """Raises a Problem when this computer cannot run Datas as a service this way."""
    if platform.system() != "Linux":
        raise Problem(
            "Starting Datas with the computer is only available on Linux for now. On Windows "
            "and macOS, leave Datas open (it uses almost nothing while the AI sleeps)."
        )
    if not shutil.which("systemctl"):
        raise Problem(
            "This system has no systemd, the part of Linux that Datas uses to start with the "
            "computer. Start it yourself with: datas-cli serve --no-browser"
        )


def _env() -> dict:
    """The environment for systemctl --user. Over SSH or after `su` the address of the user's
    systemd is sometimes missing; it is always /run/user/<number of the user>."""
    env = dict(os.environ)
    if not env.get("XDG_RUNTIME_DIR") and hasattr(os, "getuid"):
        run = Path(f"/run/user/{os.getuid()}")
        if run.is_dir():
            env["XDG_RUNTIME_DIR"] = str(run)
    return env


def _systemctl(*args: str, run=subprocess.run) -> subprocess.CompletedProcess:  # noqa: ANN001
    return run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=60,
        env=_env(),
    )


def _user() -> str:
    try:
        import getpass

        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return os.environ.get("USER", "")


def _lingers(run=subprocess.run) -> bool:  # noqa: ANN001
    """Does this user's systemd start at boot, before anyone logs in?"""
    try:
        r = run(
            ["loginctl", "show-user", _user(), "--property=Linger"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
        )
        return "Linger=yes" in (r.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return False


def install(run=subprocess.run) -> dict:  # noqa: ANN001
    """Write the service, switch it on and start it. Returns what happened:
    {"file", "started", "at_boot", "notes": [sentences]} — ``run`` replaces subprocess.run in
    the tests."""
    supported()
    path = unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit_text(), encoding="utf-8")
    out: dict = {"file": str(path), "started": False, "at_boot": False, "notes": []}
    try:
        _systemctl("daemon-reload", run=run)
        r = _systemctl("enable", "--now", NAME, run=run)
    except (OSError, subprocess.SubprocessError) as e:
        r = subprocess.CompletedProcess([], 1, "", str(e))
    if r.returncode != 0:
        why = (r.stderr or r.stdout or "").strip().splitlines()
        out["notes"].append(
            "The service file was written, but it could not be started from this session "
            f"({(why[-1] if why else 'no answer')[:200]}). Log in on the computer itself or "
            "restart it; or start Datas now with: datas-cli serve --no-browser"
        )
        return out
    out["started"] = True
    # start at boot, before anyone logs in (needed for a computer without a screen)
    if not _lingers(run):
        try:
            run(["loginctl", "enable-linger"], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
    out["at_boot"] = _lingers(run)
    if not out["at_boot"]:
        out["notes"].append(
            "Datas now starts when you log in. To start it when the computer is switched on, "
            f"before anyone logs in, run once: sudo loginctl enable-linger {_user()}"
        )
    return out


def remove(run=subprocess.run) -> dict:  # noqa: ANN001
    """Stop the service and delete its file. Your AIs, chats and settings are not touched."""
    supported()
    path = unit_path()
    had = path.exists()
    try:
        _systemctl("disable", "--now", NAME, run=run)
    except (OSError, subprocess.SubprocessError):
        pass
    path.unlink(missing_ok=True)
    try:
        _systemctl("daemon-reload", run=run)
    except (OSError, subprocess.SubprocessError):
        pass
    return {"removed": had, "file": str(path)}


def status(run=subprocess.run) -> dict:  # noqa: ANN001
    """{"installed", "running", "at_boot"}"""
    supported()
    running = False
    try:
        running = _systemctl("is-active", NAME, run=run).stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "installed": unit_path().exists(),
        "running": running,
        "at_boot": _lingers(run),
        "file": str(unit_path()),
    }
