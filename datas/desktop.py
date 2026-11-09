"""The Datas window: the local server in a thread + a native window (pywebview).

No browser, no terminal. ``datas`` / ``Datas.exe`` with no arguments opens this; a model
shortcut passes ``--model <id>`` so the AI starts right away. Closing the window stops
the engine too — nothing keeps running unnoticed. Falls back to the default browser when
pywebview cannot create a window (e.g. a Linux box without GTK/Qt WebKit).
"""

from __future__ import annotations

import socket
import threading
import time
import webbrowser

import httpx

from datas.config import Config


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _already_running(port: int) -> bool:
    try:
        return httpx.get(f"http://127.0.0.1:{port}/api/status", timeout=1.5).status_code == 200
    except httpx.HTTPError:
        return False


def _serve(port: int) -> None:
    import uvicorn

    from datas.server.app import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


def open_window(
    model_id: str | None = None,
    path: str = "/",
    title: str = "Datas.ar",
    width: int = 1120,
    height: int = 820,
) -> None:
    cfg = Config.load()
    port = cfg.ui_port
    url = f"http://127.0.0.1:{port}{path}"
    if model_id:
        url += ("&" if "?" in url else "?") + f"autorun={model_id}"

    started_here = False
    if not _already_running(port):
        if not _port_free(port):
            raise SystemExit(f"Port {port} is busy. Change ui_port in the Datas settings file.")
        threading.Thread(target=_serve, args=(port,), daemon=True).start()
        started_here = True
        deadline = time.time() + 20
        while time.time() < deadline and not _already_running(port):
            time.sleep(0.2)

    try:
        import webview  # pywebview

        win = webview.create_window(
            title,
            url,
            width=width,
            height=height,
            min_size=(760, 560),
            background_color="#0E1116",
            text_select=True,
        )

        def on_closed():
            if started_here and path == "/":
                try:
                    httpx.post(f"http://127.0.0.1:{port}/api/shutdown", timeout=5)
                except httpx.HTTPError:
                    pass

        win.events.closed += on_closed
        webview.start(
            private_mode=cfg.forget
        )  # forget-mode: no cookies/storage persisted by the webview
    except Exception:  # pywebview unavailable → browser, keep serving until Ctrl-C
        webbrowser.open(url)
        if started_here:
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass
