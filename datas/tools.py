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
    exe = programs.ffmpeg()
    if not exe:  # fetched once, checked against its published checksum (datas.programs)
        if job:
            dl = programs.ffmpeg_download()
            job.say(
                "Getting FFmpeg, the free program that reads recordings"
                + (f" (about {dl['bytes'] // 1_000_000} MB, once)…" if dl else "…")
            )
        try:
            exe = programs.fetch_ffmpeg(job.progress if job else None)
        except RuntimeError as e:
            raise RuntimeError(f"This recording needs FFmpeg to be read. {e}") from e
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
PART_TOKENS = 800  # the most an AI may write about one part of a document being summarised
FINAL_TOKENS = 1500  # … and for the summary of the whole
LANG_NAMES = {
    "en": "English",
    "es": "Spanish",
    "pt": "Portuguese",
    "fr": "French",
    "it": "Italian",
    "de": "German",
}


def _ask(core, prompt: str, max_tokens: int | None = None, provider=None) -> str:  # noqa: ANN001
    """One question, one answer, from the AI in use — or from ``provider`` (the AI of a
    linked device that is helping with a long job)."""
    from datas.chat_engine import is_local_url
    from datas.providers import active_provider

    if provider is not None:
        prov = provider
    else:
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
    if prov.kind in ("local", "pool", "linked"):
        # Piece work (summarise this part, translate that one) needs the answer, not the
        # thinking aloud some AIs do first: a small one can think until its working memory
        # is full and then answer nothing. llama.cpp's server takes this per request and
        # AIs without that switch ignore it. Paid services are not sent an unknown field.
        body["chat_template_kwargs"] = {"enable_thinking": False}
    from datas.chat_engine import friendly_error

    url = f"{prov.base_url}/chat/completions"
    with httpx.Client(
        timeout=httpx.Timeout(900, connect=30), trust_env=not is_local_url(prov.base_url)
    ) as c:
        if prov.kind == "linked":
            # The AI of another device: take the answer as it is written. A long answer sent
            # in one piece is silent for minutes, and the link takes silence for a device
            # that stopped answering.
            import json

            pieces = []
            with c.stream("POST", url, headers=prov.headers(), json=body | {"stream": True}) as r:
                if r.status_code >= 400:
                    r.read()
                    raise RuntimeError(friendly_error(r.status_code, r.text))
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0].get("delta") or {}
                    except (ValueError, KeyError, IndexError, AttributeError):
                        continue
                    pieces.append(delta.get("content") or "")
            core.touch()
            return "".join(pieces).strip()
        r = c.post(url, headers=prov.headers(), json=body)
    if r.status_code >= 400:
        raise RuntimeError(friendly_error(r.status_code, r.text))
    core.touch()
    msg = r.json()["choices"][0]["message"]
    return (msg.get("content") or "").strip()


def helpers(core) -> list[dict]:  # noqa: ANN001
    """Linked computers of the person whose own AI can take parts of a long job right now:
    connected, with an AI of their own ready, and not already the AI this device is using."""
    from datas.providers import linked_provider

    lm = getattr(core, "link", None)
    if lm is None and getattr(core.cfg, "link_enabled", False):
        try:  # the link is made on first use
            lm = core.link_manager()
        except Exception:  # noqa: BLE001 - linking is not available on this copy
            return []
    if lm is None:
        return []
    out = []
    for pid in lm._computers():  # noqa: SLF001 - phones only call in
        p = lm.peer_public(pid)
        ai = p.get("ai") or {}
        if p["online"] and ai.get("available") and not p["in_use"]:
            out.append(
                {
                    "id": pid,
                    "name": p["name"],
                    "ai": ai.get("name") or "",
                    "context": int(ai.get("context") or 8192),
                    "provider": linked_provider(core.cfg, pid),
                }
            )
    return out


