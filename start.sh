#!/bin/bash
cd "$(dirname "$0")"
DL="$(xdg-user-dir DOWNLOAD 2>/dev/null || echo "$HOME/Downloads")"
mkdir -p "$DL/С телефона"
xdg-open "$DL/С телефона" >/dev/null 2>&1 &
python3 drop.py
echo; read -p "Нажми Enter, чтобы закрыть окно"
