"""Runtime-mode detection: source vs PyInstaller-frozen bundle.

Single source of truth for resolving paths to bundled assets so the
codebase doesn't sprinkle ``Path(__file__)`` calls that break under
PyInstaller's ``_MEIPASS`` extraction.

The same module is imported in source mode (development via pipx) and
in frozen mode (after running PyInstaller). All consumers should call
the helpers below -- never compute paths from ``__file__`` directly.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def bundle_root() -> Path:
    """Return the root directory of the bundle.

    In frozen mode this is ``sys._MEIPASS`` (PyInstaller's extraction dir).
    In source mode it's the repo root -- the parent of the ``claude_mnemos``
    package directory.
    """
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    import claude_mnemos
    return Path(claude_mnemos.__file__).resolve().parent.parent


def executable_path() -> Path:
    """Return path to the running executable.

    In frozen mode: ``sys.executable`` is the bundled exe -- a stable path
    after install. In source mode: ``sys.executable`` is the Python
    interpreter (pipx-venv on the dev box). Hook installation uses this
    to write a stable command line into ``~/.claude/settings.json``.
    """
    return Path(sys.executable).resolve()


def static_dir() -> Path:
    """Frontend SPA assets bundled by ``frontend/`` build."""
    return bundle_root() / "claude_mnemos" / "daemon" / "static"


def prompts_dir() -> Path:
    """LLM prompt templates packaged at ``claude_mnemos/ingest/prompts``."""
    return bundle_root() / "claude_mnemos" / "ingest" / "prompts"


def tray_assets_dir() -> Path:
    """Tray icon PNGs."""
    return bundle_root() / "claude_mnemos" / "tray" / "assets"


def hooks_dir() -> Path:
    """Plain hook scripts at ``hooks/`` -- used in source mode for testing.

    In frozen mode this directory still exists (datas-included) but the
    cli_hooks installer prefers the ``mnemos hook <event>`` subcommand
    over invoking ``python <script.py>``.
    """
    return bundle_root() / "hooks"
