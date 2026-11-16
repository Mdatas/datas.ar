"""The agent's own browser: a separate Edge, Chrome, Chromium or Brave window with a profile of
its own (``<data>/agent/browser``) — never the person's own browser, sign-ins or history.

It is driven through the Chrome DevTools Protocol (the debugging interface built into these
browsers) over a local WebSocket, so nothing extra is downloaded. The window is visible: the
person sees every step and can take over, for example to type a password — the agent itself
never types into a password field. Internet must be on for the session; addresses inside the
person's own network are refused unless allowed in Settings (``datas/netguard.py``).

In Forget mode the profile is wiped when the task ends.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

import httpx

SYSTEM = platform.system()

# what the AI gets to see of a page, and how elements are numbered for it
_READ_JS = r"""
(() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-datas-n]').forEach(e => e.removeAttribute('data-datas-n'));
  const items = []; let n = 0;
  const sel = 'a[href], button, input, select, textarea, [role=button], [role=link], [contenteditable=true]';
  for (const e of document.querySelectorAll(sel)) {
    if (!vis(e) || e.disabled) continue;
    if (e.tagName === 'INPUT' && e.type === 'hidden') continue;
    n += 1; e.setAttribute('data-datas-n', n);
    const label = (e.getAttribute('aria-label') || e.innerText || e.value || e.placeholder ||
      e.title || e.name || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    let kind = e.tagName.toLowerCase();
    if (kind === 'input') kind = 'input ' + (e.type || 'text');
    if (kind === 'a') kind = 'link';
    items.push(`[${n}] ${kind}: ${label}` + (e.tagName === 'A' ? ` -> ${e.href}`.slice(0, 160) : ''));
    if (n >= 150) break;
  }
  const text = (document.body ? document.body.innerText : '').replace(/\n{3,}/g, '\n\n').slice(0, 12000);
  return JSON.stringify({title: document.title, url: location.href, text, items});
})()
"""


def find_browser() -> str | None:
    """A Chromium-family browser on this computer (they all speak the same debugging protocol)."""
    if SYSTEM == "Windows":
        roots = [
            os.environ.get(k, "") for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")
        ]
        rel = [
            r"Microsoft\Edge\Application\msedge.exe",
            r"Google\Chrome\Application\chrome.exe",
            r"BraveSoftware\Brave-Browser\Application\brave.exe",
            r"Chromium\Application\chrome.exe",
        ]
        for root in roots:
            for r in rel:
                p = Path(root) / r if root else None
                if p and p.is_file():
                    return str(p)
        return None
    if SYSTEM == "Darwin":
        for app in ("Google Chrome", "Microsoft Edge", "Chromium", "Brave Browser"):
            p = Path("/Applications") / f"{app}.app" / "Contents" / "MacOS" / app
            if p.is_file():
                return str(p)
        return None
    for name in (
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "microsoft-edge",
        "brave-browser",
    ):
        p = shutil.which(name)
        if p:
            return p
    return None


def profile_dir() -> Path:
    from datas.config import home

    d = home() / "agent" / "browser"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Browser:
    """One browser window for one agent task."""

    def __init__(self, allow_local: bool = False, forget: bool = False) -> None:
        self.allow_local, self.forget = allow_local, forget
        self.proc: subprocess.Popen | None = None
        self.ws = None
        self._id = 0

    # ---- starting and talking ------------------------------------------------
    def _start(self) -> None:
        if self.ws is not None:
            return
        exe = find_browser()
        if not exe:
            raise RuntimeError(
                "No Edge, Chrome, Chromium or Brave was found on this computer; the agent's "
                "own browser needs one of them."
            )
        prof = profile_dir()
        (prof / "DevToolsActivePort").unlink(missing_ok=True)
        # no screen (a Raspberry Pi or server without one): the same browser, without a window
        unseen = SYSTEM == "Linux" and not (
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        )
        extra = ["--headless=new"] if unseen else []
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            extra.append("--no-sandbox")  # Chromium refuses to run as root otherwise
        self.proc = subprocess.Popen(
            [
                exe,
                *extra,
                f"--user-data-dir={prof}",
                "--remote-debugging-port=0",
                "--remote-debugging-address=127.0.0.1",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-sync",
                "--new-window",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=(prof.parent / "browser.log").open("wb"),
        )
        port = None
        for _ in range(100):  # the browser writes its debugging port into the profile
            f = prof / "DevToolsActivePort"
            if f.exists():
                first = f.read_text("utf-8", "replace").splitlines()[:1]
                if first and first[0].strip().isdigit():
                    port = int(first[0])
                    break
            time.sleep(0.2)
        if not port:
            self.close()
            why = ""
            try:  # the browser's own last words, e.g. a sandbox the system does not allow
                lines = (
                    (prof.parent / "browser.log").read_text("utf-8", "replace").strip().splitlines()
                )
                why = (" It said: " + lines[-1][:300]) if lines else ""
            except OSError:
                pass
            raise RuntimeError("The browser did not open its debugging port." + why)
        pages = []
        for _ in range(50):
            try:
                pages = [
                    t
                    for t in httpx.get(
                        f"http://127.0.0.1:{port}/json/list", timeout=3, trust_env=False
                    ).json()
                    if t.get("type") == "page"
                ]
            except (httpx.HTTPError, ValueError):
                pages = []
            if pages:
                break
            time.sleep(0.2)
        if not pages:
            self.close()
            raise RuntimeError("The browser opened no page.")
        from websockets.sync.client import connect

        self.ws = connect(pages[0]["webSocketDebuggerUrl"], max_size=None, open_timeout=10)
        self._send("Page.enable")
        self._send("Runtime.enable")

    def _send(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(self.ws.recv(timeout=max(0.1, deadline - time.time())))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message", "browser error"))
                return msg.get("result", {})
        raise TimeoutError(f"the browser did not answer {method}")

    def _eval(self, js: str):  # noqa: ANN202
        r = self._send(
            "Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True}
        )
        if r.get("exceptionDetails"):
            raise RuntimeError(r["exceptionDetails"].get("text", "script error"))
        return r.get("result", {}).get("value")

    def _settle(self, limit: float = 20) -> None:
        deadline = time.time() + limit
        time.sleep(0.4)
        while time.time() < deadline:
            try:
                if self._eval("document.readyState") == "complete":
                    break
            except Exception:  # noqa: BLE001 - mid-navigation
                pass
            time.sleep(0.3)
        time.sleep(0.4)

    def _guard_here(self) -> None:
        """After a click the page may have gone anywhere: refuse to stay inside the network."""
        from datas import netguard

        url = self._eval("location.href") or ""
        if url.startswith(("http://", "https://")):
            netguard.check_url(url, self.allow_local)

    # ---- what the agent can do -------------------------------------------------
    def open(self, url: str) -> str:
        from datas import netguard

        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        netguard.check_url(url, self.allow_local)
        self._start()
        self._send("Page.navigate", {"url": url})
        self._settle()
        return self.read()

    def read(self) -> str:
        self._start()
        d = json.loads(self._eval(_READ_JS))
        out = [f"Page: {d['title']}", f"Address: {d['url']}", "", d["text"].strip()]
        if d["items"]:
            out += ["", "Things to click or fill, by number:", *d["items"]]
        return "\n".join(out)

    def click(self, number: int) -> str:
        self._start()
        ok = self._eval(f"""(() => {{ const e = document.querySelector('[data-datas-n="{int(number)}"]');
            if (!e) return false; e.scrollIntoView({{block: 'center'}}); e.click(); return true; }})()""")
        if not ok:
            return f"There is no element {number} on the page any more; read the page again."
        self._settle()
        self._guard_here()
        return self.read()

    def type_text(self, number: int, text: str, submit: bool = False) -> str:
        self._start()
        kind = self._eval(f"""(() => {{ const e = document.querySelector('[data-datas-n="{int(number)}"]');
            if (!e) return null; if (e.type === 'password') return 'password';
            const field = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.tagName) || e.isContentEditable;
            if (!field) return 'notfield';
            e.scrollIntoView({{block: 'center'}}); e.focus();
            if ('value' in e) e.value = ''; return 'ok'; }})()""")
        if kind is None:
            return f"There is no element {number} on the page any more; read the page again."
        if kind == "notfield":
            return f"Element {number} is not a field to type in; pick a field from the list."
        if kind == "password":
            return (
                "REFUSED: that is a password field. The person types passwords themselves in "
                "the browser window; ask them to, then continue."
            )
        self._send("Input.insertText", {"text": text})
        if submit:
            js = f"""(() => {{ const e = document.querySelector('[data-datas-n="{int(number)}"]');
                if (e && e.form) {{ e.form.requestSubmit(); return true; }} return false; }})()"""
            try:  # the form's own submit, as pressing Enter would; else a real Enter key
                sent = self._eval(js)
            except RuntimeError:  # the page started to change while answering: it was sent
                sent = True
            if not sent:
                for t in ("keyDown", "keyUp"):
                    key = {"type": t, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}
                    if t == "keyDown":
                        key["text"] = "\r"
                    self._send("Input.dispatchKeyEvent", key)
            self._settle()
            self._guard_here()
        return self.read()

    def back(self) -> str:
        self._start()
        h = self._send("Page.getNavigationHistory")
        i = h.get("currentIndex", 0)
        if i <= 0:
            return "There is no earlier page.\n\n" + self.read()
        self._send("Page.navigateToHistoryEntry", {"entryId": h["entries"][i - 1]["id"]})
        self._settle()
        return self.read()

    def close(self) -> None:
        try:
            if self.ws is not None:
                self.ws.close()
        except Exception:  # noqa: BLE001
            pass
        self.ws = None
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if self.forget:
            shutil.rmtree(profile_dir(), ignore_errors=True)
