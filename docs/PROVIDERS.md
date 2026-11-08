# Providers

One interface — an OpenAI-compatible `/v1/chat/completions` — three sources of tokens.

| Provider | What it is | Key |
|---|---|---|
| `local` | `llama-server` on this machine, started by Datas | none |
| `pool` | the same `llama-server` with `--rpc` workers | none |
| any name you choose | an external OpenAI-compatible API | yours, stored locally |

The UI's *Using* dropdown, `datas provider use <name>`, or `POST /api/providers/active`
switches the active provider. Chat, agents and every app pointed at
`http://127.0.0.1:8420/v1` follow it immediately.

## Presets

Base URLs offered in the UI (you still enter the key and model id):

| Preset | Base URL |
|---|---|
| openai | `https://api.openai.com/v1` |
| anthropic (openai-compatible) | `https://api.anthropic.com/v1` (Datas also sends `x-api-key` + `anthropic-version`) |
| groq | `https://api.groq.com/openai/v1` |
| mistral | `https://api.mistral.ai/v1` |
| openrouter | `https://openrouter.ai/api/v1` |
| together | `https://api.together.xyz/v1` |
| ollama (local) | `http://127.0.0.1:11434/v1` |
| lm studio (local) | `http://127.0.0.1:1234/v1` |
| another datas node | `http://<host>:8421/v1` |

Presets are conveniences, not endorsements; check each vendor's current docs.

```bash
datas provider add openai https://api.openai.com/v1 --model gpt-4.1-mini     # prompts for the key
datas provider use openai
datas chat
datas provider use local
```

## The `/v1` proxy

`datas/server/app.py::v1_proxy` forwards `GET/POST /v1/*` to the active provider,
streaming the response body unchanged (SSE included). It:

- rejects with `503 datas_no_model` when `local`/`pool` is active but nothing is running;
- fills in `model` when the client sends none or `"datas"`/`"default"`/`"auto"`;
- strips hop-by-hop headers and the client's own `Authorization`, adds the provider's.

Keys never appear in logs or in `GET /api/providers` (only `has_key: true`).

## Exposure warning

By default everything binds to `127.0.0.1`. `datas serve --host 0.0.0.0` makes the UI
*and* the proxy reachable on your network: anyone who can reach port 8420 can spend your
remote API quota. Put it behind a VPN (Tailscale/WireGuard) or a reverse proxy with auth
if you need remote access.
