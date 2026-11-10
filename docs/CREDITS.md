# Credits — what Datas stands on

Datas is deliberately a thin layer. This is who does the heavy lifting. The same list, with
links, is in the app under *About Datas → Built on open work*
([`datas/sources.json`](../datas/sources.json)).

Licences below were read from each project's own files or package metadata, or from the
model card; where that was not possible the line says "verify".

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
| Hermes 4 14B, Hermes 4.3 36B | Nous Research (on Qwen3 14B and Seed-OSS 36B) | Apache-2.0 (model cards) | bartowski, Nous Research |
| Hermes 4 70B | Nous Research (on Meta Llama 3.1 70B) | Llama 3 licence (model card) | lmstudio-community |
| Dolphin 3.0 (Llama 3.1 8B) | Cognitive Computations (on Meta Llama 3.1 8B) | Llama 3.1 licence (model card) | dphn |
| Qwen2.5-Math 7B (math) | Alibaba Qwen | Apache-2.0 | bartowski |
| Saul 7B (legal texts) | Equall | MIT | mradermacher |
| MedGemma 1.5 4B (medical) | Google | Health AI Developer Foundations terms (the user accepts them) | Unsloth |

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
| python-zeroconf | LGPL-2.1-or-later | finding your other devices on the home network |
| platformdirs | MIT | per-OS data directories |
| numpy (via gguf) | BSD-3 | GGUF reader |
| pywebview | BSD-3 | the window (WebView2 on Windows, WKWebView on macOS) |
| PyQt6 + Qt WebEngine | GPL-3.0-only (PyQt6); LGPL v3 (Qt libraries) | the window on Linux |
| pypdf | BSD-3-Clause | reading PDF |
| python-docx, openpyxl, python-pptx | MIT | reading and writing Word, Excel, PowerPoint |
| fpdf2 | LGPL-3.0-only | writing PDF |
| markdown-it-py | MIT | reading the structure of an answer to save it as a document |
| cryptography | Apache-2.0 OR BSD-3-Clause | each device's key and certificate for the encrypted link |
| Pillow | MIT-CMU | pictures: the picture of the screen, photo sizes |
| pySerial | BSD | boards and instruments on a serial cable (Arduino, ESP32, 3D printers) |
| Eclipse Paho MQTT | EPL-2.0 OR BSD-3-Clause | messages of smart-home devices through your own broker |
| PyAutoGUI (with PyScreeze, PyTweening, PyGetWindow, PyMsgBox, MouseInfo; python-xlib on Linux) | BSD; MIT; GPL-3.0-or-later (MouseInfo, PyMsgBox); GPL-2.0-or-later (python-xlib) | the mouse and keyboard, when you let the agent use them |
| uv | Apache-2.0 / MIT | isolated environments for the bigger creative tools |
| PyInstaller, Inno Setup | GPL with exception; Inno Setup License | building the installers |

## Typefaces

