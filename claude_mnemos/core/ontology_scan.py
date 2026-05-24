"""Ontology scanner — find duplicate/merge/rename candidates.

V1 plan (Phases B3a–B3d). Two-stage detection:

**Stage 1 — heuristic prefilter (this module, B3a/B3b)**. No LLM. Surfaces a
shortlist of suspicious pages. False positives are fine (LLM filters them);
false negatives are not (real duplicates must reach the LLM stage).

**Stage 2 — LLM validator** (:mod:`claude_mnemos.core.ontology_validator`).
Classifies each candidate as duplicate / merge / distinct.

**Stage 3 — orchestrator** (:func:`scan_ontology`, B3d). Glues stages 1+2,
materialises results as pending Suggestions via SuggestionStore. Enforces
idempotency: re-running scan never duplicates suggestions, honors archived
verdicts (user rejected → never re-propose).

Three finders:

- :func:`find_exact_duplicates` — pages with **identical normalized body**
  (SHA-256 hash on whitespace+case-folded body). The only path to a
  ``delete_page`` suggestion (design rule: never delete based on title alone).
- :func:`find_partial_duplicates` — Jaccard similarity ≥ threshold but < 1.0
  (exact pairs excluded so they don't surface twice). Feeds ``merge_entities``.
- :func:`find_slug_mismatches` — filename slug vs ``slugify(title)`` with
  Levenshtein ≥ 4. Cosmetic rename — no content changes, no data loss.

All finders return vault-relative POSIX paths (e.g. ``wiki/concepts/foo.md``).
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from claude_mnemos.core.ontology_similarity import (
    body_hash,
    jaccard_similarity,
    tokenize_for_similarity,
)
from claude_mnemos.core.ontology_validator import (
    OntologyLLMValidator,
    ValidationVerdict,
    VerdictKind,
)
from claude_mnemos.core.page_io import PageParseError, read_page
from claude_mnemos.core.slug import make_slug
from claude_mnemos.ingest.llm import LLMClient, LLMExtractionError
from claude_mnemos.lint.utils import levenshtein_distance
from claude_mnemos.state.ontology import (
    Suggestion,
    SuggestionFrontmatter,
    SuggestionStore,
    generate_suggestion_id,
)

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


# ---------------------------------------------------------------------------
# Orchestrator (Phase B3d)
# ---------------------------------------------------------------------------


DEFAULT_PARTIAL_THRESHOLD = 0.7
DEFAULT_MAX_LLM_CALLS = 50


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Counts + IDs from a single scan run.

    ``created`` is the list of suggestion IDs the orchestrator wrote to the
    SuggestionStore. ``errors`` collects (pair_repr, message) tuples for pairs
    where the LLM call raised — they're skipped, not fatal.

    ``skipped_distinct`` counts pairs the LLM classified as unrelated (good —
    LLM did its filtering job). ``skipped_existing`` counts pairs that would
    have produced an already-existing Suggestion (idempotency). ``skipped_capped``
    counts pairs dropped because they exceeded ``max_llm_calls`` budget.
    """

    created: list[str]
    skipped_distinct: int
    skipped_existing: int
    skipped_capped: int
    errors: list[tuple[str, str]]
    scanned_pages: int


def _collect_wiki_pages(vault: Path) -> list[Path]:
    """Return all ``wiki/**/*.md`` files (excluding dotfile-prefixed dirs).

    Same selection logic as :class:`LintRunner` — keep them in sync if either
    set of rules changes.
    """
    out: list[Path] = []
    for p in sorted((vault / "wiki").glob("**/*.md") if (vault / "wiki").is_dir() else []):
        if any(part.startswith(".") for part in p.parts):
            continue
        if p.is_file():
            out.append(p)
    return out


def _existing_dedup_keys(
    store: SuggestionStore,
) -> set[tuple[str, frozenset[str], str | None]]:
    """Collect dedup keys for ALL existing suggestions (pending + archived).

    Archived = approved/rejected — we never re-propose them. The user already
    decided. Re-proposing rejected suggestions wastes the user's attention.
    """
    keys: set[tuple[str, frozenset[str], str | None]] = set()
    for s in store.list(include_archive=True):
        keys.add(
            (
                s.frontmatter.operation,
                frozenset(s.frontmatter.affected_pages),
                s.frontmatter.proposed_target,
            )
        )
    return keys


