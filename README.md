# Datas.ar

**Your own AI, on your own computer. One install, one icon, one button.**

Datas puts an AI (Artificial Intelligence) assistant — the kind you know from ChatGPT —
on your own computer or phone. It runs there, offline, for free. Nothing you type leaves
your device unless *you* switch the internet on for a session or decide to plug in a
paid service.

It is made for people who have never heard the words "model", "GPU" or "quantization":
install, double-click the icon, press **Run**, pick what you'll use it for, and Datas
chooses the best open AI your machine can carry **without slowing everything else down**,
downloads it, and opens a chat.

## How it works, in three steps

1. **Run — check my computer.** Datas reads your working memory (RAM), graphics card (GPU)
   and disk, and asks two simple questions: *what will you use it for?* (chat & writing,
   understanding pictures, programming, doing tasks) and *how much of the computer may
   it use?* (light / balanced / heavy).
2. **The recommendation**, in plain words: why this one, what it can't do, who made it
   (with a link), how big the download is, and **how it compares to the paid AIs you know**
   (OpenAI, Google, Anthropic/Claude — approximate, by class). "See the other
   recommendations" shows every alternative that fits.
3. **Install and start.** The AI is downloaded once and opens in the chat. From then on it
   appears under **My AIs**, with its own Desktop icon if you want one.

## Your choice: remember or forget

On first start Datas asks one question:

- **Remember me** — your chats and a short notes file stay on this computer so the AI gets
  to know you. You can read, edit or delete the notes at any time.
- **Forget everything** — nothing is saved, not even technical logs. Every conversation
  starts from zero. Fully anonymous.

Switch any time in *Settings → Privacy*. → [docs/PRIVACY.md](docs/PRIVACY.md)

## What else it does

- **Internet, per session.** A switch in the chat lets the AI search and open web pages;
  it tells you which links it used. Off by default.
- **Skills and documents.** One-tap skills (summarize, translate, fix my writing, teach me…)
  and "My documents": text files you add so the AI can answer about them.
- **The agent.** Opens in its own window and works step by step in its own folder: read and
  write files, look things up, and — only if you allow it — run commands. Everything it
  does is shown.
- **Paid AIs, optionally.** Paste an API key (a password-like code from OpenAI, Google,
  Anthropic, Groq…) and use the same chat with their model. The key stays on your computer.
- **My devices working together.** Two or more computers at home can pool their memory so
  a bigger AI fits (own network only). → [docs/POOLING.md](docs/POOLING.md)
- **Everything used is credited.** *About* lists GitHub and every project, model and library
  Datas is built on, with links.

## Install

| Platform | How |
|---|---|
| **Windows 10/11** | `Datas-Setup-<version>.exe` from the [Releases](https://github.com/Mdatas/datas.ar/releases) page — one file. Double-click it: a window with **Install · Repair · Uninstall · Exit** (and *Read me*). Install replaces any earlier copy with a clean one and keeps your AIs, chats and notes; Uninstall asks whether to keep or delete them. No wizard, no folder to pick, no administrator password. Until a release exists, the `windows-installer` GitHub Action builds the exe on every push. |
| **macOS / Linux** | `pipx install datas-ar` then `datas` (opens the window; `datas shortcut` puts it on your Desktop). |
| **Android** | Native app in [`android/`](android/README.md) — APK built by the `android-apk` Action. |
| **Anything with Python** | `pip install datas-ar && datas` |

Needs an arm64 phone or a 64-bit computer. No account. No admin rights for the per-user
install. First start downloads the engine (llama.cpp, 30–200 MB depending on your graphics
card); the AI itself is a one-time download of 0.5–20 GB depending on what fits.

## For developers

Datas is deliberately a thin layer: the engine is [llama.cpp](https://github.com/ggml-org/llama.cpp),
the models are the open-weight community's, the hardware math is deterministic arithmetic
you can read in [`datas/recommend/engine.py`](datas/recommend/engine.py).

| | |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | layers, data flow, code map |
| [RECOMMENDER.md](docs/RECOMMENDER.md) | the memory math, thresholds, ranking |
| [HARDWARE_DETECTION.md](docs/HARDWARE_DETECTION.md) | what is read, from where, per OS |
| [CATALOG.md](docs/CATALOG.md) | 20 verified models, schema, how to add |
| [RUNTIME.md](docs/RUNTIME.md) | llama.cpp asset selection, pinning, flags |
| [PRIVACY.md](docs/PRIVACY.md) | remember/forget, what is stored where |
| [PROVIDERS.md](docs/PROVIDERS.md) | local / pool / API keys, the `/v1` proxy |
| [POOLING.md](docs/POOLING.md) · [P2P.md](docs/P2P.md) | your own devices today; strangers' devices — ruled out until it can be private, and why |
| [AGENTS.md](docs/AGENTS.md) | the agent runner, permissions |
| [MOBILE.md](docs/MOBILE.md) · [android/](android/README.md) | phones |
| [API.md](docs/API.md) | the local HTTP API |
| [ROADMAP.md](docs/ROADMAP.md) · [CREDITS.md](docs/CREDITS.md) · [CONTRIBUTING.md](CONTRIBUTING.md) | |

```bash
git clone https://github.com/Mdatas/datas.ar && cd datas.ar
pip install -e ".[dev]" && pytest        # 38 tests, ~3 s; one runs a real llama-server on a synthetic model
datas-cli --help  # or: datas scan | recommend | run | chat | agent | pool worker | provider | runtime | catalog
```

Command line, local API (`http://127.0.0.1:8420/api/…`) and an OpenAI-compatible endpoint
(`http://127.0.0.1:8420/v1`) are all there for people who want them; the window never shows them.

## License

GPL-3.0-or-later (chosen when the repository was created; switchable). Models keep their own licenses (shown on every card).
