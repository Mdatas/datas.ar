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

import json
from importlib import resources
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from datas import __version__, chat_engine, chats, library, shortcuts
from datas.catalog import add_user_model
from datas.catalog import reload as reload_catalog
from datas.orchestrator import Datas
from datas.providers import PRESETS, active_provider, all_providers, remove_remote, set_remote
from datas.recommend.abilities import assess
from datas.recommend.engine import default_headroom, headroom_for_mode, wants_for

app = FastAPI(title="Datas.ar", version=__version__, docs_url="/api/docs", redoc_url=None)
core = Datas()


def ui_html() -> str:
    return Path(str(resources.files("datas.server").joinpath("ui/index.html"))).read_text(
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return ui_html()


# ---------------------------------------------------------------------------
# Device + recommendation
# ---------------------------------------------------------------------------


@app.on_event("startup")
def _start_background() -> None:
    try:
        core.start_scheduler()
    except Exception:  # noqa: BLE001 - never block the server on this
        pass


@app.get("/api/status")
def status() -> dict:
    return core.status()


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
    out = rec.to_dict()
    out["unsupported_use_cases"] = unsupported
    out["headroom"] = headroom if headroom is not None else core.cfg.headroom
    va = core.voice_status()["available"]
    out["abilities"] = [
        a.to_dict() for a in assess(core.spec(), rec, voice_available=va["stt"] and va["tts"])
    ]
    if "video" in uses:
        try:
            out["images"] = core.image_status()["choice"]
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


@app.get("/api/images")
def images_status() -> dict:
    return core.image_status()


@app.post("/api/images/setup")
def images_setup() -> dict:
    return core.start_images_job().to_dict()


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


@app.get("/api/images/list")
def images_list() -> dict:
    from datas.engines import images as image_engine

    d = image_engine.images_dir()
    files = sorted(d.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[:60]
    return {
        "images": [
            {"name": f.name, "when": f.stat().st_mtime, "bytes": f.stat().st_size} for f in files
        ]
    }


@app.get("/api/images/file/{name}")
def images_file(name: str):
    from fastapi.responses import FileResponse

    from datas.engines import images as image_engine

    p = (image_engine.images_dir() / Path(name).name).resolve()
    if not p.exists() or p.parent != image_engine.images_dir().resolve():
        raise HTTPException(404, "no such image")
    return FileResponse(str(p), media_type="image/png")


@app.delete("/api/images/file/{name}")
def images_delete(name: str) -> dict:
    from datas.engines import images as image_engine

    p = image_engine.images_dir() / Path(name).name
    existed = p.exists()
    p.unlink(missing_ok=True)
    return {"removed": existed}


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
    from fastapi.responses import Response

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
    c.save()
    return settings_get()


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


@app.get("/api/hello")
def hello() -> dict:
    """Called once per app start by the UI: says what was found from an earlier install."""
    from datas import __version__ as ver

    prev = core.cfg.last_version
    first_run_of_version = prev != ver
    if first_run_of_version:
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
def library_list() -> dict:
    return {"installed": library.installed(), "running": core.server.state.to_dict()}


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


class ChatBody(BaseModel):
    messages: list[dict[str, Any]]
    internet: bool = False
    skill: str | None = None
    lang: str | None = None
    chat_id: str | None = None


@app.post("/api/chat")
async def chat(body: ChatBody):
    prov = active_provider(core.cfg, core.server.running(), core.server.state.rpc)
    if prov.kind in ("local", "pool") and not core.server.running():
        return JSONResponse(
            {"error": "no_model", "message": "No AI is running yet."}, status_code=503
        )
    extra = None
    if body.skill == "guide":
        from datas import guide

        try:
            extra = guide.build(core, body.lang or core.cfg.lang)
        except Exception as e:  # noqa: BLE001 - the guide must never break the chat
            extra = f"You are the Datas guide. (Device facts unavailable: {e})"
    req = chat_engine.ChatRequest(
        messages=body.messages,
        internet=body.internet,
        skill=body.skill,
        lang=body.lang or core.cfg.lang,
        extra=extra,
    )
    return StreamingResponse(
        chat_engine.stream_chat(core.cfg, prov, req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class SaveChatBody(BaseModel):
    chat_id: str | None = None
    messages: list[dict[str, Any]]
    model: str = ""


@app.get("/api/chats")
def chats_list() -> dict:
    return {"chats": [] if core.cfg.forget else chats.list_chats(), "forget": core.cfg.forget}


@app.post("/api/chats")
def chats_save(body: SaveChatBody) -> dict:
    cid = chats.save_chat(core.cfg, body.chat_id, body.messages, body.model or core.cfg.model_id)
    return {"chat_id": cid, "saved": cid is not None}


@app.get("/api/chats/{chat_id}")
def chats_get(chat_id: str) -> dict:
    d = chats.load_chat(chat_id)
    if not d:
        raise HTTPException(404, "no such chat")
    return d


@app.delete("/api/chats/{chat_id}")
def chats_del(chat_id: str) -> dict:
    return {"deleted": chats.delete_chat(chat_id)}


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

    return chats.add_context(body.name, base64.b64decode(body.content_base64))


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
    return {"skills": [{"id": s["id"], "en": s["en"], "es": s["es"]} for s in chats.SKILLS]}


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


@app.post("/api/agent/run")
def agent_run(body: AgentBody):
    from datas.agents import AgentConfig, run_agent
    from datas.agents.folders import resolve_grant

    try:
        roots = [resolve_grant(f) for f in body.folders]
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    core.granted_folders = [str(r) for r in roots]
    core.agent_stop.clear()
    ask = body.ask if body.ask in ("all", "risky", "none") else "risky"
    acfg = AgentConfig(
        base_url=f"http://127.0.0.1:{core.cfg.ui_port}/v1",
        roots=roots,
        allow_shell=body.allow_shell,
        allow_network=body.internet,
        max_steps=body.max_steps,
        ask=ask,
        confirm=None if ask == "none" else core.ask_user,
        should_stop=core.agent_stop.is_set,
    )

    def gen():
        for ev in run_agent(body.task, acfg):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

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


@app.post("/api/agent/tasks")
def agent_task_add(body: TaskBody) -> dict:
    from datas.agents.folders import resolve_grant

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
def agent_task_patch(task_id: str, body: TaskPatch) -> dict:
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
    client = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30))
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


def serve(host: str = "127.0.0.1", port: int | None = None, open_browser: bool = True) -> None:
    import threading
    import webbrowser

    import uvicorn

    port = port or core.cfg.ui_port
    if open_browser:
        threading.Timer(
            1.0,
            lambda: webbrowser.open(f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}"),
        ).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
