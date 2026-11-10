# Phones and tablets

## Android — the app (`android/`)

Two things in one app:

- **My computers** — link the phone to a computer of yours that has Datas (one-time code,
  encrypted, no account) and use that computer's Datas from the phone: its AIs, chats,
  helpers, documents and Learn. Described in [DEVICES.md](DEVICES.md#phones-and-tablets).
  Needs Android 10 or newer.
- **On this phone** — scan the phone → recommend a small AI → download → chat, with nothing
  leaving the phone. Same catalog file as the desktop, a port of the recommender, Android's
  DownloadManager for the files, and the official llama.cpp Android build inside the APK
  (about 27 MB). The chat here is still llama.cpp's own page, not the Datas window.

Get it: the `android-apk` workflow builds the APK on every change and attaches it to each
release — see [android/README.md](../android/README.md).

Status, honestly: the link code is tested on every change against a real Datas (the tests
compile it and pair, open the window, get refused where a phone should be). The app is
compiled by the build. **It has not been tried on a physical phone by the project yet** —
tell us what happens on yours.

## Android — alternative path via Termux

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

### Native app notes

The native app in `android/` is the thin-shell design: a Kotlin port of the recommender
(no Python on the phone), a foreground service owning the `llama-server` process, and
the engine's web UI in a WebView. Open-source references for the next steps (file
picker, vision, Play Store packaging): PocketPal AI (MIT) and Google AI Edge Gallery
(Apache-2.0).

## iPhone and iPad

There is no way to run Python on iOS, and Apple only lets apps be installed through its
store or with a paid developer account. Two steps are planned:

1. **A companion app** (being written, `ios/`): link to your computers with the one-time
   code and use their Datas from the phone, exactly like the Android "My computers". It runs
   no AI on the phone, so it is small.
2. **An AI on the iPhone itself**, on the `llama-<tag>-xcframework.zip` that llama.cpp ships
   with every release, reusing Datas' catalog and recommender. Constraints: no work in the
   background, a hard memory limit per app (about 60 % of RAM), 8 GB iPhones → 3–4B models.

Putting either on a real iPhone needs an Apple Developer account (US$99 a year) owned by
whoever publishes the app — the project cannot do that for you.
