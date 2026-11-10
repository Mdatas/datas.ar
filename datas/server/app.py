"""FastAPI app.

- ``/``            the single-file web UI
- ``/api/*``       device, recommendation, catalog, install/run jobs, providers, pool
- ``/v1/*``        OpenAI-compatible proxy to the *active provider* (local llama-server,
                   pooled llama-server, or a remote API with your key). Any OpenAI SDK or
                   agent framework pointed at ``http://127.0.0.1:8420/v1`` just works.

Binds to 127.0.0.1 by default. Expose it on the LAN only on purpose (``datas serve
--host 0.0.0.0``) and know that the /v1 proxy will then forward your remote API keys'
requests for anyone who can reach it.
"""

from __future__ import annotations

import base64
import json
import os
from importlib import resources
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from datas import (
    __version__,
    assistants,
    chat_engine,
    chats,
    docs,
    learn,
    library,
    shortcuts,
    words,
)
from datas import export as exporter
from datas.catalog import add_user_model
from datas.catalog import reload as reload_catalog
from datas.orchestrator import Datas
from datas.providers import PRESETS, active_provider, all_providers, remove_remote, set_remote
from datas.recommend.abilities import assess
from datas.recommend.engine import default_headroom, headroom_for_mode, wants_for

app = FastAPI(title="Datas.ar", version=__version__, docs_url="/api/docs", redoc_url=None)
core = Datas()

# ---------------------------------------------------------------------------
# Who may talk to the local API
# ---------------------------------------------------------------------------
# The API listens on this device only, but a web page open in the user's browser can still
# *send* requests to 127.0.0.1. Two checks stop a stranger's page from driving Datas:
#   * Host: the request must be addressed to this device by a local name. A page that makes
#     its own domain point at 127.0.0.1 ("DNS rebinding") arrives with that domain as Host.
#   * Origin / Sec-Fetch-Site: a request that changes something must come from Datas' own
#     window, or from a program that is not a browser page (scripts and SDKs send neither).
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
ALLOWED_HOSTS: set[str] = {
    h.strip().lower() for h in os.environ.get("DATAS_ALLOW_HOSTS", "").split(",") if h.strip()
}


def allow_hosts(*names: str) -> None:
    """Used when the user starts the server on the network on purpose (``datas serve --host``)."""
    ALLOWED_HOSTS.update(n.lower() for n in names if n)


def _hostname(value: str) -> str:
    v = value.strip().lower()
    if v.startswith("["):  # [ipv6]:port
        return v.split("]")[0] + "]"
    return v.rsplit(":", 1)[0] if v.count(":") == 1 else v


# What a linked device (a phone, or another computer that was allowed to) may not do when it
# opens this device's Datas through the link. A phone
# can be lost or borrowed; these are the things that reach beyond Datas itself — the room
# (microphone, camera, screen), the computer (commands, programs, other devices) — or that
# cannot be undone.
REMOTE_REFUSED: tuple[tuple[str, str], ...] = (
    ("ANY", "/api/shutdown"),
    ("ANY", "/api/open"),
    ("ANY", "/api/open-url"),
    ("ANY", "/api/pick-file"),
    ("ANY", "/api/voice/listen/"),
    ("ANY", "/api/things/"),
    ("WRITE", "/api/link"),
    ("WRITE", "/api/service"),
    ("WRITE", "/api/mcp"),
    ("WRITE", "/api/updates/app"),
    ("WRITE", "/api/privacy/wipe"),
    ("WRITE", "/api/programs/"),
    ("WRITE", "/api/apps/"),
)


def remote_refusal(method: str, path: str) -> str | None:
    """Why a request arriving through the link (a phone, or another computer showing this
    device's Datas) is refused, or None if it may go on."""
    write = method not in ("GET", "HEAD", "OPTIONS")
    for kind, prefix in REMOTE_REFUSED:
        hit = path == prefix.rstrip("/") or path.startswith(
            prefix if prefix.endswith("/") else prefix + "/"
        )
        if hit and (kind == "ANY" or write):
            return "This can only be done at the computer itself, not from a linked device."
    return None


def remote_peer(request: Request) -> str | None:
    """The id of the linked device this request comes from, if it came through the link."""
    c = request.client
    return core.remote_clients.get((c.host, c.port)) if c else None


@app.middleware("http")
async def local_only(request: Request, call_next):
    ok = LOCAL_HOSTS | ALLOWED_HOSTS
    if _hostname(request.headers.get("host", "")) not in ok:
        return JSONResponse(
            {
                "detail": words.tr(
                    "This address is not one Datas answers to (see docs/SECURITY.md).",
                    core.cfg.lang,
                )
            },
            status_code=403,
        )
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        site = request.headers.get("sec-fetch-site")
        bad_origin = bool(origin) and (
            origin == "null" or _hostname(origin.split("://", 1)[-1]) not in ok
        )
        if bad_origin or (site and site not in ("same-origin", "none")):
            return JSONResponse(
                {
                    "detail": words.tr(
                        "Requests from other web pages are not accepted.", core.cfg.lang
                    )
                },
                status_code=403,
            )
    if remote_peer(request):
        why = remote_refusal(request.method, request.url.path)
        if why:
            return JSONResponse({"detail": words.tr(why, core.cfg.lang)}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path in ("/", "/agent"):
        # the window loads only its own files and runs only its own script files (no script
        # written into a page can run); pictures may be data: (previews) or blob:
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; media-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'none'",
        )
    return resp


@app.exception_handler(StarletteHTTPException)
async def say_it_in_their_language(request: Request, exc: StarletteHTTPException):
    """A refusal or a problem that has a Spanish wording (datas.words) is given in the
    language Datas is set to; everything else goes out as it was written."""
    detail = exc.detail
    if isinstance(detail, str):
        detail = words.tr(detail, core.cfg.lang)
    return JSONResponse(
        {"detail": detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None)
    )


def ui_dir() -> Path:
    return Path(str(resources.files("datas.server").joinpath("ui")))


def ui_html() -> str:
    return (ui_dir() / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

UI_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".html": "text/html; charset=utf-8",
}
NO_STORE = {"Cache-Control": "no-store"}  # the app is local: always serve the installed files


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(ui_html(), headers=NO_STORE)


@app.get("/ui/{path:path}")
def ui_file(path: str):
    """Style sheet, scripts, fonts and icons of the window (all shipped with the app)."""
    root = ui_dir().resolve()
    p = (root / path).resolve()
    if root not in p.parents or not p.is_file() or p.suffix.lower() not in UI_TYPES:
        raise HTTPException(404, "no such file")
    cache = {"Cache-Control": "max-age=86400"} if p.suffix == ".woff2" else NO_STORE
    return FileResponse(str(p), media_type=UI_TYPES[p.suffix.lower()], headers=cache)


# ---------------------------------------------------------------------------
# Device + recommendation
# ---------------------------------------------------------------------------


@app.on_event("startup")
def _start_background() -> None:
    try:
        core.start_scheduler()
    except Exception:  # noqa: BLE001 - never block the server on this
        pass
    try:
        core.start_watch()
    except Exception:  # noqa: BLE001
        pass
    if core.cfg.link_enabled:  # be reachable by the user's linked devices from the start
        try:
            core.link_manager()
        except Exception:  # noqa: BLE001
            pass


@app.get("/api/status")
def status(request: Request) -> dict:
    st = core.status()
    pid = remote_peer(request)
    if pid:  # the window is being shown on a linked device: it adapts (no "open this file"…)
        peer = core.link_manager().peer_public(pid)
        st["remote"] = {
            "device": core.link_manager().name,
            "phone": peer["name"],  # who is looking: a phone, or another computer
            "kind": peer["kind"],
        }
    else:  # Datas opened its own window here and can move it aside for a picture of the screen
        st["own_window"] = core.window is not None
    return st


@app.get("/api/spec")
def spec(refresh: bool = False) -> dict:
    s = core.spec(refresh)
    return s.to_dict() | {"default_headroom": default_headroom(s)}


@app.get("/api/recommend")
def recommend(
    headroom: float | None = None,
    context: int | None = None,
    kv_bits: int = 16,
    want: str = "",
    role: str = "general",
    pool: bool = False,
    use: str = "",
    mode: str = "",
) -> dict:
    """Simple UI sends `use=text,images,coding,agents` + `mode=light|balanced|heavy`;
    the advanced UI/CLI may pass `want`, `headroom`, `role` directly."""
    uses = [u for u in use.split(",") if u]
    unsupported: list[str] = []
    wants = [w for w in want.split(",") if w]
    if uses:
        auto_want, unsupported = wants_for(uses)
        wants = sorted(set(wants) | set(auto_want))
        if "coding" in uses and role == "general":
            role = "coding"
        core.cfg.use_cases = ",".join(uses)
    if mode:
        headroom = headroom_for_mode(core.spec(), mode)
        core.cfg.resource_mode = mode
    if uses or mode:
        core.cfg.save()
    nodes = core.pool_nodes() if pool else None
    rec = core.recommendation(
        headroom=headroom,
        context=context,
        kv_bits=kv_bits,
        want=wants or None,
        role=role,
        pool_nodes=nodes,
    )
    out = rec.to_dict(core.cfg.lang)
    out["unsupported_use_cases"] = unsupported
    out["headroom"] = headroom if headroom is not None else core.cfg.headroom
    va = core.voice_status()["available"]
    out["abilities"] = [
        a.to_dict() for a in assess(core.spec(), rec, voice_available=va["stt"] and va["tts"])
    ]
    if "video" in uses:
        try:
            out["images"] = core.image_status()["choice"]
            out["video"] = core.image_status("video")["choice"]
        except Exception as e:  # noqa: BLE001
            out["images_error"] = str(e)
    if "sound" in uses:
        vs = core.voice_status()
        out["voice"] = vs.get("choice")
        if not (vs["available"]["stt"] and vs["available"]["tts"]):
            out["unsupported_use_cases"] = unsupported + ["sound"]
            out["voice_missing"] = vs["available"]["missing"]
    return out


