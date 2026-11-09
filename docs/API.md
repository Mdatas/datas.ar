# Local HTTP API

Base: `http://127.0.0.1:8420`. Interactive docs at `/api/docs` (Swagger).

## Device & recommendation

| Method | Path | Returns |
|---|---|---|
| GET | `/api/status` | version, runtime, server state, active provider, installed models, pool nodes |
| GET | `/api/spec?refresh=0|1` | `DeviceSpec` + `default_headroom` |
| GET | `/api/recommend?headroom=0.25&context=8192&kv_bits=16&role=general&want=coding,vision&pool=0|1` | `Recommendation` (`budget`, `default`, `fits[]`, `does_not_fit[]`) |
| GET | `/api/catalog` | the merged catalog |
| POST | `/api/catalog` `{entry}` | add/override a model in the user catalog |
| POST | `/api/catalog/reload` | reload catalog files |

## Settings

| Method | Path | Body |
|---|---|---|
| GET | `/api/settings` | — |
| POST | `/api/settings` | `{headroom?, context?, lang?, pool_nodes?, backend?}` |

## Jobs (long-running)

| Method | Path | Body / returns |
|---|---|---|
| POST | `/api/install` | `{model_id, quant, with_vision?}` → `Job` |
| POST | `/api/run` | `{model_id, quant, context?, kv_bits?, pool?, with_vision?}` → `Job` |
| POST | `/api/run-custom` | `{path, context?, kv_bits?}` → `Job` |
| POST | `/api/stop` | stops llama-server |
| POST | `/api/bench` | → `Job` whose `result` has `prompt_tps`, `gen_tps` |
| GET | `/api/jobs/{id}` | `Job` (`state`, `phase`, `done`, `total`, `percent`, `log[]`, `error`, `result`) |
| GET | `/api/jobs` | last 20 jobs |
| GET | `/api/logs?lines=80` | llama-server log tail |

Poll `/api/jobs/{id}` every ~0.7 s; `state ∈ queued|running|done|error`.

## Providers

| Method | Path | Body |
|---|---|---|
| GET | `/api/providers` | `{active, presets, providers[]}` (keys never returned) |
| POST | `/api/providers` | `{name, base_url, api_key?, model?}` |
| DELETE | `/api/providers/{name}` | — |
| POST | `/api/providers/active` | `{name}` |

## Pool

| Method | Path | Returns |
|---|---|---|
| GET | `/api/pool/nodes?refresh=1&seconds=2.5` | discovered + manual workers, local tag |

## OpenAI-compatible

`ANY /v1/{path}` → proxied to the active provider, streaming. `POST /v1/chat/completions`
is what the UI uses. `model` may be `"datas"`; the proxy substitutes the provider's
configured model. Returns `503 {"error":{"type":"datas_no_model"}}` when nothing local is
running and the active provider is `local`/`pool`.

## Python

```python
from datas.orchestrator import Datas

d = Datas()
rec = d.recommendation(context=8192)
print(rec.default.model_id, rec.default.quant)
d.run(rec.default.model_id, rec.default.quant)  # blocks until healthy
# http://127.0.0.1:8421/v1 is now live
d.stop()
```

## v0.2 additions (simple UI)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/recommend?use=text,images&mode=light|balanced|heavy` | plain-language recommendation; adds `plain`, `unsupported_use_cases`, `headroom` |
| GET/POST | `/api/privacy` | `memory_mode` remember/forget, `keep_logs`, `internet_default`, `onboarded`, `lang` |
| POST | `/api/privacy/wipe` | delete chats, notes, documents |
| GET | `/api/library` · POST `/api/library/shortcut` · DELETE `/api/library/{id}` | installed AIs, Desktop icon per AI, remove |
| POST | `/api/shortcut/app` | Desktop icon for Datas |
| POST | `/api/chat` (SSE) | server-side chat with memory/documents/skill and optional internet tools |
| GET/POST/DELETE | `/api/chats[/{id}]` · POST `/api/chat/learn` | saved chats; distil notes |
| GET/PUT | `/api/memory` | the notes file |
| GET/POST/DELETE | `/api/context[/{name}]` | documents (JSON with base64 content) |
| GET | `/api/skills` · `/api/sources` | skills list; project + every dependency with links |
| GET | `/agent` · POST `/api/agent/run` (SSE) · GET `/api/agent/workspace` · POST `/api/window/agent` | agent page, run, files, open in a separate window/process |
| POST | `/api/pool/offer` `{on}` | run/stop the background worker |
| POST | `/api/shutdown` | window closed → stop everything |
