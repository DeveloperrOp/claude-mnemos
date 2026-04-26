from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_mnemos.core.models import (
    ExtractedPage,
    ExtractionPayload,
    ProvenanceCounts,
    WikiPage,
    WikiPageFrontmatter,
    save_wiki_pages_tool_schema,
)


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
    assert out.endswith("body text.\n")


def test_wiki_page_serialize_normalizes_trailing_newline():
    fm = WikiPageFrontmatter(
        title="Sample",
        type="source",
        created=date(2026, 4, 26),
        updated=date(2026, 4, 26),
    )
    page_no_nl = WikiPage(
        relative_path=Path("raw/chats/abc.md"),
        frontmatter=fm,
        body="end without newline",
    )
    page_many_nl = WikiPage(
        relative_path=Path("raw/chats/abc.md"),
        frontmatter=fm,
        body="end with too many\n\n\n",
    )
    assert page_no_nl.serialize().endswith("end without newline\n")
    assert page_many_nl.serialize().endswith("end with too many\n")


def test_provenance_counts_valid():
    p = ProvenanceCounts(extracted_pct=70, inferred_pct=25, ambiguous_pct=5)
    assert p.extracted_pct == 70


def test_provenance_counts_rejects_negative():
    with pytest.raises(ValidationError):
        ProvenanceCounts(extracted_pct=-1, inferred_pct=0, ambiguous_pct=0)


def test_provenance_counts_rejects_over_100():
    with pytest.raises(ValidationError):
        ProvenanceCounts(extracted_pct=101, inferred_pct=0, ambiguous_pct=0)


def test_extracted_page_minimal_valid():
    page = ExtractedPage(
        type="entity",
        title="FastAPI",
        flavor=[],
        confidence=0.8,
        provenance=ProvenanceCounts(extracted_pct=80, inferred_pct=15, ambiguous_pct=5),
        related=[],
        body="FastAPI is a Python web framework.",
    )
    assert page.title == "FastAPI"
    assert page.slug_hint is None


def test_extracted_page_rejects_source_type():
    with pytest.raises(ValidationError):
        ExtractedPage(
            type="source",
            title="X",
            flavor=[],
            confidence=0.7,
            provenance=ProvenanceCounts(extracted_pct=100, inferred_pct=0, ambiguous_pct=0),
            related=[],
            body="x",
        )


def test_extracted_page_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ExtractedPage(
            type="entity",
            title="X",
            flavor=[],
            confidence=0.7,
            provenance=ProvenanceCounts(extracted_pct=100, inferred_pct=0, ambiguous_pct=0),
            related=[],
            body="x",
            unknown="oops",
        )


def test_extracted_page_rejects_empty_body():
    with pytest.raises(ValidationError):
        ExtractedPage(
            type="entity",
            title="X",
            flavor=[],
            confidence=0.7,
            provenance=ProvenanceCounts(extracted_pct=100, inferred_pct=0, ambiguous_pct=0),
            related=[],
            body="",
        )


def test_extraction_payload_with_pages():
    payload = ExtractionPayload(
        summary="A discussion about FastAPI.",
        pages=[
            ExtractedPage(
                type="entity",
                title="FastAPI",
                flavor=["reference"],
                confidence=0.9,
                provenance=ProvenanceCounts(extracted_pct=80, inferred_pct=15, ambiguous_pct=5),
                related=[],
                body="A Python framework.",
            )
        ],
    )
    assert len(payload.pages) == 1
    assert payload.skipped_reason is None


def test_extraction_payload_empty_pages_with_reason():
    payload = ExtractionPayload(
        summary="Just a greeting.",
        skipped_reason="trivial conversation",
        pages=[],
    )
    assert payload.pages == []
    assert payload.skipped_reason == "trivial conversation"


def test_frontmatter_accepts_provenance():
    p = ProvenanceCounts(extracted_pct=70, inferred_pct=25, ambiguous_pct=5)
    fm = WikiPageFrontmatter(
        title="X",
        type="entity",
        provenance=p,
        created=date(2026, 4, 26),
        updated=date(2026, 4, 26),
    )
    assert fm.provenance is not None
    assert fm.provenance.extracted_pct == 70


def test_frontmatter_agent_written_default_true():
    fm = WikiPageFrontmatter(
        title="X",
        type="entity",
        created=date(2026, 4, 26),
        updated=date(2026, 4, 26),
    )
    assert fm.agent_written is True


def test_frontmatter_provenance_serializes_as_dict():
    p = ProvenanceCounts(extracted_pct=70, inferred_pct=25, ambiguous_pct=5)
    fm = WikiPageFrontmatter(
        title="X",
        type="entity",
        provenance=p,
        created=date(2026, 4, 26),
        updated=date(2026, 4, 26),
    )
    dumped = fm.model_dump(mode="json")
    assert dumped["provenance"] == {"extracted_pct": 70, "inferred_pct": 25, "ambiguous_pct": 5}


def test_tool_schema_shape():
    schema = save_wiki_pages_tool_schema()
    assert schema["name"] == "save_wiki_pages"
    assert "input_schema" in schema
    inp = schema["input_schema"]
    assert inp["type"] == "object"
    assert "summary" in inp["properties"]
    assert "pages" in inp["properties"]
    assert inp["additionalProperties"] is False
    page_item = inp["properties"]["pages"]["items"]
    assert page_item["additionalProperties"] is False
    assert "type" in page_item["properties"]
    assert "slug_hint" in page_item["properties"]
    assert page_item["properties"]["type"]["enum"] == ["entity", "concept"]
