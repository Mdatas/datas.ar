"""On Windows, programs Datas starts never flash a black console window.

The app (Datas.exe and the background service) has no console of its own, so every program it
starts — the AI engine, hardware checks (PowerShell, nvidia-smi…), FFmpeg, printing — would get
a new console window that opens and closes. When this process has no console, every
``subprocess.Popen`` (``run``, ``check_output`` and asyncio use it too) gets CREATE_NO_WINDOW
unless the caller asked for a console on purpose. Elsewhere this does nothing.
"""

from __future__ import annotations

import subprocess
import sys

_done = False
NEW_CONSOLE = 0x00000010  # CREATE_NEW_CONSOLE
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
DETACHED = 0x00000008  # DETACHED_PROCESS


def _has_console() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:  # noqa: BLE001
        return True  # unknown: change nothing


def flags_for(creationflags: int, has_console: bool) -> int:
    """The flags a child gets: CREATE_NO_WINDOW added when there is no console to share and
    the caller did not ask for a console or a detached process."""
    if has_console or creationflags & (NEW_CONSOLE | DETACHED):
        return creationflags
    return creationflags | NO_WINDOW


def install(force: bool = False) -> None:
    global _done
    if _done or (sys.platform != "win32" and not force):
        return
    _done = True
    original = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, N807
        if len(args) < 14:  # creationflags is the 14th positional argument of Popen
            kwargs["creationflags"] = flags_for(kwargs.get("creationflags", 0) or 0, _has_console())
        original(self, *args, **kwargs)

    subprocess.Popen.__init__ = __init__
