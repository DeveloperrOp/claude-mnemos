from __future__ import annotations

from claude_mnemos.core.models import (
    ExtractedPage,
    ExtractionPayload,
    ProvenanceCounts,
)
from claude_mnemos.ingest.extraction import _merge_payloads

_PROV = ProvenanceCounts(extracted_pct=100, inferred_pct=0, ambiguous_pct=0)


def _page(
    *,
    title: str,
    body: str,
    confidence: float = 0.7,
    slug_hint: str | None = None,
    related: list[str] | None = None,
    type_: str = "entity",
) -> ExtractedPage:
    return ExtractedPage(
        type=type_,  # type: ignore[arg-type]
        title=title,
        slug_hint=slug_hint,
        confidence=confidence,
        provenance=_PROV,
        related=related or [],
        body=body,
    )


def _payload(
    *pages: ExtractedPage,
    summary: str = "",
    skipped_reason: str | None = None,
) -> ExtractionPayload:
    return ExtractionPayload(
        summary=summary,
        skipped_reason=skipped_reason,
        pages=list(pages),
    )


def test_merge_dedups_same_slug_keeps_higher_confidence() -> None:
    low = _page(title="FastAPI", body="Low-confidence body.", confidence=0.3)
    high = _page(title="FastAPI", body="High-confidence body.", confidence=0.9)

    merged = _merge_payloads([_payload(low), _payload(high)])

    assert len(merged.pages) == 1
    kept = merged.pages[0]
    assert kept.confidence == 0.9
    assert kept.body == "High-confidence body."


def test_merge_identical_body_collapses_to_one() -> None:
    a = _page(title="FastAPI", body="Same body.", confidence=0.3)
    # Identical after normalization (case + whitespace fold), different confidence.
    b = _page(title="FastAPI", body="  SAME   body.  ", confidence=0.9)

    merged = _merge_payloads([_payload(a), _payload(b)])

    assert len(merged.pages) == 1
    # Identical content => keep the existing (first), ignoring confidence.
    assert merged.pages[0].body == "Same body."
    assert merged.pages[0].confidence == 0.3


def test_merge_unions_related_links() -> None:
    a = _page(title="FastAPI", body="Body A.", related=["[[a]]", "[[b]]"])
    b = _page(title="FastAPI", body="Body B.", related=["[[b]]", "[[c]]"])

    merged = _merge_payloads([_payload(a), _payload(b)])

    assert len(merged.pages) == 1
    assert merged.pages[0].related == ["[[a]]", "[[b]]", "[[c]]"]


def test_merge_concatenates_nonempty_summaries() -> None:
    p1 = _payload(_page(title="A", body="x"), summary="First summary.")
    p2 = _payload(_page(title="B", body="y"), summary="")
    p3 = _payload(_page(title="C", body="z"), summary="Third summary.")

    merged = _merge_payloads([p1, p2, p3])

    assert merged.summary == "First summary.\n\nThird summary."


def test_merge_single_payload_is_identity() -> None:
    page = _page(title="FastAPI", body="Body.", confidence=0.8, related=["[[x]]"])
    payload = _payload(page, summary="Only summary.")

    merged = _merge_payloads([payload])

    assert merged.summary == "Only summary."
    assert merged.skipped_reason is None
    assert len(merged.pages) == 1
    assert merged.pages[0].title == "FastAPI"
    assert merged.pages[0].body == "Body."
    assert merged.pages[0].confidence == 0.8
    assert merged.pages[0].related == ["[[x]]"]


def test_merge_empty_payloads() -> None:
    merged = _merge_payloads([])

    assert merged.pages == []
    assert merged.summary == ""
    assert merged.skipped_reason == "no pages"
