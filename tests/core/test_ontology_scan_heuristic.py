"""Tests for ontology_scan heuristic candidate finders (Phase B3b).

The finders are pre-filters: they shortlist suspicious page pairs/singletons
that the LLM validator (Phase B3c) will judge. False positives are tolerated
here (the LLM filters them); false negatives are not (a real duplicate must
make it to the LLM stage).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos.core.ontology_scan import (
    DuplicateCandidate,
    RenameCandidate,
    find_exact_duplicates,
    find_partial_duplicates,
    find_slug_mismatches,
)


def _write_page(
    vault: Path,
    rel: str,
    *,
    title: str = "Test",
    body: str = "",
    page_type: str = "concept",
) -> Path:
    """Write a minimal valid wiki page. Frontmatter strict — caller must provide
    a title that matches the slug if it cares about RenameCandidate behavior.
    """
    today = "2026-05-22"
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        f"---\n"
        f"title: {title}\n"
        f"type: {page_type}\n"
        f"status: draft\n"
        f"confidence: 0.7\n"
        f"flavor: []\n"
        f"sources: []\n"
        f"related: []\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"agent_written: false\n"
        f"---\n\n{body}"
    )
    path.write_text(fm, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# find_exact_duplicates
# ---------------------------------------------------------------------------


class TestFindExactDuplicates:
    def test_no_duplicates_empty_list(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        result = find_exact_duplicates(vault, [])
        assert result == []

    def test_finds_two_pages_with_identical_body(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        a = _write_page(vault, "wiki/concepts/foo.md", title="Foo", body="same body text")
        b = _write_page(vault, "wiki/concepts/bar.md", title="Bar", body="same body text")
        result = find_exact_duplicates(vault, [a, b])
        assert len(result) == 1
        cand = result[0]
        assert isinstance(cand, DuplicateCandidate)
        # Pair members sorted lexicographically (a < b deterministic ordering).
        assert {cand.page_a, cand.page_b} == {
            "wiki/concepts/bar.md",
            "wiki/concepts/foo.md",
        }
        assert cand.similarity == 1.0

    def test_ignores_pages_with_different_body(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        a = _write_page(vault, "wiki/concepts/foo.md", body="body A")
        b = _write_page(vault, "wiki/concepts/bar.md", body="body B")
        result = find_exact_duplicates(vault, [a, b])
        assert result == []

    def test_normalizes_whitespace(self, tmp_path: Path) -> None:
        # Two pages with semantically equal but textually different body
        # (extra whitespace) should still be detected as duplicates.
        vault = tmp_path / "v"
        vault.mkdir()
        a = _write_page(vault, "wiki/concepts/foo.md", body="hello world")
        b = _write_page(vault, "wiki/concepts/bar.md", body="hello   WORLD\n\n")
        result = find_exact_duplicates(vault, [a, b])
        assert len(result) == 1

    def test_three_identical_pages_produce_three_pairs(self, tmp_path: Path) -> None:
        # A, B, C all identical → three pairs (A-B, A-C, B-C).
        vault = tmp_path / "v"
        vault.mkdir()
        a = _write_page(vault, "wiki/concepts/a.md", body="x")
        b = _write_page(vault, "wiki/concepts/b.md", body="x")
        c = _write_page(vault, "wiki/concepts/c.md", body="x")
        result = find_exact_duplicates(vault, [a, b, c])
        assert len(result) == 3


# ---------------------------------------------------------------------------
# find_partial_duplicates
# ---------------------------------------------------------------------------


class TestFindPartialDuplicates:
    def test_finds_pair_above_threshold(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        # Heavy overlap but not identical.
        a = _write_page(
            vault,
            "wiki/concepts/foo.md",
            body="authentication uses jwt tokens with refresh logic for security",
        )
        b = _write_page(
            vault,
            "wiki/concepts/bar.md",
            body="authentication uses jwt tokens with refresh handling for safety",
        )
        result = find_partial_duplicates(vault, [a, b], threshold=0.5)
        assert len(result) == 1
        assert result[0].similarity > 0.5
        assert result[0].similarity < 1.0

    def test_excludes_pair_below_threshold(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        a = _write_page(vault, "wiki/concepts/foo.md", body="completely different content here")
        b = _write_page(vault, "wiki/concepts/bar.md", body="nothing alike whatsoever totally")
        result = find_partial_duplicates(vault, [a, b], threshold=0.5)
        assert result == []

    def test_excludes_exact_duplicates(self, tmp_path: Path) -> None:
        # Exact duplicates are handled by find_exact_duplicates — partial
        # finder must NOT also flag them (otherwise the orchestrator counts
        # the same pair twice and creates two suggestions).
        vault = tmp_path / "v"
        vault.mkdir()
        a = _write_page(vault, "wiki/concepts/foo.md", body="same identical text here")
        b = _write_page(vault, "wiki/concepts/bar.md", body="same identical text here")
        result = find_partial_duplicates(vault, [a, b], threshold=0.5)
        assert result == []

    def test_respects_threshold(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        a = _write_page(vault, "wiki/concepts/foo.md", body="alpha beta gamma delta")
        b = _write_page(vault, "wiki/concepts/bar.md", body="alpha epsilon zeta theta")
        # Jaccard = 1 / 7 ≈ 0.14
        assert find_partial_duplicates(vault, [a, b], threshold=0.5) == []
        # With low threshold it should appear:
        loose = find_partial_duplicates(vault, [a, b], threshold=0.1)
        assert len(loose) == 1


# ---------------------------------------------------------------------------
# find_slug_mismatches
# ---------------------------------------------------------------------------


class TestFindSlugMismatches:
    def test_returns_empty_when_slug_matches_title(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        # title "Auth JWT Pattern" slugifies to "auth-jwt-pattern" — matches.
        p = _write_page(vault, "wiki/concepts/auth-jwt-pattern.md", title="Auth JWT Pattern")
        result = find_slug_mismatches(vault, [p])
        assert result == []

    def test_flags_page_with_strong_mismatch(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        vault.mkdir()
        # Title implies slug "concepts/auth-pattern" but filename is "foo".
        p = _write_page(vault, "wiki/concepts/foo.md", title="Auth Pattern")
        result = find_slug_mismatches(vault, [p])
        assert len(result) == 1
        cand = result[0]
        assert isinstance(cand, RenameCandidate)
        assert cand.page == "wiki/concepts/foo.md"
        assert cand.current_slug == "foo"
        assert cand.suggested_slug == "auth-pattern"

    def test_ignores_minor_differences(self, tmp_path: Path) -> None:
        # "Auth-JWT-Pattern" filename, "Auth JWT Pattern" title — slugify both
        # gives "auth-jwt-pattern". Already matches. No false positive.
        vault = tmp_path / "v"
        vault.mkdir()
        p = _write_page(vault, "wiki/concepts/auth-jwt-pattern.md", title="Auth JWT Pattern")
        result = find_slug_mismatches(vault, [p])
        assert result == []

    def test_ignores_parse_failures(self, tmp_path: Path) -> None:
        # Broken frontmatter must not crash the finder.
        vault = tmp_path / "v"
        (vault / "wiki" / "concepts").mkdir(parents=True)
        broken = vault / "wiki" / "concepts" / "broken.md"
        broken.write_text("not yaml at all\n# Heading\n", encoding="utf-8")
        result = find_slug_mismatches(vault, [broken])
        assert result == []


# ---------------------------------------------------------------------------
# Integration: realistic mixed-vault scenario
# ---------------------------------------------------------------------------


def test_scan_works_on_mixed_vault(tmp_path: Path) -> None:
    """Sanity check — all three finders cooperate on a multi-page vault."""
    vault = tmp_path / "v"
    vault.mkdir()

    # Two exact duplicates
    a = _write_page(vault, "wiki/concepts/dup-a.md", title="Dup A", body="copy paste content")
    b = _write_page(vault, "wiki/concepts/dup-b.md", title="Dup B", body="copy paste content")
    # One slug mismatch
    c = _write_page(vault, "wiki/concepts/old-name.md", title="New Better Name")
    # One distinct page
    d = _write_page(
        vault, "wiki/concepts/separate.md", title="Separate", body="unrelated discussion"
    )

    pages = [a, b, c, d]
    exact = find_exact_duplicates(vault, pages)
    partial = find_partial_duplicates(vault, pages, threshold=0.5)
    renames = find_slug_mismatches(vault, pages)

    assert len(exact) == 1
    assert len(partial) == 0  # exact pair excluded from partial; nothing else overlaps
    assert len(renames) == 1
    assert renames[0].page == "wiki/concepts/old-name.md"
