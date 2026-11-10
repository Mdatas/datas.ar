# Local HTTP API

Base: `http://127.0.0.1:8420`. Interactive docs at `/api/docs` (Swagger).

This is the interface the window itself uses, open to your own scripts and programs on this
computer. It answers only requests addressed to a local name (`127.0.0.1`, `localhost`), and
refuses changes coming from another web page (see [SECURITY.md](SECURITY.md)). A script needs
no key: send JSON, get JSON.

## Device & recommendation

| Method | Path | Returns |
|---|---|---|
| GET | `/api/status` | version, runtime, server state, active provider, installed models, pool nodes |
| GET | `/api/spec?refresh=0\|1` | `DeviceSpec` + `default_headroom` |
| GET | `/api/recommend?headroom=0.25&context=8192&kv_bits=16&role=general&want=coding,vision&pool=0\|1` | `Recommendation` (`budget`, `default`, `fits[]`, `does_not_fit[]`) |
| GET | `/api/catalog` | the merged catalog |
| POST | `/api/catalog` `{entry}` | add/override a model in the user catalog |
| POST | `/api/catalog/reload` | reload catalog files |

## Settings

| Method | Path | Body |
|---|---|---|
| GET | `/api/settings` | — |
| POST | `/api/settings` | `{headroom?, context?, lang?, theme?, idle_sleep_min?, allow_local_fetch?, backend?, image_backend?, voice_stt_model?, voice_tts_voice?, voice_speak_answers?, pool_nodes?}` |

## Jobs (long-running)

| Method | Path | Body / returns |
|---|---|---|
| POST | `/api/install` | `{model_id, quant, with_vision?}` → `Job` |
| POST | `/api/run` | `{model_id, quant, context?, kv_bits?, pool?, with_vision?, with_voice?, starter?}` → `Job` (`starter`: a small AI starts first so chatting works during the download) |
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
| GET | `/api/pool/nodes?refresh=1&seconds=2.5` | linked devices lending memory + workers listed by hand, local tag |

## OpenAI-compatible

`ANY /v1/{path}` → proxied to the active provider, streaming. `model` may be `"datas"`; the
proxy substitutes the provider's configured model. (The window itself chats through
`POST /api/chat`, which adds notes, documents, helpers and the internet tools.) Returns `503 {"error":{"type":"datas_no_model"}}` when nothing local is
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
| GET | `/api/recommend?use=text,images&mode=light\|balanced\|heavy` | plain-language recommendation; adds `plain`, `unsupported_use_cases`, `headroom` |
| GET/POST | `/api/privacy` | `memory_mode` remember/forget, `keep_logs`, `internet_default`, `onboarded`, `lang` |
| POST | `/api/privacy/wipe` | delete chats, notes, documents |
| GET | `/api/library` · POST `/api/library/shortcut` · DELETE `/api/library/{id}` | installed AIs, Desktop icon per AI, remove |
| POST | `/api/shortcut/app` | Desktop icon for Datas |
| POST | `/api/chat` (SSE) | server-side chat with memory/documents/skill and optional internet tools |
| GET/POST/DELETE | `/api/chats[/{id}]` · POST `/api/chat/learn` | saved chats; distil notes |
| GET/PUT | `/api/memory` | the notes file |
| GET/POST/DELETE | `/api/context[/{name}]` | documents (JSON with base64 content) |
| GET | `/api/skills` · `/api/sources` | the earlier, short list of skills (the window now uses `/api/assistants`); project + every dependency with links |
| GET | `/agent` · POST `/api/agent/run` (SSE) · GET `/api/agent/workspace` · POST `/api/window/agent` | agent page, run, files, open in a separate window/process |
| POST | `/api/pool/offer` `{on}` | run/stop the background worker |
| POST | `/api/shutdown` | window closed → stop everything |

## v0.3 additions

### Chats, helpers, documents, saving answers

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chat` (SSE) | `{messages, internet?, assistant?, attachments?, lang?, chat_id?}` → events `token`, `thinking`, `tool`, `tool_result`, `error`, `done` |
| GET | `/api/chats?q=` | saved chats, newest first; `q` searches titles and messages |
| POST · GET · PATCH · DELETE | `/api/chats` · `/api/chats/{id}` | save `{chat_id?, messages, model?, model_name?, provider?, skill?, attachments?}`; read; rename `{title}`; delete |
| GET · POST · DELETE | `/api/assistants?lang=` · `/api/assistants` · `/api/assistants/{id}` | helpers: the 43 built in and your own `{name, prompt, blurb?, starters?, export?, id?}` |
| POST · DELETE | `/api/assistants/{id}/docs` · `…/docs/{name}` | reference documents of your own helper `{name, content_base64}` |
| GET | `/api/docs/formats` | file endings that can be read |
| POST | `/api/docs/extract` | `{name, content_base64}` → the text of a PDF, Word, Excel, PowerPoint, web page or text file. Nothing is stored. |
| POST | `/api/export` | `{markdown, format, title?, lang?}` with `format` ∈ docx, xlsx, pptx, pdf, html, md, txt → `{path, name, folder}` |
| POST | `/api/export/code` | `{code, lang?, title?}` → a code file |
| POST | `/api/open` | `{path, reveal?}` — open a file Datas saved, or show it in its folder |
| POST | `/api/open-url` | `{url}` — open an `http(s)` address in the usual browser |
| POST | `/api/pick-file` | the system's "open file" window for an AI file (`.gguf`) → `{available, path}` |
| GET | `/api/hello` · `/api/notice` · `/api/guide?lang=` | what was kept from an earlier install; one thing the window should tell the user; what the guide knows |

### Learn

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/learn?lang=en\|es` | levels, paths (each with its lessons and links, and `done`), glossary, counts |
| GET | `/api/learn/lesson/{id}?lang=` | one lesson as Markdown |
| POST | `/api/learn/progress` | `{ref, done?}` — remembered only in Remember mode |