def _share_out(core, prompts: list[str], hands: list[dict], job, steps: int, limit=None) -> tuple:  # noqa: ANN001
    """Many hands: this device and each helping device take the next part as soon as they are
    free. A helper that stops answering gives its part back and the others carry on; if this
    device's own AI fails, the job fails as it would alone. Returns the answers in order, the
    names of the helpers that dropped out, and how many parts each hand wrote."""
    import threading
    from collections import deque

    todo = deque(range(len(prompts)))
    results: list = [None] * len(prompts)
    lock = threading.Lock()
    dropped: list[str] = []
    failed: list[BaseException] = []
    done = [0]
    took: dict[str, int] = {}

    def tick(who: str) -> None:
        done[0] += 1
        took[who] = took.get(who, 0) + 1
        if job:
            job.progress(done[0], steps)
            job.say(f"Part {done[0]} of {len(prompts)} done ({who})")

    def work(name: str, provider) -> None:  # noqa: ANN001
        while True:
            with lock:
                if failed or not todo:
                    return
                i = todo.popleft()
            try:
                answer = _ask(core, prompts[i], limit, provider=provider)
            except Exception as e:  # noqa: BLE001 - asleep, unplugged, its AI stopped
                with lock:
                    todo.appendleft(i)
                    if provider is None:
                        failed.append(e)
                    else:
                        dropped.append(name)
                        if job:
                            job.say(f"{name} stopped answering; the others carry on.")
                return
            with lock:
                results[i] = answer
                tick(name or "this device")

    threads = [threading.Thread(target=work, args=("", None), daemon=True)]
    threads += [
        threading.Thread(target=work, args=(h["name"], h["provider"]), daemon=True) for h in hands
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if failed:
        raise failed[0]
    while todo:  # parts a helper gave back after this device had finished its own
        i = todo.popleft()
        results[i] = _ask(core, prompts[i], limit)
        tick("this device")
    return results, dropped, took


def long_document(
    core,  # noqa: ANN001
    text: str,
    mode: str,
    lang: str,
    ctx_tokens: int,
    title: str = "",
    job=None,  # noqa: ANN001
    hands: list[dict] | None = None,
) -> dict:
    """Summarise or translate ``text`` piece by piece. ``mode``: summary | translate.
    ``hands``: linked devices (see ``helpers``) that take parts at the same time."""
    text = text.strip()
    if not text:
        raise RuntimeError("The document has no text.")
    if mode not in ("summary", "translate"):
        raise ValueError("mode must be summary or translate")
    lang_name = LANG_NAMES.get(lang, lang)
    hands = list(hands or [])
    # every hand must be able to take any part: size them for the smallest working memory
    ctx_tokens = min([ctx_tokens] + [int(h.get("context") or ctx_tokens) for h in hands])
    # a piece = about 40% of the working memory, leaving room for the answer
    size = int(max(1024, ctx_tokens) * 3.0 * (0.40 if mode == "summary" else 0.30))
    pieces = docs.chunk(text, size=max(1500, size), overlap=0)
    started = time.time()
    part = PROMPTS["summary_part" if mode == "summary" else "translate"]
    prompts = [part.format(n=6, lang=lang_name, text=piece) for piece in pieces]
    steps = len(pieces) + (1 if mode == "summary" else 0)
    # the notes on one part are a handful of bullets: a small AI must not write on until its
    # working memory is full (minutes on a slow device). A translation is as long as its text.
    limit = PART_TOKENS if mode == "summary" else None
    dropped: list[str] = []
    took: dict[str, int] = {}
    if hands and len(pieces) > 1:
        if job:
            job.phase = "reading"
            job.say(
                f"{len(pieces)} parts, shared between this device and "
                + ", ".join(h["name"] for h in hands)
            )
        results, dropped, took = _share_out(core, prompts, hands, job, steps, limit)
    else:
        hands = []
        results = []
        for i, prompt in enumerate(prompts, 1):
            if job:
                job.phase = "reading"
                job.progress(i - 1, steps)
                job.say(f"Part {i} of {len(pieces)}…")
            results.append(_ask(core, prompt, limit))
    if mode == "summary":
        notes = "\n\n".join(f"Part {i}:\n{r}" for i, r in enumerate(results, 1))
        final = (
            results[0]
            if len(results) == 1
            else _ask(
                core,
                PROMPTS["summary_final"].format(lang=lang_name, text=notes[: size * 2]),
                FINAL_TOKENS,
            )
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
        # who wrote how many parts (only when the work was shared), and who gave up on the way
        "helped": [h["name"] for h in hands if took.get(h["name"]) and h["name"] not in dropped],
        "shares": took,
        "dropped": dropped,
    }
