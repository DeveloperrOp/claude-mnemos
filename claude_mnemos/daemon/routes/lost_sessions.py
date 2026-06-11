"""REST routes for lost-sessions discovery + import + ignore (Plan #13b-β2 Task 10).

Cross-vault aggregation: every mounted vault is scanned; results carry
``project_name`` for attribution.  Import and ignore operations require an
explicit ``project_name`` in the request body so the daemon knows which
vault's job-store / ignore-list to update.

Endpoints (URLs unchanged from β1/α; behaviour is now cross-vault):
* GET  /lost-sessions                   list lost sessions from ALL vaults
* POST /lost-sessions/scan              invalidate all vault caches + rescan
* POST /lost-sessions/{id}/import       body: {"project_name": "...", ...}
* POST /lost-sessions/{id}/ignore       body: {"project_name": "..."}
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core import lost_sessions as core_lost_sessions
from claude_mnemos.core.transcript_helpers import _resolve_transcripts_root
from claude_mnemos.core.transcript_scanner import invalidate_transcripts_cache
from claude_mnemos.core.uningested_sessions import global_ingested_shas
from claude_mnemos.daemon.routes._helpers import all_runtimes, get_runtime
from claude_mnemos.mapping.resolver import (
    ProjectResolver,
    ResolverAmbiguityError,
    _git_toplevel,
)
from claude_mnemos.state.jobs import JobStore

router = APIRouter()

UNASSIGNED_PROJECT = "__unassigned__"

# v0.0.10: server-side ceiling on /import-bulk to prevent a single client
# request from queueing thousands of LLM-extraction jobs by accident or
# malice. Default limit is intentionally low (200) — large historical
# imports should be paginated.
BULK_IMPORT_HARD_CAP = 1000
BULK_IMPORT_DEFAULT_LIMIT = 200


def _validate_transcript_path(transcript_path: str) -> Path:
    """Reject paths outside the canonical transcripts root.

    Defends against path-traversal where a client passes an arbitrary
    absolute path (e.g. ``/etc/passwd``) and the daemon would otherwise
    happily ingest it. The canonical root is ``MNEMOS_TRANSCRIPTS_ROOT``
    or ``~/.claude/projects/``.
    """
    root = _resolve_transcripts_root(None).resolve()
    candidate = Path(transcript_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "transcript_outside_root",
                "detail": f"transcript_path must be under {root}",
            },
        ) from exc
    return candidate


def collect_lost_sessions(runtimes: list[Any]) -> list[dict[str, Any]]:
    """Pure helper: cross-vault scan with cwd-based attribution + dedupe.

    Same filtering as scan_lost_sessions (mtime ≥ 24h ago, no agent-* files,
    not in any vault's manifest). Reusable from dashboard.snapshot.

    Loss-session attribution is determined by ``cwd`` (resolved against the
    project-map) — NOT by the vault that surfaced the session in its scan.
    A session is included once (deduped by sha) and only if it is not
    ingested in ANY mounted vault. ``project_name`` is the name of the
    project whose ``cwd_patterns`` match the session's cwd, or
    ``"__unassigned__"`` if cwd matches no registered project (or is null).
    """
    global_ingested = global_ingested_shas(runtimes)
    resolver = ProjectResolver()
    seen_shas: set[str] = set()
    out: list[dict[str, Any]] = []
    for runtime in runtimes:
        cache = runtime.lost_sessions_cache
        items = (
            cache.get_or_scan(runtime.vault_root)
            if cache is not None
            else core_lost_sessions.scan_lost_sessions(runtime.vault_root)
        )
        for item in items:
            if item.sha in seen_shas:
                continue
            if item.sha in global_ingested:
                continue
            seen_shas.add(item.sha)
            assigned = UNASSIGNED_PROJECT
            if item.cwd:
                try:
                    entry = resolver.resolve_by_cwd(Path(item.cwd), git_fallback=True)
                    if entry is not None:
                        assigned = entry.name
                except (ResolverAmbiguityError, OSError):
                    pass
            d = item.model_dump(mode="json")
            d["project_name"] = assigned
            # Grouping key for the "create brain from folder" UI: the git
            # toplevel collapses subdirectories of one repo into a single
            # group; outside a repo the cwd itself is the group.
            # .resolve() canonicalises trailing slashes / case so the
            # lru_cache on _git_toplevel doesn't miss on equivalent paths.
            group: Path | None = None
            if item.cwd:
                try:
                    group = _git_toplevel(Path(item.cwd).resolve())
                except OSError:
                    group = None
            d["group_root"] = str(group) if group is not None else (item.cwd or None)
            out.append(d)
    return out


def _scan_all_vaults(request: Request) -> list[dict[str, Any]]:
    """Cross-vault scan with cwd-based project attribution.

    Thin shim over :func:`collect_lost_sessions` — fixes a long-standing
    leakage where every vault would surface every other vault's sessions
    as "lost" simply because they were missing from its own manifest.
    """
    return collect_lost_sessions(list(all_runtimes(request)))


@router.get("/lost-sessions")
async def list_lost_route(request: Request) -> dict[str, Any]:
    # Cross-vault scan walks JSONL files on disk; offload to a worker
    # thread so the event loop stays responsive even with 500+ files.
    sessions = await asyncio.to_thread(_scan_all_vaults, request)
    return {"sessions": sessions, "total": len(sessions)}


@router.post("/lost-sessions/scan")
async def rescan_route(request: Request) -> dict[str, Any]:
    """Invalidate caches in every mounted vault, then rescan."""
    invalidate_transcripts_cache()
    for runtime in all_runtimes(request):
        cache = runtime.lost_sessions_cache
        if cache is not None:
            cache.invalidate()
    # Cross-vault scan walks JSONL files on disk; offload to a worker
    # thread to unblock the event loop during long rescans.
    sessions = await asyncio.to_thread(_scan_all_vaults, request)
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/lost-sessions/{session_id}/transcript")
async def read_transcript_route(
    session_id: str, request: Request, limit: int = 100,
) -> dict[str, Any]:
    """Return parsed messages from a session's JSONL by session_id.

    Two-tier lookup:
      1. Per-vault ``LostSessionsCache`` (fast — same set as
         ``GET /lost-sessions`` lists).
      2. **Fallback**: raw transcript scan under ``~/.claude/projects/``,
         no filters. Catches sessions that the user-facing Lost Sessions
         view hides (active sessions <24h old, ``agent-*`` sub-agent
         transcripts) but which the user can still click "Read" on from
         the dashboard's Active Sessions widget.

    Returns 404 only if no jsonl with this ``session_id`` exists anywhere
    under the transcripts root. ``limit`` is clamped to ``[1, 500]``.
    """
    capped = max(1, min(limit, 500))
    transcript_path: str | None = None

    # Tier 1: lost-sessions cache (post-filter set).
    for runtime in all_runtimes(request):
        cache = runtime.lost_sessions_cache
        items = (
            cache.get_or_scan(runtime.vault_root)
            if cache is not None
            else core_lost_sessions.scan_lost_sessions(runtime.vault_root)
        )
        match = next((i for i in items if i.session_id == session_id), None)
        if match is not None:
            transcript_path = match.transcript_path
            break

    # Tier 2: raw transcript scan (no filters). Read endpoint serves any
    # session the user can see in the dashboard, including active and
    # agent-* sessions that Lost Sessions filters out.
    if transcript_path is None:
        from claude_mnemos.core.transcript_scanner import _scan_sync
        for entry in _scan_sync(None):
            if entry.session_id == session_id:
                transcript_path = entry.transcript_path
                break

    if transcript_path is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "lost_session_not_found", "session_id": session_id},
        )
    messages, total, truncated_overall = core_lost_sessions.read_transcript_messages(
        Path(transcript_path), limit=capped,
    )
    return {
        "session_id": session_id,
        "transcript_path": transcript_path,
        "messages": [m.model_dump() for m in messages],
        "total_messages": total,
        "returned_count": len(messages),
        "truncated": truncated_overall,
    }


@router.post("/lost-sessions/import-bulk", status_code=202)
async def import_bulk_route(
    request: Request, body: dict[str, Any]
) -> dict[str, Any]:
    """Enqueue ingest jobs for every lost session attributed to ``project_name``.

    Body: ``{"project_name": str, "extract": bool? = False, "limit": int? = 200}``.

    Returns: ``{"queued": int, "skipped": int, "session_ids": [str]}``.

    Skipped: sessions whose enqueue raised. Failures are counted in ``skipped``,
    not raised — caller can retry one-at-a-time via the regular import endpoint.

    404 when ``project_name`` is not registered, 422 when missing,
    503 when the target vault has no job_store mounted.

    v0.0.10:
      * ``extract`` defaults to **False** (raw dump only). Pre-v0.0.10 the
        default was True so a single ``POST /import-bulk`` could silently
        spend hundreds of dollars on LLM tokens.
      * ``limit`` defaults to **200** (was: unbounded). 422 if caller passes
        a value above ``BULK_IMPORT_HARD_CAP`` so client mistakes can't
        queue an entire vault's history in one request.
    """
    project_name = body.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(
            status_code=422,
            detail={"error": "missing_project_name"},
        )
    runtime = get_runtime(request, project_name)
    if runtime.job_store is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "vault_unavailable", "project_name": project_name},
        )

    raw_limit = body.get("limit")
    if isinstance(raw_limit, int) and raw_limit > 0:
        if raw_limit > BULK_IMPORT_HARD_CAP:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "limit_too_large",
                    "detail": f"limit may not exceed {BULK_IMPORT_HARD_CAP}",
                    "hard_cap": BULK_IMPORT_HARD_CAP,
                },
            )
        limit = raw_limit
    else:
        limit = BULK_IMPORT_DEFAULT_LIMIT
    extract = bool(body.get("extract", False))

    cache = runtime.lost_sessions_cache
    items = (
        cache.get_or_scan(runtime.vault_root)
        if cache is not None
        else core_lost_sessions.scan_lost_sessions(runtime.vault_root)
    )

    queued = 0
    skipped = 0
    session_ids: list[str] = []
    for entry in items:
        if limit is not None and queued >= limit:
            break
        try:
            runtime.job_store.create(
                kind="ingest",
                payload={
                    "transcript_path": entry.transcript_path,
                    "extract": extract,
                },
            )
        except Exception:
            skipped += 1
            continue
        queued += 1
        session_ids.append(entry.session_id)

    if queued > 0 and runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()

    return {"queued": queued, "skipped": skipped, "session_ids": session_ids}


@router.post("/lost-sessions/import-selection", status_code=202)
async def import_selection_route(
    request: Request, body: dict[str, Any]
) -> dict[str, Any]:
    """Enqueue ingest jobs for an explicit list of session_ids in one project.

    Body: ``{"project_name": str, "session_ids": [str], "extract": bool? = True}``.

    Returns: ``{"queued": int, "skipped": int, "missing": [str], "session_ids": [str]}``.

    * ``missing`` — session_ids not found in the target vault's scan results.
    * ``skipped`` — sessions whose enqueue raised (counted separately).

    Differences from ``/import-bulk``: caller picks exactly which sessions go
    in. The frontend uses this for the multi-select flow on the Lost Sessions
    page.
    """
    project_name = body.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(
            status_code=422, detail={"error": "missing_project_name"}
        )
    raw_ids = body.get("session_ids")
    if not isinstance(raw_ids, list) or not all(isinstance(x, str) and x for x in raw_ids):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_session_ids",
                "detail": "session_ids must be a non-empty list of strings",
            },
        )
    if not raw_ids:
        raise HTTPException(
            status_code=422,
            detail={"error": "empty_session_ids"},
        )
    runtime = get_runtime(request, project_name)
    if runtime.job_store is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "vault_unavailable", "project_name": project_name},
        )

    # v0.0.10: extract defaults to False (raw dump only). UI must opt-in.
    extract = bool(body.get("extract", False))

    cache = runtime.lost_sessions_cache
    items = (
        cache.get_or_scan(runtime.vault_root)
        if cache is not None
        else core_lost_sessions.scan_lost_sessions(runtime.vault_root)
    )
    by_id = {i.session_id: i for i in items}

    queued = 0
    skipped = 0
    missing: list[str] = []
    session_ids: list[str] = []
    for sid in raw_ids:
        entry = by_id.get(sid)
        if entry is None:
            missing.append(sid)
            continue
        try:
            runtime.job_store.create(
                kind="ingest",
                payload={
                    "transcript_path": entry.transcript_path,
                    "extract": extract,
                },
            )
        except Exception:
            skipped += 1
            continue
        queued += 1
        session_ids.append(entry.session_id)

    if queued > 0 and runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()

    return {
        "queued": queued,
        "skipped": skipped,
        "missing": missing,
        "session_ids": session_ids,
    }


@router.post("/lost-sessions/ignore-selection", status_code=200)
async def ignore_selection_route(
    request: Request, body: dict[str, Any]
) -> dict[str, Any]:
    """Add multiple SHAs to the ignore list of one project vault.

    Body: ``{"project_name": str, "shas": [str]}``.
    Returns: ``{"ignored_count": int, "added": int}``.

    ``added`` counts how many of the requested shas were newly ignored.
    Already-ignored shas are silently no-op.
    """
    project_name = body.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(
            status_code=422, detail={"error": "missing_project_name"}
        )
    raw_shas = body.get("shas")
    if (
        not isinstance(raw_shas, list)
        or not raw_shas
        or not all(isinstance(x, str) and x for x in raw_shas)
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_shas",
                "detail": "shas must be a non-empty list of non-empty strings",
            },
        )
    if len(raw_shas) > 1000:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "too_many_shas",
                "detail": "shas list capped at 1000 entries per request",
            },
        )

    runtime = get_runtime(request, project_name)

    ignore = core_lost_sessions.LostSessionsIgnore.load(runtime.vault_root)
    before = set(ignore.ignored_shas)
    ignore.ignored_shas.update(raw_shas)
    added = len(ignore.ignored_shas) - len(before)
    if added > 0:
        ignore.save(runtime.vault_root)

    cache = runtime.lost_sessions_cache
    if cache is not None:
        cache.invalidate()

    return {"ignored_count": len(ignore.ignored_shas), "added": added}


@router.post("/lost-sessions/{session_id}/import", status_code=201)
async def import_route(
    session_id: str,
    request: Request,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Enqueue an ingest job for a lost session in a specific project vault.

    Body must contain ``project_name``.  ``transcript_path`` may optionally be
    supplied directly; otherwise it is resolved via the target vault's scan.
    """
    project_name = body.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(
            status_code=400, detail={"error": "missing_project_name"}
        )
    runtime = get_runtime(request, project_name)

    transcript_path = body.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        # Resolve via the target vault's cache / scan.
        cache = runtime.lost_sessions_cache
        items = (
            cache.get_or_scan(runtime.vault_root)
            if cache is not None
            else core_lost_sessions.scan_lost_sessions(runtime.vault_root)
        )
        match = next((i for i in items if i.session_id == session_id), None)
        if match is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "lost_session_not_found",
                    "session_id": session_id,
                    "project_name": project_name,
                },
            )
        transcript_path = match.transcript_path
    else:
        if not Path(transcript_path).is_file():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "transcript_not_found",
                    "transcript_path": transcript_path,
                },
            )
        # Reject path-traversal: client-supplied path must be under the
        # canonical transcripts root.
        _validate_transcript_path(transcript_path)

    if runtime.job_store is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "vault_unavailable", "project_name": project_name},
        )
    # v0.0.10: extract defaults to False. Caller opts in by passing extract=True.
    extract = bool(body.get("extract", False))
    store: JobStore = runtime.job_store
    job = store.create(
        kind="ingest",
        payload={"transcript_path": transcript_path, "extract": extract},
    )
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    dumped: dict[str, Any] = job.model_dump(mode="json")
    return dumped


