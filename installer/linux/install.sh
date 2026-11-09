#!/usr/bin/env bash
# Generic Linux installer (any distro, no root): installs the Datas folder next to this script into
# ~/.local/opt/datas, adds a menu/desktop entry and `datas-cli` to ~/.local/bin.
#   ./install.sh              install or upgrade (clean: old program files replaced, data kept)
#   ./install.sh --uninstall  remove the program (keeps ~/.local/share/Datas)
#   ./install.sh --purge      remove the program AND your AIs, chats and notes
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/.local/opt/datas"; BIN="$HOME/.local/bin"; APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"; DATA="$HOME/.local/share/Datas"
stop() { pkill -f "$APP/Datas" 2>/dev/null || true; pkill -f llama-server 2>/dev/null || true; }
case "${1:-}" in
  --uninstall|--purge)
    stop; rm -rf "$APP" "$BIN/datas-cli" "$BIN/datas" "$APPS/datas.desktop" "$ICONS/datas.png"
    if [ -f "$DATA/shortcuts.txt" ]; then while read -r f; do [ -n "$f" ] && rm -f "$f"; done < "$DATA/shortcuts.txt"; rm -f "$DATA/shortcuts.txt"; fi
    if [ "${1}" = "--purge" ]; then rm -rf "$DATA"; echo "Datas and all its data removed."; else echo "Datas removed. Your AIs, chats and notes are still in $DATA"; fi
    exit 0;;
esac
[ -x "$HERE/Datas/Datas" ] || { echo "Datas folder not found next to this script"; exit 1; }
stop
rm -rf "$APP"; mkdir -p "$APP" "$BIN" "$APPS" "$ICONS"
cp -a "$HERE/Datas/." "$APP/"
ln -sf "$APP/datas-cli" "$BIN/datas-cli"; ln -sf "$APP/Datas" "$BIN/datas"
sed "s|/opt/datas/Datas|$APP/Datas|" "$HERE/datas.desktop" > "$APPS/datas.desktop"
cp "$HERE/datas.png" "$ICONS/datas.png"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$APPS" || true
kept=""
if [ -d "$DATA/models" ]; then n=$(find "$DATA/models" -name '*.gguf' | wc -l); [ "$n" -gt 0 ] && kept="$kept $n AI model(s),"; fi
if [ -d "$DATA/chats" ]; then n=$(ls "$DATA/chats"/*.json 2>/dev/null | wc -l); [ "$n" -gt 0 ] && kept="$kept $n chat(s),"; fi
[ -f "$DATA/memory.md" ] && kept="$kept your notes,"
echo "Datas installed. Find it in your applications menu as 'Datas.ar' (or run: datas)."
[ -n "$kept" ] && echo "Kept from before:${kept%,}. Manage them from 'My AIs' and Settings."
exit 0
