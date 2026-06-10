"""Guards on installer/pyinstaller/mnemos.spec content.

The spec is executed by PyInstaller, not importable — so these are text-level
regression guards for hidden imports whose absence only explodes at runtime
inside the frozen exe (invisible to the normal test suite).
"""

from __future__ import annotations

from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / "installer" / "pyinstaller" / "mnemos.spec"


def test_spec_collects_tiktoken_ext() -> None:
    """tiktoken discovers its encodings (cl100k_base etc.) by scanning the
    tiktoken_ext namespace package at runtime — PyInstaller's static analysis
    never sees it. Without an explicit collect/hiddenimport the frozen exe
    raises "Unknown encoding cl100k_base. Plugins found: []" on every extract
    (broke 'Сохранить как знания' in all installed builds).
    """
    text = SPEC.read_text(encoding="utf-8")
    assert "tiktoken_ext" in text, (
        "mnemos.spec must collect tiktoken_ext submodules — extract is broken "
        "in the frozen exe without them"
    )


def test_py2app_setup_bundles_tiktoken_ext() -> None:
    """The macOS dmg is built by py2app, not the PyInstaller spec — same
    runtime plugin-scan, same breakage. Both packages must be listed."""
    setup_py = SPEC.parent.parent / "macos" / "setup.py"
    text = setup_py.read_text(encoding="utf-8")
    assert '"tiktoken"' in text and '"tiktoken_ext"' in text, (
        "installer/macos/setup.py must list tiktoken + tiktoken_ext in "
        "packages — extract is broken in the .app without them"
    )
