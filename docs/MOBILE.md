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

### The app (`ios/`)

**Link the phone to your computers and use their Datas**, exactly like *My computers* on
Android: type the one-time code once, then tap the computer and its Datas opens — its AIs,
chats, helpers, documents and Learn. The computer does the thinking, so the app is small and
works on any iPhone or iPad with iOS 15 or newer. Computers with Datas on the same Wi-Fi are
found by themselves. What the app does and how it is protected: [ios/README.md](../ios/README.md).

Status, honestly: on every change the build compiles the app for iPhone and runs it **in
Apple's iPhone simulator against a real Datas** — it pairs with the code, opens the
computer's Datas in the app's web view, and is refused what a phone must be refused. The
link code is also checked against the computer's own arithmetic (same key, same proofs).
**It has not been on a physical iPhone**: Apple only lets an app onto a phone when it is
signed with an Apple account, and the project has none. With your own Apple ID and a Mac you
can put it on your phone today (free: it lasts 7 days at a time; US$99 a year: a year, and
TestFlight or the App Store) — the steps are in [ios/README.md](../ios/README.md) and
[SIGNING.md](SIGNING.md#5-iphone).

### Later: an AI on the iPhone itself

There is no way to run Python on iOS, and iOS cannot run a downloaded engine program the
way Android does. An AI on the phone would be built on the `llama-<tag>-xcframework.zip`
that llama.cpp ships with every release, reusing Datas' catalog and recommender.
Constraints: no work in the background, a hard memory limit per app (about 60 % of RAM),
8 GB iPhones → 3–4B models. Not started.