def _create_suggestion(
    store: SuggestionStore,
    *,
    operation: str,
    affected_pages: list[str],
    proposed_target: str | None,
    reason: str,
    confidence: float,
    now: datetime,
) -> str:
    sid = generate_suggestion_id(now)
    suggestion = Suggestion(
        frontmatter=SuggestionFrontmatter(
            id=sid,
            created=now,
            operation=operation,  # type: ignore[arg-type]
            affected_pages=affected_pages,
            proposed_target=proposed_target,
            reason=reason,
            confidence=confidence,
        ),
        body=reason,
    )
    store.create(suggestion)
    return sid


def _resolve_target_relpath(
    page_a: str,
    page_b: str,
    target_slug: str,
) -> tuple[str, str]:
    """Decide which operation and target path to use given an LLM target_slug.

    Returns ``(operation, target_relpath_or_empty)``.

    Logic:
    - If ``target_slug`` matches one of the source page stems → ``delete_page``
      for the OTHER page (the kept one already has the right name).
    - Else → ``merge_entities`` with target ``wiki/<category>/<target_slug>.md``
      where category is page_a's parent directory name.
    """
    a_stem = Path(page_a).stem
    b_stem = Path(page_b).stem
    if target_slug == a_stem:
        return ("delete_page", page_b)
    if target_slug == b_stem:
        return ("delete_page", page_a)
    category = Path(page_a).parent.name  # e.g. "concepts"
    new_target = f"wiki/{category}/{target_slug}.md"
    return ("merge_entities", new_target)


def _process_pair(
    store: SuggestionStore,
    existing_keys: set[tuple[str, frozenset[str], str | None]],
    *,
    validator: OntologyLLMValidator,
    page_a: str,
    body_a: str,
    page_b: str,
    body_b: str,
    similarity: float,
    now: datetime,
    out_created: list[str],
    counters: dict[str, int],
    errors: list[tuple[str, str]],
) -> None:
    """Handle one candidate pair: ask LLM, then create/skip suggestion."""
    pair_repr = f"{page_a} ↔ {page_b}"
    try:
        verdict = validator.validate_pair(
            page_a=page_a,
            body_a=body_a,
            page_b=page_b,
            body_b=body_b,
            similarity=similarity,
        )
    except LLMExtractionError as exc:
        errors.append((pair_repr, str(exc)))
        return

    if verdict.verdict == VerdictKind.DISTINCT:
        counters["distinct"] += 1
        return

    # verdict ∈ {DUPLICATE, MERGE} — both require target_slug (validator already
    # rejected payloads without it, so this is defensive).
    if not verdict.target_slug:
        errors.append((pair_repr, "missing target_slug despite verdict requiring one"))
        return

    if verdict.verdict == VerdictKind.DUPLICATE:
        operation, target = _resolve_target_relpath(
            page_a, page_b, verdict.target_slug
        )
        if operation == "delete_page":
            affected = [target]
            target_for_dedup: str | None = None
        else:
            affected = sorted([page_a, page_b])
            target_for_dedup = target
    else:  # MERGE
        category = Path(page_a).parent.name
        target = f"wiki/{category}/{verdict.target_slug}.md"
        operation = "merge_entities"
        affected = sorted([page_a, page_b])
        target_for_dedup = target

    key = (operation, frozenset(affected), target_for_dedup)
    if key in existing_keys:
        counters["existing"] += 1
        return

    sid = _create_suggestion(
        store,
        operation=operation,
        affected_pages=affected,
        proposed_target=target_for_dedup,
        reason=verdict.reason,
        confidence=0.85 if similarity >= 0.99 else 0.7,
        now=now,
    )
    existing_keys.add(key)
    out_created.append(sid)


