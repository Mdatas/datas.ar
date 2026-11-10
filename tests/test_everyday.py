"""Everyday work: helpers, reading documents, saving answers as real files, the chat list."""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from datas import assistants, chat_engine, chats, docs
from datas import export as exporter
from datas.config import Config
from datas.server.app import app, core

client = TestClient(app)

SAMPLE = """# Bakery budget for March

A small plan for a **neighbourhood bakery**. All figures are examples.

## Costs

| Item | Units | Unit price | Total |
|---|---|---|---|
| Flour (kg) | 120 | 1.5 | =B2*C2 |
| Butter (kg) | 30 | 9 | =B3*C3 |
| Total | | | =SUM(D2:D3) |

## Next steps

- Ask two suppliers for quotes
- Decide the opening hours

Notes: mention that prices change monthly.

```python
print("hello")
```
"""


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ---- saving answers as files, and reading them back --------------------------------


@pytest.mark.parametrize("fmt", exporter.FORMATS)
def test_export_each_format_and_read_it_back(fmt):
    p = exporter.export(SAMPLE, fmt, "Bakery budget", "en")
    assert p.exists() and p.suffix == "." + fmt and p.stat().st_size > 200
    assert exporter.exports_dir() in p.parents
    text = docs.extract_text(p.name, p.read_bytes())
    assert "Flour" in text and "suppliers" in text or fmt == "xlsx" and "Flour" in text


def test_xlsx_keeps_formulas_and_numbers():
    from openpyxl import load_workbook

    p = exporter.export(SAMPLE, "xlsx", "Sheet test", "en")
    ws = load_workbook(p).worksheets[0]
    assert ws["A1"].value == "Item" and ws["B2"].value == 120 and ws["C2"].value == 1.5
    assert ws["D2"].value == "=B2*C2" and ws["D4"].value == "=SUM(D2:D3)"
    assert exporter.to_cell("1.234,50", "es")[0] == 1234.5
    assert exporter.to_cell("1,234.50", "en")[0] == 1234.5
    assert exporter.to_cell("15%", "en")[0] == 0.15


def test_pptx_one_slide_per_heading_with_notes():
    from pptx import Presentation

    p = exporter.export(SAMPLE, "pptx", "Deck test", "en")
    prs = Presentation(str(p))
    titles = [
        next(sh.text_frame.text for sh in s.shapes if sh.has_text_frame and sh.text_frame.text)
        for s in prs.slides
    ]
    assert titles[0] == "Bakery budget for March" and "Costs" in titles and "Next steps" in titles
    notes = " ".join(s.notes_slide.notes_text_frame.text for s in prs.slides if s.has_notes_slide)
    assert "prices change monthly" in notes


def test_export_api_and_open_only_own_files(tmp_path):
    r = client.post("/api/export", json={"markdown": SAMPLE, "format": "docx"})
    assert r.status_code == 200 and r.json()["name"].endswith(".docx")
    assert client.post("/api/export", json={"markdown": "x", "format": "exe"}).status_code == 400
    code = client.post(
        "/api/export/code", json={"code": "cube([10,10,10]);", "lang": "openscad", "title": "box"}
    ).json()
    assert code["name"] == "box.scad"
    # a file Datas did not make cannot be opened through the API
    other = tmp_path / "secret.txt"
    other.write_text("x")
    assert client.post("/api/open", json={"path": str(other)}).status_code == 400
    assert client.post("/api/open", json={"path": "/etc/passwd"}).status_code == 400


# ---- documents for the AI ---------------------------------------------------------


def test_extract_api_and_unreadable_files():
    p = exporter.export(SAMPLE, "docx", "Read me", "en")
    r = client.post(
        "/api/docs/extract", json={"name": p.name, "content_base64": b64(p.read_bytes())}
    ).json()
    assert "Flour" in r["text"] and r["chars"] > 100 and not r["truncated"]
    bad = client.post(
        "/api/docs/extract", json={"name": "photo.heic", "content_base64": b64(b"\x00\x01")}
    )
    assert bad.status_code == 400 and "detail" in bad.json()


def test_passages_are_picked_by_the_question_when_documents_are_long():
    filler = "\n\n".join(f"Paragraph {i} about the weather and the sea." for i in range(400))
    needle = "The guarantee for the oven lasts 24 months from the delivery date."
    long_doc = filler[:9000] + "\n\n" + needle + "\n\n" + filler[9000:]
    block = docs.context_block(
        "How long is the oven guarantee?", [{"name": "manual.txt", "text": long_doc}], 3000
    )
    assert needle in block and len(block) < 4200 and "part" in block
    whole = docs.context_block("anything", [{"name": "a.txt", "text": "short text"}], 3000)
    assert whole.endswith("short text")


def test_context_files_accept_office_documents():
    p = exporter.export(SAMPLE, "xlsx", "Prices", "en")
    r = client.post("/api/context", json={"name": p.name, "content_base64": b64(p.read_bytes())})
    assert r.status_code == 200 and r.json()["chars"] > 20
    assert any(d["name"] == p.name and "Flour" in d["text"] for d in chats.context_docs())
    assert client.delete(f"/api/context/{p.name}").json()["deleted"]
    assert not any(d["name"] == p.name for d in chats.context_docs())


# ---- helpers ------------------------------------------------------------------------