# ---- images: making pictures with stable-diffusion.cpp -------------------------


class GenerateBody(BaseModel):
    prompt: str
    negative: str = ""
    width: int = 1024
    height: int = 1024
    steps: int | None = None
    seed: int = -1


class VideoBody(BaseModel):
    prompt: str
    negative: str = ""
    seconds: float | None = None
    width: int | None = None
    height: int | None = None
    seed: int = -1
    init_image_b64: str | None = None  # picture → video


@app.get("/api/images")
def images_status(kind: str = "image") -> dict:
    return core.image_status("video" if kind == "video" else "image")


@app.post("/api/images/setup")
def images_setup(kind: str = "image") -> dict:
    return core.start_images_job("video" if kind == "video" else "image").to_dict()


@app.post("/api/images/stop")
def images_stop() -> dict:
    core.stop_images()
    return {"ok": True}


@app.post("/api/images/generate")
def images_generate(body: GenerateBody) -> dict:
    w = max(256, min(2048, body.width - body.width % 64))
    h = max(256, min(2048, body.height - body.height % 64))
    steps = None if body.steps is None else max(1, min(50, body.steps))
    return core.start_generate_job(
        body.prompt.strip(), body.negative.strip(), w, h, steps, body.seed
    ).to_dict()


@app.post("/api/video/generate")
def video_generate(body: VideoBody) -> dict:
    return core.start_video_job(
        body.prompt.strip(),
        body.negative.strip(),
        body.seconds,
        body.width,
        body.height,
        body.seed,
        body.init_image_b64,
    ).to_dict()


MEDIA_TYPES = {
    ".png": "image/png",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".webp": "image/webp",
}


@app.get("/api/images/list")
def images_list() -> dict:
    from datas.engines import images as image_engine

    d = image_engine.images_dir()
    files = sorted(
        (f for f in d.iterdir() if f.suffix in MEDIA_TYPES),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:80]
    return {
        "images": [
            {
                "name": f.name,
                "when": f.stat().st_mtime,
                "bytes": f.stat().st_size,
                "video": f.suffix != ".png",
            }
            for f in files
        ]
    }


@app.get("/api/images/file/{name}")
def images_file(name: str):
    from fastapi.responses import FileResponse

    from datas.engines import images as image_engine

    p = (image_engine.images_dir() / Path(name).name).resolve()
    if not p.exists() or p.parent != image_engine.images_dir().resolve():
        raise HTTPException(404, "no such file")
    return FileResponse(str(p), media_type=MEDIA_TYPES.get(p.suffix, "application/octet-stream"))


@app.delete("/api/images/file/{name}")
def images_delete(name: str) -> dict:
    from datas.engines import images as image_engine

    p = image_engine.images_dir() / Path(name).name
    existed = p.exists()
    p.unlink(missing_ok=True)
    return {"removed": existed}


# ---- third-party apps (ComfyUI, FaceFusion, user recipes) -------------------------


@app.get("/api/apps")
def apps_list() -> dict:
    return {"apps": core.apps.list()}


@app.post("/api/apps/{app_id}/open")
def apps_open(app_id: str) -> dict:
    """Install if needed, start, open its window. One click."""
    try:
        return core.start_app_job(app_id).to_dict()
    except KeyError as e:
        raise HTTPException(404, "no such app") from e


@app.post("/api/apps/{app_id}/stop")
def apps_stop(app_id: str) -> dict:
    core.apps.stop(app_id)
    return {"ok": True}


@app.delete("/api/apps/{app_id}")
def apps_remove(app_id: str, keep_models: bool = False) -> dict:
    return {"removed": core.apps.remove(app_id, keep_models)}


# ---- voice: hearing (microphone → text) and speaking (text → audio) ----------


class SpeakBody(BaseModel):
    text: str
    lang: str = "en"
    voice: str | None = None
    speed: float = 1.0


class HearBody(BaseModel):
    lang: str | None = None


@app.get("/api/voice")
def voice_status() -> dict:
    return core.voice_status()


@app.post("/api/voice/install")
def voice_install() -> dict:
    return core.start_voice_install_job().to_dict()


@app.post("/api/voice/listen/start")
def voice_listen_start() -> dict:
    try:
        core.recorder.start()
    except Exception as e:  # noqa: BLE001 - no microphone, PortAudio missing, device busy
        raise HTTPException(500, f"Could not open the microphone: {e}") from e
    return {"recording": True}


@app.get("/api/voice/listen/level")
def voice_listen_level() -> dict:
    return {"recording": core.recorder.recording, "level": core.recorder.level()}


@app.post("/api/voice/listen/stop")
def voice_listen_stop(body: HearBody) -> dict:
    audio = core.recorder.stop()
    try:
        text = core.hear(audio, body.lang)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e)) from e
    return {"text": text, "seconds": round(len(audio) / 16000, 1)}


@app.post("/api/voice/hear")
async def voice_hear(request: Request, lang: str | None = None) -> dict:
    """Alternative to the server-side microphone: POST a 16-bit PCM WAV body (any sample rate)."""
    from datas.engines import voice as voice_engine

    data = await request.body()
    try:
        pcm = voice_engine.pcm_from_wav(data)
        text = core.hear(pcm, lang)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)) from e
    return {"text": text}


@app.post("/api/voice/speak")
def voice_speak(body: SpeakBody):

    from datas.engines import voice as voice_engine

    text = body.text.strip()
    if not text:
        raise HTTPException(400, "nothing to say")
    try:
        wav = voice_engine.speak(text[:4000], body.lang, body.voice, body.speed)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e)) from e
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@app.get("/api/catalog")
def catalog() -> dict:
    c = core.catalog
    return {
        "generated": c.generated,
        "notes": c.notes,
        "models": [m.model_dump(exclude_none=True) for m in c.models],
    }


class CatalogEntry(BaseModel):
    entry: dict[str, Any]


@app.post("/api/catalog")
def catalog_add(body: CatalogEntry) -> dict:
    m = add_user_model(body.entry)
    return m.model_dump(exclude_none=True)


@app.post("/api/catalog/reload")
def catalog_reload() -> dict:
    reload_catalog()
    return {"ok": True, "models": len(core.catalog.models)}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class Settings(BaseModel):
    headroom: float | None = None
    context: int | None = None
    lang: str | None = None
    pool_nodes: str | None = None
    backend: str | None = None
    voice_stt_model: str | None = None
    voice_tts_voice: str | None = None
    voice_speak_answers: bool | None = None
    image_backend: str | None = None
    theme: str | None = None
    idle_sleep_min: int | None = None
    allow_local_fetch: bool | None = None


@app.get("/api/settings")
def settings_get() -> dict:
    c = core.cfg
    return {
        "headroom": c.headroom,
        "headroom_min_gib": c.headroom_min_gib,
        "context": c.context,
        "lang": c.lang,
        "pool_nodes": c.pool_nodes,
        "backend": c.backend,
        "llamacpp_tag": c.llamacpp_tag,
        "ui_port": c.ui_port,
        "llama_port": c.llama_port,
        "rpc_port": c.rpc_port,
        "voice_stt_model": c.voice_stt_model,
        "voice_tts_voice": c.voice_tts_voice,
        "voice_speak_answers": c.voice_speak_answers,
        "image_backend": c.image_backend,
        "theme": c.theme,
        "idle_sleep_min": c.idle_sleep_min,
        "allow_local_fetch": c.allow_local_fetch,
    }


@app.post("/api/settings")
def settings_set(body: Settings) -> dict:
    c = core.cfg
    if body.headroom is not None:
        c.headroom = max(0.05, min(0.8, body.headroom))
    if body.context is not None:
        c.context = max(1024, min(262144, body.context))
    if body.lang is not None:
        c.lang = body.lang
    if body.pool_nodes is not None:
        c.pool_nodes = body.pool_nodes
    if body.backend is not None:
        c.backend = body.backend
    if body.voice_stt_model is not None:
        c.voice_stt_model = body.voice_stt_model
    if body.voice_tts_voice is not None:
        c.voice_tts_voice = body.voice_tts_voice
    if body.voice_speak_answers is not None:
        c.voice_speak_answers = body.voice_speak_answers
    if body.image_backend is not None and body.image_backend in (
        "auto",
        "cpu",
        "vulkan",
        "cuda",
        "rocm",
        "metal",
    ):
        c.image_backend = body.image_backend
    if body.theme in ("auto", "day", "night"):
        c.theme = body.theme
    if body.idle_sleep_min is not None:
        c.idle_sleep_min = max(0, min(24 * 60, body.idle_sleep_min))
    if body.allow_local_fetch is not None:
        c.allow_local_fetch = body.allow_local_fetch
    c.save()
    return settings_get()