| | License | Where |
|---|---|---|
| [Asap](https://github.com/Omnibus-Type/Asap) (Omnibus-Type) | SIL Open Font License 1.1 | the whole window |
| [MuseoModerno](https://github.com/Omnibus-Type/MuseoModerno) (Omnibus-Type) | SIL Open Font License 1.1 | the name "Datas" |
| [DejaVu](https://dejavu-fonts.github.io) | Bitstream Vera licence; DejaVu changes in the public domain | inside the PDF files Datas writes |

Omnibus-Type is a type foundry from Argentina; the colours of the window are those of the
Argentine flag.

## Standards and services

| | |
|---|---|
| [Model Context Protocol](https://modelcontextprotocol.io) (MIT specification) | how the agent uses the functions other programs offer; Datas has its own small client (`datas/mcp.py`) |
| OpenAI-compatible HTTP interface | the common shape of `/v1`, so any tool that speaks it works with Datas |
| TLS 1.3 | the encrypted link between your devices |
| [DuckDuckGo](https://duckduckgo.com) | web search results, only when you switch internet on |
| MQTT (OASIS standard), [Home Assistant](https://www.home-assistant.io)'s web interface, Modbus TCP (Modbus Organization) | how Datas talks to your own smart-home hub and industrial devices; the Modbus part is Datas' own code (`datas/things/net.py`) → [HARDWARE.md](HARDWARE.md) |
| mDNS / DNS-SD ("Bonjour") and UPnP/SSDP | how devices on your network announce themselves; Datas only listens |

## Programs Datas can work with when you have them

Not shipped with Datas; found on your computer and used by the agent: LibreOffice, Pandoc,
Tesseract, FFmpeg, ImageMagick, Inkscape, GIMP, Krita, Blender, OpenSCAD, FreeCAD, and the
[ArtCraft](https://getartcraft.com/) apps (MIT or Apache-2.0, as stated on its site). Each
keeps its own licence. → [PROGRAMS.md](PROGRAMS.md)

## Learn

The Learn screen links to 55 courses, videos, books, reports and official texts by their own
authors and publishers; each entry names who made it. → [LEARN.md](LEARN.md)

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
  clear with zero configuration.

## Voice, pictures and video

- **Voice**: whisper.cpp (ggml-org, MIT; Whisper weights by OpenAI, MIT) via pywhispercpp (absadiki, MIT); Kokoro-82M (hexgrad, Apache-2.0) via kokoro-onnx (thewh1teagle, MIT) on ONNX Runtime (Microsoft, MIT); espeak-ng (GPL-3.0-or-later) for phonemes; python-sounddevice / PortAudio (MIT) for the microphone
- **Pictures**: stable-diffusion.cpp (leejet, MIT) running Z-Image-Turbo (Tongyi-MAI, Apache-2.0; GGUF by leejet) with the Qwen3-4B-Instruct-2507 text encoder (Qwen, Apache-2.0; GGUF by Unsloth) and the FLUX.1 autoencoder (Black Forest Labs, Apache-2.0)
- **Video**: Wan 2.2 TI2V 5B (Wan-AI, Apache-2.0 as stated on the model card) through the same engine; FFmpeg (LGPL/GPL, as published by each builder) for video, recordings and cameras — when none is installed, Datas fetches one build, checked against its SHA-256, from a fixed commit of [zackees/ffmpeg_bins](https://github.com/zackees/ffmpeg_bins), where the [static-ffmpeg](https://github.com/zackees/static_ffmpeg) project (MIT) gathers the builds of BtbN, gyan.dev, evermeet.cx and osxexperts.net → [HARDWARE.md](HARDWARE.md)
- **Bigger creative tools**: ComfyUI (GPL-3.0), FaceFusion (OpenRAIL-AS) — installed only when you open them → [APPS.md](APPS.md)

## Phone apps

- **Android**: AndroidX AppCompat and Core KTX, Material Components (Google, Apache-2.0), Kotlin
  (JetBrains, Apache-2.0) and the Android Gradle Plugin (Google, Apache-2.0).
- **iPhone and iPad**: Apple's SwiftUI, Network.framework, CryptoKit and WebKit (part of iOS);
  the Xcode project is generated by [XcodeGen](https://github.com/yonaskolb/XcodeGen) (MIT).

## Building, testing and publishing

[Hatchling](https://hatch.pypa.io) (MIT) builds the Python package; PyInstaller and Inno Setup
build the Windows installer; GitHub Actions (MIT) builds, tests and publishes every version and
records where each file was built; pytest, pytest-asyncio, Ruff and mypy (MIT) test and check
the code.

## Offline survival library

Downloaded once from each publisher, checked against a pinned SHA-256 →
[SURVIVAL.md](SURVIVAL.md): **FEMA / Ready.gov** and **CDC / US CPSC** (US Government works,
public domain in the USA), **WHO / WEDC** technical notes (© WHO), **Hesperian Health Guides**
(Hesperian Open Copyright), **US Army ATP 3-50.21 Survival** (approved for public release; copy
kept by the Federation of American Scientists), **Project Gutenberg** (public domain in the
USA). The guides also recommend [Kiwix](https://kiwix.org) and
[Meshtastic](https://meshtastic.org) (both GPL-3.0), which are not included.

The same list, grouped and with links to each licence, is in the app: *About → Built with*
(from [`datas/sources.json`](../datas/sources.json); a test keeps every dependency in it).

## Not reused, by choice

- No model is used to pick models: the recommendation is auditable arithmetic.
- No telemetry/analytics SDKs.
- No bundled binaries in the Python package: llama.cpp is fetched from its own releases
  so updates and security fixes arrive from upstream.
