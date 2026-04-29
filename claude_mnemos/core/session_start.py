"""SessionStart adaptive context inject (Plan #13c, spec §5.2 / §9.2).

Builder for the ``additionalContext`` block that the SessionStart hook emits
at session start. Combines frontmatter weights, recency, ontology graph
proximity to recent-session pages, and cwd-grep boosts to rank vault pages.

Token budgeting uses a 4-chars≈1-token approximation. No tokenizer dep.

Pure functions: no I/O beyond reading the vault's manifest + page files.
Hook entrypoint lives in ``hooks/session_start.py``.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

from claude_mnemos.core.graph import build_page_graph, pages_within_k_hops
from claude_mnemos.core.page_io import PageParseError, ParsedPage, read_page
from claude_mnemos.state.manifest import Manifest


def page_slug_from_path(vault: Path, page_path: Path) -> str:
    """Slug = relative path under ``vault/wiki/`` without ``.md`` suffix.

    Example: ``vault/wiki/concepts/foo.md`` → ``concepts/foo``.
    Always uses forward slashes (Windows safe).
    """
    rel = page_path.relative_to(vault / "wiki")
    return str(rel.with_suffix("")).replace("\\", "/")


def page_summary(parsed: ParsedPage, *, max_chars: int = 200) -> str:
    """Return the first non-empty ``max_chars`` characters of the page body.

    Strips leading whitespace. Used for short blurbs in the inject manifest.
    """
    body = parsed.body.lstrip()
    if not body:
        return ""
    return body[:max_chars]


# Score weight constants (module-level for easy tuning).
W_CONFIDENCE = 1.0
W_FLAVOR = 0.5
W_RECENCY = 0.3
W_PROXIMITY = 0.4
W_CWD_MATCH = 0.6
W_STALE_PENALTY = 0.5

FLAVOR_WEIGHTS: dict[str, float] = {
    "decision": 1.0,
    "lesson": 1.0,
    "pattern": 0.7,
    "mistake": 0.5,
    "reference": 0.4,
}

RECENCY_HALF_LIFE_DAYS = 30


def _flavor_weight(flavors: list[str]) -> float:
    """Max weight across all flavors on the page (or 0 if none)."""
    if not flavors:
        return 0.0
    return max(FLAVOR_WEIGHTS.get(f, 0.0) for f in flavors)


def _recency_decay(last_edit: datetime | None, now: datetime) -> float:
    """Exponential decay over RECENCY_HALF_LIFE_DAYS. Returns 0..1.

    Pages with no last_human_edit get a neutral 0 (not penalized, not boosted).
    """
    if last_edit is None:
        return 0.0
    days = (now - last_edit).total_seconds() / 86400.0
    if days < 0:
        return 1.0  # future-dated edit; treat as fresh
    return math.exp(-days / RECENCY_HALF_LIFE_DAYS * math.log(2))


def _proximity(hop_distance: int) -> float:
    """1.0 at hop 0, 0.5 at hop 1, 0.2 at hop 2, 0 beyond."""
    if hop_distance <= 0:
        return 1.0
    if hop_distance == 1:
        return 0.5
    if hop_distance == 2:
        return 0.2
    return 0.0


def _stale_penalty(status: str) -> float:
    if status == "stale":
        return 1.0
    if status == "archived":
        return 0.7
    return 0.0


def score_page(
    parsed: ParsedPage,
    *,
    hop_distance: int,
    cwd_segment: str,
    now: datetime,
) -> float:
    """Return a relevance score for ``parsed`` page.

    Higher = more relevant. Components:

    - confidence (0..1, weight W_CONFIDENCE)
    - flavor weight (W_FLAVOR × max flavor weight)
    - recency decay (W_RECENCY × exp-decay over 30 days)
    - graph proximity (W_PROXIMITY × hop-based score)
    - cwd-segment match in body (W_CWD_MATCH × 1.0 if substring found)
    - stale penalty (subtracted: W_STALE_PENALTY × 1.0 if status=stale, 0.7 if archived)

    All weights are module-level constants for easy tuning.
    """
    fm = parsed.frontmatter
    score = 0.0
    score += W_CONFIDENCE * fm.confidence
    score += W_FLAVOR * _flavor_weight(list(fm.flavor))
    score += W_RECENCY * _recency_decay(fm.last_human_edit, now)
    score += W_PROXIMITY * _proximity(hop_distance)
    if cwd_segment and cwd_segment in parsed.body:
        score += W_CWD_MATCH
    score -= W_STALE_PENALTY * _stale_penalty(fm.status)
    return score


# Defaults
DEFAULT_RECENT_SESSIONS = 10
DEFAULT_GRAPH_HOPS = 2
SUMMARY_CHARS = 200


def _seeds_from_manifest(vault: Path, *, recent: int) -> set[str]:
    """Collect slugs from the last ``recent`` ingest records' ``created_pages``.

    ``created_pages`` entries are stored as paths like ``wiki/concepts/foo.md``;
    we strip the ``wiki/`` prefix and ``.md`` suffix to match graph slugs.
    """
    try:
        manifest = Manifest.load(vault)
    except Exception:  # noqa: BLE001
        return set()
    records = list(manifest.ingested.values())
    records.sort(key=lambda r: r.ingested_at, reverse=True)
    seeds: set[str] = set()
    for rec in records[:recent]:
        for page_ref in rec.created_pages:
            ref = page_ref.replace("\\", "/")
            if ref.startswith("wiki/"):
                ref = ref[len("wiki/"):]
            if ref.endswith(".md"):
                ref = ref[:-3]
            seeds.add(ref)
    return seeds


def _cwd_segment(cwd: Path) -> str:
    """Last path segment of cwd, used for body-grep boosts."""
    name = cwd.name
    return name.lower().strip()


def build_adaptive_context(
    vault: Path,
    *,
    cwd: Path,
    max_chars: int = 40_000,
    recent_sessions: int = DEFAULT_RECENT_SESSIONS,
    graph_hops: int = DEFAULT_GRAPH_HOPS,
) -> str:
    """Build the additionalContext markdown block to inject at SessionStart.

    Returns an empty string if vault has no manifest or yields no candidates —
    callers (i.e. the hook) emit nothing in that case.

    Algorithm:
    1. Read last N sessions' created_pages → seed slugs.
    2. Build vault-wide page graph; BFS K hops from seeds → candidate set.
    3. Score each candidate (confidence + flavor + recency + proximity + cwd match - stale).
    4. Greedy pack top-K under ``max_chars`` budget. Top 3 get full body if room;
       others get title + 200-char summary.
    5. Format as a markdown block.
    """
    wiki_root = vault / "wiki"
    if not wiki_root.is_dir():
        return ""

    seeds = _seeds_from_manifest(vault, recent=recent_sessions)
    if not seeds:
        return ""

    graph = build_page_graph(vault)
    candidates = pages_within_k_hops(graph, seeds, k=graph_hops)
    if not candidates:
        return ""

    cwd_seg = _cwd_segment(cwd)
    now = datetime.now(UTC)

    scored: list[tuple[float, str, ParsedPage]] = []
    for slug, hop in candidates.items():
        page_path = wiki_root / f"{slug}.md"
        if not page_path.is_file():
            continue
        try:
            parsed = read_page(page_path)
        except PageParseError:
            continue
        score = score_page(
            parsed,
            hop_distance=hop,
            cwd_segment=cwd_seg,
            now=now,
        )
        scored.append((score, slug, parsed))

    if not scored:
        return ""

    scored.sort(key=lambda t: t[0], reverse=True)

    # Greedy pack under char budget.
    header = "# Project context (mnemos)\n\nRecent sessions touched these pages:\n"
    parts: list[str] = [header]
    used = len(header)
    full_body_quota = 3
    for i, (_score, slug, parsed) in enumerate(scored):
        if i < full_body_quota:
            block = f"\n## [[{slug}]]\n\n{parsed.body}\n"
        else:
            summary = page_summary(parsed, max_chars=SUMMARY_CHARS)
            block = f"\n- [[{slug}]] — {summary}\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)

    return "".join(parts).strip() + "\n"
