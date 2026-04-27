"""Lint-specific exception hierarchy."""

from __future__ import annotations


class LintError(RuntimeError):
    """Generic lint failure (autofix promote failed, etc.)."""


class LintCorruptError(ValueError):
    """Raised when .lint-results.json is unreadable or fails schema validation."""
