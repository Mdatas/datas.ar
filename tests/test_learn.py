"""Learn: the shipped lessons, glossary and list of outside material hold together."""

from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from datas import learn
from datas.config import Config


def test_catalog_is_consistent():
    cat = learn.catalog()
    ids = [i["id"] for i in cat["items"]]
    assert len(ids) == len(set(ids)), "an item id is used twice"
    kinds = {"course", "video", "article", "book", "report", "paper", "law", "guide", "site"}
    for i in cat["items"]:
        parts = urlsplit(i["url"])
        assert parts.scheme == "https" and parts.hostname, i["url"]
        assert i["kind"] in kinds, i
        assert 1 <= i["level"] <= 5
        assert i["lang"] and set(i["lang"]) <= {"en", "es"}
        assert i["why"]["en"].strip() and i["why"]["es"].strip()
    assert [lv["id"] for lv in cat["levels"]] == [1, 2, 3, 4, 5]
    used = set()
    for p in cat["paths"]:
        assert p["name"]["en"] and p["name"]["es"] and p["items"]
        for ref in p["items"]:
            assert learn.known(ref), f"{p['id']} points to {ref}, which does not exist"
            used.add(ref)
    assert set(ids) <= used, f"not on any path: {set(ids) - used}"
    for g in cat["glossary"]:
        assert g["term"]["en"] and g["term"]["es"] and g["short"]["en"] and g["short"]["es"]


def test_lessons_exist_in_both_languages():
    en, es = learn.lessons("en"), learn.lessons("es")
    assert list(en) == list(es) and len(en) >= 12
    for lid, le in en.items():
        assert le["title"] and len(le["markdown"]) > 200, lid
        assert es[lid]["title"] != le["title"] and len(es[lid]["markdown"]) > 200, lid
        assert es[lid]["level"] == le["level"] and 1 <= le["level"] <= 5
    used = {r for p in learn.catalog()["paths"] for r in p["items"] if r.startswith("lesson:")}
    assert {f"lesson:{k}" for k in en} == used  # every lesson is on a path, and nothing dangles


def test_listing_is_translated_and_ordered():
    en, es = learn.listing("en"), learn.listing("es")
    assert en["paths"][0]["id"] == "start" and en["paths"][-1]["id"] == "es"
    assert [p["id"] for p in es["paths"]][:2] == ["start", "es"]
    assert es["paths"][0]["name"] == "Empezá acá"
    first = en["paths"][0]["items"][0]
    assert first["type"] == "lesson" and first["title"]
    link = next(i for p in en["paths"] for i in p["items"] if i["type"] == "link")
    assert link["url"].startswith("https://") and link["why"] and link["langs"]
    assert en["counts"]["links"] >= 50 and en["counts"]["terms"] >= 40
    assert learn.listing("fr")["paths"][0]["name"] == "Start here"  # unknown language: English


def test_progress_is_kept_only_in_remember_mode():
    cfg = Config()
    cfg.memory_mode = "remember"
    assert learn.mark("lesson:what-is-ai", True, cfg) is True
    assert learn.mark("elements-of-ai", True, cfg) is True
    assert learn.progress(cfg) == ["lesson:what-is-ai", "elements-of-ai"]
    assert learn.listing("en", cfg)["paths"][0]["items"][0]["done"] is True
    learn.mark("lesson:what-is-ai", False, cfg)
    assert learn.progress(cfg) == ["elements-of-ai"]
    forget = Config()
    forget.memory_mode = "forget"
    assert learn.mark("lesson:ask-well", True, forget) is False
    assert learn.progress(forget) == [] and learn.listing("en", forget)["saves_progress"] is False
    try:
        learn.mark("no-such-thing", True, cfg)
    except KeyError:
        pass
    else:
        raise AssertionError("unknown items must be refused")
    learn.mark("elements-of-ai", False, cfg)


def test_learn_api_and_opening_links(monkeypatch):
    from datas.server import app as appmod

    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: opened.append(url) or True)
    c = TestClient(appmod.app)
    r = c.get("/api/learn", params={"lang": "es"})
    assert r.status_code == 200 and r.json()["paths"][0]["name"] == "Empezá acá"
    le = c.get("/api/learn/lesson/ask-well", params={"lang": "en"}).json()
    assert le["title"].startswith("Asking well") and "**" in le["markdown"]
    assert c.get("/api/learn/lesson/nope").status_code == 404
    assert c.post("/api/learn/progress", json={"ref": "nope"}).status_code == 404
    url = learn.urls()[0]
    assert c.post("/api/open-url", json={"url": url}).json() == {"opened": True}
    assert opened == [url]
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "datas://x", "https://", "notaurl"):
        assert c.post("/api/open-url", json={"url": bad}).status_code == 400, bad
    assert opened == [url]
