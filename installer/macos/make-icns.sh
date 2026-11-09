#!/usr/bin/env bash
# datas.icns from the 256 px PNG (macOS only: needs sips + iconutil).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../windows/datas-256.png"; SET="$HERE/datas.iconset"; rm -rf "$SET"; mkdir -p "$SET"
for s in 16 32 64 128 256; do
  sips -z $s $s "$SRC" --out "$SET/icon_${s}x${s}.png" >/dev/null
  d=$((s*2)); if [ $d -le 256 ]; then sips -z $d $d "$SRC" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null; fi
done
iconutil -c icns "$SET" -o "$HERE/datas.icns"
rm -rf "$SET"; echo "built $HERE/datas.icns"
