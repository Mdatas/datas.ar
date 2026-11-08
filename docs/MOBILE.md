# Phones and tablets

## Android — works today (via Termux)

[Termux](https://termux.dev) (F-Droid or GitHub release, not the Play Store build) gives
Android a real shell with Python. The llama.cpp project publishes `android-arm64` builds
on every release, and Datas selects them automatically (`os=android`).

```bash
pkg update && pkg install python python-pip
pip install datas-ar
datas serve --no-browser          # then open http://127.0.0.1:8420 in Chrome
# or
datas run && datas chat
```

What Datas does differently on a phone:

- **Headroom defaults to 40 %** — Android kills memory-hungry apps without warning.
- **Context defaults are honoured but 4k is wiser** on 8 GB devices; pick it in the UI.
- Picks: 8 GB → Phi-4 mini Q6 / Qwen3 4B Q4; 12 GB → Gemma 4 E4B Q4; 16 GB → Qwen3 8B Q4.
- Backend: the `android-arm64-snapdragon` build is chosen on Qualcomm SoCs (Adreno/Hexagon
  acceleration), the generic `android-arm64` otherwise. GPU memory is unified: RAM is
  the budget.
- Battery: Datas records `on_battery`; generation is CPU-heavy, so expect heat. Keep the
  phone plugged for long sessions. (Thermal throttling is a reason phones make poor
  *pool workers* — see POOLING.md.)

Known rough edges: Termux's `wake-lock` is needed to keep the server alive in the
background (`termux-wake-lock`); some vendors' background limits still kill it after a
while. Mark this experimental.

### Native Android app (planned)

A thin Kotlin app that bundles the Datas server (Python via Chaquopy, or a port of the
orchestrator) and the llama.cpp `.so`, with the same single-page UI in a WebView and a
foreground service for the engine. Open-source reference implementations: PocketPal AI
(MIT) and Google AI Edge Gallery (Apache-2.0).

## iOS — planned

There is no way to install Python-based tooling on iOS. The path is a native Swift shell
around the `llama-<tag>-xcframework.zip` that llama.cpp ships on every release, reusing
Datas' catalog JSON and recommender logic (ported to Swift; it is ~300 lines of
arithmetic). Constraints to design around:

- No background execution: inference stops when the app is backgrounded.
- App Store rules: the engine ships in the binary; models are downloaded as data (fine).
- Memory: iOS has a hard per-app limit (~ 60 % of RAM on recent iPhones); the headroom
  model maps onto it directly.
- Tiers: iPhone 15 Pro / 16 / 17 class (8 GB) → 3–4B models; older → ≤2B.

Until then, a phone is the best **client** of a pool or a desktop: in Datas on the
desktop run `datas serve --host 0.0.0.0` (behind a VPN), and point any OpenAI-compatible
iOS chat app at `http://<desktop>:8420/v1`.
