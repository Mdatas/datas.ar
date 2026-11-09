"""The Datas window: the local server in a thread + a native window (pywebview).

No browser, no terminal. ``datas`` / ``Datas.exe`` with no arguments opens this; a model
shortcut passes ``--model <id>`` so the AI starts right away. Closing the window stops
the engine too — nothing keeps running unnoticed. Falls back to the default browser when
pywebview cannot create a window (e.g. a Linux box without GTK/Qt WebKit).

A windowed process (pythonw / Datas.exe) has no console: everything the server prints,
and any crash, goes to ``<home>/logs/datas.log``. If the server fails to start, the window
shows that log instead of a browser error page.
"""

from __future__ import annotations

import html
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

import httpx

from datas.config import Config, logs_dir

_server_error: str | None = None


def _log_path() -> Path:
    return logs_dir() / "datas.log"


def _attach_console_to_log() -> None:
    """pythonw / windowed exe: stdout & stderr are None. Point them at the log file."""
    try:
        fh = open(_log_path(), "a", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        return
    if sys.stdout is None or not hasattr(sys.stdout, "write"):
        sys.stdout = fh
    if sys.stderr is None or not hasattr(sys.stderr, "write"):
        sys.stderr = fh


def _log(msg: str) -> None:
    try:
        with open(_log_path(), "a", encoding="utf-8", errors="replace") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _already_running(port: int) -> bool:
    try:
        # trust_env=False: ignore system proxies — this is loopback
        with httpx.Client(timeout=1.5, trust_env=False) as c:
            return c.get(f"http://127.0.0.1:{port}/api/status").status_code == 200
    except httpx.HTTPError:
        return False


def _serve(port: int) -> None:
    global _server_error
    try:
        import uvicorn

        from datas.server.app import app

        config = uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="error", log_config=None
        )
        uvicorn.Server(config).run()
    except BaseException:  # noqa: BLE001 — we want *everything* in the log
        _server_error = traceback.format_exc()
        _log("server thread failed:\n" + _server_error)


def _error_page(port: int, cfg_home: Path) -> str:
    tail = ""
    try:
        tail = "\n".join(
            _log_path().read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        )
    except OSError:
        pass
    body = f"""<!doctype html><html><head><meta charset="utf-8"><title>Datas.ar</title>
<style>body{{background:#0e1116;color:#e6e9ee;font-family:Segoe UI,Inter,Arial,sans-serif;padding:40px;max-width:900px;margin:auto}}
h1{{color:#f2a93b}} pre{{background:#151a21;border:1px solid #273040;border-radius:10px;padding:14px;white-space:pre-wrap;font-size:12px;color:#9aa4b5}}
code{{background:#151a21;padding:2px 6px;border-radius:6px}}</style></head><body>
<h1>Datas could not start its local service</h1>
<p>The window opened, but the part of Datas that does the work did not start on <code>127.0.0.1:{port}</code>.
This is a bug or a blocked port, not something you did. The details below are saved in<br><code>{html.escape(str(_log_path()))}</code>
— send that file to the developer.</p>
<p>Quick checks: is another program using port {port}? Does your antivirus block <code>pythonw.exe</code> / <code>Datas.exe</code>?</p>
<pre>{html.escape(_server_error or tail or "(no details were written to the log)")}</pre>
<p>Data folder: <code>{html.escape(str(cfg_home))}</code></p>
</body></html>"""
    return "data:text/html;charset=utf-8," + __import__("urllib.parse").parse.quote(body)


def open_window(
    model_id: str | None = None,
    path: str = "/",
    title: str = "Datas.ar",
    width: int = 1120,
    height: int = 820,
) -> None:
    _attach_console_to_log()
    cfg = Config.load()
    port = cfg.ui_port
    url = f"http://127.0.0.1:{port}{path}"
    if model_id:
        url += ("&" if "?" in url else "?") + f"autorun={model_id}"
    _log(
        f"open_window path={path} model={model_id} python={sys.version.split()[0]} exe={sys.executable}"
    )

    started_here = False
    if not _already_running(port):
        if not _port_free(port):
            _log(f"port {port} is busy but does not answer as Datas")
        threading.Thread(target=_serve, args=(port,), daemon=True, name="datas-server").start()
        started_here = True
        deadline = time.time() + 25
        while time.time() < deadline and not _already_running(port) and _server_error is None:
            time.sleep(0.2)
    ok = _already_running(port)
    _log(f"server up={ok}")
    target = url if ok else _error_page(port, logs_dir().parent)

    try:
        import webview  # pywebview

        win = webview.create_window(
            title,
            target,
            width=width,
            height=height,
            min_size=(760, 560),
            background_color="#0E1116",
            text_select=True,
        )

        def on_closed():
            if started_here and path == "/" and ok:
                try:
                    httpx.post(f"http://127.0.0.1:{port}/api/shutdown", timeout=5, trust_env=False)
                except httpx.HTTPError:
                    pass

        win.events.closed += on_closed
        webview.start(
            private_mode=cfg.forget
        )  # forget-mode: no cookies/storage persisted by the webview
    except Exception as e:  # pywebview unavailable → browser, keep serving until Ctrl-C
        _log(f"pywebview unavailable ({e}); opening the browser instead")
        webbrowser.open(url if ok else _log_path().as_uri())
        if started_here and ok:
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass
