#!/usr/bin/env bash
# Builds Datas-<version>.dmg from dist/Datas.app (drag-to-Applications layout).
#   installer/macos/build-dmg.sh <version>
set -euo pipefail
VERSION="${1:?version}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$ROOT/dist/dmg"; rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -R "$ROOT/dist/Datas.app" "$STAGE/Datas.app"
ln -s /Applications "$STAGE/Applications"
cp "$ROOT/installer/macos/README.md" "$STAGE/Read me.md"
mkdir -p "$ROOT/dist/macos"
hdiutil create -volname "Datas.ar $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$ROOT/dist/macos/Datas-$VERSION.dmg"
echo "built $ROOT/dist/macos/Datas-$VERSION.dmg"
