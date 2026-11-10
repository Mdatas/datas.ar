# Architecture

Datas is an orchestrator around existing open-source pieces. It owns four things and
borrows everything else:

1. **Device detection** — what this machine can carry.
2. **Deterministic recommendation** — which catalog file fits, where it should be placed,
   how fast it will feel.
3. **A verified catalog** — model files with byte-exact sizes and licenses.
4. **Glue & UX** — one-click install/run, a `/v1` proxy, a small agent runner, and the
   things built around the chat: helpers, documents, linked devices, Learn, updates.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Window (plain JS, EN/ES)     CLI (typer)         any OpenAI-compatible app  │
└──────────────┬───────────────────────┬────────────────────────┬──────────────┘
               │ /api/*                │ python                 │ /v1/*
┌──────────────▼───────────────────────▼────────────────────────▼──────────────┐
│  datas.server.app (FastAPI, 127.0.0.1:8420)                                  │
│    /api: spec · recommend · catalog · install/run jobs · providers · pool    │
│    /v1 : streaming proxy → active provider                                   │
└──────────────┬───────────────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────┐   ┌──────────────────────────────────────────┐
│ datas.orchestrator.Datas    │   │ datas.providers                          │
│  detect → recommend →       │──▶│  local | pool | remote (API key)         │
│  ensure_runtime → ensure_   │   │  one interface: base_url + headers       │
│  model → refine (GGUF hdr)  │   └──────────────────────────────────────────┘
│  → llama-server args → run  │
└───┬─────────┬─────────┬─────┘
    │         │         │
┌───▼───┐ ┌───▼────┐ ┌──▼────────────────────────────────────────────────────┐
│hardware│ │recommend│ │ runtime                                              │
│detect  │ │engine   │ │  llamacpp.py  — pick/download/pin prebuilt llama.cpp │
│psutil  │ │memory   │ │  downloader   — HF resume + sha256 (huggingface_hub) │
│NVML    │ │math,    │ │  gguf_meta    — exact KV/ctx from header (gguf pkg)  │
│rocm-smi│ │ranking  │ │  process      — llama-server lifecycle, llama-bench  │
│sysfs   │ └─────────┘ └──────────────────────────────────────────────────────┘
│sys_prof│       ▲
│CIM     │  ┌────┴─────┐      ┌────────────────────┐   ┌───────────────────┐
└────────┘  │ catalog  │      │ pool               │   │ agents            │
            │models.json│     │ zeroconf discovery │   │ tool loop over /v1│
            │+ user.json│     │ ggml-rpc-server    │   │ sandboxed tools   │
            └──────────┘      └────────────────────┘   └───────────────────┘
                                        │
                              ┌─────────▼──────────┐
                              │ llama.cpp (ggml-org)│  ← the engine. MIT. Not ours.
                              │ llama-server · RPC  │
                              └────────────────────┘
```

## Data flow of the happy path

1. `GET /api/spec` → `hardware.detect()` → `DeviceSpec` (cached 60 s).
2. `GET /api/recommend` → `recommend.engine.recommend(spec, catalog, headroom, ctx)` →
   every `(model, quant file)` evaluated → ranked → `default` chosen.
3. `POST /api/run {model_id, quant}` → background `Job`:
   1. `runtime.llamacpp.install` — resolve the pinned llama.cpp tag → download the asset
      for this OS/arch/backend → extract → chmod → write marker → pin tag in config.
   2. `runtime.downloader.download_model` — resolve the HF URL, stream with resume,
      verify the Hub's SHA-256, place under `models/<id>/`.
   3. `orchestrator.refine` — read the GGUF header (`gguf` package), replace the KV
      estimate with exact numbers, cap context at the trained length, shrink context if
      the exact need no longer fits.
   4. `recommend.engine.llama_server_args` — flags including `--fit-target <headroom>`.
   5. `runtime.process.LlamaServer.start` — spawn, log to `logs/llama-server.log`, poll
      `/health`, store state; config remembers the model so the next launch is instant.
4. Chat: window → `POST /api/chat` (a stream of events) → `chat_engine` adds the notes, the
   matching passages of attached documents, the helper and — if switched on — the internet
   tools, then talks to the active provider (`127.0.0.1:8421/v1/...` for a local AI). Other
   programs use `POST /v1/chat/completions`, proxied as is.

## Where things live

| Path (Linux; see `datas doctor` for yours) | What |
|---|---|
| `~/.local/share/datas/config.json` | settings, pinned tag, providers + keys |
| `~/.local/share/datas/llamacpp/<tag>/` | extracted llama.cpp build |
| `~/.local/share/datas/models/<model_id>/*.gguf` | downloaded weights |
| `~/.local/share/datas/catalog.json` | your additions/overrides to the catalog |
| `~/.local/share/datas/logs/llama-server.log` | engine log |
| `~/.local/share/datas/agent-workspace/` | the agent's own folder |
| `~/.local/share/datas/chats/`, `memory.md`, `context/`, `assistants/`, `learn.json` | chats, notes, documents at hand, your helpers, Learn progress (Remember mode only) |
| `~/.local/share/datas/link/` | this device's key and certificate, and the devices you linked |
| `~/.local/share/datas/mcp.json`, `programs.json` | connections (MCP) and programs you listed |
| `~/.local/share/datas/backups/` | the settings as each earlier version left them |
| `~/Documents/Datas/` | files you saved from answers |

`DATAS_HOME=/some/dir` relocates all of it (used by the tests).

## Ports

| Port | Service |
|---|---|
| 8420 | Datas UI + API + `/v1` proxy |
| 8421 | llama-server (local engine; also OpenAI-compatible) |
| 8424 | the encrypted link to your other devices (TLS 1.3; only when linking is on) |
| 50052 | `ggml-rpc-server` when this device lends memory — on `127.0.0.1` for linked devices |

## Why Python

The heavy lifting is in llama.cpp's native binaries, so Python's cost is only orchestration,
and the installers ship their own Python: nobody has to install it. The HTTP API is the
boundary that keeps other shells cheap — the Android app and any future native shell talk to
the same service.

## Code map

```
datas/
  __init__.py           version
  config.py             Config dataclass, paths; a damaged settings file is set aside, not fatal
  cli.py                `datas` command (typer)
  orchestrator.py       Datas class: detect→recommend→install→run, jobs, sleep/wake, fallback
  desktop.py            the native window (pywebview) + embedded server
  selftest.py           `datas selftest`: this copy checks itself
  hardware/detect.py    DeviceSpec, GPU, detect()
  recommend/engine.py   Budget, memory_need, evaluate, recommend, llama_server_args
  recommend/abilities.py what this device can do, per ability (yes / slow / no)
  catalog/__init__.py   pydantic schema, load/merge/add
  catalog/models.json   the verified list of AIs      catalog/media.json  voice + picture models
  catalog/compare.py    paid-model class equivalents (plain language)
  runtime/llamacpp.py   asset selection, download, extraction, pinning
  runtime/downloader.py HF download with resume + sha256
  runtime/gguf_meta.py  GGUF header facts
  runtime/process.py    LlamaServer, bench
  engines/voice.py      hearing (whisper.cpp) and speaking (Kokoro)
  engines/images.py     pictures and video (stable-diffusion.cpp)
  providers/__init__.py Provider, presets, config helpers
  chat_engine.py        server-side chat: system prompt (notes, documents, helper) + internet tools, SSE
  chats.py              chats, notes, documents at hand (no-ops in forget mode)
  assistants/           helpers: the built-in catalog and the user's own
  docs.py               text out of PDF, Word, Excel, PowerPoint, web pages; picking passages
  export.py             answers written as Word, Excel, PowerPoint, PDF, web page, Markdown, text
  tools.py              everyday tools: recording → text, text → audio, long documents
  guide.py              the Datas guide (knows this device)
  learn/                Learn: catalog.json (paths, links, glossary) + lessons in EN/ES
  library.py            installed AIs, per-AI metadata, removal
  link/__init__.py      linked devices: identity, pairing, mutual TLS, sync, shared memory
  pool/discovery.py     nodes; workers listed by hand      pool/worker.py  ggml-rpc-server by hand
  netguard.py           which addresses the AI may open (no private networks by default)
  updates.py            updates and going back: app, engines, list of AIs
  programs.py           programs found on the computer, conversions, ArtCraft; FFmpeg fetched once and checked
  things/               hardware: local.py (camera, screen, printers, serial ports), net.py (MQTT,
                        Home Assistant, Modbus, what is on the network), control.py (mouse and keyboard)
  words.py              the backend's sentences in English and Spanish (Problem, Said, tr)
  mcp.py                Model Context Protocol client (connections)
  apps/                 bigger creative tools in isolated environments (uv)
  agents/tools.py       the agent's tools, each checked against the allowed folders
  agents/things_tools.py the agent's hardware tools and the plain questions it asks before using them
  agents/runner.py      tool-calling loop      agents/schedule.py  tasks on a schedule
  agents/folders.py     well-known folders per system
  shortcuts.py          Desktop icons (Win .lnk / Linux .desktop / mac .command)
  sources.json          everything credited on the About page
  fonts/                DejaVu, for the PDF files Datas writes
  server/app.py         FastAPI app: /api, /v1 proxy, who may talk to it
  server/ui/            the window: index.html, app.css, i18n.js, app.js, chat.js, screens.js,
                        agent.html/.css/.js, fonts — see docs/UI.md
tests/                  unit + integration (synthetic GGUF, two linked devices, a phone, stand-ins for an
                        MCP server, an MQTT broker, a Modbus device, a serial board, a file server)
scripts/ui_shot.py      screenshots of every screen without a display
installer/              PyInstaller spec; Windows (Inno Setup), macOS (.dmg), Linux (.deb, Arch, tarball)
android/                the Android app
docs/                   this folder
```
