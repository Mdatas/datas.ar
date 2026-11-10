# Roadmap

## 0.1 — the core loop
- [x] Device detection (CPU/RAM/GPU/VRAM/disk/power/form factor) on Linux, macOS, Windows, Android
- [x] Deterministic recommender with headroom budget, placement, fit level, speed class
- [x] Verified 20-model catalog (ggml-org / Qwen / Unsloth), user catalog, `catalog add/refresh`
- [x] llama.cpp prebuilt fetcher with pinning and offline fallback
- [x] Model download with resume + SHA-256; exact KV from GGUF header
- [x] llama-server lifecycle with `--fit`, logs, health, bench
- [x] Web UI (EN/ES) + CLI
- [x] Providers: local / pool / API keys; `/v1` proxy
- [x] Pool mode: mDNS discovery, worker, summed budget, tag check
- [x] Built-in agent runner with sandboxed tools
- [x] Tests incl. a real llama-server integration test on a synthetic GGUF

## 0.2 — for non-technical users
- [x] One window (pywebview), no browser/terminal; `Datas.exe` + `datas-cli.exe`; Program Files installer with Desktop icon and keep/delete-data uninstall
- [x] Home: Run → what for (text / images / coding / agents; sound & video marked "later") → light / balanced / heavy → recommendation in plain words with paid-model comparison, limits, maker links, "see the other recommendations", advanced options
- [x] My AIs library with per-AI Desktop icons; Remember/Forget privacy switch; chats, notes, "End & learn", documents, skills
- [x] Internet per session (search + open pages) with visible lookups; agent in its own window/process; pool switches in Settings; About & sources page
- [x] Spanish/English; acronyms spelled out
- [x] One installer file with a launcher window (Install · Repair · Uninstall · Exit · Read me); detects any earlier copy, removes it, installs clean, keeps every model/chat/note and says so (finish screen + first-start notice in the app)
- [x] **Datas guide**: a chat that knows this device, its verdicts, the installed and recommended AIs and how to ask well (`datas/guide.py`, built live, no extra download)
- [x] *What this device can do*, per ability (yes / slow / no + what it would need / not yet in Datas) — `datas/recommend/abilities.py`

## 0.2.x — installers for every desktop
- [x] macOS `.dmg`; Linux `.deb` (Debian family), Arch package + PKGBUILD, generic tarball with `install.sh` — all built and smoke-tested in CI (`desktop-installers`)

## 0.2.x — voice, sound and video (the "later" chips on Home)

Ollama is not an option here: it is itself a wrapper around llama.cpp (text and vision only), so it
would add nothing Datas does not already run directly. The open, stable path is the rest of the
**ggml family** — the same C/C++ engine style as llama.cpp, one small program per media type,
prebuilt for Windows/Linux/macOS, MIT licensed:

| Media | Engine | Models to start with | Notes |
|---|---|---|---|
| Speech → text (dictate to the AI) | [whisper.cpp](https://github.com/ggml-org/whisper.cpp) (ggml-org, MIT) | Whisper `base`/`small` (CPU ok), `large-v3-turbo` (GPU) | Same download/launch code as llama.cpp; ships `whisper-server` with an HTTP API |
| Text → speech (the AI talks back) | [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0) via ONNX, CPU-friendly | one 82 M-parameter voice model, many voices | Fallback for very weak devices: Piper (GPL-3.0). Better quality / voice cloning on GPU: Chatterbox (MIT) |
| Images (make / edit) | [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp) (MIT) | Z-Image, Qwen-Image, FLUX.2, SDXL in GGUF quantisations | Has an embedded web UI and an HTTP server, same shape as `llama-server` |
| Video (make) | stable-diffusion.cpp as well | Wan 2.1/2.2, LTX-2.3 | Heavy: needs a GPU with 8 GB+ VRAM; the recommender must say so plainly |

Status:
- [x] **Voice shipped** (`datas/engines/voice.py`): whisper.cpp runs in-process through `pywhispercpp` (prebuilt wheels, no release binaries needed — ggml-org ships source only), Kokoro through `kokoro-onnx` + ONNX Runtime, microphone through PortAudio on the server side (works in every window toolkit, no browser permission prompts). Catalog `datas/catalog/media.json` with exact sizes/hashes. Home chip "Voice & sound" is live; the hearing model is chosen by processor/memory (tiny → base → small → large-v3-turbo); chat gets **Talk** and **Read answers aloud**; Settings lets you pick model and voice. Audio is never written to disk.
- [ ] Android: the same through whisper.cpp's and Kokoro's Android builds (not yet)
- [x] **Images shipped** (`datas/engines/images.py`): stable-diffusion.cpp pinned release (Vulkan on any GPU, Metal on Mac, CPU fallback; CUDA/ROCm optional in Settings), recipe Z-Image-Turbo (GGUF Q3_K/Q4_K/Q8_0 by memory + Qwen3-4B text encoder + FLUX VAE, exact sizes in `media.json`), `sd-server` managed like `llama-server` (native async API, offload to CPU on small cards), Images screen with gallery, Forget mode keeps nothing on disk. Verdict "Making images" comes from the engine's own fit check.
- [ ] Images: more recipes by device (Qwen-Image for big cards, FLUX.2 klein), image editing (Qwen-Image-Edit), upscaling
- [x] **Video shipped**: Wan 2.2 TI2V 5B through the same engine (text→video, picture→video; WebM), rated per device, never refused — docs/VIDEO.md
- [x] **More tools** (`datas/apps/`): third-party apps installed into isolated environments with uv and opened in their own window — ComfyUI (video/image making and editing) and FaceFusion (face swap, lip-sync, restoration); user recipes in `<data>/apps.d/` — docs/APPS.md
- [x] **Chat from the first second**: the guide answers from device facts with no AI installed; on the first Run a 409 MB helper AI starts first so chatting works while the chosen AI downloads
- [x] Specialist models on Home: Math, Legal texts, Medical (plus Programming)
- [ ] One-click "translate my video" chain; voice cloning engine; more recipes (audio/music, 3D, OCR)

## 0.3 (this release) — a friendlier window, everyday work, your own devices

- [x] **New window**: chats on the left with search, a new chat with any AI you have, each chat remembers its AI; day and night looks; plain verdicts instead of hidden options; English and Spanish — docs/UI.md
- [x] **My AIs** with a plain summary per AI (good for, keep in mind, memory and disk), lighter and stronger versions, *Use a model file I already have*
- [x] **Everyday work**: 43 ready helpers and your own; PDF, Word, Excel, PowerPoint, web pages and text in a chat; pictures for AIs that understand them; answers saved as Word, Excel, PowerPoint, PDF, web page, Markdown or text — docs/EVERYDAY.md
- [x] **Everyday tools**: recording → text with subtitles, text → audio, long documents summarised or translated piece by piece
- [x] **Your devices**: pairing with a one-time code, TLS 1.3 with pinned certificates on both sides; lend memory, use another device's AI, keep chats the same, carry on alone when a device drops out — docs/DEVICES.md
- [x] **Learn**: 14 lessons, a 42-word glossary and 55 checked links in 18 paths, beginner to expert — docs/LEARN.md
- [x] **Other programs**: the open programs found on the computer, connections through the Model Context Protocol (MCP), ArtCraft; agent tools to write documents, convert files and run those programs — docs/PROGRAMS.md
- [x] **Updates with a way back** for the app, the AI engine, the picture engine and the list of AIs; automatic return when a new engine fails; settings saved once per version; a damaged settings file cannot stop the app — docs/UPDATES.md
- [x] **Protection**: the local service answers only local names and refuses other web pages; no script can be written into the window; the AI cannot open addresses inside your network; downloads are checked; found programs cannot be used to run scripts while commands are off — docs/SECURITY.md
- [x] **`datas selftest`**: a copy checks itself; every installer build runs it on the finished app
- [x] **The real window is tested on every system**: each installer build opens the native window (WebView2, WKWebView, Qt WebEngine) and the page reports what it shows; a weekly and per-release run downloads a real small AI and checks a streamed answer, a document and voice (text → speech → text) on Windows, macOS and Linux
- [x] **Phones link**: a phone pairs with the one-time code and shows a computer's Datas through the encrypted link; Android app with *My computers* — docs/DEVICES.md
- [x] **Release files**: a checksum and a signed provenance record for each; certificate signing for Windows and macOS wired for when certificates exist — docs/SIGNING.md
- [x] Catalog: 27 AIs (Hermes 4 family and Dolphin 3.0 added)

## 0.4 — the things around the computer

- [x] **Cameras, the screen, printers**: a photo or a picture of the screen in a chat for AIs that understand pictures; *Print on paper* for any answer — docs/HARDWARE.md
- [x] **Boards and instruments** on a serial cable (Arduino, ESP32, 3D printers): listen from Tools; the agent reads and writes lines
- [x] **Smart home and industry**: MQTT, Home Assistant and Modbus TCP through your own hub and devices; what announces itself on the network (printers, NAS, Raspberry Pi…)
- [x] **The agent's hardware switch**, off until switched on for a task; anything that looks at you or acts on the world asks first, in plain words and in your language; scheduled tasks may be given it
- [x] **Mouse and keyboard**, experimental, behind a second switch: asks before every action, clicks only inside the picture it was shown, stops when the mouse reaches a corner
- [x] **FFmpeg fetched once and checked** (fixed commit, size, SHA-256) when the computer has none — this also makes *Recording to text* read MP3, M4A and video in the installed app
- [x] **Backend messages in Spanish**: hardware problems and refusals are said in the language Datas is set to (`datas/words.py`)
- [x] A linked phone cannot give a scheduled task commands or hardware, nor change a task that has them

## Next

**Installing and trusting**
- [ ] Certificates: Windows (SignPath Foundation, Azure Trusted Signing or a certificate authority) and macOS (Apple Developer ID + notarization) — the build steps are written; the owner has to obtain them (docs/SIGNING.md)
- [ ] A first published release, so *Check for updates* has something to find
- [ ] Community catalog signing (sigstore) and a "tested on" list per kind of device

**Devices**
- [~] Android app (WebView + foreground service + bundled engine) — code in `android/`, APK built by CI
- [x] Android: linking with computers (*My computers*)
- [ ] Android: the Datas window for the phone's own AI too; voice from the phone in a linked computer's Datas; saving files to the phone; file picker for model files, pictures, Snapdragon flavour
- [ ] iPhone companion app (link to your computers) — source in `ios/`, needs an Apple Developer account to reach a phone
- [ ] Linking devices in different places: a setup helper for WireGuard / Tailscale
- [ ] "Farm mode": many independent tasks at once across linked devices (one answer cannot be split)
- [ ] exo backend for all-Apple-Silicon pools
- [ ] iOS app on the llama.cpp xcframework — needs an Apple Developer account (US$99/yr); iOS cannot run a downloaded engine binary like Android does

**The window**
- [ ] Spanish for the texts that are still English only (limits and comparisons of each AI, picture-model descriptions, technical messages); then Portuguese (pt-BR)
- [ ] Download queue, pause and resume from the window, cleaning up unused AIs
- [ ] Measured speed stored per AI and shown next to the speed class
- [ ] Tray icon, start with the system, tasks that run with the window closed (`datas service install`)
- [ ] Learn: a scheduled re-check of every link; more material in Spanish and Portuguese

**AIs and engines**
- [ ] AI files split in several parts (Qwen3.8-Flash-Next, DeepSeek V4)
- [ ] Speculative decoding presets (ggml-org ships draft files next to many models)
- [ ] Pictures: more recipes by device (Qwen-Image for big cards, FLUX.2 klein), picture editing (Qwen-Image-Edit), upscaling
- [ ] One-click "translate my video"; voice cloning; music, 3D, text recognition recipes

**The agent**
- [x] Works in the user's own folders (per-session grants), reversible delete, web search, documents
- [x] Scheduled tasks with a results inbox
- [x] MCP client; programs found on the computer
- [ ] The agent's own browser: Playwright Firefox, isolated, hardened, optional Tor (docs/AGENTS.md)
- [ ] The system's automation hooks (AppleScript / PowerShell-COM / D-Bus)
- [x] "Look at my screen and help" (a picture of the screen in a chat; the user clicks)
- [x] Mouse and keyboard, experimental: own switch, asks before every action, corner of the screen stops it
- [ ] For the mouse and keyboard: one chosen window only, a dry run, a visible marker before a click
- [ ] Hardware: Modbus over a serial cable (RTU), OPC UA, a live camera view, scanning documents, trying it on real devices
- [ ] Per-tool allowlists; a kept record of every tool call
- [ ] Task templates (research → file, inbox triage via IMAP, questions over a folder)

**Ruled out for now**
- [~] Pooling with strangers' devices: **not an option** while it cannot be made private — see docs/P2P.md
