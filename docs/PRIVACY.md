# Privacy: remember or forget

Datas has two modes. The user picks one on first start (the Welcome screen) and can switch
any time in *Settings → Privacy*. The setting is `memory_mode` in `config.json`.

## Remember me (`memory_mode = remember`)

| What | Where | Who can read it |
|---|---|---|
| Conversations | `<home>/chats/<id>.json` | only this device; shown under *Previous chats* |
| Notes about the user | `<home>/memory.md` — plain text, editable in Settings | injected into the system prompt so the AI "knows" the user |
| Documents the user added | `<home>/context/` | given to the AI with each message |
| Technical logs | `<home>/logs/llama-server.log` (engine output; never messages) | switchable off |

"End & learn" at the end of a chat asks the running model to extract up to 6 durable facts
the user *actually said* (`chats.LEARN_PROMPT`) and appends them to `memory.md` with a date.
"Delete everything it remembers" wipes chats, notes and documents; installed AIs stay.

## Forget everything (`memory_mode = forget`)

- Nothing above is written. `save_chat`, `append_memory` are no-ops; the chat sidebar and
  "End & learn" disappear.
- The engine starts with `--log-disable` and its output goes to the null device.
- The desktop window runs in private mode (no cookies/local storage persisted).
- Job logs exist only in memory for the current process.

What still exists in forget mode: the downloaded model files, the engine, `config.json`
(settings only), and the operating system's own traces (swap, etc.) which Datas cannot
control.

## Internet

Off by default. The chat has a per-session switch; when on, the model gets exactly two
read-only tools — `web_search` (DuckDuckGo HTML results) and `fetch_url` — and the UI shows
every lookup. The agent window has its own switch. Nothing is ever *sent* anywhere by
these tools beyond the query/URL itself.

## Paid providers

An API key the user adds is stored in `config.json` on this device and sent only to the
base URL of that provider when the user chats through it. `GET /api/providers` never returns
keys. Using a paid provider means that company sees the conversation — the UI says so.

## Pooling

Pool traffic (your own devices) is unauthenticated and unencrypted llama.cpp RPC — LAN or
VPN only. Model activations cross the network; the text itself does not, but activations
can leak information. Treat your pool like you treat your home Wi-Fi.

## What Datas never does

No telemetry, no analytics, no account, no update check that sends data. The only outbound
connections are GitHub (llama.cpp download), Hugging Face (model download + hash check),
and whatever the user explicitly enables (internet switch, a paid provider).

## Voice

Hearing and speaking happen on this computer: whisper.cpp turns your voice into text and Kokoro
turns answers into speech, both on the processor. What the microphone records is kept only in
memory while it is being understood and is dropped afterwards; the spoken answer is streamed to
the window and never written to disk. Nothing about voice changes between Remember and Forget
modes — there is nothing to store either way. The only downloads are the model files, from
Hugging Face (whisper) and GitHub (Kokoro), with exact sizes and checksums in `datas/catalog/media.json`.
