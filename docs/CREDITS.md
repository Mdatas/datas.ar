# Credits — what Datas stands on

Datas is deliberately a thin layer. This is who does the heavy lifting.

## Engine

| Project | License | How we use it |
|---|---|---|
| [llama.cpp](https://github.com/ggml-org/llama.cpp) (ggml-org) | MIT | `llama-server` (OpenAI-compatible inference, tool calling, vision, `--fit`), `ggml-rpc-server` + `--rpc` (pooling), `llama-bench` (measurements), prebuilt release archives for every platform, the `gguf` Python package (header reading) |

## Models

| Family | Author | License | Quantizer repo used |
|---|---|---|---|
| Qwen3, 3.5, 3.6, 3.8, Qwen3-Coder-Next | Alibaba Qwen | Apache-2.0 (verify per card) | ggml-org, Qwen, Unsloth |
| Gemma 4 (E2B, E4B, 12B, 26B-A4B, 31B) | Google | Gemma Terms of Use | ggml-org |
| gpt-oss 20B / 120B | OpenAI | Apache-2.0 | ggml-org |
| Phi-4 mini | Microsoft | MIT | Unsloth |
| SmolLM3 3B | Hugging Face | Apache-2.0 | ggml-org |
| Nemotron 3.5 Lightning 30B-A3B | NVIDIA | NVIDIA Open Model License (verify) | ggml-org |
| MiMo V2.6 Distill (Qwen 9B) | Xiaomi | MIT (verify) | ggml-org |

Hosting, file metadata and SHA-256 hashes: [Hugging Face Hub](https://huggingface.co)
via `huggingface_hub` (Apache-2.0).

## Libraries

| | License | Role |
|---|---|---|
| psutil | BSD-3 | RAM, CPU, disk, battery |
| py-cpuinfo | MIT | CPU name and ISA flags |
| nvidia-ml-py (optional) | BSD-3 | NVIDIA VRAM via NVML |
| FastAPI, Starlette, uvicorn | MIT / BSD | local API + proxy |
| pydantic | MIT | catalog schema |
| httpx | BSD-3 | downloads, proxying, agent fetch |
| typer, rich | MIT | CLI |
| python-zeroconf | LGPL-2.1 | mDNS discovery of pool workers |
| platformdirs | MIT | per-OS data directories |
| numpy (via gguf) | BSD-3 | GGUF reader |

## Ideas and prior art

- **Hardware → model sizing CLIs**: [llmfit](https://github.com/alexsjones/llmfit),
  [canirunllm](https://pypi.org/project/canirunllm/), [llm-checker](https://github.com/Pavelevich/llm-checker),
  whichllm, best-engine-ai-helper. Datas' recommender follows their principle —
  deterministic memory math, fit levels, never recommend "too tight" — and adds the
  headroom policy, placement/speed classes and the GGUF-header refinement.
- **Distributed inference**: [exo](https://github.com/exo-explore/exo) (Apache-2.0)
  showed that a home cluster of everyday devices can run frontier-scale models. Datas
  uses llama.cpp RPC for format/platform reasons and plans an exo backend.
- **Mobile local AI**: [PocketPal AI](https://github.com/a-ghorbani/pocketpal-ai) (MIT),
  [Google AI Edge Gallery](https://github.com/google-ai-edge/gallery) (Apache-2.0),
  MLC Chat — references for the native apps on the roadmap.
- **Desktop local AI**: Jan, LM Studio, Ollama, Open WebUI — the UX bar Datas aims to
- **Planned engines for voice and video** (not shipped yet, see docs/ROADMAP.md): whisper.cpp (ggml-org, MIT), Kokoro-82M (hexgrad, Apache-2.0), Piper (GPL-3.0), Chatterbox (Resemble AI, MIT), stable-diffusion.cpp (leejet, MIT)
  clear with zero configuration.

## Not reused, by choice

- No model is used to pick models: the recommendation is auditable arithmetic.
- No telemetry/analytics SDKs.
- No bundled binaries in the Python package: llama.cpp is fetched from its own releases
  so updates and security fixes arrive from upstream.
