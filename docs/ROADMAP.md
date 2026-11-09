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

## 0.2.x — polish the loop
- [ ] Installer scripts: `curl … | sh` (Linux/macOS), `.ps1` (Windows), pipx fallback
- [ ] Multi-file (sharded) GGUF entries in the catalog (Qwen3.8-Flash-Next, DeepSeek V4)
- [ ] Vision in the UI (image attach → `--mmproj`)
- [ ] Download queue, pause/resume from the UI, disk cleanup of unused models
- [ ] Benchmarks stored per model and shown as measured tok/s next to the speed class
- [ ] Headless mode + systemd/launchd/Task Scheduler units (`datas service install`)
- [ ] i18n beyond EN/ES (pt-BR first)

## 0.3 — devices
- [ ] Tauri desktop shell (tray icon, autostart) wrapping the same local server
- [~] Android native app (WebView + foreground service + bundled engine) — code in `android/`, first APK pending CI build
- [ ] Android: file picker for existing GGUFs, vision, Snapdragon flavour
- [ ] iOS app on the llama.cpp xcframework, recommender ported to Swift
- [ ] exo backend for all-Apple-Silicon pools

## 0.4 — agents
- [ ] MCP client: use any MCP tool server from Datas agents
- [ ] Scheduled/background agents with a results inbox
- [ ] Per-tool allowlists; audit log of every tool call
- [ ] Agent templates (research → file, inbox triage via IMAP, local RAG over a folder)

## Later
- [ ] Speculative decoding presets (ggml-org ships draft/mtp/dflash files next to many models)
- [ ] Community catalog signing (sigstore) and a curated "tested on" matrix per device class
- [ ] Pools between your *own* devices beyond the LAN (WireGuard/Tailscale setup helper)
- [~] Pooling with strangers' devices: **ruled out** while it cannot be made private — see docs/P2P.md
