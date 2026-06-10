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


def test_py2app_setup_bundles_tiktoken() -> None:
    """The macOS dmg is built by py2app, not the PyInstaller spec — same
    runtime plugin-scan, same breakage. tiktoken must be listed (tiktoken_ext
    is a namespace package py2app cannot list — it rides in via the static
    import below)."""
    setup_py = SPEC.parent.parent / "macos" / "setup.py"
    text = setup_py.read_text(encoding="utf-8")
    assert '"tiktoken"' in text, (
        "installer/macos/setup.py must list tiktoken in packages — extract "
        "is broken in the .app without it"
    )


def test_tokens_module_statically_imports_tiktoken_ext() -> None:
    """The direct `import tiktoken_ext.openai_public` in tokens.py is what
    makes the encodings plugin visible to BOTH bundlers' static analysis
    (py2app cannot bundle a namespace package via `packages` at all)."""
    tokens_py = (
        Path(__file__).resolve().parent.parent
        / "claude_mnemos"
        / "ingest"
        / "llm"
        / "tokens.py"
    )
    text = tokens_py.read_text(encoding="utf-8")
    assert "import tiktoken_ext.openai_public" in text, (
        "tokens.py must statically import tiktoken_ext.openai_public — the "
        "frozen builds lose the encodings plugin without it"
    )
