#!/usr/bin/env python3
"""Developer tool: render Datas screens headlessly and save PNG screenshots.

    python scripts/ui_shot.py out_dir [--size 1280x860] [--lang es] [--js "go('chat')"] [--name chat]
    python scripts/ui_shot.py out_dir --all            # every main screen, wide and narrow

Starts the real server on a spare port with DATAS_HOME (default: a temp folder), loads the page in
Qt WebEngine offscreen, runs optional JavaScript, waits, grabs the window. Needs `datas[qt]`.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if hasattr(os, "geteuid") and os.geteuid() == 0:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --no-sandbox"


def serve(port: int) -> None:
    import uvicorn

    from datas.server.app import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--size", default="1280x860")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--js", default="")
    ap.add_argument("--name", default="shot")
    ap.add_argument("--path", default="/")
    ap.add_argument("--wait", type=float, default=2.0)
    ap.add_argument("--port", type=int, default=8479)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    os.environ.setdefault("DATAS_HOME", tempfile.mkdtemp(prefix="datas-shot-"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=serve, args=(a.port,), daemon=True).start()

    import httpx

    for _ in range(100):
        try:
            httpx.get(f"http://127.0.0.1:{a.port}/api/status", timeout=1, trust_env=False)
            break
        except httpx.HTTPError:
            time.sleep(0.2)

    from PyQt6.QtCore import QEventLoop, QTimer, QUrl
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication

    qt = QApplication(sys.argv[:1])

    def pump(seconds: float) -> None:
        loop = QEventLoop()
        QTimer.singleShot(int(seconds * 1000), loop.quit)
        loop.exec()

    def shot(name: str, size: str, js: str, path: str = "/", wait: float = a.wait) -> None:
        w, h = (int(x) for x in size.split("x"))
        view = QWebEngineView()
        view.resize(w, h)
        view.show()
        loaded = {"ok": False}
        view.loadFinished.connect(lambda ok: loaded.update(ok=ok))
        view.load(QUrl(f"http://127.0.0.1:{a.port}{path}"))
        t0 = time.time()
        while not loaded["ok"] and time.time() - t0 < 20:
            pump(0.1)
        pump(1.0)
        pre = f"try{{ if(typeof setLangForShot==='function') setLangForShot('{a.lang}'); }}catch(e){{}}"
        view.page().runJavaScript(pre)
        pump(0.4)
        if js:
            view.page().runJavaScript(js)
        pump(wait)
        view.grab().save(str(out / f"{name}.png"))
        print("saved", out / f"{name}.png")
        view.close()
        view.deleteLater()
        pump(0.2)

    if a.all:
        screens = [
            ("chat", "go('chat')"),
            ("setup", "go('setup')"),
            ("library", "go('library')"),
            ("create", "go('create')"),
            ("tools", "go('tools')"),
            ("devices", "go('devices')"),
            ("settings", "go('settings')"),
            ("about", "go('about')"),
        ]
        for name, js in screens:
            shot(f"{name}-wide", "1280x860", js)
            shot(f"{name}-narrow", "420x860", js)
    else:
        shot(a.name, a.size, a.js, a.path)
    qt.quit()


if __name__ == "__main__":
    main()
