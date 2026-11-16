"""The agent's own terminal (a real shell that remembers its folder) and its own browser."""

import http.server
import os
import platform
import threading
from functools import partial

import pytest

from datas.agents import tools as T
from datas.agents.browser import Browser, find_browser


def test_terminal_is_a_real_shell_that_remembers_cd(tmp_path):
    ctx = T.ToolContext(workspace=tmp_path, allow_shell=True)
    if platform.system() == "Windows":
        out = T.run_command(ctx, "mkdir sub; cd sub; 'hi' | Out-File a.txt; (Get-ChildItem).Count")
    else:
        out = T.run_command(ctx, "mkdir sub && cd sub && echo hi > a.txt && ls | wc -l")
    assert out.startswith("exit 0") and "1" in out
    assert ctx.shell_cwd == tmp_path / "sub"
    again = T.run_command(
        ctx, "Get-Content a.txt" if platform.system() == "Windows" else "cat a.txt"
    )
    assert "hi" in again
    failed = T.run_command(ctx, "exit 3")
    assert failed.startswith("exit 3")


def test_terminal_off_unless_allowed(tmp_path):
    assert T.run_command(T.ToolContext(workspace=tmp_path), "echo x").startswith("DENIED")


def test_browser_tools_need_their_switch_and_internet(tmp_path):
    names = lambda c: {s["function"]["name"] for s in T.schemas(c)}  # noqa: E731
    assert "browser_open" not in names(
        T.ToolContext(workspace=tmp_path, allow_network=True, allow_browser=False)
    )
    assert "browser_open" not in names(
        T.ToolContext(workspace=tmp_path, allow_browser=True, allow_network=False)
    )
    both = T.ToolContext(workspace=tmp_path, allow_browser=True, allow_network=True)
    assert {"browser_open", "browser_click", "browser_type"} <= names(both)
    assert both.is_risky("browser_click", {}) and not both.is_risky("browser_read", {})


PAGE = """<html><head><title>Test form</title></head><body><h1>Hello agent</h1>
<a href="second.html">Next page</a><form action="second.html"><input name="q" placeholder="Search">
<input type="password" name="pw"><button>Go</button></form>
<script>document.body.insertAdjacentHTML('beforeend','<p>Made by JavaScript</p>')</script></body></html>"""


@pytest.mark.skipif(find_browser() is None, reason="no Chromium-family browser here")
def test_browser_reads_types_submits_and_refuses_passwords(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAS_HOME", str(tmp_path / "home"))
    site = tmp_path / "site"
    site.mkdir()
    (site / "page.html").write_text(PAGE)
    (site / "second.html").write_text("<title>Second</title>You arrived.")
    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    )
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    b = Browser(allow_local=True)
    try:
        try:
            page = b.open(f"{base}/page.html")
        except RuntimeError as e:
            # GitHub's Ubuntu 24.04 machines do not let Chrome start its sandbox; the browser is
            # never started without it, so there is nothing to test there
            if os.environ.get("CI") and platform.system() == "Linux" and "debugging port" in str(e):
                pytest.skip(f"this machine does not start Chrome: {e}")
            raise
        assert "Made by JavaScript" in page and "[1] link: Next page" in page
        assert b.type_text(3, "secret").startswith("REFUSED: that is a password field")
        assert "not a field" in b.type_text(1, "x")
        assert "You arrived" in b.type_text(2, "hello", submit=True)
        assert "Hello agent" in b.back()
        assert "You arrived" in b.click(1)
    finally:
        b.close()
        srv.shutdown()


def test_browser_refuses_addresses_inside_the_network():
    from datas import netguard

    with pytest.raises(netguard.Blocked):
        Browser().open("http://192.168.1.1/")
