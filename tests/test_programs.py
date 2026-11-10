"""Open programs and the agent: documents, conversions, running a program, tools inside
programs that speak the Model Context Protocol (MCP)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datas import mcp, programs
from datas.agents import tools as T

FAKE = str(Path(__file__).with_name("fake_mcp_server.py"))


def test_conversion_routes():
    assert programs.routes("md", "docx") == ["datas", "pandoc"]
    assert programs.routes("docx", "pdf") == ["libreoffice"]
    assert programs.routes(".XLSX", "ods") == ["libreoffice"]
    assert programs.routes("docx", "xlsx") == []  # a letter does not become a spreadsheet
    assert programs.routes("svg", "png") == ["inkscape", "imagemagick"]
    assert programs.routes("scad", "stl") == ["openscad"]
    assert programs.routes("mp4", "mp3") == ["ffmpeg"]
    assert programs.routes("pdf", "txt") == ["datas"]


def test_built_in_conversions_and_a_clear_message_when_a_program_is_missing(tmp_path, monkeypatch):
    src = tmp_path / "plan.md"
    src.write_text("# Plan\n\n| Item | Cost |\n|---|---|\n| Paint | 20 |\n", encoding="utf-8")
    docx = programs.convert(src, "docx")
    assert docx.name == "plan.docx" and docx.stat().st_size > 2000
    assert programs.convert(src, "docx").name == "plan (2).docx"  # never overwrites
    txt = programs.convert(docx, "txt")
    assert "Paint" in txt.read_text(encoding="utf-8")
    xlsx = programs.convert(src, "xlsx")
    assert xlsx.exists()
    monkeypatch.setattr(programs, "find", lambda pid: None)
    with pytest.raises(RuntimeError, match="LibreOffice"):
        programs.convert(docx, "pdf")
    with pytest.raises(RuntimeError, match="does not know"):
        programs.convert(docx, "mp3")


def test_every_known_program_has_a_site_and_a_plain_description():
    listing = programs.listing("es")
    ids = [p["id"] for p in listing["programs"]]
    assert len(ids) == len(set(ids))
    assert {
        "libreoffice",
        "inkscape",
        "blender",
        "freecad",
        "openscad",
        "ffmpeg",
        "pdfcraft",
    } <= set(ids)
    for p in listing["programs"]:
        assert p["does"] and (p["site"].startswith("https://") or p["group"] == "yours")
    assert listing["artcraft"]["launcher"].startswith("https://github.com/storytold/")


def test_agent_documents_and_programs(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path / "home"))
    ws = tmp_path / "ws"
    ws.mkdir()
    ctx = T.ToolContext(workspace=ws)
    out = T.call(ctx, "save_document", {"path": "quote.docx", "content": "# Quote\n\nTotal: 150"})
    assert out.startswith("saved") and (ws / "quote.docx").exists()
    assert "Total: 150" in T.call(ctx, "read_file", {"path": "quote.docx"})
    assert T.call(ctx, "save_document", {"path": "quote.docx", "content": "x"}).startswith(
        "refused"
    )
    assert T.call(ctx, "save_document", {"path": "quote.exe", "content": "x"}).startswith("refused")
    assert T.call(ctx, "save_document", {"path": "../out.docx", "content": "x"}).startswith(
        "DENIED"
    )
    assert T.call(ctx, "convert_file", {"source": "quote.docx", "to": "txt"}).startswith(
        "converted"
    )
    assert (ws / "quote.txt").exists()
    # a program the user added by hand can be listed and run — and nothing else can
    (tmp_path / "home").mkdir(exist_ok=True)
    (tmp_path / "home" / "programs.json").write_text(
        json.dumps([{"id": "py", "name": "Python", "path": sys.executable, "does": "runs scripts"}])
    )
    assert "- py: Python" in T.call(ctx, "list_programs", {})
    r = T.call(ctx, "run_program", {"program": "py", "arguments": ["-c", "print(6*7)"]})
    assert r.startswith("exit 0") and "42" in r
    assert "not found" in T.call(ctx, "run_program", {"program": "format-my-disk"})
    # running a program always asks first when the user wants to approve risky actions
    asked = []
    ctx2 = T.ToolContext(workspace=ws, ask="risky", confirm=lambda t: asked.append(t) or False)
    assert T.call(ctx2, "run_program", {"program": "py", "arguments": ["-V"]}) == "DENIED by user."
    assert asked and asked[0].startswith("run_program(")


def test_mcp_client_handshake_tools_and_calls(tmp_path):
    srv = mcp.McpServer("fake", sys.executable, [FAKE, "--root", str(tmp_path)])
    try:
        srv.start(timeout=20)
        assert srv.info["serverInfo"]["name"] == "fake"
        assert [t["name"] for t in srv.tools] == ["add", "note.save", "fail"]  # both pages
        assert srv.call("add", {"a": 2, "b": 40}) == "42"
        assert srv.call("note.save", {"name": "n.txt", "text": "hola"}) == "saved n.txt"
        assert (tmp_path / "n.txt").read_text() == "hola"
        assert srv.call("fail", {}).startswith("ERROR:")
        with pytest.raises(mcp.McpError, match="unknown method"):
            srv.request("resources/list")
    finally:
        srv.stop()
    assert not srv.alive()
    gone = mcp.McpServer("gone", str(tmp_path / "no-such-program"), [])
    with pytest.raises(mcp.McpError, match="could not start"):
        gone.start()


def test_programs_with_their_own_tools_reach_the_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    work = tmp_path / "work"
    work.mkdir()
    mcp.save_user_server("fake", sys.executable, [FAKE, "--root", "{root}"])
    mcp.save_user_server("broken", str(tmp_path / "nope"), [])
    session = mcp.Session(work)
    try:
        session.start_all()
        assert "broken" in session.errors and "fake" in session.servers
        ctx = T.ToolContext(workspace=work, mcp=session)
        names = {s["function"]["name"] for s in T.schemas(ctx)}
        assert {"fake__add", "fake__note_save", "read_file"} <= names  # safe names for chat APIs
        assert T.call(ctx, "fake__add", {"a": 1, "b": 2}) == "3"
        assert T.call(ctx, "fake__note_save", {"name": "a.txt", "text": "x"}) == "saved a.txt"
        assert (work / "a.txt").exists()  # {root} was the agent's folder
        # tools inside other programs always count as risky
        asked = []
        ctx.ask, ctx.confirm = "risky", lambda t: asked.append(t) or False
        assert T.call(ctx, "fake__add", {"a": 1, "b": 2}) == "DENIED by user."
        assert asked == ["fake__add(a=1, b=2)"]
    finally:
        session.stop()
    assert mcp.remove_user_server("broken") and "broken" not in mcp.user_servers()


def test_programs_api():
    from datas.server.app import app

    c = TestClient(app)
    j = c.get("/api/programs?lang=en").json()
    assert any(p["id"] == "libreoffice" for p in j["programs"])
    r = c.post("/api/mcp", json={"name": "fake test", "command": sys.executable, "args": [FAKE]})
    assert r.status_code == 200 and r.json()["name"] == "faketest"
    t = c.post("/api/mcp/faketest/test").json()
    assert t["ok"] and [x["name"] for x in t["tools"]] == ["add", "note.save", "fail"]
    assert c.delete("/api/mcp/faketest").json()["removed"]
    assert c.post("/api/mcp/faketest/test").status_code == 404
    assert c.post("/api/programs/libreoffice-nope/open", json={}).status_code == 400
