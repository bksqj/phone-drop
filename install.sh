#!/bin/bash
# Создаёт ярлык «Phone Drop» на рабочем столе для текущего расположения папки
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
chmod +x "$DIR/start.sh"

if command -v gnome-terminal >/dev/null; then
    EXEC="gnome-terminal --title=\"Phone Drop\" -- \"$DIR/start.sh\""
else
    EXEC="x-terminal-emulator -e \"$DIR/start.sh\""
fi

cat > "$DESK/Phone Drop.desktop" <<DESKTOP
[Desktop Entry]
Name=Phone Drop
Comment=Передача файлов и текста с iPhone по Wi-Fi или кабелю
Exec=$EXEC
Icon=phone
Terminal=false
Type=Application
DESKTOP
chmod +x "$DESK/Phone Drop.desktop"
gio set "$DESK/Phone Drop.desktop" metadata::trusted true 2>/dev/null || true
echo "Готово: ярлык «Phone Drop» создан в $DESK"
