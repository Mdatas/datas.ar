"""Offline survival: Datas' own guides, the library kept on this device, the helper that reads
them, and the screen's routes. Downloads run against a local web server."""

from __future__ import annotations

import hashlib
import http.server
import json
import re
import threading
from pathlib import Path

import pytest

from datas import survival

ROOT = Path(__file__).resolve().parents[1]


def test_every_entry_of_the_library_is_complete_and_checked():
    cat = survival.catalog()
    topics = {t["id"] for t in cat["topics"]}
    ids = [it["id"] for it in cat["items"]]
    assert len(ids) == len(set(ids)) and len(ids) >= 20
    for it in cat["items"]:
        assert it["topic"] in topics, it["id"]
        assert it["lang"] in ("en", "es") and it["format"] in ("pdf", "txt")
        assert it["kind"] in ("guide", "sheet", "chapter", "book", "reading"), it["id"]
        for k in ("url", "page", "license_url"):
            assert it[k].startswith("https://"), (it["id"], k)
        assert it["license"] and it["by"] and it["why"]["en"] and it["why"]["es"]
        # only what the check downloaded and pinned is offered (scripts/check_survival.py)
        assert re.fullmatch(r"[0-9a-f]{64}", it["sha256"] or ""), it["id"]
        assert isinstance(it["size"], int) and it["size"] > 1000
    # there is something for each language and each topic, and community is not an afterthought
    for t in topics:
        assert any(i["topic"] == t for i in cat["items"]), t
    assert {i["lang"] for i in cat["items"] if i["kind"] != "reading"} == {"en", "es"}


def test_the_guides_say_the_same_in_both_languages():
    en, es = survival.guide_sections("en"), survival.guide_sections("es")
    assert [g["id"] for g in en] == [g["id"] for g in es]
    ids = {g["id"] for g in en}
    assert {"start", "water", "food", "energy", "connect", "community", "travel", "longterm"} <= ids
    for g_en, g_es in zip(en, es, strict=True):
        assert g_en["text"] and g_es["text"] and g_en["title"] != g_es["title"]
        # every section that gives figures says where they come from
        if re.search(r"\d", g_en["text"]) and g_en["id"] not in ("start", "datas", "travel"):
            assert "Sources:" in g_en["text"] or g_en["id"] in ("outdoors", "health"), g_en["id"]
    # each section (except Datas' own how-to) ends in what to do together
    for g in en:
        if g["id"] not in ("datas", "community"):
            assert "**Together:**" in g["text"], g["id"]
    for g in es:
        if g["id"] not in ("datas", "community"):
            assert "**En comunidad:**" in g["text"], g["id"]
    # the safety figures are the ones the sources give
    water = next(g for g in en if g["id"] == "water")["text"]
    for figure in (
        "**1 minute**",
        "**3 minutes**",
        "**2 drops per litre**",
        "**wait at least 30 minutes**",
    ):
        assert figure in water
    food = next(g for g in en if g["id"] == "food")["text"]
    assert "**4 hours**" in food and "**48 hours**" in food and "**24\n  hours**" in food
    energy = next(g for g in en if g["id"] == "energy")["text"]
    assert (
        "**6 metres (20 feet)**" in energy
        and "**Never plug a generator into a wall socket**" in energy
    )


