"""The window self-check: what counts as a working window, and the page's report route."""

from fastapi.testclient import TestClient

from datas import __version__, desktop

GOOD = {
    "version": __version__,
    "wordmark": "Datas",
    "nav": 6,
    "screens": {
        name: {"parts": 1, "heading": name.title(), "letters": 900}
        for name in desktop.CHECKED_SCREENS
    },
    "errors": [],
}


def test_a_window_that_shows_every_screen_passes():
    assert desktop._judge(GOOD) == []


def test_what_counts_as_a_broken_window():
    assert desktop._judge({}) != []
    assert any("version" in p for p in desktop._judge({**GOOD, "version": "0.0.1"}))
    assert any("side bar" in p for p in desktop._judge({**GOOD, "nav": 0}))
    empty = {**GOOD, "screens": {**GOOD["screens"], "learn": {"parts": 0, "letters": 0}}}
    assert any("learn screen is empty" in p for p in desktop._judge(empty))
    stuck = {
        **GOOD,
        "screens": {n: {"parts": 1, "heading": "Same", "letters": 900} for n in GOOD["screens"]},
    }
    assert any("did not change" in p for p in desktop._judge(stuck))
    assert any(
        "script error" in p for p in desktop._judge({**GOOD, "errors": ["x is not defined"]})
    )


def test_the_page_can_leave_its_report(tmp_path, monkeypatch):
    from datas.server import app as appmod

    c = TestClient(appmod.app, base_url="http://127.0.0.1:8420")
    assert c.post("/api/selfcheck", json=GOOD).json() == {"ok": True}
    assert c.get("/api/selfcheck").json()["report"]["wordmark"] == "Datas"


def test_the_window_scripts_know_shortcuts_and_the_self_check():
    js = (appmod_ui() / "app.js").read_text(encoding="utf-8")
    assert 'asked.get("autorun")' in js and 'asked.has("selfcheck")' in js


def appmod_ui():
    from datas.server.app import ui_dir

    return ui_dir()
