"""Read-only inject-context preview per project.

Operator-facing widget endpoint: returns what a *new* SessionStart hook
would inject for this project right now (text, token estimate, page list,
budget ratio). Backed by a 30-second TTLCache per project name to avoid
recomputing the graph + scoring on every refetch.

Reuses :func:`build_adaptive_context_with_stats` for the canonical text +
token counts. Re-runs the seed/graph/score pipeline locally to expose a
ranked page list with hop-scoring metadata (which the public stats struct
intentionally collapses).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from claude_mnemos.core.graph import build_page_graph_with_pages, pages_within_k_hops
from claude_mnemos.core.session_start import (
    _cwd_segment,
    _seeds_from_manifest,
    build_adaptive_context_with_stats,
    score_page,
)
from claude_mnemos.core.ttl_cache import TTLCache
from claude_mnemos.daemon.routes._helpers import get_runtime

router = APIRouter()

DEFAULT_MAX_CHARS = 40_000
DEFAULT_TTL_S = 30.0
PREVIEW_TEXT_CHARS = 5_000

_PROJECT_CACHES: dict[str, TTLCache[dict[str, Any]]] = {}


def _cache_for(project_name: str) -> TTLCache[dict[str, Any]]:
    cache = _PROJECT_CACHES.get(project_name)
    if cache is None:
        cache = TTLCache(ttl_s=DEFAULT_TTL_S)
        _PROJECT_CACHES[project_name] = cache
    return cache


def _representative_cwd(runtime: Any) -> Path:
    """Pick the cwd used to score pages.

    Order of preference:
      1. First registered cwd_pattern on the project entry (real path).
      2. vault_root as a fallback (so cwd_segment ≈ vault folder name).
    """
    patterns = getattr(runtime.project, "cwd_patterns", []) or []
    if patterns:
        return Path(patterns[0])
    return Path(runtime.vault_root)


def _build_pages_list(
    vault: Path, *, cwd: Path, packed_count: int
) -> list[dict[str, Any]]:
    """Re-derive the ranked candidate list with per-page scores.

    Mirrors the head of :func:`build_adaptive_context_with_stats` so the
    sorted order and `included` flag match what was actually packed.
    """
    seeds = _seeds_from_manifest(vault, recent=10)
    if not seeds:
        return []
    wiki_root = vault / "wiki"
    if not wiki_root.is_dir():
        return []
    graph, pages = build_page_graph_with_pages(vault)
    candidates = pages_within_k_hops(graph, seeds, k=2)
    if not candidates:
        return []
    cwd_seg = _cwd_segment(cwd)
    now = datetime.now(UTC)

    scored: list[tuple[float, str, str]] = []
    for slug, hop in candidates.items():
        parsed = pages.get(slug)
        if parsed is None:
            continue
        score = score_page(
            parsed, hop_distance=hop, cwd_segment=cwd_seg, now=now
        )
        # path = wiki/<slug>.md (vault-relative, POSIX-style for the UI)
        path = f"wiki/{slug}.md"
        scored.append((score, slug, path))
    scored.sort(key=lambda t: t[0], reverse=True)

    out: list[dict[str, Any]] = []
    for i, (score, slug, path) in enumerate(scored):
        out.append(
            {
                "path": path,
                "slug": slug,
                "score": round(score, 4),
                "included": i < packed_count,
            }
        )
    return out


def _compute_preview_sync(vault: Path, cwd: Path) -> dict[str, Any]:
    """Run the full inject computation synchronously (CPU-bound)."""
    context, stats = build_adaptive_context_with_stats(
        vault,
        cwd=cwd,
        max_chars=DEFAULT_MAX_CHARS,
    )
    pages_list = _build_pages_list(
        vault, cwd=cwd, packed_count=stats.candidates_packed
    )
    tokens_estimate = stats.tokens_actual
    limit = DEFAULT_MAX_CHARS // 4  # token budget = char budget / 4 (same heuristic)
    ratio = (tokens_estimate / limit) if limit else 0.0
    preview_text = context[:PREVIEW_TEXT_CHARS]
    return {
        "tokens_estimate": tokens_estimate,
        "limit": limit,
        "ratio": round(ratio, 4),
        "pages": pages_list,
        "preview_text": preview_text,
        "computed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


@router.get("/projects/{name}/inject-preview")
async def inject_preview(name: str, request: Request) -> dict[str, Any]:
    """Return what SessionStart would inject for project ``name`` right now.

    Cached per-project for 30s. On unknown project: 404 via ``get_runtime``.
    """
    runtime = get_runtime(request, name)
    cache = _cache_for(name)
    vault = Path(runtime.vault_root)
    cwd = _representative_cwd(runtime)

    async def _compute() -> dict[str, Any]:
        # Offload to a worker thread — graph traversal + page parsing is
        # IO + CPU heavy and would otherwise block the event loop.
        return await asyncio.to_thread(_compute_preview_sync, vault, cwd)

    return await cache.get_or_compute(_compute)
