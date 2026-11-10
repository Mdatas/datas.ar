"""Everyday tools: recording → text, text → audio pieces, documents longer than the AI's memory."""

from __future__ import annotations

import io
import wave
from pathlib import Path

import pytest

from datas import tools
from datas.config import Config
from datas.orchestrator import Datas


def test_subtitles_and_sentence_pieces():
    s = tools.srt([(0, 1.5, "Hola"), (3661.25, 3662, "Chau")])
    assert "1\n00:00:00,000 --> 00:00:01,500\nHola" in s
    assert "2\n01:01:01,250 --> 01:01:02,000\nChau" in s
    pieces = tools._sentences("Primera oración. Segunda, más larga. " * 30)
    assert all(len(p) <= 380 for p in pieces) and len(pieces) == 3
    assert "".join(pieces).replace(" ", "") == (
        "Primera oración. Segunda, más larga. " * 30
    ).replace(" ", "")
    one = tools._sentences("palabra " * 200)  # no sentence end at all: still cut
    assert all(len(p) <= 380 for p in one) and len(one) >= 4


def _wav(seconds: float = 1.0, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x10" * int(rate * seconds))
    return buf.getvalue()


def test_recording_becomes_text_and_subtitles(tmp_path, monkeypatch):
    pytest.importorskip("numpy")
    from datas.engines import voice

    monkeypatch.setenv("DATAS_HOME", str(tmp_path))
    core = Datas(Config())
    core.cfg.memory_mode = "remember"
    monkeypatch.setattr(
        voice,
        "installed",
        lambda cfg=None, spec=None: {
            "stt_models": ["tiny"],
            "tts": False,
            "ready": False,
            "stt_model": "tiny",
        },
    )
    heard = {}

    def fake(pcm, language, model, threads=4):  # noqa: ANN001
        heard.update(samples=len(pcm), language=language, model=model)
        return [
            (0.0, 1.0, "Buenos días."),
            (1.2, 2.0, "Empezamos la reunión."),
            (6.0, 7.0, "Segundo tema."),
        ]

    monkeypatch.setattr(voice, "transcribe_segments", fake)
    rec = tmp_path / "Reunión lunes.wav"
    rec.write_bytes(_wav(2.0))
    r = tools.transcribe_file(core, rec, rec.name, "es")
    assert heard == {"samples": 32000, "language": "es", "model": "tiny"}  # resampled to 16 kHz
    assert r["text"] == "Buenos días. Empezamos la reunión. Segundo tema." and r["segments"] == 3
    # a pause of more than two seconds starts a new paragraph
    assert "Empezamos la reunión.\n\nSegundo tema." in r["markdown"]
    assert Path(r["path"]).read_text(encoding="utf-8").startswith("Reunión lunes")
    assert "00:00:06,000 --> 00:00:07,000" in Path(r["srt"]).read_text(encoding="utf-8")
    # Forget mode: the text comes back, nothing is written
    core.cfg.memory_mode = "forget"
    r2 = tools.transcribe_file(core, rec, rec.name, None)
    assert r2["text"] and "path" not in r2 and heard["language"] is None
    monkeypatch.setattr(
        voice,
        "installed",
        lambda cfg=None, spec=None: {"stt_models": [], "tts": False, "ready": False},
    )
    with pytest.raises(RuntimeError, match="hearing model"):
        tools.transcribe_file(core, rec, rec.name, None)


def test_long_documents_are_worked_piece_by_piece(monkeypatch):
    core = Datas(Config())
    asked = []

    def fake_ask(core_, prompt, max_tokens=None):  # noqa: ANN001
        asked.append(prompt)
        if prompt.startswith("These are notes"):
            return "Main point.\n- a\n- b"
        if prompt.startswith("Summarize"):
            return f"- note {len(asked)}"
        return "TRADUCIDO"

    monkeypatch.setattr(tools, "_ask", fake_ask)
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(40))  # ~26k characters
    r = tools.long_document(core, text, "summary", "es", ctx_tokens=2048, title="Report")
    assert r["parts"] > 3 and r["markdown"].startswith("# Report\n\nMain point.")
    assert len(asked) == r["parts"] + 1 and "Spanish" in asked[0]
    assert all(len(a) < 2048 * 3 for a in asked[:-1])  # every piece fits the AI's memory
    asked.clear()
    r = tools.long_document(core, text, "translate", "en", ctx_tokens=2048)
    assert r["markdown"].count("TRADUCIDO") == r["parts"] == len(asked)
    short = tools.long_document(core, "One short paragraph.", "summary", "en", ctx_tokens=8192)
    assert short["parts"] == 1 and short["markdown"].startswith("- note")
    with pytest.raises(RuntimeError):
        tools.long_document(core, "   ", "summary", "en", 8192)
    with pytest.raises(ValueError):
        tools.long_document(core, "x", "poem", "en", 8192)


