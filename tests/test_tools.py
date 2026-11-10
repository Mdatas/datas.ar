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
