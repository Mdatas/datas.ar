"""`python -m datas` → the CLI (also the PyInstaller entry point for Datas.exe / datas-cli.exe)."""

import multiprocessing
import sys


def _utf8_console() -> None:
    # Windows consoles default to a legacy code page that cannot print "→" or "·";
    # a windowed (no-console) exe has no stdout at all. Never let either crash the app.
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    multiprocessing.freeze_support()  # py-cpuinfo spawns a helper process; required when frozen
    _utf8_console()
    from datas.cli import app

    app()


if __name__ == "__main__":
    main()
