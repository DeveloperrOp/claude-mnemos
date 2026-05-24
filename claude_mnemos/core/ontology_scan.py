"""Ontology scanner — find duplicate/merge/rename candidates.

Phase B3b of the V1 plan. Pure heuristic prefilter (no LLM) — surfaces a
shortlist of suspicious pages that the LLM validator (Phase B3c) will judge.

False positives here are fine: the LLM filters them. False negatives are not:
real duplicates must reach the LLM stage.

Three finders:

- :func:`find_exact_duplicates` — pages with **identical normalized body**.
  Detected by SHA-256 hash on whitespace+case-folded body. These are the only
  candidates eligible for a ``delete_page`` suggestion (per the rule: never
  propose deletion based on title alone — text must match in full).

- :func:`find_partial_duplicates` — pairs with Jaccard similarity ≥ threshold
  but < 1.0 (the exact-duplicates set is explicitly excluded). These feed
  ``merge_entities`` suggestions: the apply pipeline concatenates all source
  bodies with ``## From [[slug]]`` separators, so nothing is ever lost.

- :func:`find_slug_mismatches` — pages where filename slug disagrees
  significantly with ``slugify(title)``. Cosmetic rename only — no content
  changes, no data loss.

All finders return vault-relative POSIX paths (e.g. ``wiki/concepts/foo.md``).
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from pathlib import Path

from claude_mnemos.core.ontology_similarity import (
    body_hash,
    jaccard_similarity,
    tokenize_for_similarity,
)
from claude_mnemos.core.page_io import PageParseError, read_page
from claude_mnemos.core.slug import make_slug
from claude_mnemos.lint.utils import levenshtein_distance

logger = logging.getLogger(__name__)


RENAME_LEVENSHTEIN_MIN = 4
"""Minimum edit distance between actual and suggested slug to flag a rename.

Small differences (typos, missing punctuation) are below this threshold and
are not worth bothering the user with. A rename suggestion implies physical
file move + wikilink rewrites, so it should only fire on clear mismatches.
"""


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    """A pair of pages flagged as potentially identical or overlapping.

    ``page_a`` and ``page_b`` are vault-relative POSIX paths, sorted
    lexicographically (so ``(A, B)`` and ``(B, A)`` collapse to a single
    canonical representation — important for idempotency in the orchestrator).

    ``similarity`` is 1.0 for exact duplicates, else the Jaccard score in
    [threshold, 1.0).
    """

    page_a: str
    page_b: str
    similarity: float


@dataclass(frozen=True, slots=True)
class RenameCandidate:
    """A page whose slug doesn't match its title strongly enough to warrant
    a cosmetic rename suggestion.
    """

    page: str
    current_slug: str
    suggested_slug: str


def _rel(vault: Path, p: Path) -> str:
    return p.relative_to(vault).as_posix()


def _read_body_safe(path: Path) -> str | None:
    """Return body text, or None if the page is unparseable.

    Unparseable pages are reported separately by the ``page_parse_failed``
    lint rule; the scanner just skips them to avoid blowing up on a single
    bad file.
    """
    try:
        return read_page(path).body
    except (PageParseError, OSError) as exc:
        logger.debug("scanner: skipping %s (parse error: %s)", path, exc)
        return None


def find_exact_duplicates(
    vault: Path, page_paths: list[Path]
) -> list[DuplicateCandidate]:
    """Group pages by SHA-256 of their normalized body and emit pairs.

    A group of N pages with identical body produces ``N * (N - 1) / 2`` pairs
    (every unordered pair) — the LLM validator decides which to keep.
    """
    by_hash: dict[str, list[str]] = {}
    for path in page_paths:
        body = _read_body_safe(path)
        if body is None:
            continue
        h = body_hash(body)
        by_hash.setdefault(h, []).append(_rel(vault, path))

    out: list[DuplicateCandidate] = []
    for group in by_hash.values():
        if len(group) < 2:
            continue
        group_sorted = sorted(group)
        for a, b in itertools.combinations(group_sorted, 2):
            out.append(DuplicateCandidate(page_a=a, page_b=b, similarity=1.0))
    return out


def find_partial_duplicates(
    vault: Path,
    page_paths: list[Path],
    *,
    threshold: float,
) -> list[DuplicateCandidate]:
    """Find pairs with Jaccard ≥ threshold but < 1.0 (exact pairs excluded).

    O(N²) pair walk. For an average vault (~500 pages) this is ~125K
    comparisons of set operations — sub-second. Tokens are cached per page
    so we don't tokenize the same body twice.
    """
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError("threshold must be in [0, 1]")

    cache: list[tuple[str, str, set[str]]] = []  # (rel_path, body_hash, tokens)
    for path in page_paths:
        body = _read_body_safe(path)
        if body is None:
            continue
        tokens = tokenize_for_similarity(body)
        if not tokens:
            # Empty bodies match each other 1.0 by jaccard convention; treated
            # as exact duplicates above. Skip here to avoid double-emission.
            continue
        cache.append((_rel(vault, path), body_hash(body), tokens))

    cache.sort(key=lambda t: t[0])  # deterministic pairing order

    out: list[DuplicateCandidate] = []
    for i in range(len(cache)):
        rel_a, hash_a, tok_a = cache[i]
        for j in range(i + 1, len(cache)):
            rel_b, hash_b, tok_b = cache[j]
            if hash_a == hash_b:
                # Exact duplicate — handled by find_exact_duplicates. Skip
                # here so the orchestrator doesn't see the pair twice.
                continue
            sim = jaccard_similarity(tok_a, tok_b)
            if sim >= threshold and sim < 1.0:
                out.append(
                    DuplicateCandidate(page_a=rel_a, page_b=rel_b, similarity=sim)
                )
    return out


def find_slug_mismatches(
    vault: Path, page_paths: list[Path]
) -> list[RenameCandidate]:
    """Flag pages whose filename slug doesn't match ``slugify(title)``.

    Edit distance ≥ ``RENAME_LEVENSHTEIN_MIN`` between actual and suggested
    slugs. Smaller differences (typos, hyphen variations) are below the bar.

    Unparseable pages are skipped (no frontmatter → no title to compare).
    """
    out: list[RenameCandidate] = []
    for path in page_paths:
        try:
            parsed = read_page(path)
        except (PageParseError, OSError):
            continue
        current_slug = path.stem
        suggested_slug = make_slug(parsed.frontmatter.title)
        if current_slug == suggested_slug:
            continue
        if levenshtein_distance(current_slug, suggested_slug) < RENAME_LEVENSHTEIN_MIN:
            continue
        out.append(
            RenameCandidate(
                page=_rel(vault, path),
                current_slug=current_slug,
                suggested_slug=suggested_slug,
            )
        )
    return out
