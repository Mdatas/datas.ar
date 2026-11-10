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
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

import httpx

from datas.config import Config, logs_dir, rotate_log

_server_error: str | None = None


def _log_path() -> Path:
    return logs_dir() / "datas.log"


def _attach_console_to_log() -> None:
    """pythonw / windowed exe: stdout & stderr are None. Point them at the log file."""
    rotate_log(_log_path(), 2 * 2**20)
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

        from datas.server.app import app, set_http_port

        set_http_port(port)
        config = uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="error", log_config=None
        )
        uvicorn.Server(config).run()
    except BaseException:  # noqa: BLE001 — we want *everything* in the log
        _server_error = traceback.format_exc()
        _log("server thread failed:\n" + _server_error)


def _loading_page() -> str:
    body = """<!doctype html><html><head><meta charset="utf-8"><title>Datas</title>
<style>body{background:#F3F8FD;color:#0F2742;font-family:Segoe UI,Asap,Inter,Arial,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.b{text-align:center}.d{font-size:34px;font-weight:700;letter-spacing:-.01em}p{color:#4A5F7A}
.bar{width:230px;height:8px;background:#E4F0FB;border-radius:4px;margin:18px auto;overflow:hidden}.bar i{display:block;width:40%;height:100%;background:#F6B40E;border-radius:4px;animation:m 1.2s infinite ease-in-out}
@keyframes m{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}
@media (prefers-color-scheme: dark){body{background:#0B1626;color:#EAF2FB}p{color:#9DB3CC}.bar{background:#18304D}}</style></head><body><div class="b">
<div class="d">Datas</div><div class="bar"><i></i></div><p>Starting… / Iniciando…<br><small>The first start after installing can take a minute.</small></p></div></body></html>"""
    return "data:text/html;charset=utf-8," + __import__("urllib.parse").parse.quote(body)


def _error_page(port: int, cfg_home: Path) -> str:
    tail = ""
    try:
        tail = "\n".join(
            _log_path().read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        )
    except OSError:
        pass
    body = f"""<!doctype html><html><head><meta charset="utf-8"><title>Datas</title>
<style>body{{background:#F3F8FD;color:#0F2742;font-family:Segoe UI,Asap,Inter,Arial,sans-serif;padding:40px;max-width:900px;margin:auto}}
h1{{color:#85340A}} pre{{background:#fff;border:1px solid #D5E3F1;border-radius:10px;padding:14px;white-space:pre-wrap;font-size:12px;color:#4A5F7A}}
code{{background:#E4F0FB;padding:2px 6px;border-radius:6px}}</style></head><body>
<h1>Datas could not start its local service</h1>
<p>The window opened, but the part of Datas that does the work did not start on <code>127.0.0.1:{port}</code>.
This is a bug or a blocked port, not something you did. The details below are saved in<br><code>{html.escape(str(_log_path()))}</code>
— send that file to the developer.</p>
<p>Quick checks: is another program using port {port}? Does your antivirus block <code>pythonw.exe</code> / <code>Datas.exe</code>?</p>
<pre>{html.escape(_server_error or tail or "(no details were written to the log)")}</pre>
<p>Data folder: <code>{html.escape(str(cfg_home))}</code></p>
</body></html>"""
    return "data:text/html;charset=utf-8," + __import__("urllib.parse").parse.quote(body)


# ---------------------------------------------------------------------------
# window self-check: open the real window, let the page say what it shows, close it
# ---------------------------------------------------------------------------
# Used by the installer builds on Windows, macOS and Linux (`Datas open --selfcheck out.json`):
# the only way to know that the native window — WebView2, WKWebView or Qt WebEngine — really
# shows the app on that system is to open it there. The page, loaded with ``?selfcheck``,
# walks through its screens and reports to the local service; nothing is injected into it
# (the window's own rules forbid running injected script, and that stays so).
CHECKED_SCREENS = ("chat", "learn", "setup", "devices", "tools", "settings", "about")


def _judge(seen: dict) -> list[str]:
    """What is wrong with a window report; an empty list means the window works."""
    from datas import __version__

    bad = []
    if seen.get("version") != __version__:
        bad.append(f"the page reports version {seen.get('version')!r}, expected {__version__}")
    if seen.get("wordmark") != "Datas" or (seen.get("nav") or 0) < 5:
        bad.append("the side bar did not render")
    screens = seen.get("screens") or {}
    for name in CHECKED_SCREENS:
        got = screens.get(name) or {}
        if not got.get("parts") or (got.get("letters") or 0) < 20:
            bad.append(f"the {name} screen is empty")
    titles = {(screens.get(n) or {}).get("heading") for n in ("learn", "settings", "about")}
    if len(titles) < 3 or "" in titles:
        bad.append("moving between screens did not change what is shown")
    for e in seen.get("errors") or []:
        bad.append(f"script error: {e}")
    return bad


