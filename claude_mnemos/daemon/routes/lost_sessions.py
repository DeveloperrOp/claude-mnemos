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

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core import lost_sessions as core_lost_sessions
from claude_mnemos.daemon.routes._helpers import all_runtimes, get_runtime
from claude_mnemos.state.jobs import JobStore

router = APIRouter()


def _scan_all_vaults(request: Request) -> list[dict[str, Any]]:
    """Cross-vault scan with project attribution.

    For each mounted runtime, read from its LostSessionsCache (preferred) or
    run a synchronous scan.  Every returned item is serialised to a dict and
    annotated with ``project_name``.
    """
    out: list[dict[str, Any]] = []
    for runtime in all_runtimes(request):
        cache = runtime.lost_sessions_cache
        items = (
            cache.get_or_scan(runtime.vault_root)
            if cache is not None
            else core_lost_sessions.scan_lost_sessions(runtime.vault_root)
        )
        for item in items:
            d = item.model_dump(mode="json")
            d["project_name"] = runtime.name
            out.append(d)
    return out


@router.get("/lost-sessions")
async def list_lost_route(request: Request) -> dict[str, Any]:
    sessions = _scan_all_vaults(request)
    return {"sessions": sessions, "total": len(sessions)}


@router.post("/lost-sessions/scan")
async def rescan_route(request: Request) -> dict[str, Any]:
    """Invalidate caches in every mounted vault, then rescan."""
    for runtime in all_runtimes(request):
        cache = runtime.lost_sessions_cache
        if cache is not None:
            cache.invalidate()
    sessions = _scan_all_vaults(request)
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/lost-sessions/{session_id}/transcript")
async def read_transcript_route(
    session_id: str, request: Request, limit: int = 100,
) -> dict[str, Any]:
    """Return parsed messages from a lost session's JSONL.

    Looks up ``transcript_path`` via the per-vault ``LostSessionsCache``.
    Returns 404 if ``session_id`` is not in any vault's current scan
    results. ``limit`` is clamped to ``[1, 500]``.
    """
    capped = max(1, min(limit, 500))
    entry = None
    for runtime in all_runtimes(request):
        cache = runtime.lost_sessions_cache
        items = (
            cache.get_or_scan(runtime.vault_root)
            if cache is not None
            else core_lost_sessions.scan_lost_sessions(runtime.vault_root)
        )
        match = next((i for i in items if i.session_id == session_id), None)
        if match is not None:
            entry = match
            break
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "lost_session_not_found", "session_id": session_id},
        )
    messages, total, truncated_overall = core_lost_sessions.read_transcript_messages(
        Path(entry.transcript_path), limit=capped,
    )
    return {
        "session_id": session_id,
        "transcript_path": entry.transcript_path,
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

    Body: ``{"project_name": str, "extract": bool? = True, "limit": int? = unbounded}``.

    Returns: ``{"queued": int, "skipped": int, "session_ids": [str]}``.

    Skipped: sessions whose enqueue raised. Failures are counted in ``skipped``,
    not raised — caller can retry one-at-a-time via the regular import endpoint.

    404 when ``project_name`` is not registered, 422 when missing,
    503 when the target vault has no job_store mounted.
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
    limit = raw_limit if isinstance(raw_limit, int) and raw_limit > 0 else None
    extract = bool(body.get("extract", True))

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
    elif not Path(transcript_path).is_file():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "transcript_not_found",
                "transcript_path": transcript_path,
            },
        )

    if runtime.job_store is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "vault_unavailable", "project_name": project_name},
        )
    store: JobStore = runtime.job_store
    job = store.create(kind="ingest", payload={"transcript_path": transcript_path})
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

    ignore = core_lost_sessions.add_to_ignore(
        runtime.vault_root, sha, tracker=runtime.tracker
    )
    cache = runtime.lost_sessions_cache
    if cache is not None:
        cache.invalidate()
    return {"ignored_count": len(ignore.ignored_shas)}
