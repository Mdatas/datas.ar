"""`datas selftest` — is every part of this copy of Datas present, and does it work?

Two uses:

* the installer builds run it on the finished app, so a copy that lost its window files, a
  document template or a font never reaches anyone;
* someone helping a user can ask for it ("run `datas-cli selftest` and tell me what it says").

It works in a throw-away folder: nothing of the user's is read or changed, nothing is
downloaded, no AI is started and no network port is opened.
"""

from __future__ import annotations

import json
import os
import shutil
import ssl
import tempfile
from collections.abc import Callable
from importlib import resources
from pathlib import Path

WINDOW_FILES = (
    "index.html",
    "app.css",
    "i18n.js",
    "app.js",
    "chat.js",
    "screens.js",
    "agent.html",
    "agent.css",
    "agent.js",
    "datas.png",
    "fonts/asap-latin-wght-normal.woff2",
    "fonts/museomoderno-latin-wght-normal.woff2",
)

SAMPLE = """# Datas self-test

A line with **bold** text, an accent (más información) and the word zorzal.

| Fruit | Kilos |
|---|---|
| Apples | 3 |
| Pears | 2.5 |

- first point
- second point
"""


def _window() -> str:
    root = Path(str(resources.files("datas.server").joinpath("ui")))
    missing = [f for f in WINDOW_FILES if not (root / f).is_file()]
    if missing:
        raise RuntimeError("missing: " + ", ".join(missing))
    text = (root / "i18n.js").read_text(encoding="utf-8")
    words = json.loads(text[text.index("{") : text.rindex("}") + 1])
    if set(words["en"]) != set(words["es"]):
        raise RuntimeError("the English and Spanish texts do not have the same entries")
    return f"{len(WINDOW_FILES)} files, {len(words['en'])} texts in English and Spanish"


def _lists() -> str:
    from datas import assistants
    from datas import catalog as cat

    models = cat.load().models
    helpers = assistants.all_assistants()
    sources = json.loads(
        resources.files("datas").joinpath("sources.json").read_text(encoding="utf-8")
    )["sources"]
    media = json.loads(
        resources.files("datas.catalog").joinpath("media.json").read_text(encoding="utf-8")
    )
    if not (models and helpers and sources and media):
        raise RuntimeError("a list is empty")
    return f"{len(models)} AIs, {len(helpers)} helpers, {len(sources)} credits"


def _learn() -> str:
    from datas import learn

    c = learn.catalog()
    en, es = learn.lessons("en"), learn.lessons("es")
    if not en or list(en) != list(es):
        raise RuntimeError("the English and Spanish lessons do not match")
    unknown = [r for p in c["paths"] for r in p["items"] if not learn.known(r)]
    if unknown:
        raise RuntimeError("paths point at missing entries: " + ", ".join(unknown[:5]))
    return f"{len(en)} lessons, {len(c['items'])} links, {len(c['glossary'])} words"


def _documents(tmp: Path) -> str:
    from datas import docs, export

    made = []
    for fmt in export.FORMATS:
        p = export.render(SAMPLE, fmt, tmp / "documents" / f"selftest.{fmt}", "Datas self-test")
        if not p.is_file() or p.stat().st_size == 0:
            raise RuntimeError(f"{fmt}: nothing was written")
        if p.suffix.lower() in docs.RICH_SUFFIXES:
            text = docs.extract_text(p.name, p.read_bytes())
            if "Apples" not in text:
                raise RuntimeError(f"{fmt}: written, but the text could not be read back")
        made.append(fmt)
    return "written and read back: " + ", ".join(made)


