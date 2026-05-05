#!/usr/bin/env bash
# installer/macos/build-dmg.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

# Resolve the actual Python that setup.py will run under.
#
# Caveat: actions/setup-python@v5 on macOS installs python3 as a wrapper
# whose sys.executable re-exec's into /Library/Frameworks/Python.framework
# (the "real" install target). So just doing `python3 -m pip install`
# installs into the toolcache, but `python3 setup.py py2app` runs against
# the system Framework Python — a different site-packages.
#
# Resolve sys.executable explicitly and install into THAT Python.
WRAPPER_PYTHON="${pythonLocation:+$pythonLocation/bin/python3}"
WRAPPER_PYTHON="${WRAPPER_PYTHON:-python3}"
PYTHON_BIN=$("$WRAPPER_PYTHON" -c "import sys; print(sys.executable)")
echo "[build-dmg] Wrapper python: $WRAPPER_PYTHON"
echo "[build-dmg] Real sys.executable (will be used): $PYTHON_BIN"

# Install setuptools + py2app into the SAME Python that runs setup.py.
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
