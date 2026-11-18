"""One chat, one conversation: with "hands" on, the same /api/chat runs the agent and streams
its steps, its final answer as an ordinary answer, and what the tools really did."""

import json

from fastapi.testclient import TestClient


def _events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_hands_run_the_agent_in_the_same_conversation(monkeypatch):
    import datas.agents as agents
    from datas.server import app as server

    seen = {}

    def fake_agent(task, cfg):  # noqa: ANN001
        seen["task"], seen["cfg"] = task, cfg
        yield {"type": "tool_call", "step": 0, "name": "list_dir", "arguments": "{}"}
        yield {"type": "tool_result", "step": 0, "name": "list_dir", "result": "a.txt"}
        yield {
            "type": "final",
            "step": 1,
            "content": "There is one file.",
            "events": [],
            "really": [{"name": "list_dir", "ok": True, "said": "a.txt"}],
        }

    monkeypatch.setattr(agents, "run_agent", fake_agent)
    monkeypatch.setattr(server.core.server, "running", lambda: True)
    c = TestClient(server.app, base_url="http://127.0.0.1")
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "what is in my folder?"},
    ]
    r = c.post("/api/chat", json={"messages": msgs, "hands": {"files": True, "ask": "none"}})
    ev = _events(r.text)
    kinds = [e["type"] for e in ev]
    assert kinds == ["step", "step", "token", "really", "done"]
    assert [e.get("kind") for e in ev[:2]] == ["tool_call", "tool_result"]
    assert ev[2]["text"] == "There is one file." and ev[3]["really"][0]["ok"]
    cfg = seen["cfg"]
    assert seen["task"] == "what is in my folder?"
    roles = [m["role"] for m in cfg.conversation]
    assert roles[0] == "system" and roles[1:] == ["user", "assistant", "user"]  # the whole chat
    assert cfg.confirm is None and not cfg.allow_shell and not cfg.allow_browser


def test_plain_chat_stays_plain_and_risky_hands_are_refused_from_a_phone(monkeypatch):
    import datas.agents as agents
    from datas.server import app as server

    monkeypatch.setattr(agents, "run_agent", lambda *a: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(server.core.server, "running", lambda: True)
    monkeypatch.setattr(server, "remote_peer", lambda request: "phone-1")
    c = TestClient(server.app, base_url="http://127.0.0.1")
    r = c.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "x"}], "hands": {"shell": True}}
    )
    assert r.status_code == 403


def test_the_runner_keeps_the_chat_as_its_conversation(tmp_path):
    import httpx

    from datas.agents import runner

    sent = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "Done."}}]})

    real = httpx.Client
    import pytest

    mp = pytest.MonkeyPatch()
    mp.setattr(runner.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(answer)))
    try:
        cfg = runner.AgentConfig(
            base_url="http://127.0.0.1:1/v1",
            workspace=tmp_path / "ws",
            use_programs=False,
            conversation=[
                {"role": "system", "content": "NOTES: likes short answers"},
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "ok"},
                {"role": "user", "content": "now this"},
            ],
        )
        list(runner.run_agent("now this", cfg))
    finally:
        mp.undo()
    m = sent[0]["messages"]
    assert m[0]["role"] == "system" and "NOTES: likes short answers" in m[0]["content"]
    assert [x["content"] for x in m[1:]] == ["earlier", "ok", "now this"]
