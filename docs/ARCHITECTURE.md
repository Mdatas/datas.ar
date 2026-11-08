# Architecture

Datas is an orchestrator around existing open-source pieces. It owns four things and
borrows everything else:

1. **Device detection** — what this machine can carry.
2. **Deterministic recommendation** — which catalog file fits, where it should be placed,
   how fast it will feel.
3. **A verified catalog** — model files with byte-exact sizes and licenses.
4. **Glue & UX** — one-click install/run, a `/v1` proxy, pooling, a small agent runner.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  UI (single HTML, EN/ES)      CLI (typer)         any OpenAI-compatible app  │
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
4. Chat: UI → `POST /v1/chat/completions` (stream) → proxy → `127.0.0.1:8421/v1/...`.

## Where things live

| Path (Linux; see `datas doctor` for yours) | What |
|---|---|
| `~/.local/share/datas/config.json` | settings, pinned tag, providers + keys |
| `~/.local/share/datas/llamacpp/<tag>/` | extracted llama.cpp build |
| `~/.local/share/datas/models/<model_id>/*.gguf` | downloaded weights |
| `~/.local/share/datas/catalog.json` | your additions/overrides to the catalog |
| `~/.local/share/datas/logs/llama-server.log` | engine log |
| `~/.local/share/datas/agent-workspace/` | agent sandbox |

`DATAS_HOME=/some/dir` relocates all of it (used by the tests).

## Ports

| Port | Service |
|---|---|
| 8420 | Datas UI + API + `/v1` proxy |
| 8421 | llama-server (local engine; also OpenAI-compatible) |
| 50052 | `ggml-rpc-server` when this device is a pool worker |

## Why Python

The user base this targets already has Python on Linux/macOS and gets it in one step on
Windows and Termux; the heavy lifting is in llama.cpp's native binaries, so Python's cost
is only orchestration. A native shell (Tauri) wrapping the same local server is on the
roadmap for app-store distribution; the HTTP API is the boundary that keeps that cheap.

## Code map

```
datas/
  __init__.py          version
  config.py            Config dataclass, paths
  cli.py               `datas` command (typer)
  orchestrator.py      Datas class: detect→recommend→install→run, jobs
  hardware/detect.py   DeviceSpec, GPU, detect()
  recommend/engine.py  Budget, memory_need, evaluate, recommend, llama_server_args
  catalog/__init__.py  pydantic schema, load/merge/add
  catalog/models.json  the verified catalog
  runtime/llamacpp.py  asset selection, download, extraction, pinning
  runtime/downloader.py HF download with resume + sha256
  runtime/gguf_meta.py GGUF header facts
  runtime/process.py   LlamaServer, bench
  providers/__init__.py Provider, presets, config helpers
  pool/discovery.py    zeroconf advertise/discover
  pool/worker.py       run ggml-rpc-server as a worker
  agents/tools.py      sandboxed tools
  agents/runner.py     tool-calling loop
  server/app.py        FastAPI app + /v1 proxy
  server/ui/index.html the UI
tests/                 unit + integration (synthetic GGUF)
docs/                  this folder
```
