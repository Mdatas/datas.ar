"""Desktop shortcuts ("direct access" icons) for Datas and for each installed AI.

Each shortcut launches the Datas window and, for a model shortcut, auto-starts that AI:
``Datas.exe open --model <id>`` (frozen) or ``python -m datas open --model <id>``.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from datas.config import home


def launcher() -> list[str]:
    """Executable + base args that open the Datas window."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = shutil.which("datas")
    if exe:
        return [exe]
    return [sys.executable, "-m", "datas"]


def icon_path() -> Path | None:
    """An icon file we can point shortcuts at (ico on Windows, png elsewhere)."""
    sysname = platform.system()
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
        for cand in (
            base / "datas.ico",
            base / "_internal" / "datas.ico",
            base / "datas.png",
            base / "_internal" / "datas.png",
        ):
            if cand.exists():
                return cand
    try:
        name = "datas.ico" if sysname == "Windows" else "datas.png"
        src = Path(str(resources.files("datas.server").joinpath(f"ui/{name}")))
        if src.exists():
            dst = home() / name
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                shutil.copy(src, dst)
            return dst
    except Exception:
        pass
    return None


def desktop_dir() -> Path:
    sysname = platform.system()
    if sysname == "Windows":
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.strip()
            if out:
                return Path(out)
        except Exception:
            pass
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    if sysname == "Linux":
        try:
            out = subprocess.run(
                ["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            if out:
                return Path(out)
        except Exception:
            pass
    return Path.home() / "Desktop"


def _safe(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in " -_.()").strip() or "Datas AI"


def create(name: str, args: list[str], description: str = "Datas.ar — local AI") -> Path:
    """Create a desktop shortcut that runs the Datas launcher with ``args``. Returns its path."""
    sysname = platform.system()
    cmd = launcher()
    exe, base_args = cmd[0], cmd[1:]
    all_args = base_args + args
    desk = desktop_dir()
    desk.mkdir(parents=True, exist_ok=True)
    icon = icon_path()
    safe = _safe(name)

    if sysname == "Windows":
        lnk = desk / f"{safe}.lnk"
        arg_str = " ".join(f'"{a}"' if " " in a else a for a in all_args)
        ps = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{lnk}')
$s.TargetPath = '{exe}'
$s.Arguments = '{arg_str}'
$s.WorkingDirectory = '{Path(exe).parent}'
$s.Description = '{description.replace("'", "''")}'
{f"$s.IconLocation = '{icon},0'" if icon else ""}
$s.Save()
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return lnk

    if sysname == "Darwin":
        script = desk / f"{safe}.command"
        quoted = " ".join(f"'{a}'" for a in [exe, *all_args])
        script.write_text(f"#!/bin/bash\n{quoted}\n")
        script.chmod(0o755)
        return script

    # Linux: a .desktop file on the Desktop and in the applications menu
    quoted = " ".join(f'"{a}"' if " " in a else a for a in [exe, *all_args])
    content = (
        "[Desktop Entry]\nType=Application\n"
        f"Name={name}\nComment={description}\nExec={quoted}\n"
        f"Icon={icon if icon else 'applications-science'}\nTerminal=false\nCategories=Utility;\n"
    )
    entry = desk / f"{safe}.desktop"
    entry.write_text(content)
    entry.chmod(0o755)
    apps = Path.home() / ".local/share/applications"
    apps.mkdir(parents=True, exist_ok=True)
    (apps / f"datas-{safe.lower().replace(' ', '-')}.desktop").write_text(content)
    return entry


def create_app_shortcut() -> Path:
    return create("Datas.ar", ["open"], "Datas.ar — local AI for everyone")


def create_model_shortcut(model_id: str, display_name: str) -> Path:
    return create(
        f"{display_name} (Datas)",
        ["open", "--model", model_id],
        f"Start {display_name} in Datas.ar",
    )


def remove(name: str) -> bool:
    safe = _safe(name)
    desk = desktop_dir()
    removed = False
    for ext in (".lnk", ".command", ".desktop"):
        p = desk / f"{safe}{ext}"
        if p.exists():
            p.unlink()
            removed = True
    app = (
        Path.home()
        / ".local/share/applications"
        / f"datas-{safe.lower().replace(' ', '-')}.desktop"
    )
    if app.exists():
        app.unlink()
    return removed
