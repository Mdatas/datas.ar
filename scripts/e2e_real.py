"""End-to-end check with real downloads: the AI engine, a real small AI, a real answer, voice.

Run it against a Datas service that is already listening, for example:

    datas serve --port 8420 &                      # or dist/Datas/datas-cli serve
    python scripts/e2e_real.py --base http://127.0.0.1:8420 --voice

Everything goes through the same local interface the window uses, so this is what happens
when a person presses the buttons. It needs the internet (GitHub for the engine, Hugging
Face for the files) and about 1.5 GB of disk. The unit tests never download anything; this
is the test that does. It is run by the `e2e` workflow on Windows, macOS and Linux.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import httpx

STEPS: list[dict] = []


def step(name: str, ok: bool, detail: str = "", seconds: float = 0.0) -> bool:
    STEPS.append({"step": name, "ok": ok, "detail": detail, "seconds": round(seconds, 1)})
    print(f"{'ok    ' if ok else 'FAILED'} {name} ({seconds:.0f}s) {detail}", flush=True)
    return ok


def wait_job(c: httpx.Client, job: dict, limit: float) -> dict:
    """Poll a job until it ends; print its progress now and then."""
    t0, last = time.time(), ""
    while time.time() - t0 < limit:
        j = c.get(f"/api/jobs/{job['id']}").json()
        line = f"{j.get('phase') or j.get('state')} {j.get('percent') or 0:.0f}%"
        if line != last and int(time.time() - t0) % 5 == 0:
            print("       …", line, flush=True)
            last = line
        if j["state"] in ("done", "error"):
            return j
        time.sleep(1)
    return {"state": "error", "error": f"still running after {limit:.0f}s", "log": []}


def chat(c: httpx.Client, text: str, limit: float = 300) -> tuple[str, list[str]]:
    """One question through /api/chat; returns (answer, errors)."""
    answer, errors = "", []
    body = {"messages": [{"role": "user", "content": text}], "lang": "en"}
    with c.stream("POST", "/api/chat", json=body, timeout=limit) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            if ev.get("type") == "token":
                answer += ev.get("text", "")
            elif ev.get("type") == "error":
                errors.append(ev.get("message", "?"))
            elif ev.get("type") == "done":
                break
    return answer, errors


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # a Windows console may not know every letter
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8420")
    ap.add_argument("--model", default="qwen3-0.6b")
    ap.add_argument("--quant", default="Q4_0")
    ap.add_argument("--voice", action="store_true", help="also test speaking and hearing")
    ap.add_argument(
        "--hardware", action="store_true", help="also test FFmpeg, the camera and the screen"
    )
    ap.add_argument("--report", default="")
    ap.add_argument("--serve", action="store_true", help="start `datas serve` here, stop it after")
    ap.add_argument("--serve-log", default="serve.log")
    a = ap.parse_args()
    service = None
    if a.serve:
        import subprocess

        port = a.base.rsplit(":", 1)[-1].strip("/")
        log = open(a.serve_log, "w", encoding="utf-8")  # noqa: SIM115 - lives as long as the service
        service = subprocess.Popen(
            [sys.executable, "-m", "datas", "serve", "--port", port],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        return run(a)
    finally:
        if service is not None:
            service.terminate()
            try:
                service.wait(20)
            except Exception:  # noqa: BLE001
                service.kill()


def run(a: argparse.Namespace) -> int:
    c = httpx.Client(base_url=a.base, timeout=60, trust_env=False)

    # the service is up
    t = time.time()
    st = {}
    for _ in range(90):
        try:
            st = c.get("/api/status").json()
            break
        except httpx.HTTPError:
            time.sleep(1)
    if not step(
        "the local service answers", bool(st), f"Datas {st.get('version')}", time.time() - t
    ):
        return 1
    spec = c.get("/api/spec").json()
    gpus = ", ".join(g.get("name", "?") for g in spec.get("gpus", [])) or "no graphics card seen"
    print(f"       {spec.get('os')} · {spec.get('arch')} · {spec.get('cpu_name', '')} · {gpus}")

    # 1. engine + a real AI: download, check, start
    t = time.time()
    job = c.post("/api/run", json={"model_id": a.model, "quant": a.quant, "context": 4096}).json()
    j = wait_job(c, job, 1500)
    if not step(
        f"download and start {a.model} {a.quant}",
        j["state"] == "done",
        j.get("error") or "",
        time.time() - t,
    ):
        print("\n".join(j.get("log", [])[-25:]))
        return finish(a, 1)
    st = c.get("/api/status").json()
    srv = st.get("server", {})
    step(
        "the AI is running",
        bool(srv.get("running")),
        f"{srv.get('model_id')} {' '.join(srv.get('args', [])[:14])}",
    )

    # 2. a real answer, streamed the way the window receives it
    t = time.time()
    try:
        answer, errors = chat(c, "What is the capital of France? Answer with one word.")
    except httpx.HTTPError as e:
        answer, errors = "", [f"{type(e).__name__}: {e}"]
    ok = "paris" in answer.lower() and not errors
    step(
        "a streamed answer to a question",
        ok,
        repr(answer[:120]) + (f" errors={errors}" if errors else ""),
        time.time() - t,
    )

    # 3. the chat is kept and can be found again (Remember mode)
    t = time.time()
    c.post("/api/privacy", json={"memory_mode": "remember"})
    saved = c.post(
        "/api/chats",
        json={
            "messages": [
                {"role": "user", "content": "What is the capital of France?"},
                {"role": "assistant", "content": answer or "Paris"},
            ]
        },
    ).json()
    found = c.get("/api/chats", params={"q": "capital of France"}).json()
    items = found.get("chats", found) if isinstance(found, dict) else found
    step(
        "the chat is saved and found by search",
        any(x.get("id") == saved.get("chat_id") for x in items),
        "",
        time.time() - t,
    )

    # 4. a document: written by Datas, read back, used in an answer
    t = time.time()
    import base64

    note = "Meeting notes. The delivery date agreed with the client is the 14th of March."
    ex = c.post(
        "/api/docs/extract",
        json={"name": "notes.txt", "content_base64": base64.b64encode(note.encode()).decode()},
    ).json()
    body = {
        "messages": [
            {
                "role": "user",
                "content": "According to the attached notes, which month is the delivery? One word.",
            }
        ],
        "attachments": [{"name": "notes.txt", "text": ex.get("text", "")}],
        "lang": "en",
    }
    doc_answer = ""
    try:
        with c.stream("POST", "/api/chat", json=body, timeout=300) as r:
            for line in r.iter_lines():
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    if ev.get("type") == "token":
                        doc_answer += ev.get("text", "")
    except httpx.HTTPError as e:
        doc_answer = f"{type(e).__name__}: {e}"
    step(
        "an answer that uses an attached document",
        "march" in doc_answer.lower(),
        repr(doc_answer[:120]),
        time.time() - t,
    )

    # 5. voice: text -> speech -> text, no microphone needed
    if a.voice:
        t = time.time()
        vj = wait_job(c, c.post("/api/voice/install").json(), 1500)
        if step(
            "download the voice parts",
            vj["state"] == "done",
            vj.get("error") or "",
            time.time() - t,
        ):
            t = time.time()
            said = "Good morning. Today we will plant tomatoes in the garden."
            r = c.post("/api/voice/speak", json={"text": said, "lang": "en"}, timeout=300)
            wav = r.content if r.status_code == 200 else b""
            step(
                "text to speech",
                len(wav) > 20000,
                f"{len(wav)} bytes of audio" if wav else r.text[:200],
                time.time() - t,
            )
            t = time.time()
            heard = ""
            if wav:
                r = c.post("/api/voice/hear", content=wav, params={"lang": "en"}, timeout=600)
                heard = r.json().get("text", "") if r.status_code == 200 else r.text[:200]
            words = [w for w in ("morning", "tomatoes", "garden") if w in heard.lower()]
            step(
                "speech to text hears what was said",
                len(words) >= 2,
                repr(heard[:120]),
                time.time() - t,
            )

    # 6. hardware: FFmpeg fetched and checked, a recording read through it, camera and screen
    if a.hardware:
        hardware(c, a)

    # 7. stop the AI; the service stays
    t = time.time()
    c.post("/api/stop")
    time.sleep(2)
    st = c.get("/api/status").json()
    step("the AI stops when asked", not st.get("server", {}).get("running"), "", time.time() - t)
    return finish(a, 0 if all(s["ok"] for s in STEPS) else 1)


def hardware(c: httpx.Client, a: argparse.Namespace) -> None:
    """What can be checked about cameras, the screen and FFmpeg on a machine that has no
    camera: the list answers, FFmpeg is fetched from its pinned address and matches its
    checksum, it really runs (an MP3 becomes text), and asking for a photo or a picture of
    the screen ends in a picture or in a plain sentence — never in a crash."""
    t = time.time()
    r = c.get("/api/things")
    th = r.json() if r.status_code == 200 else {}
    step(
        "the list of hardware answers",
        r.status_code == 200 and "cameras" in th,
        f"{len(th.get('cameras', []))} camera(s), {len(th.get('printers', []))} printer(s), "
        f"{len(th.get('serial', []))} board(s), screen: {bool(th.get('screens'))}, "
        f"mouse and keyboard: {th.get('control', {}).get('ok')}, problems: {th.get('problems')}",
        time.time() - t,
    )
    t = time.time()
    j = wait_job(c, c.post("/api/things/ffmpeg").json(), 900)
    th = c.get("/api/things").json()
    step(
        "FFmpeg is fetched and matches its checksum",
        j["state"] == "done" and th.get("ffmpeg", {}).get("found") is True,
        j.get("error") or str((j.get("result") or {}).get("path", "")),
        time.time() - t,
    )
    if a.voice:  # a recording that only FFmpeg can read: text -> MP3 -> text
        t = time.time()
        said = "The printer is in the kitchen, next to the window."
        sj = wait_job(c, c.post("/api/tools/speak", json={"text": said, "lang": "en"}).json(), 600)
        mp3 = (sj.get("result") or {}).get("mp3") or ""
        heard = ""
        if mp3:
            with open(mp3, "rb") as fh:
                tj = wait_job(
                    c,
                    c.post(
                        "/api/tools/transcribe",
                        params={"name": "note.mp3", "lang": "en"},
                        content=fh.read(),
                        timeout=300,
                    ).json(),
                    900,
                )
            heard = (tj.get("result") or {}).get("text", "") or tj.get("error") or ""
        words = [w for w in ("printer", "kitchen", "window") if w in heard.lower()]
        step(
            "an MP3 recording becomes text (FFmpeg really runs)",
            len(words) >= 2,
            repr(heard[:120]) if mp3 else f"no MP3 was made: {sj.get('error') or sj.get('result')}",
            time.time() - t,
        )
    for name, path in (
        ("a photo", "/api/things/camera/photo"),
        ("the screen", "/api/things/screen"),
    ):
        t = time.time()
        r = c.post(path, json={}, timeout=120)
        body = r.json() if "json" in r.headers.get("content-type", "") else {}
        got = str(body.get("image", "")).startswith("data:image/jpeg;base64,")
        said = str(body.get("detail", ""))
        step(
            f"asking for {name} gives a picture or a plain sentence",
            (r.status_code == 200 and got) or (r.status_code == 409 and len(said) > 20),
            f"{body.get('width')}x{body.get('height')} picture" if got else said[:160],
            time.time() - t,
        )


def finish(a: argparse.Namespace, code: int) -> int:
    if a.report:
        with open(a.report, "w", encoding="utf-8") as fh:
            json.dump({"ok": code == 0, "steps": STEPS}, fh, indent=2)
    bad = [s["step"] for s in STEPS if not s["ok"]]
    print(
        f"\n{len(STEPS) - len(bad)} of {len(STEPS)} steps passed"
        + (f"; failed: {bad}" if bad else ".")
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