@app.get("/api/notice")
def notice() -> dict:
    """One thing the window should tell the user (an engine that stopped, a device that went
    offline…). Returned once."""
    n, core.notice = core.notice, None
    return {"notice": n}


# ---------------------------------------------------------------------------
# Jobs: install / run / stop / bench
# ---------------------------------------------------------------------------


class InstallBody(BaseModel):
    model_id: str
    quant: str
    with_vision: bool = False


class RunBody(BaseModel):
    model_id: str
    quant: str
    context: int | None = None
    kv_bits: int = 16
    pool: bool = False
    with_vision: bool = False
    with_voice: bool = False
    starter: bool = True


class RunCustomBody(BaseModel):
    path: str
    context: int | None = None
    kv_bits: int = 16


@app.post("/api/install")
def install(body: InstallBody) -> dict:
    return core.start_install_job(body.model_id, body.quant, body.with_vision).to_dict()


@app.post("/api/run")
def run(body: RunBody) -> dict:
    return core.start_run_job(
        body.model_id,
        body.quant,
        body.context,
        body.kv_bits,
        body.pool,
        body.with_vision,
        body.with_voice,
        body.starter,
    ).to_dict()


@app.post("/api/starter")
def starter() -> dict:
    """The small starter AI (about 0.4 GB): fetched and started at the device test, so the
    guide can answer questions — about AI, about Datas, from every document Datas ships —
    before the person chooses and downloads a bigger AI. Nothing happens if an AI is running."""
    from datas.orchestrator import STARTER_ID, STARTER_QUANT

    if core.server.running():
        return {"skipped": "an AI is already running"}
    return core.start_run_job(
        STARTER_ID, STARTER_QUANT, 4096, 16, False, False, False, False
    ).to_dict()


@app.post("/api/run-custom")
def run_custom(body: RunCustomBody) -> dict:
    job = core._job("run", f"Run {Path(body.path).name}")
    return core._run_job(
        job, lambda j: core.run_custom(body.path, body.context, body.kv_bits, job=j)
    ).to_dict()


@app.post("/api/stop")
def stop() -> dict:
    core.stop()
    return {"ok": True}


@app.post("/api/bench")
def bench_start() -> dict:
    return core.start_bench_job().to_dict()


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    j = core.jobs.get(job_id)
    if not j:
        raise HTTPException(404, "no such job")
    return j.to_dict()


@app.get("/api/jobs")
def jobs() -> list[dict]:
    return [
        j.to_dict() for j in sorted(core.jobs.values(), key=lambda j: j.started, reverse=True)[:20]
    ]


@app.get("/api/logs")
def logs(lines: int = 80) -> dict:
    return {"llama_server": core.server.log_tail(lines)}


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class ProviderBody(BaseModel):
    name: str
    base_url: str = ""
    api_key: str = ""
    model: str = ""


@app.get("/api/providers")
def providers() -> dict:
    rpc = core.server.state.rpc
    return {
        "active": core.cfg.provider,
        "presets": PRESETS,
        "providers": [
            p.to_public_dict() for p in all_providers(core.cfg, core.server.running(), rpc)
        ],
    }


@app.post("/api/providers")
def providers_add(body: ProviderBody) -> dict:
    if body.name in ("local", "pool"):
        raise HTTPException(400, "reserved name")
    r = set_remote(core.cfg, body.name, body.base_url, body.api_key, body.model)
    return {"ok": True, "name": r.name}


@app.delete("/api/providers/{name}")
def providers_del(name: str) -> dict:
    return {"ok": remove_remote(core.cfg, name)}


class ActiveBody(BaseModel):
    name: str


@app.post("/api/providers/active")
def providers_active(body: ActiveBody) -> dict:
    if body.name not in ("local", "pool") and core.cfg.remote(body.name) is None:
        raise HTTPException(404, "unknown provider")
    core.cfg.provider = body.name
    core.cfg.save()
    return {"active": core.cfg.provider}


# ---------------------------------------------------------------------------
# Everyday tools (datas.tools): recording → text, text → audio, long documents
# ---------------------------------------------------------------------------


@app.post("/api/tools/transcribe")
async def tools_transcribe(request: Request, name: str = "recording.wav", lang: str | None = None):
    """Send the recording as the request body (any audio or video file)."""
    import tempfile

    from datas import tools

    suffix = Path(name).suffix.lower() or ".wav"
    if suffix not in tools.AUDIO_VIDEO:
        raise HTTPException(400, "Give an audio or video file (mp3, wav, m4a, mp4, mkv…).")
    tmp = tempfile.NamedTemporaryFile(prefix="datas-rec-", suffix=suffix, delete=False)
    size = 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            tmp.write(chunk)
    finally:
        tmp.close()
    if size == 0:
        Path(tmp.name).unlink(missing_ok=True)
        raise HTTPException(400, "The file arrived empty.")

    def run(j) -> dict:  # noqa: ANN001
        try:
            return tools.transcribe_file(core, Path(tmp.name), name, lang, j)
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    return _update_job("Recording to text", run) | {"kind": "tool"}


class SpeakFileBody(BaseModel):
    text: str
    lang: str | None = None
    voice: str | None = None
    title: str = ""


@app.post("/api/tools/speak")
def tools_speak(body: SpeakFileBody) -> dict:
    from datas import tools

    lang = body.lang or core.cfg.lang
    return _update_job(
        "Text to audio",
        lambda j: tools.speak_to_file(core, body.text, lang, body.voice, body.title, j),
    )


class LongBody(BaseModel):
    mode: str = "summary"  # summary | translate
    text: str = ""
    name: str = ""
    content_base64: str = ""
    lang: str | None = None  # language of the result
    devices: bool = False  # share the parts with the AIs of my linked devices


@app.get("/api/tools/long/helpers")
def tools_long_helpers() -> dict:
    """Linked devices whose own AI could take parts of a long document right now."""
    from datas import tools

    return {"devices": [{"name": h["name"], "ai": h["ai"]} for h in tools.helpers(core)]}


@app.post("/api/tools/long")
def tools_long(body: LongBody) -> dict:
    """Summarise or translate a document of any length, piece by piece — with ``devices``,
    this device and the linked ones each take the next part at the same time."""
    from datas import tools

    text, title = body.text, ""
    if body.content_base64:
        try:
            text = docs.extract_text(
                body.name, _decode(FileBody(name=body.name, content_base64=body.content_base64))
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        title = Path(body.name).stem
    if not text.strip():
        raise HTTPException(400, "There is no text to work on.")
    if body.mode not in ("summary", "translate"):
        raise HTTPException(400, "mode must be summary or translate")
    prov = active_provider(core.cfg, core.server.running(), core.server.state.rpc)
    ctx = _ctx_tokens(prov)
    lang = body.lang or core.cfg.lang
    hands = tools.helpers(core) if body.devices else []
    return _update_job(
        "Long document",
        lambda j: tools.long_document(core, text, body.mode, lang, ctx, title, j, hands),
    )


@app.post("/api/programs/artcraft/get")
def programs_get_artcraft() -> dict:
    """Download the ArtCraft Launcher for this computer (checked against the checksums published
    with the release) and open it. The launcher installs and updates the Craft apps."""
    from datas import programs, updates

    def run(j) -> dict:  # noqa: ANN001
        asset = programs.artcraft_launcher_asset()
        path = updates.download_installer(asset, j)
        return {
            "path": str(path),
            "opened": updates.open_installer(path),
            "version": asset.get("version"),
        }

    return _update_job("ArtCraft Launcher", run)


# ---------------------------------------------------------------------------
# Hardware around this computer and on its network (datas.things, docs/HARDWARE.md):
# cameras, the screen, printers, boards on serial ports, MQTT, Home Assistant, Modbus.
# Everything under /api/things is refused from a linked phone (REMOTE_REFUSED).
# ---------------------------------------------------------------------------


def _thing(fn, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
    """Run a hardware call; a problem becomes a sentence the window can show."""
    from datas.things import ThingError

    try:
        return fn(*args, **kwargs)
    except ThingError as e:
        raise HTTPException(409, e.say(core.cfg.lang)) from e


def _picture_out(data: bytes) -> dict:
    from datas.things import local

    w, h = local.picture_size(data)
    return {
        "image": "data:image/jpeg;base64," + base64.b64encode(data).decode(),
        "width": w,
        "height": h,
        "bytes": len(data),
    }


@app.get("/api/things")
def things_list() -> dict:
    """What is plugged into this computer, the connections that are set up (without their
    secrets), and whether the AI in use can look at pictures."""
    from datas import things

    return things.inventory(core.cfg.lang) | {
        "settings": things.public_settings(),
        "vision": core.ai_sees(),
    }


@app.get("/api/things/ffmpeg")
def things_ffmpeg_state() -> dict:
    """Is FFmpeg here, and how big is the download if it is not (a quick answer, for the
    camera button of a chat)."""
    from datas import things

    return things.ffmpeg_state()


@app.post("/api/things/ffmpeg")
def things_get_ffmpeg() -> dict:
    """Fetch FFmpeg once (it reads cameras and recordings); checked against its checksum."""
    from datas import programs

    def run(j) -> dict:  # noqa: ANN001
        j.say(
            words.tr(
                "Getting FFmpeg, the free program that reads cameras and recordings…",
                core.cfg.lang,
            )
        )
        return {"path": programs.fetch_ffmpeg(j.progress)}

    return _update_job("FFmpeg", run) | {"kind": "tool"}


class PhotoBody(BaseModel):
    camera: str | None = None


@app.post("/api/things/camera/photo")
def things_photo(body: PhotoBody) -> dict:
    """One picture from a camera of this computer, for the person to look at or attach."""
    from datas.things import local

    return _picture_out(_thing(local.photo, body.camera))


class ScreenBody(BaseModel):
    hide: bool = False  # take Datas' own window out of the way first
    wait: float = 0.0  # seconds to wait before the picture (when the window cannot be hidden)


@app.post("/api/things/screen")
def things_screen(body: ScreenBody | None = None) -> dict:
    """A picture of what is on the screen right now. For a chat the person wants what is
    *behind* Datas: the window steps aside for a moment when Datas opened it itself."""
    import time

    from datas.things import local

    body = body or ScreenBody()
    win = core.window if body.hide else None
    if win is not None:
        try:
            win.hide()
            time.sleep(0.7)  # let the system redraw what was underneath
        except Exception:  # noqa: BLE001 - a window that cannot hide: take the picture anyway
            win = None
    elif body.wait > 0:
        time.sleep(min(body.wait, 5.0))
    try:
        return _picture_out(_thing(local.screenshot))
    finally:
        if win is not None:
            try:
                win.show()
            except Exception:  # noqa: BLE001
                pass


class PrintBody(BaseModel):
    markdown: str | None = None  # an answer: it becomes a PDF first
    title: str = ""
    path: str | None = None  # or a file Datas saved earlier
    printer: str | None = None
    copies: int = 1
    lang: str | None = None


@app.post("/api/things/print")
def things_print(body: PrintBody) -> dict:
    """Print an answer or a file Datas saved. The answer becomes a PDF first (plain text on a
    Windows computer without LibreOffice, which cannot print a PDF by itself); that file is
    kept in the Datas folder like any saved answer."""
    from datas.things import local

    try:
        if body.markdown and body.markdown.strip():
            path = exporter.export(
                body.markdown, local.answer_format(), body.title, body.lang or core.cfg.lang
            )
        elif body.path:
            path = exporter.allowed(body.path)
        else:
            raise ValueError("There is nothing to print.")
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e)) from e
    said = _thing(local.print_file, path, body.printer, body.copies)
    return {"said": words.say(said, core.cfg.lang), "path": str(path), "name": path.name}


