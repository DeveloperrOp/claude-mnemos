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
from datetime import datetime
from pathlib import Path

from claude_mnemos.core.page_io import ParsedPage


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
