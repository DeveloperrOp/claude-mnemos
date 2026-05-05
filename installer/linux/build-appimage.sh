#!/usr/bin/env bash
# installer/linux/build-appimage.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

LINUXDEPLOY="${LINUXDEPLOY:-./linuxdeploy-x86_64.AppImage}"

if [ ! -x "$LINUXDEPLOY" ]; then
  curl -L -o linuxdeploy-x86_64.AppImage "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
  chmod +x linuxdeploy-x86_64.AppImage
  LINUXDEPLOY=./linuxdeploy-x86_64.AppImage
fi

# Build the PyInstaller bundle first.
python -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm

# Stage the AppDir.
APPDIR=installer/linux/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -r dist/claude-mnemos/* "$APPDIR/usr/bin/"
mv "$APPDIR/usr/bin/claude-mnemos" "$APPDIR/usr/bin/claude-mnemos.real"
cat > "$APPDIR/usr/bin/claude-mnemos" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/claude-mnemos.real" "$@"
EOF
chmod +x "$APPDIR/usr/bin/claude-mnemos"

cp installer/linux/claude-mnemos.desktop "$APPDIR/usr/share/applications/"

if [ -f claude_mnemos/tray/assets/icon.png ]; then
  cp claude_mnemos/tray/assets/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/claude-mnemos.png"
else
  echo "[warn] no icon.png found — using placeholder"
  convert -size 256x256 xc:gray "$APPDIR/usr/share/icons/hicolor/256x256/apps/claude-mnemos.png" || true
fi

mkdir -p installer/linux/dist
"$LINUXDEPLOY" --appdir "$APPDIR" \
  --desktop-file installer/linux/claude-mnemos.desktop \
  --icon-file "$APPDIR/usr/share/icons/hicolor/256x256/apps/claude-mnemos.png" \
  --output appimage

mv claude-mnemos-*.AppImage installer/linux/dist/ 2>/dev/null || true

echo "[ok] AppImage at installer/linux/dist/"
ls installer/linux/dist/
