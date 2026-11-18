# Where the AI's words come from

One interface — an OpenAI-compatible `/v1/chat/completions` — two sources:

| Provider | What it is |
|---|---|
| `local` | `llama-server` on this machine, started by Datas |
| `link:<device>` | the AI running on another of your linked devices ([DEVICES.md](DEVICES.md)) |

The AI picker in the chat, *Devices → Use its AI*, or `POST /api/providers/active` switches
between them. Chat, the agent and every app pointed at `http://127.0.0.1:8420/v1` follow it
immediately.

Paid online AIs (an API key for a company's service) were **removed in 0.9**: Datas runs on
your own devices, and a chat sent to a company's service would leave them. A settings file
from an older version that still names one simply uses the AI on this device.

## The `/v1` address for other apps

`datas/server/app.py::v1_proxy` forwards `GET/POST /v1/*` to the active provider, streaming
the answer unchanged (SSE included). Any app that speaks the OpenAI API (an editor plugin, a
script, an agent framework) can use Datas' AI by setting its address to
`http://127.0.0.1:8420/v1` and any key. It:

- answers `503 datas_no_model` when nothing is running here (it wakes a sleeping AI first);
- fills in `model` when the app sends none or `"datas"`/`"default"`/`"auto"`;
- strips hop-by-hop headers and the app's own `Authorization`.

## Exposure warning

By default everything listens on `127.0.0.1` only. `datas serve --host 0.0.0.0` makes the
window *and* the `/v1` address reachable on your network: anyone who can reach port 8420 can
use your AI. Use linked devices instead (encrypted, paired), or a VPN you control.