class SerialBody(BaseModel):
    port: str
    seconds: float = 3.0
    baud: int = 9600


@app.post("/api/things/serial")
def things_serial(body: SerialBody) -> dict:
    """Listen to a board or instrument on a serial port for a few seconds (nothing is sent;
    sending is the agent's, with its own switch and question)."""
    from datas.things import local

    seconds = max(0.5, min(body.seconds, 15.0))
    return {"text": _thing(local.serial_talk, body.port, None, seconds, body.baud)}


@app.get("/api/things/around")
def things_around(seconds: float = 3.0) -> dict:
    """Devices on this network that announce themselves (nothing is probed)."""
    from datas.things import net

    found = net.around(seconds)
    for d in found:
        d["kind"] = words.tr(d["kind"], core.cfg.lang)
    return {"devices": found}


class ThingsSettingsBody(BaseModel):
    mqtt: dict[str, Any] | None = None
    home_assistant: dict[str, Any] | None = None
    modbus: list[dict[str, Any]] | None = None


@app.post("/api/things/settings")
def things_settings(body: ThingsSettingsBody) -> dict:
    """Save the addresses of the person's own broker, Home Assistant and Modbus devices. A
    password or token left empty keeps the one already saved; "-" removes it."""
    from datas import things

    try:
        return things.save_settings(body.model_dump(exclude_none=True))
    except (TypeError, ValueError) as e:
        raise HTTPException(
            400, words.tr("That could not be saved: {why}", core.cfg.lang, why=str(e))
        ) from e


class ThingsCheckBody(BaseModel):
    what: str  # mqtt | home_assistant | modbus
    name: str | None = None  # which Modbus device


@app.post("/api/things/check")
def things_check(body: ThingsCheckBody) -> dict:
    """Try a connection that was set up and say in a sentence how it went."""
    from datas.things import ThingError, net

    try:
        return {"ok": True, "detail": net.check(body.what, body.name).say(core.cfg.lang)}
    except ThingError as e:
        return {"ok": False, "detail": e.say(core.cfg.lang)}


# ---------------------------------------------------------------------------
# Programs on this computer the agent can use, and connections to their own tools (MCP)
# ---------------------------------------------------------------------------


class McpBody(BaseModel):
    name: str
    command: str
    args: list[str] = []


class OpenProgramBody(BaseModel):
    path: str | None = None


@app.get("/api/programs")
def programs_list(lang: str | None = None) -> dict:
    from datas import programs

    return programs.listing(lang or core.cfg.lang)


@app.post("/api/programs/{pid}/open")
def programs_open(pid: str, body: OpenProgramBody) -> dict:
    from datas import programs

    file = None
    if body.path:
        try:
            file = str(exporter.allowed(body.path))
        except OSError as e:
            raise HTTPException(400, str(e)) from e
    try:
        programs.open_program(pid, file)
    except (RuntimeError, OSError) as e:
        raise HTTPException(400, str(e)) from e
    return {"opened": True}


@app.post("/api/mcp")
def mcp_add(body: McpBody) -> dict:
    """Add a connection to a program that offers its own tools (Model Context Protocol)."""
    from datas import mcp

    try:
        return mcp.save_user_server(body.name, body.command, body.args)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/mcp/{name}")
def mcp_remove(name: str) -> dict:
    from datas import mcp

    return {"removed": mcp.remove_user_server(name)}


@app.post("/api/mcp/{name}/test")
def mcp_test(name: str) -> dict:
    """Start the program, ask which tools it offers, stop it. Shows the user that it works."""
    from datas import mcp
    from datas.config import agent_workspace

    spec = mcp.all_servers().get(name)
    if not spec:
        raise HTTPException(404, "no such connection")
    srv = mcp.McpServer(
        name, spec["command"], mcp.fill(spec["args"], agent_workspace()), spec.get("env")
    )
    try:
        srv.start(timeout=20)
        return {
            "ok": True,
            "server": (srv.info.get("serverInfo") or {}),
            "tools": [
                {"name": t["name"], "description": str(t.get("description", ""))[:200]}
                for t in srv.tools
            ],
        }
    except mcp.McpError as e:
        return {"ok": False, "error": str(e)}
    finally:
        srv.stop()


# ---------------------------------------------------------------------------
# Updates and going back (datas.updates). Network only when the user asks.
# ---------------------------------------------------------------------------


class TagBody(BaseModel):
    tag: str | None = None


class AppUpdateBody(BaseModel):
    version: str | None = None  # None = the newest; or an earlier one to go back


@app.get("/api/updates")
def updates_installed() -> dict:
    from datas import updates

    return updates.installed(core)


@app.post("/api/updates/check")
def updates_check() -> dict:
    from datas import updates

    return updates.check(core)


def _update_job(title: str, fn) -> dict:  # noqa: ANN001
    job = core._job("update", title)  # noqa: SLF001
    return core._run_job(job, fn).to_dict()  # noqa: SLF001


@app.post("/api/updates/engine")
def updates_engine(body: TagBody) -> dict:
    """Install a newer engine beside the current one, try it, go back by itself if it fails."""
    from datas import updates
    from datas.runtime import llamacpp

    tag = body.tag or llamacpp.latest_tag()
    if not tag:
        raise HTTPException(502, "Could not find the newest engine version (no connection?)")
    return _update_job(f"Engine {tag}", lambda j: updates.switch_engine(core, tag, j))


@app.post("/api/updates/engine/rollback")
def updates_engine_rollback() -> dict:
    from datas import updates

    return _update_job("Engine: previous version", lambda j: updates.rollback_engine(core, j))


@app.post("/api/updates/engine/cleanup")
def updates_engine_cleanup() -> dict:
    from datas import updates

    return updates.remove_old_engines(core)


@app.post("/api/updates/images")
def updates_images(body: TagBody) -> dict:
    from datas import updates

    if not body.tag:
        raise HTTPException(400, "which version?")
    return _update_job(
        f"Image engine {body.tag}", lambda j: updates.switch_images(core, body.tag, j)
    )


@app.post("/api/updates/images/rollback")
def updates_images_rollback() -> dict:
    from datas import updates

    return _update_job("Image engine: previous version", lambda j: updates.rollback_images(core, j))


@app.post("/api/updates/catalog")
def updates_catalog() -> dict:
    from datas import updates

    try:
        return updates.update_catalog()
    except Exception as e:  # noqa: BLE001 - no connection, malformed list
        raise HTTPException(502, f"The list of AIs could not be updated: {e}") from e


@app.delete("/api/updates/catalog")
def updates_catalog_rollback() -> dict:
    from datas import updates

    return updates.rollback_catalog()


@app.post("/api/updates/app")
def updates_app(body: AppUpdateBody) -> dict:
    """Download the installer of the newest release (or of an earlier one, to go back) and open
    it. The installer keeps AIs, chats and settings."""
    from datas import updates

    def run(j) -> dict:  # noqa: ANN001
        with httpx.Client(timeout=30, follow_redirects=True, headers=updates._headers()) as c:  # noqa: SLF001
            info = updates.check_app(c)
        pick = None
        if body.version:
            pick = next(
                (r for r in [info["latest"], *info["older"]] if r and r["version"] == body.version),
                None,
            )
        else:
            pick = info["latest"]
        if not pick:
            raise RuntimeError("That version was not found on the releases page.")
        if not pick["asset"]:
            raise RuntimeError(
                f"Release {pick['version']} has no installer for this computer. See {pick['page']}"
            )
        path = updates.download_installer(pick["asset"], j)
        how = updates.open_installer(path)
        return {"version": pick["version"], "path": str(path), "opened": how, "page": pick["page"]}

    return _update_job("Datas update", run)