def _selfcheck(out: Path, port: int, server_up: bool) -> bool:
    """Wait for the page's own report, judge it, write the result. Never raises."""
    import json

    from datas import __version__

    t0 = time.time()
    report: dict = {"ok": False, "datas": __version__, "server_up": server_up}
    try:
        seen = None
        deadline = time.time() + 150
        while server_up and seen is None and time.time() < deadline:
            try:
                with httpx.Client(timeout=3, trust_env=False) as c:
                    seen = c.get(f"http://127.0.0.1:{port}/api/selfcheck").json().get("report")
            except (httpx.HTTPError, ValueError):
                seen = None
            if seen is None:
                time.sleep(1)
        if seen is None:
            report["problems"] = [
                "the window opened but the page never reported: it did not load or its "
                "scripts did not run"
                if server_up
                else "the local service did not start"
            ]
        else:
            report["seen"] = seen
            report["problems"] = _judge(seen)
            report["ok"] = not report["problems"]
        try:  # a picture of the screen for the build log, where the system allows one
            from PIL import ImageGrab

            shot = out.with_suffix(".png")
            ImageGrab.grab().save(shot)
            report["screenshot"] = str(shot)
        except Exception as e:  # noqa: BLE001
            report["screenshot_error"] = f"{type(e).__name__}: {e}"[:200]
    except Exception:  # noqa: BLE001
        report["error"] = traceback.format_exc()[-1500:]
    report["seconds"] = round(time.time() - t0, 1)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError as e:
        _log(f"selfcheck: could not write {out}: {e}")
    _log(f"selfcheck ok={report['ok']} in {report['seconds']}s")
    return bool(report["ok"])


def open_window(
    model_id: str | None = None,
    path: str = "/",
    title: str = "Datas.ar",
    width: int = 1120,
    height: int = 820,
    selfcheck: Path | None = None,
) -> None:
    _attach_console_to_log()
    cfg = Config.load()
    port = cfg.ui_port
    _log(
        f"open_window path={path} model={model_id} python={sys.version.split()[0]} exe={sys.executable}"
    )

    started_here = False
    if not _already_running(port):
        if not _port_free(port):
            # Another program has the port: take the next free one and remember it, so every
            # part of Datas (agent window, shortcuts, command line) finds the app there.
            for cand in range(port + 1, port + 40):
                if _port_free(cand) and cand not in (cfg.llama_port, cfg.sd_port, cfg.link_port):
                    _log(f"port {port} is used by another program; using {cand} from now on")
                    cfg.ui_port = port = cand
                    cfg.save()
                    break
        threading.Thread(target=_serve, args=(port,), daemon=True, name="datas-server").start()
        started_here = True
    url = f"http://127.0.0.1:{port}{path}"
    if model_id:
        url += ("&" if "?" in url else "?") + f"autorun={model_id}"
    if selfcheck is not None:
        url += ("&" if "?" in url else "?") + "selfcheck=1"

    def wait_for_server(limit: float) -> bool:
        deadline = time.time() + limit
        while time.time() < deadline and _server_error is None:
            if _already_running(port):
                return True
            time.sleep(0.3)
        return _already_running(port)

    try:
        import webview  # pywebview

        # Open the window immediately with a "starting…" page; switch to the app when the
        # server answers (a cold start on Windows can take a while: antivirus scans a fresh
        # install file by file). Only after a long wait show the error page with the log.
        win = webview.create_window(
            title,
            _loading_page(),
            width=width,
            height=height,
            min_size=(760, 560),
            background_color="#F3F8FD",
            text_select=True,
        )
        state = {"ok": False, "checked": None}

        def switch_when_ready():
            state["ok"] = wait_for_server(180)
            _log(f"server up={state['ok']}")
            win.load_url(url if state["ok"] else _error_page(port, logs_dir().parent))
            if selfcheck is not None:
                state["checked"] = _selfcheck(selfcheck, port, state["ok"])
                win.destroy()

        def on_closed():
            if started_here and path == "/" and state["ok"]:
                try:
                    httpx.post(f"http://127.0.0.1:{port}/api/shutdown", timeout=5, trust_env=False)
                except httpx.HTTPError:
                    pass

        win.events.closed += on_closed
        gui = None
        if sys.platform.startswith("linux"):
            try:  # the Linux build ships Qt WebEngine; use it rather than the distro's WebKitGTK
                import qtpy  # noqa: F401

                gui = "qt"
                flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
                if hasattr(os, "geteuid") and os.geteuid() == 0 and "--no-sandbox" not in flags:
                    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (flags + " --no-sandbox").strip()
            except ImportError:
                gui = None
        webview.start(switch_when_ready, private_mode=cfg.forget, gui=gui)
        if selfcheck is not None:
            raise SystemExit(0 if state["checked"] else 1)
    except Exception as e:  # pywebview unavailable → browser, keep serving until Ctrl-C
        if selfcheck is not None:
            import json

            _log(f"selfcheck: no window could be opened ({e})")
            selfcheck.write_text(
                json.dumps({"ok": False, "error": f"no window: {type(e).__name__}: {e}"}),
                encoding="utf-8",
            )
            raise SystemExit(1) from e
        _log(f"pywebview unavailable ({e}); opening the browser instead")
        ok = wait_for_server(60)
        webbrowser.open(url if ok else _log_path().as_uri())
        if started_here and ok:
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass


def open_external(url: str, title: str = "Datas.ar", width: int = 1280, height: int = 860) -> None:
    """A plain window on a local web app Datas started (ComfyUI, FaceFusion…)."""
    _attach_console_to_log()
    _log(f"open_external {url}")
    try:
        import webview

        gui = None
        if sys.platform.startswith("linux"):
            try:
                import qtpy  # noqa: F401

                gui = "qt"
                flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
                if hasattr(os, "geteuid") and os.geteuid() == 0 and "--no-sandbox" not in flags:
                    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (flags + " --no-sandbox").strip()
            except ImportError:
                gui = None
        webview.create_window(title, url, width=width, height=height)
        webview.start(gui=gui)
    except Exception as e:  # noqa: BLE001
        _log(f"pywebview unavailable ({e}); opening the browser instead")
        webbrowser.open(url)