### Linked devices

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/link?refresh=0\|1` | on/off, this device's name and identity, addresses, linked devices and their state |
| POST | `/api/link/enable` | `{on}` — let my other devices connect to this one |
| POST · DELETE | `/api/link/pairing` | show a one-time code (ten minutes) · cancel it |
| POST | `/api/link/pair` | `{address, code}` — link with the device that shows the code |
| GET | `/api/link/nearby` | devices on this network with linking on (names only) |
| POST | `/api/link/options` | `{share_memory?, sync_chats?, device_name?}` |
| DELETE · POST | `/api/link/peers/{id}` | unlink · for a phone `{window}`: may it open this device's Datas |
| POST | `/api/link/sync` · `/api/link/use/{id}` | sync chats now · chat with the AI running on that device |
| ANY | `/link/{id}/v1/{path}` | local door to the AI on a linked device; the request travels over the encrypted link |

### Tools, programs, connections

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/tools/transcribe?name=&lang=` | the recording as the request body → `Job` (text, Markdown, subtitles file) |
| POST | `/api/tools/speak` | `{text, lang?, voice?, title?}` → `Job` (an audio file) |
| POST | `/api/tools/long` | `{mode?: summary\|translate, text? \| name? + content_base64?, lang?}` → `Job` |
| GET | `/api/programs?lang=` | programs found on this computer, connections, ArtCraft state |
| POST | `/api/programs/{id}/open` · `/api/programs/artcraft/get` | open a program `{path?}` · download the ArtCraft Launcher (checksum verified) |
| POST · DELETE | `/api/mcp` · `/api/mcp/{name}` | add `{name, command, args?}` · remove a connection (Model Context Protocol) |
| POST | `/api/mcp/{name}/test` | start it, list its tools, stop it |
| GET · POST | `/api/apps` · `/api/apps/{id}/open` · `/api/apps/{id}/stop` · DELETE `/api/apps/{id}` | bigger creative tools |

### Agent

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/agent/run` (SSE) · `/api/agent/stop` | run a task; stop at the next step |
| GET · POST | `/api/agent/approvals` · `/api/agent/approvals/{id}` `{ok}` | questions waiting for an answer; answer one |
| GET · POST | `/api/agent/folders` · `/api/agent/folders/check` `{path}` | folders that can be granted; check a typed path |
| GET · POST · PATCH · DELETE | `/api/agent/tasks[/{id}]` · POST `/api/agent/tasks/{id}/run` | tasks on a schedule `{title, task, every?, at?, weekday?, folders?, internet?, allow_shell?, enabled?}` |
| GET | `/api/agent/results` | the inbox of finished scheduled runs |

### Voice, pictures, video

| Method | Path | Purpose |
|---|---|---|
| GET · POST | `/api/voice` · `/api/voice/install` · `/api/voice/hear` · `/api/voice/speak` | state; download; audio → text; text → audio |
| POST · GET | `/api/voice/listen/start` · `/api/voice/listen/level` · `/api/voice/listen/stop` `{lang?}` | the microphone, on the service side |
| GET · POST | `/api/images?kind=` · `/api/images/setup?kind=` · `/api/images/stop` | engine state; download and start; stop |
| POST | `/api/images/generate` | `{prompt, negative?, width?, height?, steps?, seed?}` → `Job` |
| POST | `/api/video/generate` | `{prompt, negative?, seconds?, width?, height?, seed?, init_image_b64?}` → `Job` |
| GET · DELETE | `/api/images/list` · `/api/images/file/{name}` | what was made; one file |

### Updates

| Method | Path | Purpose |
|---|---|---|
| GET · POST | `/api/updates` · `/api/updates/check` | what is installed and what is known; look for newer versions (the only call that contacts GitHub) |
| POST | `/api/updates/app` | `{version?}` — download that installer (newest by default, or an earlier one to go back), verify, open it |
| POST | `/api/updates/engine` `{tag?}` · `/api/updates/engine/rollback` · `/api/updates/engine/cleanup` | new AI engine beside the old one, tried, with automatic return; go back; delete old copies |
| POST | `/api/updates/images` `{tag?}` · `/api/updates/images/rollback` | the same for the picture engine |
| POST · DELETE | `/api/updates/catalog` | fetch the newest list of AIs · go back to the built-in list |

### Checking the window

| Method | Path | Purpose |
|---|---|---|
| POST · GET | `/api/selfcheck` | the window, opened with `?selfcheck`, reports what it showed; `Datas open --selfcheck out.json` reads it (used by the installer builds) |

Requests that arrive from a linked phone through the link are answered like any other, except
the ones listed in `REMOTE_REFUSED` (`datas/server/app.py`), which get `403`; `/api/status`
then carries `remote: {device, phone}`.

## Command line

`datas-cli --help` lists everything; the ones added in 0.3: `datas link status | code |
pair <address> <code> | unlink <name> | sync`, and `datas selftest`, which checks that a
copy of Datas is whole (window files, lessons, documents, device link, local service) and
exits with 1 if a part is missing.
