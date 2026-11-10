"""Everyday tools that need no chat: turn a recording into text, read a text aloud into an
audio file, and summarise or translate a document that is longer than the AI can hold at once.

Each runs as a job (the window shows progress) and leaves its result as a file in the user's
Documents/Datas folder, ready to open, share or continue working on.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import httpx

from datas import docs
from datas import export as exporter

AUDIO_VIDEO = {
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".amr", ".3gp",
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v",
}  # fmt: skip


def _stamp(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt(segments: list[tuple[float, float, str]]) -> str:
    """Subtitles (.srt) from timed segments."""
    out = []
    for i, (t0, t1, text) in enumerate(segments, 1):
        out.append(f"{i}\n{_stamp(t0)} --> {_stamp(max(t1, t0 + 0.2))}\n{text}\n")
    return "\n".join(out)


def _to_pcm(path: Path, job=None):  # noqa: ANN001, ANN202
    """Any recording → what the hearing model wants (mono, 16 kHz). WAV is read directly;
    everything else goes through FFmpeg (the system's, or a copy fetched once)."""
    from datas import programs
    from datas.engines import voice

    data = path.read_bytes()
    if path.suffix.lower() == ".wav":
        try:
            return voice.pcm_from_wav(data)
        except (ValueError, wave.Error, EOFError):
            pass  # not plain 16-bit PCM: let FFmpeg handle it
    exe = programs.ffmpeg(fetch=True)
    if not exe:
        raise RuntimeError(
            "This recording needs FFmpeg to be read and it could not be found or downloaded. "
            "Install it from https://ffmpeg.org, or give a .wav file."
        )
    if job:
        job.say("Preparing the audio…")
    with tempfile.TemporaryDirectory(prefix="datas-audio-") as tmp:
        wav = Path(tmp) / "audio.wav"
        out = subprocess.run(
            [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-vn", "-ac", "1",
             "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
            capture_output=True,
            text=True,
            timeout=3600,
        )  # fmt: skip
        if out.returncode != 0 or not wav.exists():
            raise RuntimeError(
                f"The recording could not be read: {(out.stderr or '').strip()[-300:]}"
            )
        return voice.pcm_from_wav(wav.read_bytes())


def transcribe_file(core, path: Path, name: str, lang: str | None, job=None) -> dict:  # noqa: ANN001
    """A recording (audio or video) → a text file and subtitles."""
    from datas.engines import voice

    inst = voice.installed(core.cfg, core.spec())
    if not inst.get("stt_models"):
        raise RuntimeError(
            "The hearing model is not installed yet. Install the voice in Settings → Voice first."
        )
    model = (
        inst.get("stt_model")
        if inst.get("stt_model") in inst["stt_models"]
        else inst["stt_models"][-1]
    )
    pcm = _to_pcm(path, job)
    seconds = len(pcm) / voice.SAMPLE_RATE
    if job:
        job.phase = "transcribing"
        job.say(f"Listening to {seconds / 60:.1f} minutes of audio with whisper {model}…")
    threads = max(1, min(8, (core.spec().cpu_cores_logical or 4) - 1))
    segs = voice.transcribe_segments(
        pcm, None if lang in (None, "", "auto") else lang, model, threads
    )
    text = " ".join(t for _, _, t in segs).strip()
    title = Path(name).stem or "recording"
    paragraphs, cur, last_end = [], [], 0.0
    for t0, t1, t in segs:  # a new paragraph after a pause of two seconds
        if cur and t0 - last_end > 2.0:
            paragraphs.append(" ".join(cur))
            cur = []
        cur.append(t)
        last_end = t1
    if cur:
        paragraphs.append(" ".join(cur))
    md = f"# {title}\n\n" + "\n\n".join(paragraphs) + "\n"
    out: dict = {"text": text, "markdown": md, "seconds": round(seconds, 1), "segments": len(segs)}
    if not core.cfg.forget and text:
        txt = exporter.render(md, "txt", exporter._target(title, "txt"), title)  # noqa: SLF001
        sub = exporter._target(title, "srt")  # noqa: SLF001
        sub.write_text(srt(segs), encoding="utf-8")
        out |= {"path": str(txt), "srt": str(sub), "folder": str(txt.parent)}
    return out


def _sentences(text: str, limit: int = 380) -> list[str]:
    """Pieces short enough for the voice to say well, cut at sentence ends."""
    import re

    out, cur = [], ""
    for part in re.split(r"(?<=[.!?…:;])\s+|\n+", text):
        part = part.strip()
        if not part:
            continue
        while len(part) > limit:  # a very long sentence: cut at a comma or a space
            cut = max(part.rfind(",", 0, limit), part.rfind(" ", 0, limit))
            cut = cut if cut > limit // 2 else limit
            out.append((cur + " " + part[:cut]).strip())
            cur, part = "", part[cut:].strip()
        if len(cur) + len(part) + 1 > limit and cur:
            out.append(cur)
            cur = part
        else:
            cur = (cur + " " + part).strip()
    if cur:
        out.append(cur)
    return out


def speak_to_file(core, text: str, lang: str, voice_id: str | None, title: str, job=None) -> dict:  # noqa: ANN001
    """Read a text aloud into a .wav file (and .mp3 when FFmpeg is on this computer)."""
    from datas import programs
    from datas.engines import voice

    text = exporter.plain_text(text).strip()
    if not text:
        raise RuntimeError("There is no text to read.")
    if not voice.installed(core.cfg).get("tts"):
        raise RuntimeError("The voice is not installed yet. Install it in Settings → Voice first.")
    pieces = _sentences(text)
    frames, rate = [], 24000
    for i, piece in enumerate(pieces, 1):
        if job:
            job.phase = "speaking"
            job.progress(i - 1, len(pieces))
        with wave.open(io.BytesIO(voice.speak(piece, lang, voice_id or None))) as w:
            rate = w.getframerate()
            frames.append(w.readframes(w.getnframes()))
            frames.append(b"\x00\x00" * int(rate * 0.25))  # a short breath between pieces
    if job:
        job.progress(len(pieces), len(pieces))
    name = exporter.safe_name(title or text[:40], "Audio")
    dest = exporter._target(name, "wav")  # noqa: SLF001
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(frames))
    out = {
        "path": str(dest),
        "folder": str(dest.parent),
        "seconds": round(sum(len(f) for f in frames) / 2 / rate, 1),
    }
    exe = programs.ffmpeg(fetch=False)
    if exe:
        mp3 = dest.with_suffix(".mp3")
        r = subprocess.run(
            [
                exe,
                "-hide_banner",
                "-loglevel",
                "error",
                "-n",
                "-i",
                str(dest),
                "-b:a",
                "96k",
                str(mp3),
            ],
            capture_output=True,
        )
        if r.returncode == 0 and mp3.exists():
            out["mp3"] = str(mp3)
    return out


# ---- documents longer than the AI's working memory --------------------------------

PROMPTS = {
    "summary_part": "Summarize this part of a longer document in at most {n} bullet points. Keep names, "
    "numbers, dates and decisions exact. Write in {lang}. Only the bullets.\n\n---\n{text}",
    "summary_final": "These are notes on consecutive parts of one document. Write the summary of the whole "
    "document in {lang}: one sentence with the main point, then the key points as bullets, then "
    "(only if present) what is still open or must be done. Do not add anything that is not in the notes."
    "\n\n---\n{text}",
    "translate": "Translate the following text into {lang}. Keep the meaning, tone, names, numbers and the "
    "Markdown formatting. Output only the translation.\n\n---\n{text}",
}
LANG_NAMES = {
    "en": "English",
    "es": "Spanish",
    "pt": "Portuguese",
    "fr": "French",
    "it": "Italian",
    "de": "German",
}


def _ask(core, prompt: str, max_tokens: int | None = None) -> str:  # noqa: ANN001
    from datas.chat_engine import is_local_url
    from datas.providers import active_provider

    if not core.server.running() and core.can_wake():
        core.wake()
    prov = active_provider(core.cfg, core.server.running(), core.server.state.rpc)
    if prov.kind in ("local", "pool") and not core.server.running():
        raise RuntimeError("No AI is running. Start one in My AIs first.")
    core.touch()
    body = {
        "model": prov.model or "default",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    if max_tokens:
        body["max_tokens"] = max_tokens
    with httpx.Client(
        timeout=httpx.Timeout(900, connect=30), trust_env=not is_local_url(prov.base_url)
    ) as c:
        r = c.post(f"{prov.base_url}/chat/completions", headers=prov.headers(), json=body)
    if r.status_code >= 400:
        from datas.chat_engine import friendly_error

        raise RuntimeError(friendly_error(r.status_code, r.text))
    core.touch()
    msg = r.json()["choices"][0]["message"]
    return (msg.get("content") or "").strip()


def long_document(
    core, text: str, mode: str, lang: str, ctx_tokens: int, title: str = "", job=None
) -> dict:  # noqa: ANN001
    """Summarise or translate ``text`` piece by piece. ``mode``: summary | translate."""
    text = text.strip()
    if not text:
        raise RuntimeError("The document has no text.")
    if mode not in ("summary", "translate"):
        raise ValueError("mode must be summary or translate")
    lang_name = LANG_NAMES.get(lang, lang)
    # a piece = about 40% of the working memory, leaving room for the answer
    size = int(max(1024, ctx_tokens) * 3.0 * (0.40 if mode == "summary" else 0.30))
    pieces = docs.chunk(text, size=max(1500, size), overlap=0)
    started = time.time()
    results = []
    for i, piece in enumerate(pieces, 1):
        if job:
            job.phase = "reading"
            job.progress(i - 1, len(pieces) + (1 if mode == "summary" else 0))
            job.say(f"Part {i} of {len(pieces)}…")
        if mode == "summary":
            results.append(
                _ask(core, PROMPTS["summary_part"].format(n=6, lang=lang_name, text=piece))
            )
        else:
            results.append(_ask(core, PROMPTS["translate"].format(lang=lang_name, text=piece)))
    if mode == "summary":
        notes = "\n\n".join(f"Part {i}:\n{r}" for i, r in enumerate(results, 1))
        final = (
            results[0]
            if len(results) == 1
            else _ask(core, PROMPTS["summary_final"].format(lang=lang_name, text=notes[: size * 2]))
        )
        md = (f"# {title}\n\n" if title else "") + final
    else:
        md = "\n\n".join(results)
    if job:
        job.progress(1, 1)
    return {
        "markdown": md,
        "parts": len(pieces),
        "seconds": round(time.time() - started, 1),
        "mode": mode,
    }
