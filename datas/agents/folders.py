"""The user's well-known folders, per OS, offered as one-click grants to the agent."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

KNOWN = ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"]
KNOWN_ES = {
    "Desktop": "Escritorio",
    "Documents": "Documentos",
    "Downloads": "Descargas",
    "Pictures": "Imágenes",
    "Music": "Música",
    "Videos": "Videos",
}


def _xdg(name: str) -> Path | None:
    try:
        out = subprocess.run(
            ["xdg-user-dir", name.upper()], capture_output=True, text=True, timeout=3
        ).stdout.strip()
        return Path(out) if out and out != str(Path.home()) else None
    except (OSError, subprocess.SubprocessError):
        return None


def known_folders() -> list[dict]:
    """[{id, name, name_es, path, exists}] — only folders that exist on this computer."""
    home = Path.home()
    out = []
    for name in KNOWN:
        cands = [home / name]
        if platform.system() == "Linux":
            x = _xdg(name)
            if x:
                cands.insert(0, x)
        if platform.system() == "Windows":
            one = os.environ.get("OneDrive")
            if one:
                cands.append(Path(one) / name)
        for c in cands:
            if c.is_dir():
                out.append({"id": name, "name": name, "name_es": KNOWN_ES[name], "path": str(c)})
                break
    return out


def resolve_grant(path: str) -> Path:
    """Validate a folder the user typed/picked: must exist, be a directory, not the whole home."""
    p = Path(os.path.expanduser(path)).resolve()
    if not p.is_dir():
        raise ValueError(f"not a folder: {path}")
    if p == Path.home().resolve() or p == Path(p.anchor):
        raise ValueError("choose a specific folder, not your whole home or disk")
    return p
