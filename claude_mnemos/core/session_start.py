"""SessionStart adaptive context inject (Plan #13c, spec §5.2 / §9.2).

Builder for the ``additionalContext`` block that the SessionStart hook emits
at session start. Combines frontmatter weights, recency, ontology graph
proximity to recent-session pages, and cwd-grep boosts to rank vault pages.

Token budgeting uses a 4-chars≈1-token approximation. No tokenizer dep.

Pure functions: no I/O beyond reading the vault's manifest + page files.
Hook entrypoint lives in ``hooks/session_start.py``.
"""

from __future__ import annotations

from pathlib import Path

from claude_mnemos.core.page_io import ParsedPage


def page_slug_from_path(vault: Path, page_path: Path) -> str:
    """Slug = relative path under ``vault/wiki/`` without ``.md`` suffix.

    Example: ``vault/wiki/concepts/foo.md`` → ``concepts/foo``.
    Always uses forward slashes (Windows safe).
    """
    rel = page_path.relative_to(vault / "wiki")
    return str(rel.with_suffix("")).replace("\\", "/")


def page_summary(parsed: ParsedPage, *, max_chars: int = 200) -> str:
    """Return the first non-empty ``max_chars`` characters of the page body.

    Strips leading whitespace. Used for short blurbs in the inject manifest.
    """
    body = parsed.body.lstrip()
    if not body:
        return ""
    return body[:max_chars]
