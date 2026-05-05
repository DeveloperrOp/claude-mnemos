# installer/macos/setup.py
"""py2app build for claude-mnemos.

Run on macOS:
    python setup.py py2app

Output:
    dist/claude-mnemos.app/
"""
from setuptools import setup
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PKG = ROOT / "claude_mnemos"

APP = [str(PKG / "__main__.py")]
DATA_FILES = [
    ("claude_mnemos/daemon/static",  [str(p) for p in (PKG / "daemon" / "static").rglob("*") if p.is_file()]),
    ("claude_mnemos/ingest/prompts", [str(p) for p in (PKG / "ingest" / "prompts").rglob("*") if p.is_file()]),
    ("claude_mnemos/tray/assets",    [str(p) for p in (PKG / "tray" / "assets").rglob("*") if p.is_file()]),
    ("hooks",                        [str(p) for p in (ROOT / "hooks").rglob("*") if p.is_file()]),
]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": str(PKG / "tray" / "assets" / "icon.icns") if (PKG / "tray" / "assets" / "icon.icns").exists() else None,
    "plist": {
        "CFBundleName": "claude-mnemos",
        "CFBundleDisplayName": "claude-mnemos",
        "CFBundleIdentifier": "com.yarik.claude-mnemos",
        "CFBundleVersion": "0.0.1",
        "CFBundleShortVersionString": "0.0.1",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    },
    "packages": ["claude_mnemos", "fastapi", "uvicorn", "pydantic", "watchdog", "pystray", "apscheduler"],
    "includes": ["uvicorn.logging", "uvicorn.lifespan.on", "uvicorn.protocols.http.auto"],
    "excludes": ["tkinter"],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