@router.post("/lost-sessions/{session_id}/ignore", status_code=200)
async def ignore_route(
    session_id: str,
    request: Request,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Add a SHA to the ignore list in a specific project vault.

    Body must contain ``project_name``.  ``sha`` may optionally be supplied
    directly; otherwise it is resolved via the target vault's scan.
    """
    project_name = body.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(
            status_code=400, detail={"error": "missing_project_name"}
        )
    runtime = get_runtime(request, project_name)

    sha = body.get("sha")
    if not isinstance(sha, str) or not sha:
        cache = runtime.lost_sessions_cache
        items = (
            cache.get_or_scan(runtime.vault_root)
            if cache is not None
            else core_lost_sessions.scan_lost_sessions(runtime.vault_root)
        )
        match = next((i for i in items if i.session_id == session_id), None)
        if match is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "lost_session_not_found",
                    "session_id": session_id,
                    "project_name": project_name,
                },
            )
        sha = match.sha

    ignore = core_lost_sessions.add_to_ignore(runtime.vault_root, sha)
    cache = runtime.lost_sessions_cache
    if cache is not None:
        cache.invalidate()
    return {"ignored_count": len(ignore.ignored_shas)}


@router.get("/lost-sessions/ignored")
async def list_ignored_route(request: Request) -> dict[str, Any]:
    """List all ignored session SHAs across every mounted vault."""
    daemon = request.app.state.daemon
    all_details: list[dict[str, Any]] = []
    for project_name, runtime in daemon.runtimes.items():
        for detail in core_lost_sessions.list_ignored_session_details(
            runtime.vault_root
        ):
            d = detail.model_dump(mode="json")
            d["project_name"] = project_name
            all_details.append(d)
    return {"ignored": all_details, "total": len(all_details)}


@router.post("/lost-sessions/un-ignore-selection")
async def un_ignore_selection_route(
    request: Request, body: dict[str, Any]
) -> dict[str, Any]:
    """Remove SHAs from a project vault's ignore list.

    Body: ``{"project_name": str, "shas": [str]}``.
    Returns: ``{"removed": int, "ignored_count": int}``.
    """
    project_name = body.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(
            status_code=422, detail={"error": "missing_project_name"}
        )
    raw_shas = body.get("shas")
    if not isinstance(raw_shas, list) or not all(isinstance(s, str) for s in raw_shas):
        raise HTTPException(
            status_code=422, detail={"error": "invalid_shas"}
        )
    runtime = get_runtime(request, project_name)
    updated, removed = core_lost_sessions.remove_from_ignore(runtime.vault_root, raw_shas)
    cache = runtime.lost_sessions_cache
    if cache is not None:
        cache.invalidate()
    return {"removed": removed, "ignored_count": len(updated.ignored_shas)}