def _process_rename(
    vault: Path,
    store: SuggestionStore,
    existing_keys: set[tuple[str, frozenset[str], str | None]],
    *,
    candidate: RenameCandidate,
    now: datetime,
    out_created: list[str],
    counters: dict[str, int],
) -> None:
    """Create a rename_entity suggestion if the new path is free."""
    src = candidate.page
    category = Path(src).parent.name
    target = f"wiki/{category}/{candidate.suggested_slug}.md"
    if (vault / target).exists():
        # Target collides with an existing page — silently skip; the user can
        # still rename manually if they want.
        return

    key = ("rename_entity", frozenset([src]), target)
    if key in existing_keys:
        counters["existing"] += 1
        return

    sid = _create_suggestion(
        store,
        operation="rename_entity",
        affected_pages=[src],
        proposed_target=target,
        reason=(
            f"Filename slug '{candidate.current_slug}' diverges from "
            f"slugified title '{candidate.suggested_slug}'. Rename keeps title and slug in sync."
        ),
        confidence=0.6,
        now=now,
    )
    existing_keys.add(key)
    out_created.append(sid)


def scan_ontology(
    vault: Path,
    *,
    llm: LLMClient,
    max_llm_calls: int = DEFAULT_MAX_LLM_CALLS,
    partial_threshold: float = DEFAULT_PARTIAL_THRESHOLD,
    now: datetime | None = None,
) -> ScanResult:
    """Run the full scanner on ``vault``. Idempotent across re-invocations.

    Pipeline:
    1. Collect ``wiki/**/*.md`` pages.
    2. Heuristic finders: exact duplicates, partial duplicates, slug mismatches.
    3. Cap duplicate candidates at ``max_llm_calls`` (highest similarity wins).
    4. For each duplicate candidate: ask LLM, materialise suggestion or skip.
    5. For each rename candidate: create suggestion directly (no LLM needed —
       it's a cosmetic move, semantically harmless).

    Existing suggestions (pending + archived) are honored: never duplicate.
    """
    now = now or datetime.now(UTC)
    pages = _collect_wiki_pages(vault)
    store = SuggestionStore(vault)
    store.root.mkdir(parents=True, exist_ok=True)

    validator = OntologyLLMValidator(llm=llm)
    existing_keys = _existing_dedup_keys(store)

    exact = find_exact_duplicates(vault, pages)
    partial = find_partial_duplicates(vault, pages, threshold=partial_threshold)
    renames = find_slug_mismatches(vault, pages)

    # Cap: take highest-similarity first. Exact (1.0) always wins over partial.
    duplicate_candidates = sorted(
        exact + partial, key=lambda c: c.similarity, reverse=True
    )
    skipped_capped = max(0, len(duplicate_candidates) - max_llm_calls)
    duplicate_candidates = duplicate_candidates[:max_llm_calls]

    out_created: list[str] = []
    counters = {"distinct": 0, "existing": 0}
    errors: list[tuple[str, str]] = []

    # Body cache so we don't re-read pages already parsed by the finders.
    body_cache: dict[str, str] = {}

    def _body(rel: str) -> str:
        if rel not in body_cache:
            try:
                body_cache[rel] = read_page(vault / rel).body
            except (PageParseError, OSError):
                body_cache[rel] = ""
        return body_cache[rel]

    for cand in duplicate_candidates:
        _process_pair(
            store,
            existing_keys,
            validator=validator,
            page_a=cand.page_a,
            body_a=_body(cand.page_a),
            page_b=cand.page_b,
            body_b=_body(cand.page_b),
            similarity=cand.similarity,
            now=now,
            out_created=out_created,
            counters=counters,
            errors=errors,
        )

    for rc in renames:
        _process_rename(
            vault,
            store,
            existing_keys,
            candidate=rc,
            now=now,
            out_created=out_created,
            counters=counters,
        )

    return ScanResult(
        created=out_created,
        skipped_distinct=counters["distinct"],
        skipped_existing=counters["existing"],
        skipped_capped=skipped_capped,
        errors=errors,
        scanned_pages=len(pages),
    )
