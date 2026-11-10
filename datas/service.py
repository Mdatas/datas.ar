"""Datas without a window: start with the computer and keep running.

For a Raspberry Pi, a NAS or a home server that has no screen — you then use it from the
phone app or from another computer of yours, through the encrypted link — and for a desktop
whose scheduled tasks should run while the window is closed.

It always runs as you, never as the administrator, and touches nothing outside your own
folders:

* **Linux**: a *user* service of systemd (the part of Linux that starts programs),
  ``~/.config/systemd/user/datas.service``; it can start at boot, before anyone logs in.
* **macOS**: a LaunchAgent (the macOS way to start a program for one person),
  ``~/Library/LaunchAgents/ar.datas.service.plist``; it starts when you log in.
* **Windows**: an entry in your own "Run" list of the registry
  (``HKEY_CURRENT_USER\\...\\CurrentVersion\\Run``, the same place every app that starts with
  Windows uses); it starts when you log in, with no window.

See docs/SMALL_COMPUTERS.md.
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


LABEL = "ar.datas.service"  # macOS
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"  # Windows, under HKEY_CURRENT_USER
RUN_NAME = "Datas"


def command() -> list[str]:
    """How this copy of Datas is started without a window."""
    home = ["--home", os.environ["DATAS_HOME"]] if os.environ.get("DATAS_HOME") else []
    exe = Path(sys.executable)
    if platform.system() == "Windows":
        # programs without a console, so nothing appears on the screen at logon: Datas.exe
        # (the installed app runs the same commands), or pythonw.exe beside python.exe
        if getattr(sys, "frozen", False):
            gui = exe.with_name("Datas.exe")
            return [str(gui if gui.exists() else exe), "serve", "--no-browser", *home]
        pyw = exe.with_name("pythonw.exe")
        return [str(pyw if pyw.exists() else exe), "-m", "datas", "serve", "--no-browser", *home]
    if getattr(sys, "frozen", False):  # the installed app: the command-line program beside it
        cli = exe.with_name("datas-cli")
        return [str(cli if cli.exists() else exe), "serve", "--no-browser", *home]
    return [str(exe), "-m", "datas", "serve", "--no-browser", *home]


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
    return UNIT.format(command=" ".join(_quote(a) for a in (cmd or command())), environment="")


def supported() -> None:
    """Raises a Problem when this computer cannot run Datas as a service this way."""
    system = platform.system()
    if system in ("Windows", "Darwin"):
        return
    if system != "Linux":
        raise Problem(
            "Starting Datas with the computer is available on Linux, Windows and macOS. Start "
            "it yourself with: datas-cli serve --no-browser"
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


def _linux_install(run=subprocess.run) -> dict:  # noqa: ANN001
    """Linux: write the service, switch it on and start it. Returns what happened:
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


def _linux_remove(run=subprocess.run, stop: bool = True) -> dict:  # noqa: ANN001
    """Stop the service and delete its file. Your AIs, chats and settings are not touched."""
    supported()
    path = unit_path()
    had = path.exists()
    try:
        _systemctl("disable", *(["--now"] if stop else []), NAME, run=run)
    except (OSError, subprocess.SubprocessError):
        pass
    path.unlink(missing_ok=True)
    try:
        _systemctl("daemon-reload", run=run)
    except (OSError, subprocess.SubprocessError):
        pass
    return {"removed": had, "file": str(path)}


def _linux_status(run=subprocess.run) -> dict:  # noqa: ANN001
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


# ---------------------------------------------------------------------------
# macOS: a LaunchAgent
# ---------------------------------------------------------------------------
def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def plist_bytes(cmd: list[str] | None = None) -> bytes:
    import plistlib

    from datas.config import home

    logs = home() / "logs"
    d = {
        "Label": LABEL,
        "ProgramArguments": cmd or command(),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},  # started again if it stops by accident
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "service.log"),
        "StandardErrorPath": str(logs / "service.log"),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    }
    return plistlib.dumps(d)


def _launchctl(*args: str, run=subprocess.run) -> subprocess.CompletedProcess:  # noqa: ANN001
    return run(["launchctl", *args], capture_output=True, text=True, errors="replace", timeout=60)


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _mac_install(run=subprocess.run) -> dict:  # noqa: ANN001
    from datas.config import home

    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    (home() / "logs").mkdir(parents=True, exist_ok=True)
    try:  # an older copy is replaced, not doubled
        _launchctl("bootout", f"{_domain()}/{LABEL}", run=run)
    except (OSError, subprocess.SubprocessError):
        pass
    path.write_bytes(plist_bytes())
    out: dict = {"file": str(path), "started": False, "at_boot": False, "notes": []}
    try:
        r = _launchctl("bootstrap", _domain(), str(path), run=run)
        if r.returncode != 0:  # older macOS, or no login session: the older command
            r = _launchctl("load", "-w", str(path), run=run)
    except (OSError, subprocess.SubprocessError) as e:
        r = subprocess.CompletedProcess([], 1, "", str(e))
    out["started"] = r.returncode == 0
    if not out["started"]:
        why = (r.stderr or r.stdout or "").strip().splitlines()
        out["notes"].append(
            "The file was written; Datas will start the next time you log in "
            f"({(why[-1] if why else 'no answer')[:200]})."
        )
    out["notes"].append("Datas starts when you log in to this Mac.")
    return out