# ---------------------------------------------------------------------------
# Linked devices (datas.link): pairing, presence, shared memory, chat sync
# ---------------------------------------------------------------------------


def _link():  # noqa: ANN202
    from datas.link import LinkError

    try:
        return core.link_manager()
    except LinkError as e:
        raise HTTPException(400, e.say(core.cfg.lang)) from e
    except Exception as e:  # noqa: BLE001 - e.g. the cryptography package is missing
        raise HTTPException(500, f"Device linking is not available on this copy: {e}") from e


def _link_call(fn, *args):  # noqa: ANN001, ANN202
    from datas.link import LinkError

    try:
        return fn(*args)
    except LinkError as e:
        raise HTTPException(400, e.say(core.cfg.lang)) from e


class OnBody(BaseModel):
    on: bool


class PairBody(BaseModel):
    address: str
    code: str


class LinkOptions(BaseModel):
    share_memory: bool | None = None
    sync_chats: bool | None = None
    device_name: str | None = None


@app.get("/api/link")
def link_state(refresh: bool = False) -> dict:
    lm = _link()
    if refresh:
        import threading

        threading.Thread(target=lm.refresh, daemon=True).start()
    return lm.state()


@app.post("/api/link/enable")
def link_enable(body: OnBody) -> dict:
    return _link_call(_link().enable, body.on)


@app.post("/api/link/pairing")
def link_pairing_begin() -> dict:
    """Show an address and a one-time code on this device (valid for ten minutes)."""
    return _link_call(_link().begin_pairing)


@app.delete("/api/link/pairing")
def link_pairing_cancel() -> dict:
    _link().cancel_pairing()
    return _link().state()


@app.post("/api/link/pair")
def link_pair(body: PairBody) -> dict:
    """Type here the address and the code shown on the other device."""
    lm = _link()
    peer = _link_call(lm.pair, body.address, body.code)
    try:
        lm.refresh()
    except Exception:  # noqa: BLE001
        pass
    return {"peer": lm.peer_public(peer["id"]), "state": lm.state()}


@app.delete("/api/link/peers/{pid}")
def link_unpair(pid: str) -> dict:
    return {"removed": _link().unpair(pid)}


class LinkPeerOptions(BaseModel):
    window: bool | None = None  # may that device open this device's Datas?


@app.post("/api/link/peers/{pid}")
def link_peer_options(pid: str, body: LinkPeerOptions) -> dict:
    return _link_call(_link().set_peer, pid, body.window)


class LinkOpen(BaseModel):
    show: bool = True  # open it in a window of its own; False: only say where it is


@app.post("/api/link/peers/{pid}/open")
def link_open(pid: str, body: LinkOpen | None = None) -> dict:
    """The Datas of another computer of yours, shown on this one through the encrypted link
    (for a computer without a screen, for example). That computer has to allow it, and treats
    what arrives this way like a phone's requests."""
    out = _link_call(_link().open_window, pid)
    out["shown"] = False
    if body is None or body.show:
        try:
            core.open_url_window(out["url"], f"{out['name']} — Datas.ar")
            out["shown"] = True
        except OSError:
            pass  # no window could be opened here: the address is still good in a browser
    return out


@app.post("/api/link/options")
def link_options(body: LinkOptions) -> dict:
    lm = _link()
    if body.share_memory is not None:
        core.cfg.link_share_memory = body.share_memory
    if body.sync_chats is not None:
        core.cfg.link_sync_chats = body.sync_chats
        lm.chats_changed()
    core.cfg.save()
    if body.device_name:
        lm.rename(body.device_name)
    return lm.state()


@app.post("/api/link/sync")
def link_sync() -> dict:
    lm = _link()
    try:
        lm.refresh()
    except Exception:  # noqa: BLE001
        pass
    return _link_call(lm.sync_now)


@app.get("/api/link/nearby")
def link_nearby() -> dict:
    """Devices on this network with Datas linking switched on (names only)."""
    return {"devices": _link().nearby()}


@app.post("/api/link/use/{pid}")
def link_use(pid: str) -> dict:
    """Chat with the AI that is running on a linked device."""
    lm = _link()
    if pid not in {p["id"] for p in lm.state()["peers"]}:
        raise HTTPException(404, "that device is not linked")
    core.cfg.provider = f"link:{pid}"
    core.cfg.save()
    return {"active": core.cfg.provider}


@app.api_route("/link/{pid}/v1/{path:path}", methods=["GET", "POST"])
async def link_v1(pid: str, path: str, request: Request):
    """Local door to the AI on a linked device; the request travels over mutual TLS."""
    from datas.link import LinkError

    lm = _link()
    body = None
    if request.method == "POST":
        try:
            body = json.loads(await request.body() or b"{}")
        except json.JSONDecodeError:
            raise HTTPException(400, "bad request body") from None
    try:
        reader, writer, head = await lm.open_v1(pid, path, body)
    except LinkError as e:
        return JSONResponse({"error": {"message": str(e), "type": "datas_link"}}, status_code=502)
    except Exception as e:  # noqa: BLE001 - unreachable, timed out, TLS refused
        return JSONResponse(
            {
                "error": {
                    "message": f"The linked device did not answer ({type(e).__name__}).",
                    "type": "datas_link",
                }
            },
            status_code=502,
        )

    async def gen():
        try:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            writer.close()

    return StreamingResponse(
        gen(),
        status_code=int(head.get("status", 200)),
        media_type=head.get("content_type") or "application/json",
    )


# ---------------------------------------------------------------------------
# Pool
# ---------------------------------------------------------------------------


@app.get("/api/pool/nodes")
def pool_nodes(refresh: bool = True, seconds: float = 2.5) -> dict:
    nodes = core.pool_nodes(refresh=refresh, seconds=seconds)
    return {
        "nodes": [n.to_dict() for n in nodes],
        "local_tag": core.cfg.llamacpp_tag,
        "worker_command": f"datas pool worker  # on each other device (port {core.cfg.rpc_port})",
    }


# ---------------------------------------------------------------------------
# Simple-UI extras: sources, privacy, library, chats, memory, context, skills, agent, window
# ---------------------------------------------------------------------------


_window_report: dict | None = None


@app.post("/api/selfcheck")
async def selfcheck_report(request: Request) -> dict:
    """The window, opened with ``?selfcheck``, says what it showed (see datas/desktop.py)."""
    global _window_report
    body = await request.json()
    _window_report = body if isinstance(body, dict) else None
    return {"ok": True}


@app.get("/api/selfcheck")
def selfcheck_read() -> dict:
    return {"report": _window_report}


@app.get("/api/hello")
def hello() -> dict:
    """Called once per app start by the UI: says what was found from an earlier install."""
    from datas import __version__ as ver

    prev = core.cfg.last_version
    first_run_of_version = prev != ver
    if first_run_of_version:
        try:  # the settings as the previous version left them, in case the user goes back
            from datas import updates

            updates.backup_settings(prev)
        except Exception:  # noqa: BLE001
            pass
        core.cfg.last_version = ver
        core.cfg.save()
    models = library.installed()
    return {
        "version": ver,
        "upgraded_from": prev if (first_run_of_version and prev) else None,
        "reinstalled": first_run_of_version and (bool(models) or core.cfg.onboarded),
        "models": len(models),
        "chats": 0 if core.cfg.forget else len(chats.list_chats()),
        "notes": bool(chats.read_memory().strip()) and not core.cfg.forget,
    }


@app.get("/api/sources")
def sources() -> dict:
    return json.loads(
        Path(str(resources.files("datas").joinpath("sources.json"))).read_text(encoding="utf-8")
    )


class PrivacyBody(BaseModel):
    memory_mode: str | None = None  # remember | forget
    keep_logs: bool | None = None
    internet_default: bool | None = None
    onboarded: bool | None = None
    lang: str | None = None


@app.get("/api/privacy")
def privacy_get() -> dict:
    c = core.cfg
    return {
        "memory_mode": c.memory_mode,
        "keep_logs": c.keep_logs,
        "internet_default": c.internet_default,
        "onboarded": c.onboarded,
        "lang": c.lang,
        "chats": len(chats.list_chats()) if not c.forget else 0,
        "memory_chars": len(chats.read_memory()),
    }


@app.post("/api/privacy")
def privacy_set(body: PrivacyBody) -> dict:
    c = core.cfg
    if body.memory_mode in ("remember", "forget"):
        c.memory_mode = body.memory_mode
        if body.memory_mode == "forget":
            c.keep_logs = False
    if body.keep_logs is not None and not c.forget:
        c.keep_logs = body.keep_logs
    if body.internet_default is not None:
        c.internet_default = body.internet_default
    if body.onboarded is not None:
        c.onboarded = body.onboarded
    if body.lang in ("en", "es"):
        c.lang = body.lang
    c.save()
    return privacy_get()


@app.post("/api/privacy/wipe")
def privacy_wipe() -> dict:
    """Delete chats, notes and context files. Models stay (remove them from the library)."""
    return chats.wipe_everything()


