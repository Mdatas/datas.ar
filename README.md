# Datas.ar

**Local AI for everyone. Download, hit run.**

Datas reads your device — CPU, RAM, every GPU and its VRAM, disk, power — picks the best
open-weight model it can carry *without freezing the machine*, downloads it, and runs it.
Phones, laptops, desktops, servers. One click, no accounts, no telemetry, nothing leaves
your device unless you plug in an API key on purpose.

Then it gets out of your way:

- **Switch models** from a curated, verified catalog, or run any GGUF you already have.
- **Plug in an API key** (OpenAI, Anthropic, Groq, Mistral, OpenRouter, …) and use the
  same chat and the same local `/v1` endpoint — your apps never notice the difference.
- **Pool several devices**: your laptop + desktop + an old PC become one bigger machine
  (llama.cpp RPC over your LAN).
- **Run agents** that read, write, fetch and — only if you allow it — execute, inside a
  sandboxed workspace.

Datas is glue, on purpose. The engine is [llama.cpp](https://github.com/ggml-org/llama.cpp)
(MIT), the models are the open-weight community's, the hardware math is deterministic
arithmetic you can read in [`datas/recommend/engine.py`](datas/recommend/engine.py).
See [docs/CREDITS.md](docs/CREDITS.md) for everything we stand on.

---

## Quick start

```bash
pipx install datas-ar        # or: pip install datas-ar
datas                        # opens http://127.0.0.1:8420
```

In the browser: **1. Your device** (scanned) → **2. Recommended** → *Install & run* →
**3. Chat**. That's the whole flow.

From the terminal:

```bash
datas scan                   # what Datas sees
datas recommend              # ranked models for this device, with the memory math
datas run                    # install llama.cpp + the recommended model, start serving
datas chat                   # talk to it
datas agent "summarize every .md file in my workspace into INDEX.md"
```

Anything that speaks the OpenAI API can now use your local model at
`http://127.0.0.1:8420/v1` (model name: anything; Datas routes to the active provider).

> **Requirements:** Python 3.10+. Linux, macOS (Apple Silicon or Intel), Windows 10/11.
> **Android:** native app in [`android/`](android/README.md) (APK built by GitHub Actions or
> Android Studio), or the Python version via [Termux](https://termux.dev) — see [docs/MOBILE.md](docs/MOBILE.md).
> No admin rights, no drivers to install for CPU/Metal; NVIDIA/AMD need their normal
> driver only (the CUDA/ROCm runtimes ship inside the llama.cpp download).

---

## How the recommendation works (no AI involved)

```
needed  = weights (exact, verified on Hugging Face)
        + KV cache (exact from the GGUF header once downloaded; conservative estimate before)
        + runtime overhead (8% of weights + 512 MiB)

budget  = RAM − headroom  (+ VRAM − 10% per GPU)
headroom = max(2 GiB, 25% of RAM)   # 40% on phones; one slider in the UI
fits    = needed ≤ budget,  "comfortable" if ≥10% of the budget is still spare
```

Every catalog file that fits is placed (all-GPU / split / CPU / unified / pooled) and given
a speed class from the bytes it touches per token. The default pick is the highest-quality
*general* model that fits comfortably at a usable speed. Specialists (coding) are only
picked when you ask. Low-bit quants (≤ Q3) are ranked a tier lower. Details and the reasoning
behind the thresholds: [docs/RECOMMENDER.md](docs/RECOMMENDER.md).

When llama-server starts, a second safety net applies: `--fit on --fit-target <headroom>`
makes llama.cpp itself place layers so that your headroom stays free.

## What you get on typical hardware

| Device | Default pick (Nov 2026 catalog) |
|---|---|
| Phone, 8 GB | Phi-4 mini Q6 / Qwen3 4B Q4 |
| Phone, 12 GB | Gemma 4 E4B Q4 |
| Laptop, 16 GB, no GPU | Gemma 4 E4B Q4 |
| Laptop, 16 GB + 8 GB VRAM | Gemma 4 26B-A4B Q4 (split, fast) |
| Mac, 36 GB unified | Qwen3.6 35B-A3B Q4 |
| Desktop, 64 GB + RTX 4090 | Qwen3.6 35B-A3B Q4 (94% on GPU) |
| Workstation, 128 GB + 32 GB VRAM | Qwen3.6 35B-A3B Q4 all-GPU; gpt-oss 120B and Qwen3-Coder-Next fit as options |

(From `tests/test_recommender.py` scenarios — run `datas recommend` for yours.)

## The catalog

20 models, 5 tiers, from 0.4 GB to 63 GB — Qwen3 / 3.5 / 3.6 / 3.8, Gemma 4 (E2B → 31B),
gpt-oss 20B/120B, Phi-4 mini, SmolLM3, Nemotron 3.5 Lightning, MiMo V2.6, Qwen3-Coder-Next.
Official `ggml-org` conversions wherever they exist. Every byte count was read from the
Hugging Face API; nothing is estimated or pattern-guessed. Add your own with
`datas catalog add <repo> <file>`. → [docs/CATALOG.md](docs/CATALOG.md)

## Pooling devices

```bash
# on each extra device
datas pool worker
# on the device you chat from
datas recommend --pool && datas run --pool
```

Workers are discovered over mDNS; memory adds up, speed does not (every token crosses the
network). Works best with MoE models. Unauthenticated by design of the RPC protocol — LAN
or VPN only. → [docs/POOLING.md](docs/POOLING.md)

## Agents

```bash
datas agent "download the README of https://github.com/ggml-org/llama.cpp and write a 10-line summary to llama.md"
datas agent --allow-shell "clone … and run the tests"      # asks before each command
```

Tools: `list_dir`, `read_file`, `write_file`, `fetch_url`, `run_command` (off by default).
Sandboxed to `~/.local/share/datas/agent-workspace`. Any external agent framework can use
the same `/v1` endpoint. → [docs/AGENTS.md](docs/AGENTS.md)

## Documentation

| | |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | layers, data flow, where every file lives |
| [RECOMMENDER.md](docs/RECOMMENDER.md) | the memory math, thresholds, ranking rules |
| [HARDWARE_DETECTION.md](docs/HARDWARE_DETECTION.md) | what is read, from where, per OS |
| [CATALOG.md](docs/CATALOG.md) | schema, curation rules, how to add/refresh models |
| [RUNTIME.md](docs/RUNTIME.md) | llama.cpp asset selection, pinning, flags we pass |
| [PROVIDERS.md](docs/PROVIDERS.md) | local / pool / API keys and the `/v1` proxy |
| [POOLING.md](docs/POOLING.md) | multi-device inference |
| [AGENTS.md](docs/AGENTS.md) | the agent runner, permissions, external frameworks |
| [MOBILE.md](docs/MOBILE.md) | Android today, iOS/Android native apps plan |
| [API.md](docs/API.md) | the local HTTP API |
| [ROADMAP.md](docs/ROADMAP.md) | what's next |
| [CREDITS.md](docs/CREDITS.md) | every project we reuse and how |
| [CONTRIBUTING.md](CONTRIBUTING.md) | dev setup, tests, style |

## Privacy & security, in one paragraph

Everything runs on 127.0.0.1 by default. The only outbound connections are: GitHub (to
fetch llama.cpp), Hugging Face (to fetch models and verify their hashes), and — only if
you add one — the API base URL you typed. Keys live in `~/.local/share/datas/config.json`.
There is no telemetry and no account. `datas serve --host 0.0.0.0` exposes the UI *and*
the `/v1` proxy to your network; do that knowingly.

## License

Apache-2.0. Models keep their own licenses (shown in the catalog and the UI).
