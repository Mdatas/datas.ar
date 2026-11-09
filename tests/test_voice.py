"""Voice engines: catalog integrity, model choice by device, and (when the files are around)
real speaking + hearing round trips. Network-free."""

from __future__ import annotations

import io
import os
import wave
from pathlib import Path

import pytest

from datas.config import Config
from datas.engines import voice
from datas.hardware.detect import GPU, DeviceSpec

GiB = 2**30


def spec(ram: float, cores: int = 4, form: str = "laptop", unified: bool = False) -> DeviceSpec:
    gpus = [GPU(vendor="apple", name="Apple M2", vram_total=0, unified=True)] if unified else []
    return DeviceSpec(
        os="linux",
        os_version="test",
        arch="x86_64",
        hostname="test",
        cpu_name="test",
        cpu_cores_physical=cores,
        cpu_cores_logical=cores,
        cpu_flags=[],
        ram_total=int(ram * GiB),
        ram_available=int(ram * GiB * 0.8),
        swap_total=0,
        gpus=gpus,
        disk_free_models=100 * GiB,
        form_factor=form,
    )


def test_catalog_is_complete_and_sizes_are_exact():
    cat = voice.catalog()
    ids = [m["id"] for m in cat["speech_to_text"]["models"]]
    assert ids == ["tiny", "base", "small", "large-v3-turbo-q5_0"]
    for m in cat["speech_to_text"]["models"]:
        assert m["bytes"] > 10_000_000 and m["file"].startswith("ggml-") and "plain_es" in m
    tts = cat["text_to_speech"]
    assert {f["name"] for f in tts["files"]} == {"kokoro-v1.0.int8.onnx", "voices-v1.0.bin"}
    assert all(len(f["sha256"]) == 64 for f in tts["files"])
    assert tts["voices"]["es"][0] == "ef_dora" and tts["langs"]["es"] == "es"


def test_choice_scales_with_the_device():
    assert voice.choose(spec(3, 2, "phone")).stt_model == "tiny"
    assert voice.choose(spec(6, 4)).stt_model == "base"
    assert voice.choose(spec(16, 4)).stt_model == "small"
    assert voice.choose(spec(16, 12)).stt_model == "large-v3-turbo-q5_0"
    assert voice.choose(spec(16, 4, unified=True)).stt_model == "large-v3-turbo-q5_0"
    cfg = Config()
    cfg.voice_stt_model = "tiny"
    c = voice.choose(spec(32, 16), cfg)
    assert c.stt_model == "tiny" and c.total_bytes == c.stt_bytes + c.tts_bytes
    assert c.plain("es")["download"].endswith("MB")


def test_wav_decoding_and_resampling():
    import numpy as np

    rate = 44100
    t = np.arange(rate) / rate
    x = (np.sin(2 * np.pi * 440 * t) * 0.5 * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.stack([x, x], axis=1).tobytes())
    pcm = voice.pcm_from_wav(buf.getvalue())
    assert pcm.dtype == np.float32 and abs(len(pcm) - 16000) <= 2
    assert 0.2 < float(np.abs(pcm).max()) <= 0.51


KOKORO = Path(os.environ.get("DATAS_TEST_KOKORO_DIR", "/tmp/voice"))


@pytest.mark.skipif(
    not (KOKORO / "kokoro-v1.0.int8.onnx").exists() or not voice.available()["tts"],
    reason="Kokoro files not present",
)
def test_speak_en_and_es(monkeypatch):
    monkeypatch.setattr(voice, "voice_dir", lambda: KOKORO)
    voice.unload()
    wav = voice.speak("Hello from Datas.", "en")
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getframerate() == 24000 and w.getnframes() > 24000 * 0.5
    wav_es = voice.speak("Hola, soy Datas.", "es")
    assert len(wav_es) > 20000 and voice.default_voice("es") == "ef_dora"


@pytest.mark.skipif(
    not (KOKORO / "whisper" / "ggml-tiny.bin").exists() or not voice.available()["stt"],
    reason="whisper test model not present",
)
def test_transcribe_runs(monkeypatch):
    import numpy as np

    monkeypatch.setattr(voice, "stt_path", lambda mid: KOKORO / "whisper" / "ggml-tiny.bin")
    voice.unload()
    assert voice.transcribe(np.zeros(1000, dtype=np.float32), "en", "tiny") == ""
    out = voice.transcribe(np.zeros(16000 * 2, dtype=np.float32), "en", "tiny", threads=2)
    assert isinstance(out, str)