def _handshake(server: ssl.SSLContext, client: ssl.SSLContext) -> tuple[str | None, bytes | None]:
    """A complete TLS conversation in memory (no network): the version agreed, and the
    certificate the listening side saw from the calling side."""
    c_in, c_out, s_in, s_out = (ssl.MemoryBIO() for _ in range(4))
    c = client.wrap_bio(c_in, c_out, server_side=False)
    s = server.wrap_bio(s_in, s_out, server_side=True)
    c_done = s_done = False
    for _ in range(12):
        if not c_done:
            try:
                c.do_handshake()
                c_done = True
            except ssl.SSLWantReadError:
                pass
        s_in.write(c_out.read())
        if not s_done:
            try:
                s.do_handshake()
                s_done = True
            except ssl.SSLWantReadError:
                pass
        c_in.write(s_out.read())
        if c_done and s_done:
            break
    if not (c_done and s_done):
        raise RuntimeError("the two sides did not finish their greeting")
    return c.version(), s.getpeercert(binary_form=True)


def _devices(tmp: Path) -> str:
    from datas import link

    a_key, a_crt, a_pem = link.ensure_identity("self-test A", tmp / "link-a")
    b_key, b_crt, b_pem = link.ensure_identity("self-test B", tmp / "link-b")
    version, seen = _handshake(
        link.server_context(a_key, a_crt, [b_pem]), link.client_context(b_key, b_crt, a_pem)
    )
    if version != "TLSv1.3":
        raise RuntimeError(f"expected TLS 1.3, got {version}")
    if seen != ssl.PEM_cert_to_DER_cert(b_pem):
        raise RuntimeError("the listening device did not see the other device's certificate")
    # a device that was never linked must be turned away
    c_key, c_crt, _ = link.ensure_identity("self-test stranger", tmp / "link-c")
    try:
        _handshake(
            link.server_context(a_key, a_crt, [b_pem]), link.client_context(c_key, c_crt, a_pem)
        )
    except ssl.SSLError:
        pass
    else:
        raise RuntimeError("a device that is not linked was accepted")
    key = link.derive(link.new_code(), b"selftest")
    if len(key) != 32:
        raise RuntimeError("pairing code maths failed")
    return "encrypted link (TLS 1.3) between two identities; a stranger is refused"


def _service() -> str:
    from starlette.testclient import TestClient

    from datas import __version__
    from datas.server import app as appmod

    c = TestClient(appmod.app, base_url="http://127.0.0.1:8420")
    page = c.get("/")
    if page.status_code != 200 or "/ui/app.js" not in page.text:
        raise RuntimeError(f"the window page did not load ({page.status_code})")
    if "script-src 'self'" not in page.headers.get("content-security-policy", ""):
        raise RuntimeError("the window page came without its script protection")
    for f in ("app.css", "i18n.js", "app.js", "chat.js", "screens.js"):
        r = c.get("/ui/" + f)
        if r.status_code != 200 or not r.content:
            raise RuntimeError(f"/ui/{f} did not load ({r.status_code})")
    st = c.get("/api/status")
    if st.status_code != 200 or st.json().get("version") != __version__:
        raise RuntimeError("the status answer is wrong")
    if c.get("/api/learn?lang=es").status_code != 200:
        raise RuntimeError("the Learn screen has no data")
    # the two checks that keep other web pages out (docs/SECURITY.md)
    if c.get("/api/status", headers={"host": "example.org"}).status_code != 403:
        raise RuntimeError("a request addressed to another name was answered")
    r = c.post("/api/privacy", json={}, headers={"origin": "https://example.org"})
    if r.status_code != 403:
        raise RuntimeError("a request from another web page was accepted")
    return "window, lessons and status answer; other web pages are refused"