def test_helpers_catalog_is_complete_and_bilingual():
    cat = assistants.builtin()
    ids = [a["id"] for a in cat["assistants"]]
    assert len(ids) == len(set(ids)) >= 40
    cats = {c["id"] for c in cat["categories"]}
    for a in cat["assistants"]:
        assert a["cat"] in cats and len(a["prompt"]) > 120
        for lang in ("en", "es"):
            assert a["name"][lang] and a["blurb"][lang] and len(a["starters"][lang]) == 3
        assert set(a["export"]) <= set(exporter.FORMATS)
    es = client.get("/api/assistants?lang=es").json()
    names = {a["id"]: a["name"] for a in es["assistants"]}
    assert names["spreadsheet"] == "Planillas y finanzas"
    one = client.get("/api/assistants/slides").json()
    assert "## " in one["prompt"] and one["export"][0] == "pptx"


def test_own_helper_with_reference_documents():
    r = client.post(
        "/api/assistants",
        json={
            "name": "Shop replies",
            "prompt": "Answer customers of my shop politely, using the price list.",
            "starters": ["Reply to a question about delivery"],
        },
    ).json()
    aid = r["id"]
    assert r["custom"] and aid.startswith("my-shop-replies-")
    doc = client.post(
        f"/api/assistants/{aid}/docs",
        json={"name": "prices.txt", "content_base64": b64(b"Sourdough loaf: 4 pesos")},
    )
    assert doc.status_code == 200
    listing = client.get("/api/assistants").json()
    assert listing["categories"][0]["id"] == "mine"
    mine = next(a for a in listing["assistants"] if a["id"] == aid)
    assert mine["docs"][0]["name"] == "prices.txt"
    # the helper's instruction and its document reach the AI
    sp = chat_engine.system_prompt(Config(), aid, False, "en", question="price of a loaf?")
    assert "using the price list" in sp and "Sourdough loaf: 4 pesos" in sp
    assert client.delete(f"/api/assistants/{aid}").json()["deleted"]
    assert not assistants.get(aid)
    assert client.post("/api/assistants", json={"name": "", "prompt": ""}).status_code == 400


# ---- what the AI is sent ---------------------------------------------------------------


def test_long_chats_are_trimmed_from_the_oldest_message():
    msgs = []
    for i in range(60):
        msgs.append({"role": "user", "content": f"question {i} " + "x" * 400})
        msgs.append({"role": "assistant", "content": f"answer {i} " + "y" * 400})
    msgs.append({"role": "user", "content": "the last question"})
    req = chat_engine.ChatRequest(messages=msgs, ctx_tokens=2048)
    out = chat_engine.build_messages(Config(), req)
    assert out[0]["role"] == "system" and out[1]["role"] == "user"
    assert out[-1]["content"] == "the last question"
    total = sum(len(chat_engine.text_of(m["content"])) for m in out)
    assert total < 2048 * 0.75 * chat_engine.CHARS_PER_TOKEN + 600 and len(out) < len(msgs)


def test_attachments_and_pictures_pass_through():
    req = chat_engine.ChatRequest(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What does the contract say about rent?"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                ],
            }
        ],
        attachments=[{"name": "contract.txt", "text": "The rent is 500 per month."}],
    )
    out = chat_engine.build_messages(Config(), req)
    assert "contract.txt" in out[0]["content"] and "500 per month" in out[0]["content"]
    assert out[1]["content"][1]["type"] == "image_url"


# ---- the chat list -------------------------------------------------------------------


def test_chat_list_search_rename_delete():
    core.cfg.memory_mode = "remember"
    a = client.post(
        "/api/chats",
        json={
            "messages": [
                {"role": "user", "content": "Plan a trip to Bariloche"},
                {"role": "assistant", "content": "Day one: the lake and the chocolate shops."},
            ],
            "model": "qwen3-4b",
            "skill": "plan",
            "attachments": [{"name": "tickets.txt", "text": "Flight at 9"}],
        },
    ).json()["chat_id"]
    b = client.post(
        "/api/chats",
        json={"messages": [{"role": "user", "content": "Write an invoice template"}]},
    ).json()["chat_id"]
    all_ = client.get("/api/chats").json()["chats"]
    assert {a, b} <= {c["id"] for c in all_}
    first = next(c for c in all_ if c["id"] == a)
    assert first["title"].startswith("Plan a trip") and first["skill"] == "plan"
    assert first["model_name"] == "Qwen3 4B"
    hits = client.get("/api/chats", params={"q": "chocolate lake"}).json()["chats"]
    assert [c["id"] for c in hits] == [a] and "chocolate" in hits[0]["snippet"]
    assert client.get("/api/chats", params={"q": "zzzz"}).json()["chats"] == []
    assert client.patch(f"/api/chats/{a}", json={"title": "Patagonia"}).status_code == 200
    # a renamed chat keeps its title when saved again
    client.post(
        "/api/chats",
        json={"chat_id": a, "messages": [{"role": "user", "content": "Something else"}]},
    )
    d = client.get(f"/api/chats/{a}").json()
    assert d["title"] == "Patagonia" and d["attachments"][0]["name"] == "tickets.txt"
    assert client.delete(f"/api/chats/{b}").json()["deleted"]
    assert b in chats.tombstones()
    assert client.get(f"/api/chats/{b}").status_code == 404


def test_settings_file_survives_damage(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    c = Config()
    c.lang = "es"
    c.save()
    c.theme = "night"
    c.save()  # the first save is now the .bak copy
    (tmp_path / "config.json").write_text("{ this is not json")
    again = Config.load()
    assert again.lang == "es"  # restored from the last good copy
    assert (tmp_path / "config.json.damaged").exists()
    (tmp_path / "config.json.bak").unlink()
    (tmp_path / "config.json").write_text("[]")
    assert Config.load().lang == "en"  # nothing to restore: a fresh start, not a crash
    assert json.loads((tmp_path / "config.json.damaged").read_text()) == []
