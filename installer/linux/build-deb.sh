#!/usr/bin/env bash
# Builds datas_<version>_amd64.deb from the PyInstaller folder dist/Datas.
#   installer/linux/build-deb.sh <version> [arch]
set -euo pipefail
VERSION="${1:?version}"; ARCH="${2:-amd64}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PKG="$ROOT/dist/deb/datas_${VERSION}_${ARCH}"
rm -rf "$PKG"; mkdir -p "$PKG/DEBIAN" "$PKG/opt/datas" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps" "$PKG/usr/share/doc/datas"
cp -a "$ROOT/dist/Datas/." "$PKG/opt/datas/"
ln -s /opt/datas/datas-cli "$PKG/usr/bin/datas-cli"
ln -s /opt/datas/Datas "$PKG/usr/bin/datas"
cp "$ROOT/installer/linux/datas.desktop" "$PKG/usr/share/applications/datas.desktop"
cp "$ROOT/installer/windows/datas-256.png" "$PKG/usr/share/icons/hicolor/256x256/apps/datas.png"
cp "$ROOT/LICENSE" "$PKG/usr/share/doc/datas/copyright"
SIZE=$(du -sk "$PKG/opt" | cut -f1)
{
  echo "Package: datas"
  echo "Version: $VERSION"
  echo "Section: utils"
  echo "Priority: optional"
  echo "Architecture: $ARCH"
  echo "Installed-Size: $SIZE"
  echo "Maintainer: Datas.ar contributors <https://github.com/Mdatas/datas.ar/issues>"
  echo "Homepage: https://github.com/Mdatas/datas.ar"
  echo "Depends: libc6 (>= 2.35), libgl1, libegl1, libxcb-cursor0, libxkbcommon-x11-0, libxcb-xinerama0, libnss3, libasound2 | libasound2t64, libfontconfig1, libdbus-1-3, libxcomposite1, libxdamage1, libxrandr2, libxtst6"
  echo "Description: Local AI for everyone"
  echo " Datas looks at your computer (memory, graphics card, processor), picks the best"
  echo " free open AI model it can run without freezing it, downloads it and runs it."
  echo " Everything stays on your machine. Your AIs, chats and notes live in"
  echo " ~/.local/share/Datas and are kept when the package is removed or upgraded."
} > "$PKG/DEBIAN/control"
{
  echo '#!/bin/sh'
  echo 'set -e'
  echo 'command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true'
  echo 'command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true'
  echo 'exit 0'
} > "$PKG/DEBIAN/postinst"
{
  echo '#!/bin/sh'
  echo '# stop a running Datas; never touch ~/.local/share/Datas (the user'"'"'s AIs, chats, notes)'
  echo 'pkill -f /opt/datas/Datas 2>/dev/null || true'
  echo 'pkill -f llama-server 2>/dev/null || true'
  echo 'exit 0'
} > "$PKG/DEBIAN/prerm"
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/prerm"
chmod -R go-w "$PKG"
mkdir -p "$ROOT/dist/linux"
dpkg-deb --build --root-owner-group "$PKG" "$ROOT/dist/linux/datas_${VERSION}_${ARCH}.deb"
echo "built $ROOT/dist/linux/datas_${VERSION}_${ARCH}.deb"
