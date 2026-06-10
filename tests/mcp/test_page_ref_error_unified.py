"""Regression guard: PageRefError must be ONE class across the codebase.

There used to be two unrelated classes with the same name and different base
classes (mcp.errors.PageRefError(ValueError) vs core.pages.PageRefError(
LookupError)). A handler / `except` importing one silently failed to catch
the other. They are now the same object.
"""

from __future__ import annotations

from claude_mnemos.core.pages import PageRefError as CorePageRefError
from claude_mnemos.mcp.errors import PageRefError as McpPageRefError


def test_page_ref_error_is_a_single_class() -> None:
    assert McpPageRefError is CorePageRefError


def test_except_from_either_import_catches_the_other() -> None:
    # Raise via the core import, catch via the mcp import.
    try:
        raise CorePageRefError("boom")
    except McpPageRefError as exc:
        assert str(exc) == "boom"
    else:  # pragma: no cover
        raise AssertionError("mcp PageRefError did not catch core PageRefError")
