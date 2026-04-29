from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.core.models import WikiPageFrontmatter
from claude_mnemos.core.page_io import ParsedPage, slug_from_page_path
from claude_mnemos.core.session_start import (
    FLAVOR_WEIGHTS,
    InjectStats,
    build_adaptive_context,
    build_adaptive_context_with_stats,
    page_summary,
    score_page,
)
from claude_mnemos.state.manifest import IngestRecord, Manifest


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
    assert slug_from_page_path(tmp_path, page) == "concepts/foo"


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
    now = datetime(2026, 4, 29, tzinfo=UTC)
    score_a = score_page(a, hop_distance=2, cwd_segment="zzz", now=now)
    score_b = score_page(b, hop_distance=2, cwd_segment="zzz", now=now)
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


def _seed_manifest(vault: Path, *, sessions: list[tuple[str, list[str]]]) -> None:
    """Seed vault/.manifest.json with ingest records.

    Each tuple is ``(session_id, created_pages)``.
    """
    records: dict[str, IngestRecord] = {}
    for sid, pages in sessions:
        records[sid] = IngestRecord(
            session_id=sid,
            ingested_at=datetime.now(UTC),
            raw_path=f"raw/{sid}.md",
            source_path=None,
            created_pages=pages,
            skipped_collisions=[],
            model=None,
            input_tokens=None,
            output_tokens=None,
        )
    manifest = Manifest(ingested=records)
    atomic_write(vault / ".manifest.json", manifest.serialize_to_string())


def _write_full_page(
    vault: Path,
    slug: str,
    body: str = "",
    *,
    confidence: float = 0.7,
    flavor: list[str] | None = None,
    related: list[str] | None = None,
    status: str = "draft",
) -> None:
    page_path = vault / "wiki" / f"{slug}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    flavor_str = "[]" if not flavor else "[" + ", ".join(flavor) + "]"
    related_str = "[]" if not related else "[" + ", ".join(related) + "]"
    fm = (
        "---\n"
        f"title: {slug}\n"
        "type: concept\n"
        f"status: {status}\n"
        f"confidence: {confidence}\n"
        f"flavor: {flavor_str}\n"
        "sources: []\n"
        f"related: {related_str}\n"
        "created: 2026-04-29\n"
        "updated: 2026-04-29\n"
        "agent_written: true\n"
        "---\n"
    )
    page_path.write_text(fm + body, encoding="utf-8")


def test_build_adaptive_context_empty_vault_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir()
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=1000)
    assert out == ""


def test_build_adaptive_context_no_manifest_returns_empty(tmp_path: Path) -> None:
    _write_full_page(tmp_path, "concepts/a", body="hello")
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=1000)
    assert out == ""


def test_build_adaptive_context_includes_seeded_pages(tmp_path: Path) -> None:
    _write_full_page(tmp_path, "concepts/a", body="alpha body")
    _seed_manifest(tmp_path, sessions=[("s1", ["wiki/concepts/a.md"])])
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=2000)
    assert "concepts/a" in out


def test_build_adaptive_context_respects_char_budget(tmp_path: Path) -> None:
    for i in range(20):
        _write_full_page(tmp_path, f"concepts/p{i}", body="x" * 5000)
    pages_seeded = [f"wiki/concepts/p{i}.md" for i in range(20)]
    _seed_manifest(tmp_path, sessions=[("s1", pages_seeded)])
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=3000)
    assert len(out) <= 3500


def test_build_adaptive_context_graph_expansion(tmp_path: Path) -> None:
    _write_full_page(tmp_path, "concepts/a", body="See [[concepts/b]]")
    _write_full_page(tmp_path, "concepts/b", body="bravo body")
    _seed_manifest(tmp_path, sessions=[("s1", ["wiki/concepts/a.md"])])
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=3000)
    assert "concepts/a" in out
    assert "concepts/b" in out


def test_build_adaptive_context_with_stats_returns_pair(tmp_path: Path) -> None:
    _write_full_page(tmp_path, "concepts/a", body="alpha body")
    _seed_manifest(tmp_path, sessions=[("s1", ["wiki/concepts/a.md"])])
    context, stats = build_adaptive_context_with_stats(
        tmp_path, cwd=tmp_path, max_chars=2000,
    )
    assert "concepts/a" in context
    assert isinstance(stats, InjectStats)
    assert stats.tokens_actual > 0
    assert stats.tokens_full >= stats.tokens_actual
    assert stats.candidates_total >= 1
    assert stats.candidates_packed >= 1


def test_build_adaptive_context_with_stats_empty_vault(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir()
    context, stats = build_adaptive_context_with_stats(
        tmp_path, cwd=tmp_path, max_chars=1000,
    )
    assert context == ""
    assert stats.mode == "empty"
    assert stats.tokens_full == 0
    assert stats.tokens_actual == 0
    assert stats.candidates_total == 0
    assert stats.candidates_packed == 0


def test_build_adaptive_context_with_stats_full_mode(tmp_path: Path) -> None:
    """When all candidates fit under budget, mode == 'full'."""
    _write_full_page(tmp_path, "concepts/a", body="short body")
    _seed_manifest(tmp_path, sessions=[("s1", ["wiki/concepts/a.md"])])
    _, stats = build_adaptive_context_with_stats(
        tmp_path, cwd=tmp_path, max_chars=10_000,
    )
    assert stats.mode == "full"
    assert stats.tokens_full == stats.tokens_actual


def test_build_adaptive_context_with_stats_trimmed_mode(tmp_path: Path) -> None:
    """When budget is too small for all candidates, mode == 'trimmed'."""
    for i in range(20):
        _write_full_page(tmp_path, f"concepts/p{i}", body="x" * 5000)
    pages_seeded = [f"wiki/concepts/p{i}.md" for i in range(20)]
    _seed_manifest(tmp_path, sessions=[("s1", pages_seeded)])
    _, stats = build_adaptive_context_with_stats(
        tmp_path, cwd=tmp_path, max_chars=3000,
    )
    assert stats.mode == "trimmed"
    assert stats.tokens_full > stats.tokens_actual
    assert stats.candidates_packed < stats.candidates_total


def test_build_adaptive_context_wrapper_drops_stats(tmp_path: Path) -> None:
    """Backward-compat wrapper still returns plain string."""
    _write_full_page(tmp_path, "concepts/a", body="alpha")
    _seed_manifest(tmp_path, sessions=[("s1", ["wiki/concepts/a.md"])])
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=2000)
    assert isinstance(out, str)
    assert "concepts/a" in out