def test_tools_api_refuses_what_it_cannot_use():
    from fastapi.testclient import TestClient

    from datas.server.app import app

    c = TestClient(app)
    assert c.post("/api/tools/transcribe?name=notes.txt", content=b"x").status_code == 400
    assert c.post("/api/tools/transcribe?name=a.mp3", content=b"").status_code == 400
    assert c.post("/api/tools/long", json={"mode": "summary", "text": ""}).status_code == 400
    assert c.post("/api/tools/long", json={"mode": "poem", "text": "x"}).status_code == 400


def test_a_long_document_is_shared_out_between_this_device_and_linked_ones(monkeypatch):
    """Many hands: each device takes the next part as soon as it is free. The result is the
    same text, in the same order, as when one device does it all — also when a helper
    drops out half way."""
    import hashlib
    import threading
    import time

    core = Datas(Config())
    who, lock = [], threading.Lock()

    def fake_ask(core_, prompt, max_tokens=None, provider=None):  # noqa: ANN001
        hand = provider or "here"
        if prompt.startswith("These are notes"):
            assert provider is None  # the final summary is written by this device
            return "Main point."
        with lock:
            if hand == "pi" and any(h == "pi" for h, _ in who):
                raise RuntimeError("unplugged")  # the Pi answers one part, then is gone
            who.append((hand, prompt))
        time.sleep(0.01)
        return hashlib.sha256(prompt.encode()).hexdigest()[:10]

    monkeypatch.setattr(tools, "_ask", fake_ask)
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(40))
    alone = tools.long_document(core, text, "translate", "en", ctx_tokens=1024)
    assert alone["helped"] == [] and alone["dropped"] == [] and alone["parts"] > 8
    assert alone["shares"] == {}
    who.clear()

    said = []

    class Job:
        phase = ""

        def progress(self, done, total):  # noqa: ANN001
            assert 0 < done <= total

        def say(self, line):  # noqa: ANN001
            said.append(line)

    hands = [
        {"name": "Desk", "provider": "desk", "context": 4096},
        {"name": "Pi", "provider": "pi", "context": 1024},
    ]
    # this device has room for 8192, the Pi for 1024: the parts are cut for the smallest
    shared = tools.long_document(core, text, "translate", "en", 8192, job=Job(), hands=hands)
    assert shared["parts"] == alone["parts"] and shared["markdown"] == alone["markdown"]
    assert shared["helped"] == ["Desk"] and shared["dropped"] == ["Pi"]
    took = {hand: sum(1 for h, _ in who if h == hand) for hand in ("here", "desk", "pi")}
    assert took["pi"] == 1 and took["here"] >= 1 and took["desk"] >= 1, took
    assert sum(took.values()) == shared["parts"]  # nothing twice, nothing lost
    assert shared["shares"] == {"this device": took["here"], "Desk": took["desk"], "Pi": 1}
    assert any("Pi stopped answering" in line for line in said)
    assert any("shared between this device and Desk, Pi" in line for line in said)

    # a summary: the parts are shared, the final text is this device's
    who.clear()
    r = tools.long_document(core, text, "summary", "en", 8192, title="Report", hands=hands[:1])
    assert r["markdown"] == "# Report\n\nMain point." and r["helped"] == ["Desk"]
    # one part only: nothing to share
    one = tools.long_document(core, "One short paragraph.", "translate", "en", 8192, hands=hands)
    assert one["parts"] == 1 and one["helped"] == []

    # if this device's own AI fails, the job fails as it would alone
    def broken(core_, prompt, max_tokens=None, provider=None):  # noqa: ANN001
        if provider is None:
            raise RuntimeError("No AI is running. Start one in My AIs first.")
        time.sleep(0.01)
        return "x"

    monkeypatch.setattr(tools, "_ask", broken)
    with pytest.raises(RuntimeError, match="No AI is running"):
        tools.long_document(core, text, "translate", "en", 8192, hands=hands[:1])


