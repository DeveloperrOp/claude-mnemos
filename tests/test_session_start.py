from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos.core.session_start import (
    page_slug_from_path,
    page_summary,
)
from claude_mnemos.core.page_io import ParsedPage
from claude_mnemos.core.models import WikiPageFrontmatter
from datetime import date


def _make_parsed(slug: str, body: str, *, confidence: float = 0.7) -> ParsedPage:
    fm = WikiPageFrontmatter(
        title=slug,
        type="concept",
        status="draft",
        confidence=confidence,
        flavor=[],
        sources=[],
        related=[],
        created=date(2026, 4, 29),
        updated=date(2026, 4, 29),
        agent_written=True,
    )
    return ParsedPage(frontmatter=fm, extra_fm={}, body=body)


def test_page_slug_from_path_strips_wiki_prefix_and_md(tmp_path: Path) -> None:
    page = tmp_path / "wiki" / "concepts" / "foo.md"
    page.parent.mkdir(parents=True)
    page.write_text("", encoding="utf-8")
    assert page_slug_from_path(tmp_path, page) == "concepts/foo"


def test_page_summary_returns_first_n_chars() -> None:
    parsed = _make_parsed("foo", "Hello world. " * 50)
    summary = page_summary(parsed, max_chars=80)
    assert len(summary) <= 80
    assert summary.startswith("Hello world.")


def test_page_summary_strips_leading_whitespace() -> None:
    parsed = _make_parsed("foo", "\n\n   Hello world\n\nMore content")
    summary = page_summary(parsed, max_chars=200)
    assert summary.startswith("Hello world")


def test_page_summary_empty_body_returns_empty() -> None:
    parsed = _make_parsed("foo", "")
    assert page_summary(parsed, max_chars=200) == ""
