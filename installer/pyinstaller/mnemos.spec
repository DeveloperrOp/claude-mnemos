# installer/pyinstaller/mnemos.spec
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for claude-mnemos.

Build:
    python -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm

Output: dist/claude-mnemos/  (one-dir mode, bundled python.exe + DLLs + assets)
Main exe: dist/claude-mnemos/claude-mnemos.exe
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent.parent  # repo root
PKG = ROOT / "claude_mnemos"

block_cipher = None

# Datas: include frontend bundle, prompts, tray assets, and hook scripts.
datas = [
    (str(PKG / "daemon" / "static"),     "claude_mnemos/daemon/static"),
    (str(PKG / "ingest" / "prompts"),    "claude_mnemos/ingest/prompts"),
    (str(PKG / "tray" / "assets"),       "claude_mnemos/tray/assets"),
    (str(ROOT / "hooks"),                "hooks"),
]

# Hidden imports that PyInstaller's static analysis misses.
hiddenimports = [
    # FastAPI / uvicorn dynamic loads
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.workers",
    # Pydantic v2 internals
    "pydantic.deprecated.decorator",
    "pydantic_core",
    # APScheduler
    "apscheduler.executors.pool",
    "apscheduler.executors.asyncio",
    "apscheduler.triggers.cron",
    "apscheduler.triggers.interval",
    "apscheduler.jobstores.memory",
    # File watching
    "watchdog.observers",
    "watchdog.observers.polling",
    "watchdog.observers.read_directory_changes",
    # Tray (Windows)
    "pystray._win32",
    # HTTP client used by hooks
    "requests",
    "urllib3",
    "charset_normalizer",
    # pywebview launcher (platform-specific submodules tolerated to be missing)
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.cocoa",
    "webview.platforms.gtk",
    "clr_loader",
    "pythonnet",
]

a = Analysis(
    [str(PKG / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest", "doctest", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="claude-mnemos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # console for daemon foreground; tray launches detached
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PKG / "tray" / "assets" / "icon.ico") if (PKG / "tray" / "assets" / "icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="claude-mnemos",
)
