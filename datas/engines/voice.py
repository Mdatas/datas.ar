"""Hearing and speaking, in-process.

* speech → text: whisper.cpp through ``pywhispercpp`` (CPU; wheels for Windows, macOS, Linux)
* text → speech: Kokoro-82M through ``kokoro-onnx`` (ONNX Runtime on the CPU)
* microphone: ``sounddevice`` (PortAudio) on the server side, so it works inside every window
  toolkit without browser permission prompts — the server and the window are on the same machine.

Nothing here keeps audio: recordings live in memory and are dropped after transcription; the
spoken answer is streamed back as WAV bytes and not written to disk. Forget mode therefore needs
no special casing. Models live in ``<data>/voice``.

Everything is optional: if the ``datas[voice]`` packages are missing, ``available()`` says so and
the UI hides the microphone and speaker buttons.
"""

from __future__ import annotations

import hashlib
import io
import json
import threading
import time
import wave
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from datas.config import Config, home
from datas.hardware.detect import DeviceSpec
from datas.runtime import downloader

if TYPE_CHECKING:
    from datas.orchestrator import Job

SAMPLE_RATE = 16_000  # whisper.cpp input
GiB = 2**30


def catalog() -> dict:
    with resources.files("datas.catalog").joinpath("media.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def voice_dir() -> Path:
    d = home() / "voice"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# availability


def available() -> dict[str, Any]:
    """Which parts of the voice stack are importable on this install."""
    out = {"stt": False, "tts": False, "mic": False, "missing": []}
    try:
        import pywhispercpp  # noqa: F401

        out["stt"] = True
    except Exception:  # noqa: BLE001
        out["missing"].append("pywhispercpp")
    try:
        import kokoro_onnx  # noqa: F401

        out["tts"] = True
    except Exception:  # noqa: BLE001
        out["missing"].append("kokoro-onnx")
    try:
        import sounddevice  # noqa: F401

        out["mic"] = True
    except Exception:  # noqa: BLE001 - also raised when PortAudio is not installed on Linux
        out["missing"].append("sounddevice/PortAudio")
    return out


# ---------------------------------------------------------------------------
# choosing the models


@dataclass
class VoiceChoice:
    stt_model: str
    stt_file: str
    stt_bytes: int
    tts_bytes: int
    total_bytes: int
    ram_gib: float
    reasons: list[str]

    def plain(self, lang: str = "en") -> dict:
        cat = catalog()
        stt = next(m for m in cat["speech_to_text"]["models"] if m["id"] == self.stt_model)
        return {
            "stt": stt[f"plain_{lang}" if f"plain_{lang}" in stt else "plain_en"],
            "tts": cat["text_to_speech"][f"plain_{lang}" if lang == "es" else "plain_en"],
            "download": f"{self.total_bytes / 2**20:.0f} MB",
            "memory": f"{self.ram_gib:.1f} GB",
        }


def choose(spec: DeviceSpec, cfg: Config | None = None) -> VoiceChoice:
    """Pick the hearing model by processor and memory; speaking is always Kokoro (82 M params)."""
    cat = catalog()
    models = {m["id"]: m for m in cat["speech_to_text"]["models"]}
    cores = max(1, spec.cpu_cores_logical or spec.cpu_cores_physical or 1)
    ram = spec.ram_total / GiB
    phone = spec.form_factor == "phone"
    reasons: list[str] = []
    forced = (cfg.voice_stt_model if cfg else "auto") or "auto"
    if forced != "auto" and forced in models:
        pick = forced
        reasons.append("Chosen by you in Settings.")
    elif phone or ram < 4:
        pick = "tiny"
        reasons.append("Small device: the tiny hearing model keeps things responsive.")
    elif ram < 8 or cores < 4:
        pick = "base"
        reasons.append("Base hearing model: good dictation without slowing a normal laptop.")
    elif cores >= 8 or any(g.unified for g in spec.gpus):
        pick = "large-v3-turbo-q5_0"
        reasons.append("Strong processor: the best hearing model still keeps up with speech.")
    else:
        pick = "small"
        reasons.append("Small hearing model: noticeably better with accents and Spanish.")
    stt = models[pick]
    tts_bytes = sum(f["bytes"] for f in cat["text_to_speech"]["files"])
    ram_need = stt["ram_gib"] + cat["text_to_speech"]["ram_gib"]
    reasons.append("Kokoro voice: natural English and Spanish, runs on the processor.")
    return VoiceChoice(
        stt_model=pick,
        stt_file=stt["file"],
        stt_bytes=stt["bytes"],
        tts_bytes=tts_bytes,
        total_bytes=stt["bytes"] + tts_bytes,
        ram_gib=ram_need,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# downloads


def stt_path(model_id: str) -> Path:
    cat = catalog()
    m = next(x for x in cat["speech_to_text"]["models"] if x["id"] == model_id)
    return voice_dir() / m["file"]


def tts_paths() -> dict[str, Path]:
    return {f["name"]: voice_dir() / f["name"] for f in catalog()["text_to_speech"]["files"]}


def installed(cfg: Config | None = None, spec: DeviceSpec | None = None) -> dict:
    """What is on disk. ``stt_model`` is the configured/auto model when a spec is given."""
    stt_models = [
        m["id"] for m in catalog()["speech_to_text"]["models"] if stt_path(m["id"]).exists()
    ]
    tts_ok = all(p.exists() for p in tts_paths().values())
    out = {"stt_models": stt_models, "tts": tts_ok, "ready": bool(stt_models) and tts_ok}
    if spec is not None:
        out["stt_model"] = choose(spec, cfg).stt_model
    return out


def _download_url(url: str, dest: Path, expected: int, sha256: str | None, job: Job | None) -> Path:
    say = job.say if job else print
    if dest.exists() and dest.stat().st_size == expected:
        say(f"Already on disk: {dest.name}")
        return dest
    part = dest.with_suffix(dest.suffix + ".part")
    done = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": "datas.ar"}
    if done:
        headers["Range"] = f"bytes={done}-"
    with httpx.Client(
        timeout=httpx.Timeout(60, read=300), follow_redirects=True, headers=headers
    ) as c:
        with c.stream("GET", url) as r:
            r.raise_for_status()
            mode = "ab" if (done and r.status_code == 206) else "wb"
            if mode == "wb":
                done = 0
            with part.open(mode) as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
                    done += len(chunk)
                    if job:
                        job.progress(done, expected)
    if part.stat().st_size != expected:
        raise OSError(
            f"Incomplete download of {dest.name}: {part.stat().st_size} of {expected} bytes"
        )
    if sha256:
        h = hashlib.sha256()
        with part.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        if h.hexdigest() != sha256:
            part.unlink(missing_ok=True)
            raise ValueError(f"Checksum mismatch for {dest.name}; file deleted.")
    part.replace(dest)
    return dest


def ensure(choice: VoiceChoice, job: Job | None = None) -> dict:
    """Download the hearing model (Hugging Face) and the Kokoro voice (GitHub release)."""
    cat = catalog()
    say = job.say if job else print
    if job:
        job.phase = "voice"
        job.total = choice.total_bytes
    base = 0

    def prog(done: int, total: int | None) -> None:
        if job:
            job.progress(base + done, choice.total_bytes)

    say(f"Hearing model: whisper {choice.stt_model} ({choice.stt_bytes / 2**20:.0f} MB)")
    stt = downloader.download_file(
        cat["speech_to_text"]["repo"],
        choice.stt_file,
        stt_path(choice.stt_model),
        expected_size=choice.stt_bytes,
        progress=prog,
        log=say,
    )
    base += choice.stt_bytes
    paths = tts_paths()
    for f in cat["text_to_speech"]["files"]:
        say(f"Voice: {f['name']} ({f['bytes'] / 2**20:.0f} MB)")

        class _J:  # progress adapter for the second file
            def progress(self, d: int, t: int | None) -> None:
                prog(d, t)

            def say(self, m: str) -> None:
                say(m)

        _download_url(f["url"], paths[f["name"]], f["bytes"], f.get("sha256"), _J())  # type: ignore[arg-type]
        base += f["bytes"]
    return {"stt": str(stt), "tts": {k: str(v) for k, v in paths.items()}}


# ---------------------------------------------------------------------------
# hearing


_stt_lock = threading.Lock()
_stt: tuple[str, Any] | None = None


def _whisper(model_id: str, threads: int):
    global _stt
    with _stt_lock:
        if _stt and _stt[0] == model_id:
            return _stt[1]
        from pywhispercpp.model import Model

        m = Model(str(stt_path(model_id)), redirect_whispercpp_logs_to=None, n_threads=threads)
        _stt = (model_id, m)
        return m


def transcribe(pcm16k: Any, language: str | None, model_id: str, threads: int = 4) -> str:
    """``pcm16k``: float32 numpy array at 16 kHz, mono. Returns plain text."""
    import numpy as np

    audio = np.asarray(pcm16k, dtype=np.float32)
    if audio.size < SAMPLE_RATE // 4:  # < 0.25 s: nothing to hear
        return ""
    m = _whisper(model_id, threads)
    kw = {"language": language} if language and language != "auto" else {}
    segs = m.transcribe(audio, **kw)
    return " ".join(s.text.strip() for s in segs).strip()


def transcribe_segments(
    pcm16k: Any, language: str | None, model_id: str, threads: int = 4
) -> list[tuple[float, float, str]]:
    """Like ``transcribe`` but keeps the timing: [(start seconds, end seconds, text)]."""
    import numpy as np

    audio = np.asarray(pcm16k, dtype=np.float32)
    if audio.size < SAMPLE_RATE // 4:
        return []
    m = _whisper(model_id, threads)
    kw = {"language": language} if language and language != "auto" else {}
    # whisper.cpp counts time in hundredths of a second
    return [(s.t0 / 100.0, s.t1 / 100.0, s.text.strip()) for s in m.transcribe(audio, **kw)]


def pcm_from_wav(data: bytes) -> Any:
    """Decode a 16-bit PCM WAV (any rate, mono/stereo) into float32 mono at 16 kHz."""
    import numpy as np

    with wave.open(io.BytesIO(data)) as w:
        rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width != 2:
        raise ValueError("WAV must be 16-bit PCM")
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return resample(x, rate, SAMPLE_RATE)


def resample(x: Any, src: int, dst: int) -> Any:
    import numpy as np

    if src == dst:
        return x
    n = int(round(len(x) * dst / src))
    idx = np.linspace(0, len(x) - 1, n)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


# ---------------------------------------------------------------------------
# microphone (server side)


class Recorder:
    """Start/stop recording from the default microphone; keeps the audio only in memory."""

    MAX_SECONDS = 120

    def __init__(self) -> None:
        self._chunks: list[Any] = []
        self._stream = None
        self._lock = threading.Lock()
        self.started: float | None = None

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import sounddevice as sd

        with self._lock:
            if self._stream is not None:
                return
            self._chunks = []

            def cb(indata, frames, t, status):  # noqa: ANN001
                self._chunks.append(indata[:, 0].copy())
                if self.started and time.time() - self.started > self.MAX_SECONDS:
                    raise sd.CallbackStop()

            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=cb
            )
            self._stream.start()
            self.started = time.time()

    def stop(self) -> Any:
        import numpy as np

        with self._lock:
            if self._stream is None:
                return np.zeros(0, dtype=np.float32)
            self._stream.stop()
            self._stream.close()
            self._stream = None
            self.started = None
            audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
            self._chunks = []
            return audio

    def level(self) -> float:
        """Rough loudness of the last chunk, 0..1, for a little meter in the UI."""
        import numpy as np

        if not self._chunks:
            return 0.0
        return float(min(1.0, np.abs(self._chunks[-1]).mean() * 8))


# ---------------------------------------------------------------------------
# speaking


_tts_lock = threading.Lock()
_tts: Any = None


def _kokoro():
    global _tts
    with _tts_lock:
        if _tts is None:
            from kokoro_onnx import Kokoro

            p = tts_paths()
            _tts = Kokoro(str(p["kokoro-v1.0.int8.onnx"]), str(p["voices-v1.0.bin"]))
        return _tts


def default_voice(lang: str, cfg: Config | None = None) -> str:
    voices = catalog()["text_to_speech"]["voices"]
    if cfg and cfg.voice_tts_voice and cfg.voice_tts_voice != "auto":
        return cfg.voice_tts_voice
    return voices.get(lang, voices["en"])[0]


def speak(text: str, lang: str = "en", voice: str | None = None, speed: float = 1.0) -> bytes:
    """Text → 16-bit mono WAV bytes (24 kHz). Long texts are spoken in full; callers may cut."""
    import numpy as np

    k = _kokoro()
    code = catalog()["text_to_speech"]["langs"].get(lang, "en-us")
    samples, rate = k.create(text, voice=voice or default_voice(lang), speed=speed, lang=code)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def unload() -> None:
    global _stt, _tts
    _stt = None
    _tts = None
