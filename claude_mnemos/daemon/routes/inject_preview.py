"""Read-only inject-context preview per project.

Operator-facing widget endpoint: returns what a *new* SessionStart hook
would inject for this project right now (text, token estimate, page list,
budget ratio). Backed by a 30-second TTLCache per project name to avoid
recomputing the graph + scoring on every refetch.

Consumes :func:`build_adaptive_context_with_stats` for the canonical text,
token counts AND the ranked candidate pages — `InjectStats.pages_ranked`
now carries everything the route used to re-derive locally.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from claude_mnemos.core.session_start import build_adaptive_context_with_stats
from claude_mnemos.core.ttl_cache import TTLCache
from claude_mnemos.daemon.routes._helpers import get_runtime

router = APIRouter()

DEFAULT_MAX_CHARS = 40_000
DEFAULT_TTL_S = 30.0
PREVIEW_TEXT_CHARS = 5_000
_MAX_CACHED_PROJECTS = 50

# LRU-bounded per-project TTL caches. Without the bound, a daemon that has
# repeatedly mounted/unmounted projects (or seen 100+ vaults over its
# lifetime) would accumulate entries forever.
_PROJECT_CACHES: "OrderedDict[str, TTLCache[dict[str, Any]]]" = OrderedDict()


def _cache_for(project_name: str) -> TTLCache[dict[str, Any]]:
    cache = _PROJECT_CACHES.get(project_name)
    if cache is None:
        if len(_PROJECT_CACHES) >= _MAX_CACHED_PROJECTS:
            # Evict the least-recently-used entry.
            _PROJECT_CACHES.popitem(last=False)
        cache = TTLCache(ttl_s=DEFAULT_TTL_S)
        _PROJECT_CACHES[project_name] = cache
    else:
        # Mark as most-recently-used.
        _PROJECT_CACHES.move_to_end(project_name)
    return cache


def invalidate_project_cache(project_name: str) -> None:
    """Drop the inject-preview cache for a project. Call on unmount/remount
    so a project that re-mounts with a different vault_root doesn't see a
    stale preview from the previous mount.
    """
    _PROJECT_CACHES.pop(project_name, None)


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


def _compute_preview_sync(vault: Path, cwd: Path) -> dict[str, Any]:
    """Run the full inject computation synchronously (CPU-bound).

    The ranked pages list comes straight from ``stats.pages_ranked`` —
    no need to re-walk seeds → graph → score, the public function already
    did it.
    """
    context, stats = build_adaptive_context_with_stats(
        vault,
        cwd=cwd,
        max_chars=DEFAULT_MAX_CHARS,
    )
    pages_list: list[dict[str, Any]] = [
        {
            "path": p.path,
            "slug": p.slug,
            "score": p.score,
            "included": p.included,
        }
        for p in stats.pages_ranked
    ]
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
