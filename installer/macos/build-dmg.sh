#!/usr/bin/env bash
# installer/macos/build-dmg.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

# 1) Build the .app bundle
cd installer/macos
python setup.py py2app
cd ../..

APP="installer/macos/dist/claude-mnemos.app"
test -d "$APP" || { echo "py2app did not produce $APP"; exit 1; }

# 2) Sign nothing (initial release ships unsigned)

# 3) Create DMG
DMG_OUT="installer/macos/dist/claude-mnemos.dmg"
rm -f "$DMG_OUT"
create-dmg \
  --volname "claude-mnemos" \
  --window-size 540 380 \
  --icon-size 100 \
  --icon "claude-mnemos.app" 130 200 \
  --app-drop-link 410 200 \
  "$DMG_OUT" \
  "$APP"

echo "[ok] DMG written to $DMG_OUT"
