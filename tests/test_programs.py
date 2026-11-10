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


def test_found_programs_are_not_a_side_door_for_running_code():
    code = programs.runs_code
    assert code("blender", ["-b", "scene.blend", "--python", "x"]) == "--python"
    assert code("blender", ["-b", "scene.blend", "-P", "do.py"]) == "-P"
    assert code("blender", ["-Pdo"]) == "-Pdo"  # the value written right after the letter
    assert code("blender", ["--python-expr=import os"]) == "--python-expr=import os"
    assert code("libreoffice", ["--headless", "macro:///Standard.M.Main"])
    assert code("libreoffice", ["-env:UserInstallation=file:///tmp/other-profile"])
    assert code("pandoc", ["in.md", "-o", "out.pdf", "--lua-filter", "f.lua"])
    assert code("pandoc", ["in.md", "--lua-f=f"]) == "--lua-f=f"  # a long option cut short
    assert code("pandoc", ["in.md", "-Fmyfilter"]) == "-Fmyfilter"
    assert code("pandoc", ["in.md", "-o", "o.pdf", "--pdf-engine-opt=-shell-escape"])
    assert code("gimp", ["-i", "-b", "(gimp-quit 0)"]) == "-b"
    assert code("gimp", ["-ib", "(gimp-quit 0)"]) == "-ib"  # letters grouped
    assert code("imagemagick", ["msl:evil.msl"])
    assert code("imagemagick", ["@arguments.txt"])
    assert code("freecad", ["--response-file", "a.txt"])
    assert code("ffmpeg", ["x.sh"])
    for ok in (
        ("libreoffice", ["--headless", "--convert-to", "pdf", "letter.docx"]),
        ("ffmpeg", ["-i", "talk.mp4", "-vn", "-b:a", "128k", "talk.mp3"]),
        ("inkscape", ["logo.svg", "--export-type=png", "--export-filename=logo.png"]),
        ("pandoc", ["notes.md", "-f", "markdown", "--to=docx", "--file-scope", "-o", "n.docx"]),
        ("blender", ["-b", "scene.blend", "-o", "//frame_", "-F", "PNG", "-f", "1"]),
        ("blender", ["-b", "s.blend", "-p", "0", "0", "800", "600", "-noaudio", "-Y"]),
        ("gimp", ["-i", "-d", "-f", "photo.xcf"]),
        ("tesseract", ["scan.png", "scan", "-l", "eng+spa"]),
    ):
        assert code(*ok) is None, ok


def test_found_programs_keep_to_the_internet_switch_and_the_allowed_folders(tmp_path):
    net = programs.network_addresses
    assert net(["-i", "http://example.org/a.mp4", "out.mp3"]) == ["http://example.org/a.mp4"]
    assert net(["--output=rtmp://10.0.0.5/live"]) == ["rtmp://10.0.0.5/live"]
    assert net(["file://server/share/x.docx"]) == ["file://server/share/x.docx"]  # a shared folder
    assert net(["file:///tmp/a.png", "//frame_", "scale=640:480", "C://x", "-ss", "00:01:00"]) == []

    ws, other = tmp_path / "ws", tmp_path / "other"
    ws.mkdir()
    other.mkdir()
    (other / "private.txt").write_text("x")
    out = programs.outside_paths
    assert out("pandoc", [str(other / "private.txt"), "-o", "copy.txt"], [ws], ws)
    assert out("pandoc", ["../other/private.txt", "-o", "copy.txt"], [ws], ws)
    assert out("pandoc", ["notes.md", f"--output={other / 'new.docx'}"], [ws], ws)  # writing there
    assert out("libreoffice", ["--convert-to", "pdf", "--outdir", str(other), "a.docx"], [ws], ws)
    assert out("ffmpeg", ["-i", "~"], [ws], ws)
    # the same file is fine once the user gave the agent that folder
    assert out("pandoc", [str(other / "private.txt"), "-o", "copy.txt"], [ws, other], ws) == []
    for ok in (
        ("ffmpeg", ["-i", "talk.mp4", "-vf", "scale=iw/2:ih/2", "-r", "30000/1001", "out.mp4"]),
        ("ffmpeg", ["-i", "talk.mp4", "-f", "null", "/dev/null"]),
        ("ffmpeg", ["-i", "talk.mp4", "-map", "0:a", "-f", "wav", "-"]),
        ("blender", ["-b", "scene.blend", "-o", "//frame_", "-f", "1"]),
        ("pandoc", ["notes.md", "-V", "geometry:margin=1in", "-o", str(ws / "sub" / "n.pdf")]),
    ):
        assert out(*ok, [ws], ws) == [], ok


def test_running_a_found_program_is_checked_and_a_user_program_is_not(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path / "home"))
    ws, other = tmp_path / "ws", tmp_path / "other"
    ws.mkdir()
    other.mkdir()
    (other / "private.txt").write_text("x")
    # stand-in: "pandoc" is found on this computer (the real one is not needed for the checks)
    monkeypatch.setattr(programs, "find", lambda pid: sys.executable if pid == "pandoc" else None)
    show = ["-c", "import sys; print('ran', len(sys.argv))"]
    run = lambda ctx, args: T.run_program(ctx, "pandoc", args)  # noqa: E731

    off = T.ToolContext(workspace=ws, allow_network=False)
    assert run(off, show).startswith("exit 0")
    assert "can make pandoc run code" in run(off, [*show, "--lua-filter", "f"])
    assert "internet is off" in run(off, [*show, "https://example.org/page.html"])
    assert "outside the folders" in run(off, [*show, str(other / "private.txt")])

    on = T.ToolContext(workspace=ws, allow_network=True)
    assert "inside your own network" in run(on, [*show, "http://192.168.1.1/setup"])
    assert "inside your own network" in run(on, [*show, "rtmp://127.0.0.1/live"])
    home_net = T.ToolContext(workspace=ws, allow_network=True, allow_local=True)
    assert run(home_net, [*show, "http://192.168.1.1/setup"]).startswith("exit 0")

    # the user gave the agent that folder: allowed
    granted = T.ToolContext(workspace=ws, roots=[other])
    assert run(granted, [*show, str(other / "private.txt")]).startswith("exit 0")
    # "may run commands" is on: the user already allowed anything
    free = T.ToolContext(workspace=ws, allow_shell=True, allow_network=False)
    r = run(free, [*show, "x.sh", str(other / "private.txt"), "https://example.org/"])
    assert r.startswith("exit 0") and "ran 4" in r
