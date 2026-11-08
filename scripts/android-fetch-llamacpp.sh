#!/usr/bin/env bash
# Fetch the prebuilt llama.cpp Android build and place the pieces the APK needs under
# android/app/src/main/jniLibs/arm64-v8a/. The executable is renamed lib<name>.so so the
# package manager extracts it into the app's native library dir (the only exec-able place).
#
#   scripts/android-fetch-llamacpp.sh [TAG] [VARIANT]
#   TAG      llama.cpp build tag, default: the KNOWN_GOOD_TAG in datas/runtime/llamacpp.py
#   VARIANT  android-arm64 (default, runs on every arm64 phone) | android-arm64-snapdragon
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${1:-$(grep -oE 'KNOWN_GOOD_TAG = "b[0-9]+"' "$ROOT/datas/runtime/llamacpp.py" | grep -oE 'b[0-9]+')}"
VARIANT="${2:-android-arm64}"
DEST="$ROOT/android/app/src/main/jniLibs/arm64-v8a"
NAME="llama-${TAG}-bin-${VARIANT}.tar.gz"
URL="https://github.com/ggml-org/llama.cpp/releases/download/${TAG}/${NAME}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "→ $URL"
curl -fL --retry 3 -o "$TMP/$NAME" "$URL"
tar -xzf "$TMP/$NAME" -C "$TMP"
SRC="$(find "$TMP" -maxdepth 1 -type d -name 'llama-*' | head -1)"
[ -n "$SRC" ] || { echo "unexpected archive layout"; exit 1; }

# Prefer the NDK's llvm-strip (GitHub runners have ANDROID_NDK_LATEST_HOME), else any llvm-strip.
STRIP=""
for cand in "${ANDROID_NDK_LATEST_HOME:-}/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" \
            "${ANDROID_NDK_HOME:-}/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" \
            "${ANDROID_NDK:-}/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" \
            "$(command -v llvm-strip || true)"; do
  if [ -n "$cand" ] && [ -x "$cand" ]; then STRIP="$cand"; break; fi
done

mkdir -p "$DEST"
rm -f "$DEST"/*.so
copy() { # src-name dest-name
  if [ -n "$STRIP" ]; then "$STRIP" --strip-unneeded -o "$DEST/$2" "$SRC/$1"; else cp "$SRC/$1" "$DEST/$2"; fi
}
copy llama-server libllama-server.so
for lib in libllama-server-impl.so libllama-common.so libmtmd.so libllama.so libggml.so libggml-base.so; do copy "$lib" "$lib"; done
for lib in "$SRC"/libggml-cpu-*.so; do copy "$(basename "$lib")" "$(basename "$lib")"; done
# Optional backends shipped in some variants (OpenCL/Hexagon on the snapdragon build)
for lib in "$SRC"/libggml-opencl*.so "$SRC"/libggml-hexagon*.so "$SRC"/libggml-vulkan*.so; do
  [ -f "$lib" ] && copy "$(basename "$lib")" "$(basename "$lib")" || true
done
cp "$SRC/LICENSE" "$DEST/../LICENSE.llama.cpp" 2>/dev/null || true
echo "$TAG $VARIANT" > "$DEST/../llamacpp-build.txt"

echo "✓ $(ls "$DEST" | wc -l) files, $(du -sh "$DEST" | cut -f1) → $DEST ($( [ -n "$STRIP" ] && echo stripped || echo unstripped ))"
