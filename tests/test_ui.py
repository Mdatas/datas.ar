"""The window: every text it asks for exists in both languages, it runs only its own script
files, and the page pieces it names are really shipped."""

import re

from fastapi.testclient import TestClient

from tests import ui_keys

COMPARED = {"forget", "remember", "no", "video", "moe"}  # values tested in the code, not shown


def client():
    from datas.server import app as appmod

    return TestClient(appmod.app)


def test_every_text_key_exists_in_english_and_spanish():
    keys, prefixes = ui_keys.used()
    d = ui_keys.dictionary()
    assert set(d) == {"en", "es"}
    assert set(d["en"]) == set(d["es"]), set(d["en"]) ^ set(d["es"])
    missing = sorted(k for k in keys - COMPARED if k not in d["en"])
    assert not missing, f"the window asks for texts that do not exist: {missing}"
    for p in prefixes:
        assert any(k.startswith(p) for k in d["en"]), f"no text starts with {p}"
    unused = sorted(k for k in d["en"] if k not in keys and not any(k.startswith(p) for p in prefixes))
    assert not unused, f"texts nobody uses: {unused}"
    for lang in d:
        for k, v in d[lang].items():
            assert v.strip(), (lang, k)
            assert sorted(re.findall(r"\{(\w+)\}", v)) == sorted(re.findall(r"\{(\w+)\}", d["en"][k])), k


def test_pages_run_only_their_own_script_files():
    c = client()
    for path in ("/", "/agent"):
        r = c.get(path)
        assert r.status_code == 200
        csp = r.headers["content-security-policy"]
        assert "script-src 'self';" in csp and "'unsafe-inline'; script-src" in csp  # styles only
        html = r.text
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "a script is written into the page"
        assert not re.search(r"\son[a-z]+\s*=", html), "an inline event handler is written into the page"
        for ref in re.findall(r'(?:src|href)="(/ui/[^"]+)"', html):
            got = c.get(ref)
            assert got.status_code == 200 and got.content, ref
    for name in ("app.js", "chat.js", "screens.js", "i18n.js", "agent.js", "app.css", "agent.css"):
        assert c.get("/ui/" + name).status_code == 200
    assert c.get("/ui/../config.py").status_code == 404


def test_fonts_are_shipped_and_nothing_points_outside():
    css = (ui_keys.UI / "app.css").read_text(encoding="utf-8")
    fonts = re.findall(r"url\((/ui/fonts/[^)]+)\)", css)
    assert len(fonts) >= 4
    c = client()
    for f in fonts:
        assert c.get(f).status_code == 200, f
    for name in ("index.html", "agent.html", "app.css", "agent.css", "app.js", "chat.js", "screens.js", "agent.js"):
        text = (ui_keys.UI / name).read_text(encoding="utf-8")
        outside = [u for u in re.findall(r'(?:src|href|url)\s*[=(]\s*["\']?(https?://[^"\')\s]+)', text)]
        assert not outside, (name, outside)


def test_file_chooser_and_ai_folder(monkeypatch):
    from datas import export as exporter
    from datas.config import models_dir

    c = client()
    assert c.post("/api/pick-file").json() == {"available": False, "path": None}  # no window here
    assert exporter.allowed(models_dir()) == models_dir().resolve()
    try:
        exporter.allowed("/etc")
    except PermissionError:
        pass
    else:
        raise AssertionError("only Datas' own folders may be opened")
