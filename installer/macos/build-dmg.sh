#!/usr/bin/env bash
# installer/macos/build-dmg.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

# Resolve the Python to use. On CI, $pythonLocation is set by
# actions/setup-python@v5 and points at the toolcache install where we
# installed setuptools + py2app. Without this, `python` may resolve to
# /Library/Frameworks/Python.framework (system Python) which doesn't
# have setuptools or py2app — setup.py would crash with
# 'ModuleNotFoundError: No module named pkg_resources'.
PYTHON_BIN="${pythonLocation:+$pythonLocation/bin/python3}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
echo "[build-dmg] Using Python: $PYTHON_BIN"
"$PYTHON_BIN" -c "import sys; print('[build-dmg] sys.executable:', sys.executable)"

# Belt-and-suspenders: ensure setuptools/py2app are present in the chosen Python.
"$PYTHON_BIN" -m pip install --quiet setuptools py2app==0.28.6

# 1) Build the .app bundle
cd installer/macos
"$PYTHON_BIN" setup.py py2app
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
