from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_mnemos.core.models import WikiPage, WikiPageFrontmatter


def test_frontmatter_minimal_valid():
    fm = WikiPageFrontmatter(
        title="Sample chat",
        type="source",
        created=date(2026, 4, 26),
        updated=date(2026, 4, 26),
    )
    assert fm.status == "draft"
    assert fm.confidence == 0.7
    assert fm.flavor == []


def test_frontmatter_rejects_unknown_type():
    with pytest.raises(ValidationError):
        WikiPageFrontmatter(
            title="X",
            type="not-a-real-type",
            created=date(2026, 4, 26),
            updated=date(2026, 4, 26),
        )


def test_frontmatter_rejects_extra_fields():
    with pytest.raises(ValidationError):
        WikiPageFrontmatter(
            title="X",
            type="source",
            created=date(2026, 4, 26),
            updated=date(2026, 4, 26),
            unknown_field="oops",
        )


def test_frontmatter_confidence_range():
    with pytest.raises(ValidationError):
        WikiPageFrontmatter(
            title="X",
            type="source",
            confidence=1.5,
            created=date(2026, 4, 26),
            updated=date(2026, 4, 26),
        )


def test_wiki_page_serialize_roundtrip_shape():
    fm = WikiPageFrontmatter(
        title="Sample",
        type="source",
        created=date(2026, 4, 26),
        updated=date(2026, 4, 26),
    )
    page = WikiPage(
        relative_path=Path("raw/chats/abc.md"),
        frontmatter=fm,
        body="# Sample\n\nbody text.\n",
    )
    out = page.serialize()
    assert out.startswith("---\n")
    assert "\n---\n" in out
    assert "title: Sample" in out
    assert "type: source" in out
    assert out.rstrip().endswith("body text.")
