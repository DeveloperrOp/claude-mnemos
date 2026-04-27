from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from claude_mnemos.core.models import WikiPageFrontmatter
from claude_mnemos.core.page_io import (
    PageParseError,
    ParsedPage,
    read_page,
    serialize_page,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_read_page_plain(tmp_path: Path):
    p = tmp_path / "wiki/entities/foo.md"
    _write(
        p,
        """---
title: Foo
type: entity
status: draft
confidence: 0.7
flavor: []
sources: []
related: []
created: 2026-04-26
updated: 2026-04-26
agent_written: true
---
body line one
body line two
""",
    )
    parsed = read_page(p)
    assert parsed.frontmatter.title == "Foo"
    assert parsed.frontmatter.type == "entity"
    assert parsed.frontmatter.agent_written is True
    assert parsed.extra_fm == {}
    assert "body line one" in parsed.body
    assert "body line two" in parsed.body


def test_read_page_with_extras(tmp_path: Path):
    p = tmp_path / "wiki/entities/foo.md"
    _write(
        p,
        """---
title: Foo
type: entity
created: 2026-04-26
updated: 2026-04-26
agent_written: true
cssclass: my-class
obsidianUIMode: preview
---
body
""",
    )
    parsed = read_page(p)
    assert parsed.frontmatter.title == "Foo"
    assert parsed.extra_fm == {"cssclass": "my-class", "obsidianUIMode": "preview"}


def test_read_page_invalid_yaml_raises(tmp_path: Path):
    p = tmp_path / "wiki/entities/foo.md"
    _write(
        p,
        """---
title: [unclosed
type: entity
---
body
""",
    )
    with pytest.raises(PageParseError):
        read_page(p)


def test_read_page_missing_required_field_raises(tmp_path: Path):
    p = tmp_path / "wiki/entities/foo.md"
    # Missing `title` (required).
    _write(
        p,
        """---
type: entity
created: 2026-04-26
updated: 2026-04-26
---
body
""",
    )
    with pytest.raises(PageParseError):
        read_page(p)


def test_read_page_no_frontmatter_raises(tmp_path: Path):
    p = tmp_path / "wiki/entities/foo.md"
    _write(p, "# just a heading\nno frontmatter here\n")
    with pytest.raises(PageParseError):
        read_page(p)


def test_serialize_round_trip_plain(tmp_path: Path):
    fm = WikiPageFrontmatter(
        title="Foo",
        type="entity",
        created=date(2026, 4, 26),
        updated=date(2026, 4, 26),
    )
    parsed = ParsedPage(frontmatter=fm, extra_fm={}, body="body line\n")
    out = serialize_page(parsed)

    assert out.startswith("---\n")
    assert "title: Foo" in out
    assert "type: entity" in out
    assert "agent_written: true" in out
    assert out.endswith("body line\n")


def test_serialize_preserves_extras(tmp_path: Path):
    fm = WikiPageFrontmatter(
        title="Foo",
        type="entity",
        created=date(2026, 4, 26),
        updated=date(2026, 4, 26),
    )
    parsed = ParsedPage(
        frontmatter=fm,
        extra_fm={"cssclass": "my-class", "obsidianUIMode": "preview"},
        body="body\n",
    )
    out = serialize_page(parsed)
    assert "cssclass: my-class" in out
    assert "obsidianUIMode: preview" in out


def test_serialize_after_mutation_preserves_extras(tmp_path: Path):
    p = tmp_path / "wiki/entities/foo.md"
    _write(
        p,
        """---
title: Foo
type: entity
created: 2026-04-26
updated: 2026-04-26
agent_written: true
cssclass: my-class
---
body
""",
    )
    parsed = read_page(p)
    new_fm = parsed.frontmatter.model_copy(
        update={
            "agent_written": False,
            "last_human_edit": datetime(2026, 4, 27, 14, 0, 0, tzinfo=UTC),
        }
    )
    new_parsed = ParsedPage(frontmatter=new_fm, extra_fm=parsed.extra_fm, body=parsed.body)
    out = serialize_page(new_parsed)

    assert "agent_written: false" in out
    assert "last_human_edit:" in out
    assert "cssclass: my-class" in out  # extras preserved


def test_round_trip_byte_stable_for_known_fields(tmp_path: Path):
    """Read → serialize must yield a result that re-parses to the same model."""
    p = tmp_path / "wiki/entities/foo.md"
    _write(
        p,
        """---
title: Foo
type: entity
status: draft
confidence: 0.7
flavor: []
sources: []
related: []
created: 2026-04-26
updated: 2026-04-26
agent_written: true
---
body
""",
    )
    parsed = read_page(p)
    out = serialize_page(parsed)
    p.write_text(out, encoding="utf-8")
    parsed2 = read_page(p)
    assert parsed2.frontmatter == parsed.frontmatter
    assert parsed2.body == parsed.body