class _Server:
    def __init__(self, files: dict[str, bytes]):
        files = dict(files)

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = files.get(self.path)
                self.send_response(200 if body is not None else 404)
                self.send_header("Content-Length", str(len(body or b"")))
                self.end_headers()
                self.wfile.write(body or b"")

            def log_message(self, *a):  # noqa: ANN002
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A small library of two documents served from this computer."""
    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    monkeypatch.setattr(survival, "RETRY_WAIT", 0.01)
    howto = (
        b"Boil water for one minute.\n\nA neighbour with a generator shares the charging.\n" * 40
    )
    novel = b"Call me Ishmael. " * 200
    srv = _Server({"/howto.txt": howto, "/novel.txt": novel})
    real = survival.catalog()

    def item(id_, path, data, kind):
        return {
            "id": id_, "title": id_.title(), "by": "Test", "topic": "water", "lang": "en",
            "kind": kind, "page": "https://example.org/", "url": srv.url + path,
            "format": "txt", "license": "test", "license_url": "https://example.org/",
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "why": {"en": "why", "es": "por qué"},
        }  # fmt: skip

    fake = dict(real, items=[item("howto", "/howto.txt", howto, "guide"),
                             item("novel", "/novel.txt", novel, "reading"),
                             dict(item("unchecked", "/howto.txt", howto, "guide"), sha256=None)])  # fmt: skip
    monkeypatch.setattr(survival, "catalog", lambda: fake)
    yield srv
    srv.close()


def test_a_document_is_kept_checked_and_read_by_the_helper(library):
    st = survival.state("es")
    assert [i["id"] for i in st["items"]] == ["howto", "novel"]  # never the unchecked one
    assert st["items"][0]["why"] == "por qué" and not st["items"][0]["have"]
    seen = []
    survival.fetch("howto", lambda d, t: seen.append(d))
    assert seen and survival.state()["items"][0]["have"]
    assert "Boil water" in survival.text_of("howto")
    survival.fetch("novel")
    names = [d["name"] for d in survival.docs_text("en")]
    assert names[0].startswith("Datas — offline survival guides") and "Howto — Test" in names
    assert not any(n.startswith("Novel") for n in names)  # novels are read, not asked
    assert survival.docs_text("es")[0]["name"].startswith("Datas — guías")
    assert survival.remove("howto") and not survival.remove("howto")
    with pytest.raises(survival.Problem):
        survival.text_of("howto")
    with pytest.raises(survival.Problem, match="not been checked"):
        survival.fetch("unchecked")


def test_a_changed_or_missing_document_is_refused_with_a_sentence(library):
    with pytest.raises(survival.Problem) as e:
        survival.fetch("howto", source=library.url + "/novel.txt")  # not what was checked
    assert "is not the one Datas checked" in str(e.value)
    assert "no es el que Datas verificó" in e.value.say("es")
    assert not (survival.folder() / "howto.txt").exists()
    with pytest.raises(survival.Problem) as e:
        survival.fetch("howto", source=library.url + "/gone.txt")
    assert "Could not download it from 127.0.0.1" in str(e.value)
    with pytest.raises(survival.Problem, match="not in the library"):
        survival.fetch("nothing")
    got = survival.fetch_all("en")
    assert sorted(got["got"]) == ["howto", "novel"] and got["failed"] == []


def test_the_screen_routes(library):
    from fastapi.testclient import TestClient

    from datas.server import app as server

    c = TestClient(server.app, base_url="http://127.0.0.1")
    st = c.get("/api/survival?lang=en").json()
    assert st["missing_bytes"] > 0 and len(st["guides"]) >= 10
    job = c.post("/api/survival/keep/howto").json()
    for _ in range(100):
        j = c.get(f"/api/jobs/{job['id']}").json()
        if j["state"] in ("done", "error"):
            break
        import time

        time.sleep(0.05)
    assert j["state"] == "done", j
    f = c.get("/api/survival/file/howto")
    assert f.status_code == 200 and f.content.startswith(b"Boil water")
    assert "Boil water" in c.get("/api/survival/text/howto").json()["text"]
    assert c.delete("/api/survival/keep/howto").json() == {"removed": True}
    assert c.get("/api/survival/file/howto").status_code == 400
    assert c.post("/api/survival/keep/nothing").status_code == 400


def test_the_survival_helper_is_built_in_and_reads_the_library(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    from datas import assistants

    helper = assistants.get("survival")
    assert helper and "never give medicine doses" in helper["prompt"]
    assert len(helper["starters"]["en"]) == len(helper["starters"]["es"]) == 3
    docs = assistants.docs_text("survival")
    assert docs and "Offline survival" in docs[0]["text"]


def test_the_files_ship_with_the_program():
    toml = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    spec = (ROOT / "installer" / "datas.spec").read_text(encoding="utf-8")
    for name in ("catalog.json", "guides.en.md", "guides.es.md"):
        assert f'"datas/survival/{name}"' in toml
        assert f'"survival", "{name}"' in spec
    js = (ROOT / "datas" / "server" / "ui" / "i18n.js").read_text(encoding="utf-8")
    d = json.loads(re.search(r"const I18N = (\{.*\});", js, re.S).group(1))
    for lang in ("en", "es"):
        assert d[lang]["nav_survival"] and d[lang]["surv_keep_all"]


def test_every_part_datas_uses_is_credited_with_an_official_link():
    """One place (About, from datas/sources.json) names everything Datas is built on: every
    Python dependency, the phone apps' building blocks and the survival publishers."""
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+

    src = json.loads((ROOT / "datas" / "sources.json").read_text(encoding="utf-8"))
    groups = {g["id"] for g in src["groups"]}
    text = json.dumps(src).lower()
    for s in src["sources"]:
        assert s["group"] in groups, s["name"]
        assert s["url"].startswith("https://") and s["license"] and s["role"] and s["by"], s["name"]
        if "license_url" in s:
            assert s["license_url"].startswith("https://"), s["name"]
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    deps = list(py["dependencies"]) + [d for ds in py["optional-dependencies"].values() for d in ds]
    known = {  # package name -> how the credit names it
        "huggingface_hub": "hugging face hub", "gguf": "gguf-py", "uvicorn[standard]": "uvicorn",
        "py-cpuinfo": "py-cpuinfo", "pyserial": "pyserial", "paho-mqtt": "paho", "pyqt6": "pyqt6",
        "pyqt6-webengine": "qt webengine", "sounddevice": "sounddevice", "qtpy": "qtpy",
        "pytest-asyncio": "pytest-asyncio", "nvidia-ml-py": "nvidia-ml-py", "fpdf2": "fpdf2",
    }  # fmt: skip
    for d in deps:
        name = re.split(r"[<>=\[ ]", d)[0].lower()
        assert known.get(name, name) in text, (
            f"{name} is used but not credited in datas/sources.json"
        )
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    if "androidx" in gradle:
        assert "androidx" in text and "material components" in text
    for publisher in ("fema", "cdc", "hesperian", "gutenberg", "who / wedc"):
        assert publisher in text


def test_no_title_in_italics_is_split_across_two_lines():
    """The window's markdown does not join a *title* cut by a line break."""
    for lang in ("en", "es"):
        for line in survival.guides(lang).splitlines():
            bare = line.replace("**", "")
            assert bare.count("*") % 2 == 0, line
