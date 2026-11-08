# Datas for Android

Native Android app (Kotlin) with the same flow as the desktop version: scan the phone →
recommend a model → download → run → chat. The engine is the official llama.cpp Android
build, bundled inside the APK; chat is llama-server's own web UI in a WebView.

```
app/src/main/java/ar/datas/app/
  Device.kt          RAM / storage / cores / SoC / ABI / battery (ActivityManager, StatFs, Build)
  Catalog.kt         reads assets/models.json — the same catalog as the Python package
  Recommender.kt     port of datas/recommend/engine.py (phone = unified memory, CPU placement)
  Downloader.kt      Android DownloadManager (resumable, notification, app-specific storage)
  Engine.kt          llama-server command line + health check
  EngineService.kt   foreground service that owns the llama-server process (+ wake lock)
  MainActivity.kt    the three-step screen; WebView → http://127.0.0.1:8421/
app/src/main/jniLibs/arm64-v8a/   llama.cpp binaries (fetched by scripts/android-fetch-llamacpp.sh)
```

## Get an APK

**Option A — GitHub Actions (no local tooling).** Push this repo to GitHub. The
`android-apk` workflow builds `Datas-debug.apk` (and a release APK, signed with your key
if the `KEYSTORE_*` secrets are set, else debug-signed) on every push touching `android/`
and attaches both to releases for `v*` tags. Download from *Actions → artifacts*.

**Option B — Android Studio.** Open the `android/` folder, let it sync (needs internet
for AGP/Kotlin), plug in a phone with USB debugging, press Run. Or from a terminal:

```bash
scripts/android-fetch-llamacpp.sh          # once; places ~27 MB of stripped llama.cpp libs
cd android && ./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Requirements: JDK 17, Android SDK 35 (Android Studio installs it), an **arm64** phone
running Android 8.0+ (API 26). 8 GB RAM gets Phi-4 mini / Qwen3 4B; 12 GB gets Gemma 4 E4B.

## How the binary runs

Android ≥ 10 only lets an app execute files from its native library directory. The script
renames `llama-server` to `libllama-server.so` and places it with its shared libraries in
`jniLibs/arm64-v8a/`; `useLegacyPackaging = true` makes the installer extract them to
`applicationInfo.nativeLibraryDir`, from where `EngineService` launches it with
`LD_LIBRARY_PATH` and `GGML_BACKEND_PATH` pointing at that directory (ggml picks the best
`libggml-cpu-android_armv*.so` variant for the SoC at runtime).

Flags mirror the desktop recommender: `-c <ctx> -t <cores-1> --jinja -fa auto --fit on
--fit-target <headroom MiB> -ngl 0`. Default headroom on phones is 40 % (min 2 GiB).

## Variants

`scripts/android-fetch-llamacpp.sh b11669 android-arm64-snapdragon` fetches the Qualcomm
build (Adreno OpenCL / Hexagon). It only runs on Snapdragon SoCs — ship it as a separate
flavour, not as the default. The generic `android-arm64` build runs on every arm64 phone.

## Known limits (v0.1)

- Models download into the app's external files dir (`Android/data/ar.datas.app/files/models`);
  uninstalling the app deletes them.
- No "run a GGUF you already have" yet (needs a file picker + SAF copy).
- Vision (`--mmproj`) not wired on Android yet.
- Battery/thermal: inference is CPU-bound; the app keeps a partial wake lock while the
  engine runs and shows a persistent notification with a Stop action.
- Play Store distribution would require the `specialUse` foreground-service justification
  review; sideloading needs none of that.
