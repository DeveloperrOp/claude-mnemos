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


from datetime import datetime, UTC
from claude_mnemos.core.session_start import score_page, FLAVOR_WEIGHTS


def _make_parsed_full(
    *, confidence: float = 0.7,
    flavor: list[str] | None = None,
    status: str = "draft",
    body: str = "",
    last_human_edit: datetime | None = None,
) -> ParsedPage:
    fm = WikiPageFrontmatter(
        title="x",
        type="concept",
        status=status,  # type: ignore[arg-type]
        confidence=confidence,
        flavor=flavor or [],  # type: ignore[arg-type]
        sources=[],
        related=[],
        created=date(2026, 4, 29),
        updated=date(2026, 4, 29),
        agent_written=True,
        last_human_edit=last_human_edit,
    )
    return ParsedPage(frontmatter=fm, extra_fm={}, body=body)


def test_score_page_higher_confidence_wins() -> None:
    a = _make_parsed_full(confidence=0.9)
    b = _make_parsed_full(confidence=0.3)
    score_a = score_page(a, hop_distance=2, cwd_segment="zzz", now=datetime(2026, 4, 29, tzinfo=UTC))
    score_b = score_page(b, hop_distance=2, cwd_segment="zzz", now=datetime(2026, 4, 29, tzinfo=UTC))
    assert score_a > score_b


def test_score_page_decision_flavor_outranks_reference() -> None:
    decision = _make_parsed_full(flavor=["decision"])
    reference = _make_parsed_full(flavor=["reference"])
    now = datetime(2026, 4, 29, tzinfo=UTC)
    s_decision = score_page(decision, hop_distance=2, cwd_segment="zzz", now=now)
    s_reference = score_page(reference, hop_distance=2, cwd_segment="zzz", now=now)
    assert s_decision > s_reference


def test_score_page_closer_hop_wins() -> None:
    parsed = _make_parsed_full()
    now = datetime(2026, 4, 29, tzinfo=UTC)
    s_close = score_page(parsed, hop_distance=0, cwd_segment="zzz", now=now)
    s_far = score_page(parsed, hop_distance=2, cwd_segment="zzz", now=now)
    assert s_close > s_far


def test_score_page_cwd_segment_in_body_boosts() -> None:
    matched = _make_parsed_full(body="Working on the foo project today.")
    unmatched = _make_parsed_full(body="No mention of the cwd here.")
    now = datetime(2026, 4, 29, tzinfo=UTC)
    s_match = score_page(matched, hop_distance=2, cwd_segment="foo", now=now)
    s_no_match = score_page(unmatched, hop_distance=2, cwd_segment="foo", now=now)
    assert s_match > s_no_match


def test_score_page_stale_status_penalized() -> None:
    fresh = _make_parsed_full(status="reviewed")
    stale = _make_parsed_full(status="stale")
    archived = _make_parsed_full(status="archived")
    now = datetime(2026, 4, 29, tzinfo=UTC)
    s_fresh = score_page(fresh, hop_distance=2, cwd_segment="zzz", now=now)
    s_stale = score_page(stale, hop_distance=2, cwd_segment="zzz", now=now)
    s_archived = score_page(archived, hop_distance=2, cwd_segment="zzz", now=now)
    assert s_fresh > s_stale
    assert s_fresh > s_archived


def test_score_page_recency_decay() -> None:
    fresh = _make_parsed_full(last_human_edit=datetime(2026, 4, 29, tzinfo=UTC))
    old = _make_parsed_full(last_human_edit=datetime(2025, 1, 1, tzinfo=UTC))
    now = datetime(2026, 4, 29, tzinfo=UTC)
    s_fresh = score_page(fresh, hop_distance=2, cwd_segment="zzz", now=now)
    s_old = score_page(old, hop_distance=2, cwd_segment="zzz", now=now)
    assert s_fresh > s_old


def test_flavor_weights_decision_max() -> None:
    assert FLAVOR_WEIGHTS["decision"] >= FLAVOR_WEIGHTS["reference"]
    assert FLAVOR_WEIGHTS["lesson"] >= FLAVOR_WEIGHTS["reference"]
