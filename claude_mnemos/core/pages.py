"""Resolve user-supplied page references to absolute paths inside a vault."""

from __future__ import annotations

from pathlib import Path

from claude_mnemos.lint.utils import build_slug_index


class PageRefError(LookupError):
    """Raised when a page reference doesn't resolve to a vault page."""


def page_ref_to_path(vault: Path, ref: str) -> Path:
    """Resolve a page reference to an absolute path inside the vault.

    Accepts:
    - bare slug (`"foo"`) — looks up via slug index, prefers entity > concept > source
    - relative path with .md (`"wiki/entities/foo.md"`)
    - relative path without .md (`"wiki/entities/foo"`)

    Raises PageRefError on unknown slug, missing file, or path outside vault.
    """
    if not ref:
        raise PageRefError("empty page reference")

    if ref.startswith("/") or ref.startswith("\\") or ":" in ref:
        raise PageRefError(f"absolute paths not allowed: {ref!r}")

    vault_resolved = vault.resolve()

    # Detect path-like ref (contains a slash)
    if "/" in ref or "\\" in ref:
        candidate = ref if ref.endswith(".md") else f"{ref}.md"
        path = (vault / candidate).resolve()
        if not path.is_relative_to(vault_resolved):
            raise PageRefError(f"path escapes vault: {ref!r}")
        if not path.is_file():
            raise PageRefError(f"page file not found: {ref!r}")
        return path

    # Bare slug — use slug index
    index = build_slug_index(vault)
    matched = index.get(ref)
    if matched is None:
        raise PageRefError(f"unknown slug: {ref!r}")
    return matched.resolve()