@app.get("/api/library")
def library_list(lang: str | None = None) -> dict:
    """Installed AIs with a plain summary, this device's cost and other versions."""
    try:
        items = library.details(core, lang or core.cfg.lang)
    except Exception:  # noqa: BLE001 - never lose the list over the extras
        items = library.installed()
    return {"installed": items, "running": core.server.state.to_dict()}


class ModelIdBody(BaseModel):
    model_id: str


@app.post("/api/library/shortcut")
def library_shortcut(body: ModelIdBody) -> dict:
    items = {i["model_id"]: i for i in library.installed()}
    it = items.get(body.model_id)
    if not it:
        raise HTTPException(404, "not installed")
    p = shortcuts.create_model_shortcut(body.model_id, it["name"])
    library.set_shortcut(body.model_id, str(p))
    return {"shortcut": str(p)}


@app.post("/api/shortcut/app")
def app_shortcut() -> dict:
    return {"shortcut": str(shortcuts.create_app_shortcut())}


@app.delete("/api/library/{model_id:path}")
def library_remove(model_id: str) -> dict:
    if core.server.running() and core.server.state.model_id == model_id:
        core.stop()
    return library.remove(model_id)


class Attachment(BaseModel):
    name: str
    text: str = ""


class ChatBody(BaseModel):
    messages: list[dict[str, Any]]
    internet: bool = False
    skill: str | None = None  # helper id ("assistant" is accepted too)
    assistant: str | None = None
    attachments: list[Attachment] = []
    lang: str | None = None
    chat_id: str | None = None


def _ctx_tokens(prov) -> int:  # noqa: ANN001 - Provider
    """Working memory of the AI that will answer: the running engine's, else an assumption."""
    if prov.kind in ("local", "pool"):
        args = core.server.state.args or []
        for i, a in enumerate(args[:-1]):
            if a in ("-c", "--ctx-size"):
                try:
                    return int(args[i + 1])
                except ValueError:
                    break
        return core.cfg.context
    if prov.kind == "linked" and core.link is not None:
        info = (core.link.status.get(prov.name[5:], {}).get("info") or {}).get("ai") or {}
        return int(info.get("context") or 8192)
    return chat_engine.REMOTE_CONTEXT


def _canned(text: str) -> StreamingResponse:
    async def gen():
        yield f"data: {json.dumps({'type': 'token', 'text': text}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@app.post("/api/chat")
async def chat(body: ChatBody):
    helper = body.assistant or body.skill
    lang = body.lang or core.cfg.lang
    core.touch()
    prov = active_provider(core.cfg, core.server.running(), core.server.state.rpc)
    local = prov.kind in ("local", "pool")
    if local and not core.server.running() and core.can_wake():
        # the AI was put to sleep after a quiet spell (or the app restarted): wake the same one
        try:
            await run_in_threadpool(core.wake)
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                {"error": "wake_failed", "message": f"The AI could not be started again: {e}"},
                status_code=503,
            )
        prov = active_provider(core.cfg, core.server.running(), core.server.state.rpc)
    if local and not core.server.running() and helper == "guide":
        from datas import guide

        last = next(
            (
                chat_engine.text_of(m.get("content", ""))
                for m in reversed(body.messages)
                if m.get("role") == "user"
            ),
            "",
        )
        return _canned(guide.offline_answer(core, last, lang))
    if local and not core.server.running():
        return JSONResponse(
            {"error": "no_model", "message": "No AI is running yet."}, status_code=503
        )
    extra = None
    if helper == "guide":
        from datas import guide

        try:
            extra = guide.build(core, lang)
        except Exception as e:  # noqa: BLE001 - the guide must never break the chat
            extra = f"You are the Datas guide. (Device facts unavailable: {e})"
    req = chat_engine.ChatRequest(
        messages=body.messages,
        internet=body.internet,
        skill=helper,
        lang=lang,
        extra=extra,
        attachments=[a.model_dump() for a in body.attachments],
        ctx_tokens=_ctx_tokens(prov),
        allow_local=core.cfg.allow_local_fetch,
    )

    async def stream():
        try:
            async for chunk in chat_engine.stream_chat(core.cfg, prov, req):
                core.touch()
                yield chunk
        finally:
            core.touch()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class SaveChatBody(BaseModel):
    chat_id: str | None = None
    messages: list[dict[str, Any]]
    model: str = ""
    model_name: str = ""
    skill: str | None = None
    attachments: list[Attachment] | None = None
    provider: str | None = None


class RenameBody(BaseModel):
    title: str


def _model_name(model_id: str | None) -> str:
    if not model_id:
        return ""
    try:
        return core.catalog.get(model_id).name
    except Exception:  # noqa: BLE001 - custom file or a remote provider's model
        return Path(model_id.split(":", 1)[-1]).stem if model_id.startswith("custom:") else model_id


@app.get("/api/chats")
def chats_list(q: str | None = None) -> dict:
    """All saved chats, newest first; ``q`` searches titles and messages."""
    return {"chats": [] if core.cfg.forget else chats.list_chats(q), "forget": core.cfg.forget}


@app.post("/api/chats")
def chats_save(body: SaveChatBody) -> dict:
    model = body.model or core.cfg.model_id or ""
    cid = chats.save_chat(
        core.cfg,
        body.chat_id,
        body.messages,
        model,
        body.model_name or _model_name(model),
        body.skill,
        None if body.attachments is None else [a.model_dump() for a in body.attachments],
        body.provider if body.provider is not None else core.cfg.provider,
    )
    if cid:
        core.chat_saved(cid)
    return {"chat_id": cid, "saved": cid is not None}


@app.patch("/api/chats/{chat_id}")
def chats_rename(chat_id: str, body: RenameBody) -> dict:
    if not chats.rename_chat(chat_id, body.title):
        raise HTTPException(404, "no such chat")
    core.chat_saved(chat_id)
    return {"renamed": True}


@app.get("/api/chats/{chat_id}")
def chats_get(chat_id: str) -> dict:
    d = chats.load_chat(chat_id)
    if not d:
        raise HTTPException(404, "no such chat")
    return d


@app.delete("/api/chats/{chat_id}")
def chats_del(chat_id: str) -> dict:
    ok = chats.delete_chat(chat_id)
    if ok:
        core.chat_saved(chat_id)
    return {"deleted": ok}


@app.post("/api/chat/learn")
async def chat_learn(body: SaveChatBody) -> dict:
    """End of session in 'remember' mode: distil durable facts into the notes file."""
    if core.cfg.forget:
        return {"learned": 0, "forget": True}
    prov = active_provider(core.cfg, core.server.running(), core.server.state.rpc)
    if prov.kind in ("local", "pool") and not core.server.running():
        return {"learned": 0}
    facts = await chat_engine.learn(prov, body.messages)
    return {"learned": chats.append_memory(core.cfg, facts), "facts": facts}


class MemoryBody(BaseModel):
    text: str


@app.get("/api/memory")
def memory_get() -> dict:
    return {"text": chats.read_memory(), "forget": core.cfg.forget}


@app.put("/api/memory")
def memory_put(body: MemoryBody) -> dict:
    if core.cfg.forget:
        raise HTTPException(400, "memory is off (forget mode)")
    chats.write_memory(body.text)
    return {"ok": True}


class ContextBody(BaseModel):
    name: str
    content_base64: str


@app.get("/api/context")
def context_list() -> dict:
    return {"files": chats.list_context()}


@app.post("/api/context")
def context_add(body: ContextBody) -> dict:
    import base64

    try:
        return chats.add_context(body.name, base64.b64decode(body.content_base64))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/context/{name}")
def context_del(name: str) -> dict:
    return {"deleted": chats.delete_context(name)}


@app.get("/api/guide")
def guide_info(lang: str | None = None) -> dict:
    """What the guide knows right now (for the UI and for curious users) + starter questions."""
    from datas import guide

    lg = lang or core.cfg.lang
    return {
        "starters": guide.STARTERS.get(lg, guide.STARTERS["en"]),
        "briefing": guide.build(core, lg),
    }


@app.get("/api/skills")
def skills() -> dict:
    """Older name of /api/assistants, kept for scripts written against it."""
    return {
        "skills": [
            {
                "id": a["id"],
                "en": assistants.public(a, "en")["name"],
                "es": assistants.public(a, "es")["name"],
            }
            for a in assistants.all_assistants()
        ]
    }


# ---- helpers (assistants): ready-made and the user's own --------------------------


class HelperBody(BaseModel):
    name: str
    prompt: str
    blurb: str = ""
    starters: list[str] = []
    export: list[str] = []
    id: str | None = None


@app.get("/api/assistants")
def assistants_list(lang: str | None = None) -> dict:
    return assistants.listing(lang or core.cfg.lang)


@app.get("/api/assistants/{aid}")
def assistants_get(aid: str, lang: str | None = None) -> dict:
    a = assistants.get(aid)
    if not a:
        raise HTTPException(404, "no such helper")
    return assistants.public(a, lang or core.cfg.lang, with_prompt=True)


@app.post("/api/assistants")
def assistants_save(body: HelperBody) -> dict:
    try:
        return assistants.save_custom(
            body.name, body.prompt, body.blurb, body.starters, body.export, body.id
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, "no such helper") from e


@app.delete("/api/assistants/{aid}")
def assistants_delete(aid: str) -> dict:
    return {"deleted": assistants.delete_custom(aid)}


