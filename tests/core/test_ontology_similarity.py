"""Tests for ontology_similarity helpers (Plan: Ontology Scanner V1, Phase B3a).

Pure math, no I/O. Each helper has a single responsibility and the tests cover:
- normalize_body: whitespace + case folding stability
- body_hash: identical normalized bodies hash equal, different bodies differ
- tokenize: extracts useful tokens, drops noise (short words, punctuation)
- jaccard: bounds [0, 1] + correctness on simple sets + edge cases
"""

from __future__ import annotations

from claude_mnemos.core.ontology_similarity import (
    body_hash,
    jaccard_similarity,
    normalize_body,
    tokenize_for_similarity,
)


class TestNormalizeBody:
    def test_lowercases(self) -> None:
        assert normalize_body("Hello WORLD") == "hello world"

    def test_collapses_whitespace(self) -> None:
        assert normalize_body("a   b\tc\n\nd") == "a b c d"

    def test_strips_edges(self) -> None:
        assert normalize_body("  hi  \n") == "hi"

    def test_empty_input(self) -> None:
        assert normalize_body("") == ""
        assert normalize_body("   \n\t") == ""


class TestBodyHash:
    def test_identical_normalized_bodies_hash_equal(self) -> None:
        assert body_hash("Hello World") == body_hash("hello   world")
        assert body_hash("a\nb") == body_hash("a b")

    def test_different_bodies_hash_differently(self) -> None:
        assert body_hash("hello") != body_hash("world")

    def test_returns_hex_string(self) -> None:
        h = body_hash("anything")
        assert isinstance(h, str)
        assert len(h) == 64  # sha256
        int(h, 16)  # must be valid hex


class TestTokenize:
    def test_extracts_words(self) -> None:
        tokens = tokenize_for_similarity("the quick brown fox")
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens

    def test_drops_short_words(self) -> None:
        # Words of length <= 2 are noise (a, an, of, to, is, ...). Drop them.
        tokens = tokenize_for_similarity("a fox is on the run")
        assert "a" not in tokens
        assert "is" not in tokens
        assert "on" not in tokens
        assert "fox" in tokens
        assert "run" in tokens

    def test_lowercases(self) -> None:
        tokens = tokenize_for_similarity("Hello WORLD")
        assert "hello" in tokens
        assert "world" in tokens

    def test_handles_punctuation(self) -> None:
        tokens = tokenize_for_similarity("hello, world! it's great.")
        assert "hello" in tokens
        assert "world" in tokens
        assert "great" in tokens

    def test_returns_set(self) -> None:
        tokens = tokenize_for_similarity("repeat repeat repeat")
        assert isinstance(tokens, set)
        assert tokens == {"repeat"}

    def test_empty_input(self) -> None:
        assert tokenize_for_similarity("") == set()

    def test_handles_markdown_artifacts(self) -> None:
        # Wikilinks, markdown headers, bold — extract the word content.
        tokens = tokenize_for_similarity("# Heading\n\n**bold** [[wikilink]]")
        assert "heading" in tokens
        assert "bold" in tokens
        assert "wikilink" in tokens


class TestJaccard:
    def test_identical_sets(self) -> None:
        s = {"a", "b", "c"}
        assert jaccard_similarity(s, s) == 1.0

    def test_disjoint_sets(self) -> None:
        assert jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_half_overlap(self) -> None:
        # |A ∩ B| = 1 ({"b"}), |A ∪ B| = 3 ({"a", "b", "c"}) → 1/3
        result = jaccard_similarity({"a", "b"}, {"b", "c"})
        assert abs(result - 1 / 3) < 1e-9

    def test_subset(self) -> None:
        # B ⊂ A: |A ∩ B| = |B|, |A ∪ B| = |A|, so result = |B| / |A|
        result = jaccard_similarity({"a", "b", "c", "d"}, {"a", "b"})
        assert abs(result - 0.5) < 1e-9

    def test_both_empty(self) -> None:
        # Convention: two empty sets are "identical" (no disagreement).
        assert jaccard_similarity(set(), set()) == 1.0

    def test_one_empty(self) -> None:
        assert jaccard_similarity({"a"}, set()) == 0.0
        assert jaccard_similarity(set(), {"a"}) == 0.0