def _mac_remove(run=subprocess.run, stop: bool = True) -> dict:  # noqa: ANN001
    path = plist_path()
    had = path.exists()
    for args in (
        () if not stop else (("bootout", f"{_domain()}/{LABEL}"), ("unload", "-w", str(path)))
    ):
        try:
            if _launchctl(*args, run=run).returncode == 0:
                break
        except (OSError, subprocess.SubprocessError):
            pass
    path.unlink(missing_ok=True)
    return {"removed": had, "file": str(path)}


def _mac_status(run=subprocess.run) -> dict:  # noqa: ANN001
    running = False
    try:
        r = _launchctl("print", f"{_domain()}/{LABEL}", run=run)
        running = r.returncode == 0 and "state = running" in (r.stdout or "")
    except (OSError, subprocess.SubprocessError):
        pass
    return {"installed": plist_path().exists(), "running": running, "at_boot": False,
            "file": str(plist_path())}  # fmt: skip


# ---------------------------------------------------------------------------
# Windows: the user's own "Run" list
# ---------------------------------------------------------------------------
def run_line(cmd: list[str] | None = None) -> str:
    return subprocess.list2cmdline(cmd or command())


def _answers() -> bool:
    """Is a Datas answering on this computer's port?"""
    import httpx

    from datas.config import Config

    try:
        port = Config.load().ui_port
        return httpx.get(
            f"http://127.0.0.1:{port}/api/status", timeout=2, trust_env=False
        ).is_success
    except Exception:  # noqa: BLE001
        return False


def _win_install(run=subprocess.run) -> dict:  # noqa: ANN001
    import time
    import winreg  # noqa: PLC0415 - Windows only

    line = run_line()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, line)
    out: dict = {"file": f"HKEY_CURRENT_USER\\{RUN_KEY}\\{RUN_NAME}", "started": _answers(),
                 "at_boot": False, "notes": ["Datas starts when you log in to Windows."]}  # fmt: skip
    if not out["started"]:  # start it now, with no window, independent of this program
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            subprocess.Popen(command(), creationflags=flags, close_fds=True,  # noqa: S603
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)  # fmt: skip
            for _ in range(60):
                time.sleep(1)
                if _answers():
                    out["started"] = True
                    break
        except OSError as e:
            out["notes"].append(f"It could not be started now ({e}); it will at the next login.")
    return out


def _win_remove(run=subprocess.run, stop: bool = True) -> dict:  # noqa: ANN001
    import winreg  # noqa: PLC0415

    had = False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, RUN_NAME)
            had = True
    except OSError:
        pass
    if stop:
        _shutdown()
    return {"removed": had, "file": f"HKEY_CURRENT_USER\\{RUN_KEY}\\{RUN_NAME}"}


def _win_status(run=subprocess.run) -> dict:  # noqa: ANN001
    import winreg  # noqa: PLC0415

    installed = False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            installed = bool(winreg.QueryValueEx(k, RUN_NAME)[0])
    except OSError:
        pass
    return {"installed": installed, "running": _answers(), "at_boot": False,
            "file": f"HKEY_CURRENT_USER\\{RUN_KEY}\\{RUN_NAME}"}  # fmt: skip


def _shutdown() -> None:
    """Ask the Datas running on this computer to stop (it answers only to this computer)."""
    import httpx

    from datas.config import Config

    try:
        port = Config.load().ui_port
        httpx.post(f"http://127.0.0.1:{port}/api/shutdown", timeout=5, trust_env=False)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
def _pick(name: str):  # noqa: ANN202
    supported()
    system = {"Darwin": "mac", "Windows": "win"}.get(platform.system(), "linux")
    return globals()[f"_{system}_{name}"]


def install(run=subprocess.run) -> dict:  # noqa: ANN001
    """Start Datas with the computer (or the login) and now. Returns
    {"file", "started", "at_boot", "notes": [sentences]}; ``run`` replaces subprocess.run in
    the tests."""
    return _pick("install")(run=run)


def remove(run=subprocess.run, stop: bool = True) -> dict:  # noqa: ANN001
    """Remove what makes it start, and stop it (``stop=False``: keep the running one — the
    window that asks may be showing it). Your AIs, chats and settings are not touched."""
    return _pick("remove")(run=run, stop=stop)


def status(run=subprocess.run) -> dict:  # noqa: ANN001
    """{"installed", "running", "at_boot", "file"}"""
    return _pick("status")(run=run)