class FileBody(BaseModel):
    name: str
    content_base64: str


def _decode(body: FileBody) -> bytes:
    import base64
    import binascii

    try:
        return base64.b64decode(body.content_base64, validate=False)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(400, "the file did not arrive whole; try again") from e


@app.post("/api/assistants/{aid}/docs")
def assistants_doc_add(aid: str, body: FileBody) -> dict:
    try:
        return assistants.add_doc(aid, body.name, _decode(body))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, "no such helper") from e


@app.delete("/api/assistants/{aid}/docs/{name}")
def assistants_doc_del(aid: str, name: str) -> dict:
    try:
        return {"deleted": assistants.delete_doc(aid, name)}
    except KeyError as e:
        raise HTTPException(404, "no such helper") from e


# ---- documents in a chat, and saving answers as files ------------------------------

ATTACH_CAP = 400_000  # characters kept per attached document (the AI gets matching passages)


@app.post("/api/docs/extract")
def docs_extract(body: FileBody) -> dict:
    """Turn a PDF, Word, Excel, PowerPoint or text file into text for the chat. Nothing is
    stored here: the window keeps the text with the chat."""
    try:
        text = docs.extract_text(body.name, _decode(body))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "name": Path(body.name).name,
        "text": text[:ATTACH_CAP],
        "chars": len(text),
        "truncated": len(text) > ATTACH_CAP,
    }


@app.get("/api/docs/formats")
def docs_formats() -> dict:
    return {"read": sorted(docs.SUPPORTED), "write": list(exporter.FORMATS)}


class ExportBody(BaseModel):
    markdown: str
    format: str
    title: str = ""
    lang: str | None = None


@app.post("/api/export")
def export_answer(body: ExportBody) -> dict:
    """Save an answer as Word, Excel, PowerPoint, PDF, web page, Markdown or text."""
    if body.format not in exporter.FORMATS:
        raise HTTPException(400, f"unknown format; choose one of {', '.join(exporter.FORMATS)}")
    try:
        p = exporter.export(body.markdown, body.format, body.title, body.lang or core.cfg.lang)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"path": str(p), "name": p.name, "folder": str(p.parent)}


class ExportCodeBody(BaseModel):
    code: str
    lang: str = ""
    title: str = ""


@app.post("/api/export/code")
def export_code(body: ExportCodeBody) -> dict:
    p = exporter.export_code(body.code, body.lang, body.title)
    return {"path": str(p), "name": p.name, "folder": str(p.parent)}


class OpenBody(BaseModel):
    path: str
    reveal: bool = False


@app.post("/api/open")
def open_exported(body: OpenBody) -> dict:
    """Open a file Datas saved (or show it in its folder) with the user's usual program."""
    try:
        exporter.open_file(exporter.allowed(body.path), body.reveal)
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e)) from e
    return {"opened": True}


# ---------------------------------------------------------------------------
# Learn: lessons, a glossary and a hand-checked list of outside material
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Offline survival: Datas' own guides and a library kept on this device (datas/survival)
# ---------------------------------------------------------------------------
@app.get("/api/survival")
def survival_index(lang: str | None = None) -> dict:
    from datas import survival

    return survival.state(lang or core.cfg.lang)


def _survival_call(fn, *args):  # noqa: ANN001, ANN202
    from datas.words import Problem

    try:
        return fn(*args)
    except Problem as e:
        raise HTTPException(400, e.say(core.cfg.lang)) from e


@app.post("/api/survival/keep/{item_id}")
def survival_keep(item_id: str) -> dict:
    """Download one document from its publisher (a job: it can be large)."""
    from datas import survival

    _survival_call(survival._item, item_id)  # noqa: SLF001 - unknown ids are said at once
    return _update_job("Survival library", lambda j: survival.fetch(item_id, j.progress))


@app.post("/api/survival/keep-all")
def survival_keep_all() -> dict:
    from datas import survival

    lang = core.cfg.lang
    return _update_job("Survival library", lambda j: survival.fetch_all(lang, j.progress))


@app.delete("/api/survival/keep/{item_id}")
def survival_forget(item_id: str) -> dict:
    from datas import survival

    return {"removed": _survival_call(survival.remove, item_id)}


@app.get("/api/survival/file/{item_id}")
def survival_file(item_id: str) -> FileResponse:
    """A kept document, to read in the window (PDF or plain text)."""
    from datas import survival

    f = _survival_call(survival.file_of, item_id)
    kind = "application/pdf" if f.suffix == ".pdf" else "text/plain; charset=utf-8"
    return FileResponse(str(f), media_type=kind, headers={"Content-Disposition": "inline"})


@app.get("/api/survival/text/{item_id}")
def survival_text(item_id: str) -> dict:
    from datas import survival

    return {"text": _survival_call(survival.text_of, item_id)}


@app.get("/api/learn")
def learn_index(lang: str | None = None) -> dict:
    return learn.listing(lang or core.cfg.lang, core.cfg)


@app.get("/api/learn/lesson/{lesson_id}")
def learn_lesson(lesson_id: str, lang: str | None = None) -> dict:
    le = learn.lesson(lesson_id, lang or core.cfg.lang)
    if not le:
        raise HTTPException(404, "no such lesson")
    return le


class LearnMark(BaseModel):
    ref: str
    done: bool = True


@app.post("/api/learn/progress")
def learn_progress(body: LearnMark) -> dict:
    try:
        saved = learn.mark(body.ref, body.done, core.cfg)
    except KeyError:
        raise HTTPException(404, "no such lesson or link") from None
    return {"saved": saved, "done": learn.progress(core.cfg)}


@app.post("/api/pick-file")
def pick_file() -> dict:
    """Let the person choose an AI file (.gguf) with the system's own "open file" window.
    That window exists only inside the Datas window; in a plain browser tab the answer is
    ``available: false`` and the page offers a box to type the place instead."""
    try:
        import webview

        win = webview.windows[0] if webview.windows else None
    except Exception:  # noqa: BLE001 - pywebview missing or not running
        win = None
    if win is None:
        return {"available": False, "path": None}
    try:
        kind = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
        if kind is None:
            kind = webview.OPEN_DIALOG
        picked = win.create_file_dialog(
            kind, allow_multiple=False, file_types=("AI model files (*.gguf)", "All files (*.*)")
        )
    except Exception as e:  # noqa: BLE001 - a window toolkit without file dialogs
        return {"available": False, "path": None, "error": str(e)}
    return {"available": True, "path": str(picked[0]) if picked else None}


class OpenUrl(BaseModel):
    url: str


@app.post("/api/open-url")
def open_url(body: OpenUrl) -> dict:
    """Open a web address in the user's usual browser (links in Learn, About, model pages).
    Web addresses only — never a file, a program or any other scheme."""
    import webbrowser
    from urllib.parse import urlsplit

    url = body.url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise HTTPException(400, "only web addresses can be opened")
    return {"opened": bool(webbrowser.open(url))}


@app.get("/agent", response_class=HTMLResponse)
def agent_page() -> str:
    return Path(str(resources.files("datas.server").joinpath("ui/agent.html"))).read_text(
        encoding="utf-8"
    )


class AgentBody(BaseModel):
    task: str
    allow_shell: bool = False
    internet: bool = True
    max_steps: int = 40
    folders: list[str] = []
    ask: str = "risky"  # all | risky | none
    devices: bool = False  # may use cameras, printers, boards, home and industrial devices
    control: bool = False  # may use the mouse and keyboard (experimental; needs devices)


@app.post("/api/agent/run")
def agent_run(body: AgentBody, request: Request):
    from datas.agents import AgentConfig, run_agent
    from datas.agents.folders import resolve_grant

    if remote_peer(request) and (body.allow_shell or body.devices or body.control):
        raise HTTPException(
            403,
            "From a linked device the agent cannot run commands or use the computer's devices. "
            "Switch those on at the computer itself.",
        )
    try:
        roots = [resolve_grant(f) for f in body.folders]
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    core.granted_folders = [str(r) for r in roots]
    core.agent_stop.clear()
    ask = body.ask if body.ask in ("all", "risky", "none") else "risky"
    acfg = AgentConfig(
        base_url=f"http://127.0.0.1:{core.http_port}/v1",
        roots=roots,
        allow_shell=body.allow_shell,
        allow_network=body.internet,
        max_steps=body.max_steps,
        ask=ask,
        confirm=None if ask == "none" else core.ask_user,
        should_stop=core.agent_stop.is_set,
        lang=core.cfg.lang,
        allow_local=core.cfg.allow_local_fetch,
        allow_things=body.devices,
        allow_control=body.devices and body.control,
        vision=core.ai_sees(),
    )

    def gen():
        core.agent_busy += 1
        try:
            if not core.server.running() and core.can_wake():
                yield f"data: {json.dumps({'type': 'assistant', 'step': 0, 'content': 'Waking the AI…'})}\n\n"
                core.wake()
            for ev in run_agent(body.task, acfg):
                core.touch()
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'step': 0, 'error': str(e)})}\n\n"
        finally:
            core.agent_busy -= 1

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@app.get("/api/agent/workspace")
def agent_workspace_list() -> dict:
    from datas.config import agent_workspace

    ws = agent_workspace()
    files = [
        {"name": str(p.relative_to(ws)), "bytes": p.stat().st_size}
        for p in sorted(ws.rglob("*"))
        if p.is_file()
    ]
    return {"path": str(ws), "files": files[:200]}