def test_only_linked_devices_with_an_ai_of_their_own_are_asked_to_help():
    core = Datas(Config())
    assert tools.helpers(core) == []  # nothing linked

    class Link:
        peers = {
            "a" * 64: {"name": "Desk", "online": True, "in_use": False,
                       "ai": {"available": True, "name": "Qwen3 8B", "context": 4096}},
            "b" * 64: {"name": "Asleep", "online": False, "in_use": False,
                       "ai": {"available": True}},
            "c" * 64: {"name": "No AI there", "online": True, "in_use": False, "ai": {}},
            "d" * 64: {"name": "Already the AI in use", "online": True, "in_use": True,
                       "ai": {"available": True}},
        }  # fmt: skip

        def _computers(self):
            return list(self.peers)

        def peer_public(self, pid):
            return self.peers[pid]

    core.link = Link()
    (h,) = tools.helpers(core)
    assert h["name"] == "Desk" and h["ai"] == "Qwen3 8B" and h["context"] == 4096
    assert h["provider"].kind == "linked" and h["provider"].base_url.endswith(
        f"/link/{'a' * 64}/v1"
    )

    from fastapi.testclient import TestClient

    from datas.server import app as server

    old = server.core.link
    server.core.link = Link()
    try:
        r = TestClient(server.app, base_url="http://127.0.0.1").get("/api/tools/long/helpers")
        assert r.json() == {"devices": [{"name": "Desk", "ai": "Qwen3 8B"}]}
    finally:
        server.core.link = old


def test_the_ai_of_a_linked_device_is_read_as_it_writes(monkeypatch):
    """A long answer sent in one piece is silent for minutes, and the link takes silence for
    a device that stopped answering — so a helper's answer is taken as it is written."""
    import json

    import httpx

    from datas.providers import linked_provider

    core = Datas(Config())
    asked = []

    def device(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        asked.append((str(request.url), body))
        if "fail" in body["messages"][0]["content"]:
            return httpx.Response(502, json={"error": {"message": "no AI is running there"}})
        words = ["- one", " point", "\n- another", ""]
        lines = ["data: " + json.dumps({"choices": [{"delta": {"content": w}}]}) for w in words] + [
            ": keep-alive",
            "data: not json",
            "data: [DONE]",
            "data: ignored after the end",
        ]
        return httpx.Response(200, text="\n\n".join(lines) + "\n\n")

    real = httpx.Client
    monkeypatch.setattr(
        tools.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(device), **kw)
    )
    prov = linked_provider(core.cfg, "ab" * 32)
    assert tools._ask(core, "summarise this", provider=prov) == "- one point\n- another"
    url, body = asked[0]
    assert url.endswith(f"/link/{'ab' * 32}/v1/chat/completions") and body["stream"] is True
    assert body["chat_template_kwargs"] == {"enable_thinking": False}  # the answer, no musing
    with pytest.raises(RuntimeError):
        tools._ask(core, "fail please", provider=prov)
