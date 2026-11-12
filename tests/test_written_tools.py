"""When the engine cannot write an AI's own tool format (Gemma 4 on llama.cpp: "map:
filter-mapping not implemented"), the agent describes its tools in plain text and goes on."""

import json

import httpx

from datas.agents import runner


def test_reading_tool_calls_written_as_text():
    calls, text = runner.read_written_calls(
        'Let me look.\n<tool_call>{"name": "list_dir", "arguments": {"path": "."}}</tool_call>'
    )
    assert calls[0]["function"]["name"] == "list_dir"
    assert json.loads(calls[0]["function"]["arguments"]) == {"path": "."}
    assert text == "Let me look."
    calls, text = runner.read_written_calls(
        '```json\n{"name": "pc_settings", "arguments": {}}\n```'
    )
    assert calls and text == ""
    assert runner.read_written_calls("Done, all good.") == ([], "Done, all good.")


def test_agent_switches_to_written_tools_and_finishes(tmp_path, monkeypatch):
    seen = []

    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if "tools" in body:
            return httpx.Response(
                500,
                json={"error": {"message": "NotImplemented: map: filter-mapping not implemented"}},
            )
        said = body["messages"][-1]["content"]
        if "Result of list_dir" in str(said):
            content = "The folder is empty."
        else:
            content = '<tool_call>{"name": "list_dir", "arguments": {"path": "."}}</tool_call>'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    real = httpx.Client
    monkeypatch.setattr(
        runner.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(answer))
    )
    cfg = runner.AgentConfig(
        base_url="http://127.0.0.1:1/v1", workspace=tmp_path / "ws", use_programs=False
    )
    events = list(runner.run_agent("what is in my folder?", cfg))
    kinds = [e["type"] for e in events]
    assert "tool_call" in kinds and kinds[-1] == "final"
    assert events[-1]["content"] == "The folder is empty."
    system = seen[1]["messages"][0]["content"]
    assert "<tool_call>" in system and "list_dir" in system
    assert all(m["role"] in ("system", "user", "assistant") for m in seen[-1]["messages"])