@app.post("/api/window/agent")
def window_agent() -> dict:
    return core.open_agent_window()


@app.get("/api/agent/approvals")
def agent_approvals() -> dict:
    return {
        "pending": [
            {"id": a["id"], "text": a["text"], "asked": a["asked"]} for a in core.approvals.values()
        ]
    }


class ApprovalBody(BaseModel):
    ok: bool


@app.post("/api/agent/approvals/{aid}")
def agent_approve(aid: str, body: ApprovalBody) -> dict:
    if not core.answer(aid, body.ok):
        raise HTTPException(404, "no such question (it may have timed out)")
    return {"answered": True}


@app.post("/api/agent/stop")
def agent_stop() -> dict:
    core.agent_stop.set()
    for a in list(core.approvals.values()):  # unblock any pending question as "no"
        core.answer(a["id"], False)
    return {"stopping": True}


@app.get("/api/agent/folders")
def agent_folders() -> dict:
    """Well-known folders on this computer the user can grant to the agent (per session)."""
    from datas.agents.folders import known_folders

    return {"known": known_folders(), "granted": core.granted_folders}


class FolderBody(BaseModel):
    path: str


@app.post("/api/agent/folders/check")
def agent_folder_check(body: FolderBody) -> dict:
    from datas.agents.folders import resolve_grant

    try:
        return {"ok": True, "path": str(resolve_grant(body.path))}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# ---- scheduled tasks ---------------------------------------------------------


class TaskBody(BaseModel):
    title: str
    task: str
    every: str = "day"
    at: str = "09:00"
    weekday: str = "mon"
    folders: list[str] = []
    internet: bool = True
    allow_shell: bool = False
    devices: bool = False  # may use cameras, printers, boards, home and industrial devices
    enabled: bool = True


class TaskPatch(BaseModel):
    title: str | None = None
    task: str | None = None
    every: str | None = None
    at: str | None = None
    weekday: str | None = None
    folders: list[str] | None = None
    internet: bool | None = None
    allow_shell: bool | None = None
    devices: bool | None = None
    enabled: bool | None = None


def _task_dict(t) -> dict:  # noqa: ANN001
    from dataclasses import asdict

    d = asdict(t)
    nd = t.next_due()
    d["next_due"] = nd.isoformat(timespec="minutes") if nd else None
    d["running"] = core.scheduler is not None and core.scheduler.running_id == t.id
    return d


@app.get("/api/agent/tasks")
def agent_tasks() -> dict:
    sch = core.start_scheduler()
    return {"tasks": [_task_dict(t) for t in sch.tasks]}


PHONE_TASK = (
    "From a linked device, a task that runs by itself cannot be given commands or the "
    "computer's devices, and one that has them cannot be changed. Do that at the computer."
)


@app.post("/api/agent/tasks")
def agent_task_add(body: TaskBody, request: Request) -> dict:
    from datas.agents.folders import resolve_grant

    if remote_peer(request) and (body.allow_shell or body.devices):
        raise HTTPException(403, PHONE_TASK)
    try:
        folders = [str(resolve_grant(f)) for f in body.folders]
        if body.every not in ("hour", "day", "week", "once"):
            raise ValueError("every must be hour, day, week or once")
        hh, mm = (int(x) for x in body.at.split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except (ValueError, AssertionError) as e:
        raise HTTPException(400, f"bad task: {e}") from e
    t = core.start_scheduler().add(**{**body.model_dump(), "folders": folders})
    return _task_dict(t)


@app.patch("/api/agent/tasks/{task_id}")
def agent_task_patch(task_id: str, body: TaskPatch, request: Request) -> dict:
    if remote_peer(request):
        # a task with commands or devices was given its limits at the computer: from a phone
        # it can be paused or started again, nothing else
        cur = core.start_scheduler().get(task_id)
        powerful = bool(cur and (cur.allow_shell or getattr(cur, "devices", False)))
        changes = {k for k, v in body.model_dump().items() if v is not None} - {"enabled"}
        if body.allow_shell or body.devices or (powerful and changes):
            raise HTTPException(403, PHONE_TASK)
    t = core.start_scheduler().update(task_id, **body.model_dump())
    if not t:
        raise HTTPException(404, "no such task")
    return _task_dict(t)


@app.delete("/api/agent/tasks/{task_id}")
def agent_task_delete(task_id: str) -> dict:
    return {"removed": core.start_scheduler().remove(task_id)}


@app.post("/api/agent/tasks/{task_id}/run")
def agent_task_run(task_id: str) -> dict:
    ok = core.start_scheduler().run_now(task_id)
    if not ok:
        raise HTTPException(409, "no such task, or another task is running")
    return {"started": True}


@app.get("/api/agent/results")
def agent_results() -> dict:
    from datas.agents.schedule import results_dir

    files = sorted(results_dir().glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:50]
    return {
        "results": [
            {
                "name": f.name,
                "path": str(f),
                "when": f.stat().st_mtime,
                "text": f.read_text(encoding="utf-8")[:4000],
            }
            for f in files
        ]
    }


class OfferBody(BaseModel):
    on: bool


@app.post("/api/pool/offer")
def pool_offer(body: OfferBody) -> dict:
    return core.set_pool_offer(body.on)


class ServiceBody(BaseModel):
    on: bool


@app.get("/api/service")
def service_state() -> dict:
    """Does Datas start with the computer (or the login)? {supported, installed, running…}"""
    from datas import service
    from datas.words import Problem

    try:
        return {"supported": True, **service.status()}
    except Problem as e:
        return {"supported": False, "why": e.say(core.cfg.lang)}


@app.post("/api/service")
def service_switch(body: ServiceBody) -> dict:
    """Start Datas with the computer, with no window (on), or stop doing so (off)."""
    from datas import service
    from datas.words import Problem, tr

    try:
        if body.on:
            r = service.install()
            r["notes"] = [tr(n, core.cfg.lang) for n in r.get("notes", [])]
            return r
        # off: only what makes it start next time; the Datas showing this window keeps running
        return service.remove(stop=False)
    except Problem as e:
        raise HTTPException(400, e.say(core.cfg.lang)) from e


@app.post("/api/shutdown")
def shutdown() -> dict:
    """Called when the desktop window closes: stop the engine and exit."""
    import os
    import threading

    core.shutdown()
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return {"ok": True}


# ---------------------------------------------------------------------------
# OpenAI-compatible proxy
# ---------------------------------------------------------------------------

_HOP = {
    "connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "proxy-authorization",
    "proxy-authenticate",
    "host",
    "content-length",
    "authorization",
    "x-api-key",
}


@app.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def v1_proxy(path: str, request: Request):
    core.touch()
    prov = active_provider(core.cfg, core.server.running(), core.server.state.rpc)
    if prov.kind in ("local", "pool") and not core.server.running() and core.can_wake():
        try:
            await run_in_threadpool(core.wake)
        except Exception:  # noqa: BLE001 - reported just below as "no model running"
            pass
        prov = active_provider(core.cfg, core.server.running(), core.server.state.rpc)
    if prov.kind in ("local", "pool") and not core.server.running():
        return JSONResponse(
            {
                "error": {
                    "message": "No local model is running. Install & run one first, or select a remote provider.",
                    "type": "datas_no_model",
                }
            },
            status_code=503,
        )
    url = f"{prov.base_url}/{path}"
    body = await request.body()
    # Fill in the provider's default model when the client sends none / a placeholder.
    if body and request.method == "POST":
        try:
            payload = json.loads(body)
            if isinstance(payload, dict) and (
                not payload.get("model") or payload.get("model") in ("datas", "default", "auto")
            ):
                payload["model"] = prov.model or "default"
                body = json.dumps(payload).encode()
        except json.JSONDecodeError:
            pass
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
    headers.update(prov.headers())
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(600, connect=30),
        trust_env=not chat_engine.is_local_url(prov.base_url),
    )
    try:
        req = client.build_request(
            request.method, url, content=body, headers=headers, params=dict(request.query_params)
        )
        resp = await client.send(req, stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        return JSONResponse(
            {"error": {"message": f"Provider unreachable: {e}", "type": "datas_upstream"}},
            status_code=502,
        )

    async def gen():
        try:
            async for chunk in resp.aiter_raw():
                core.touch()
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    out_headers = {
        k: v
        for k, v in resp.headers.items()
        if k.lower() not in _HOP and k.lower() != "content-encoding"
    }
    return StreamingResponse(
        gen(),
        status_code=resp.status_code,
        headers=out_headers,
        media_type=resp.headers.get("content-type"),
    )


def set_http_port(port: int) -> None:
    """Called by whoever starts the server, so internal links point at the right port."""
    from datas import providers

    core.http_port = port
    providers.HTTP_PORT = port


def serve(host: str = "127.0.0.1", port: int | None = None, open_browser: bool = True) -> None:
    import threading
    import webbrowser

    import uvicorn

    port = port or core.cfg.ui_port
    set_http_port(port)
    if host not in ("127.0.0.1", "localhost", "::1"):
        # The user chose to put Datas on the network: answer to this machine's names there.
        import socket

        from datas.link import local_addresses

        allow_hosts(host, socket.gethostname(), socket.gethostname() + ".local", *local_addresses())
    if open_browser:
        threading.Timer(
            1.0,
            lambda: webbrowser.open(f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}"),
        ).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
