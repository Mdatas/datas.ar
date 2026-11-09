# Roadmap

## 0.1 (this release) — the core loop
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

## 0.2 — for non-technical users (this release)
- [x] One window (pywebview), no browser/terminal; `Datas.exe` + `datas-cli.exe`; Program Files installer with Desktop icon and keep/delete-data uninstall
- [x] Home: Run → what for (text / images / coding / agents; sound & video marked "later") → light / balanced / heavy → recommendation in plain words with paid-model comparison, limits, maker links, "see the other recommendations", advanced options
- [x] My AIs library with per-AI Desktop icons; Remember/Forget privacy switch; chats, notes, "End & learn", documents, skills
- [x] Internet per session (search + open pages) with visible lookups; agent in its own window/process; pool switches in Settings; About & sources page
- [x] Spanish/English; acronyms spelled out
- [x] One installer file with a launcher window (Install · Repair · Uninstall · Exit · Read me); detects any earlier copy, removes it, installs clean, keeps every model/chat/note and says so (finish screen + first-start notice in the app)

## 0.2.x — polish the loop
- [x] macOS `.dmg`; Linux `.deb` (Debian family), Arch package + PKGBUILD, generic tarball with `install.sh` — all built and smoke-tested in CI (`desktop-installers`)
- [ ] Code signing: Windows (SmartScreen) and macOS (Developer ID + notarization) — needs certificates
- [ ] Multi-file (sharded) GGUF entries in the catalog (Qwen3.8-Flash-Next, DeepSeek V4)
- [ ] Vision in the UI (image attach → `--mmproj`)
- [ ] Download queue, pause/resume from the UI, disk cleanup of unused models
- [ ] Benchmarks stored per model and shown as measured tok/s next to the speed class
- [ ] Headless mode + systemd/launchd/Task Scheduler units (`datas service install`)
- [ ] i18n beyond EN/ES (pt-BR first)

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
- [ ] Images & video: stable-diffusion.cpp prebuilt releases exist for Windows (CPU/CUDA/Vulkan/ROCm), Linux (CPU/Vulkan/ROCm) and macOS arm64; next step is `datas/engines/images.py` (download `sd-server`, pick Z-Image / Qwen-Image / FLUX.2 by VRAM, an "Images" tab) and then video (Wan 2.2, LTX-2.3 — needs a GPU with 8 GB+)

## 0.3 — devices
- [ ] Tauri desktop shell (tray icon, autostart) wrapping the same local server
- [~] Android native app (WebView + foreground service + bundled engine) — code in `android/`, first APK pending CI build
- [ ] Android: file picker for existing GGUFs, vision, Snapdragon flavour
- [ ] iOS app on the llama.cpp xcframework, recommender ported to Swift — needs an Apple Developer account (US$99/yr) to run on a phone for more than 7 days / TestFlight; iOS cannot run a downloaded engine binary like Android does
- [ ] exo backend for all-Apple-Silicon pools

## 0.4 — agents
- [x] Agent works in the user's own folders (per-session grants: Desktop, Documents, Downloads…, or any path; never the whole home), with find/move/copy/open tools, reversible delete (trash), web search, PDF/.docx reading
- [x] Scheduled tasks ("every Monday at 9…") with a results inbox — run while Datas is open; catch up after the computer was off
- [x] The Run screen reports what *this* device can do, per ability (yes / slow / no + what it would need / not yet in Datas) — `datas/recommend/abilities.py`
- [ ] The agent's own browser: Playwright Firefox, isolated, hardened, optional Tor (docs/AGENTS.md)
- [ ] Script-driven app control without vision (open apps/files, write .docx/.xlsx/.pdf directly, AppleScript / PowerShell-COM / D-Bus hooks)
- [ ] "Look at my screen and help" (screenshot → vision model explains; the user clicks)
- [ ] Screen control, experimental and device-gated: one window, dry-run, confirm-before-click, Esc panic key; the abilities panel gives it a yes/slow/no verdict (docs/AGENTS.md)
- [ ] MCP client: use any MCP tool server from Datas agents
- [ ] Per-tool allowlists; audit log of every tool call
- [ ] Agent templates (research → file, inbox triage via IMAP, local RAG over a folder)

## Later
- [ ] Speculative decoding presets (ggml-org ships draft/mtp/dflash files next to many models)
- [ ] Community catalog signing (sigstore) and a curated "tested on" matrix per device class
- [ ] Pools between your *own* devices beyond the LAN (WireGuard/Tailscale setup helper)
- [~] Pooling with strangers' devices: **ruled out** while it cannot be made private — see docs/P2P.md