def _hardware() -> str:
    """The parts that reach cameras, printers, boards and home devices are all in this copy,
    and their pure logic works. Nothing is switched on, photographed, printed or sent."""
    import importlib
    import importlib.util
    import io
    import platform

    from datas import things, words
    from datas.things import control, local, net

    for mod in (
        "serial",
        "serial.tools.list_ports",
        "paho.mqtt.client",
        "PIL.Image",
        "PIL.ImageGrab",
    ):
        importlib.import_module(mod)
    # the mouse and keyboard part is only looked for, not started: starting it needs a screen
    # (and merely asking for one of its inner files would start it)
    import pkgutil

    spec = importlib.util.find_spec("pyautogui")
    if spec is None:
        raise RuntimeError("the mouse and keyboard part (PyAutoGUI) is missing")
    backend = {"Windows": "_pyautogui_win", "Darwin": "_pyautogui_osx"}.get(
        platform.system(), "_pyautogui_x11"
    )
    inside = {m.name for m in pkgutil.iter_modules(spec.submodule_search_locations or [])}
    if backend not in inside:
        raise RuntimeError(f"the mouse and keyboard part is incomplete ({backend} is missing)")
    for mod in ("pyscreeze", "pymsgbox", "pytweening"):
        if importlib.util.find_spec(mod) is None:
            raise RuntimeError(f"the mouse and keyboard part is incomplete ({mod} is missing)")
    inv = things.inventory()
    for key in ("cameras", "screens", "printers", "serial", "control", "ffmpeg", "connections"):
        if key not in inv:
            raise RuntimeError(f"the list of hardware has no {key}")
    # settings keep their secrets to themselves
    shown = things.save_settings({"mqtt": {"host": "192.0.2.1", "password": "selftest"}})
    if "password" in shown["mqtt"] or not shown["mqtt"]["password_set"]:
        raise RuntimeError("a saved password was shown")
    things.settings_path().unlink(missing_ok=True)
    # pictures, positions on the screen, names of devices, Spanish
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 36), "white").save(buf, "JPEG")
    if local.picture_size(buf.getvalue()) != (64, 36):
        raise RuntimeError("a picture came back with the wrong size")
    if control.to_screen(800, 450, (1600, 900), (1920, 1080)) != (960, 540):
        raise RuntimeError("a place on the screen was worked out wrong")
    if net.kind_of("_ipp._tcp.local.") != "printer" or not local.parse_lpstat("HP\n", ""):
        raise RuntimeError("devices are not recognised by what they announce")
    problem = things.ThingError(
        "There is no printer called {name}. Found: {names}", name="X", names="Y"
    )
    if problem.say("es") == str(problem) or "{" in problem.say("es"):
        raise RuntimeError("a message did not come out in Spanish")
    if len(words.ES) < 100:
        raise RuntimeError("the Spanish sentences are missing")
    from starlette.testclient import TestClient

    from datas.server import app as appmod

    r = TestClient(appmod.app, base_url="http://127.0.0.1:8420").get("/api/things")
    if r.status_code != 200 or "cameras" not in r.json():
        raise RuntimeError(f"the window cannot ask for the hardware ({r.status_code})")
    seen = (
        f"{len(inv['cameras'])} camera(s), {len(inv['printers'])} printer(s), "
        f"{len(inv['serial'])} board(s) seen"
    )
    ffmpeg = "FFmpeg is here" if inv["ffmpeg"]["found"] else "FFmpeg not fetched yet"
    return f"serial ports, MQTT, pictures, mouse and keyboard parts are present; {seen}; {ffmpeg}"


def run() -> list[tuple[str, bool, str]]:
    """[(what, ok, detail)] — never raises."""
    tmp = Path(tempfile.mkdtemp(prefix="datas-selftest-"))
    before = os.environ.get("DATAS_HOME")
    os.environ["DATAS_HOME"] = str(tmp / "home")
    checks: list[tuple[str, Callable[[], str]]] = [
        ("Window files", _window),
        ("Lists of AIs, helpers and credits", _lists),
        ("Lessons", _learn),
        ("Documents (Word, Excel, PowerPoint, PDF and others)", lambda: _documents(tmp)),
        ("Link between devices", lambda: _devices(tmp)),
        ("Local service", _service),
        ("Cameras, printers, boards and home devices", _hardware),
    ]
    out: list[tuple[str, bool, str]] = []
    try:
        for name, fn in checks:
            try:
                out.append((name, True, fn()))
            except Exception as e:  # noqa: BLE001 - every failure is reported, none stops the rest
                out.append((name, False, f"{type(e).__name__}: {e}"))
    finally:
        if before is None:
            os.environ.pop("DATAS_HOME", None)
        else:
            os.environ["DATAS_HOME"] = before
        shutil.rmtree(tmp, ignore_errors=True)
    return out
