"""REST routes for lost-sessions discovery + import + ignore (Plan #13a Task 7).

A "lost" session is a transcript file under the transcripts root whose SHA-256
isn't recorded in the manifest and isn't on the user-maintained ignore list.
These routes let the dashboard:

* GET  /lost-sessions                   list current lost sessions (cached)
* POST /lost-sessions/scan              force a rescan, return fresh list
* POST /lost-sessions/{id}/import       enqueue an ingest job for a lost session
* POST /lost-sessions/{id}/ignore       add the session's SHA to the ignore list

When the daemon is present it owns a TTL'd :class:`LostSessionsCache`;
without one (e.g. tests with a leaner FakeDaemon) the routes scan
synchronously every call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core import lost_sessions as core_lost_sessions
from claude_mnemos.state.jobs import JobStore

router = APIRouter()


def _vault(request: Request) -> Path:
    vault = request.app.state.vault_root
    if vault is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_vault_registered",
                "hint": "Register: mnemos project add NAME --vault PATH",
            },
        )
    assert isinstance(vault, Path)
    return vault


def _primary(request: Request) -> Any:
    daemon = request.app.state.daemon
    if daemon is None:
        return None
    return getattr(daemon, "primary_runtime", None)


def _scan_via_cache_or_direct(request: Request) -> list[core_lost_sessions.LostSession]:
    """Return current lost sessions, preferring the daemon cache when available."""
    primary = _primary(request)
    cache = getattr(primary, "lost_sessions_cache", None) if primary is not None else None
    if cache is None:
        return core_lost_sessions.scan_lost_sessions(_vault(request))
    items: list[core_lost_sessions.LostSession] = cache.get_or_scan(_vault(request))
    return items


@router.get("/lost-sessions")
async def list_lost_route(request: Request) -> dict[str, Any]:
    items = _scan_via_cache_or_direct(request)
    return {
        "sessions": [s.model_dump(mode="json") for s in items],
        "total": len(items),
    }


@router.post("/lost-sessions/scan")
async def rescan_route(request: Request) -> dict[str, Any]:
    """Invalidate the cache (if any) and run a fresh synchronous scan."""
    primary = _primary(request)
    cache = getattr(primary, "lost_sessions_cache", None) if primary is not None else None
    if cache is not None:
        cache.invalidate()
    # Re-populate the cache via get_or_scan so subsequent GETs benefit.
    if cache is not None:
        items = cache.get_or_scan(_vault(request))
    else:
        items = core_lost_sessions.scan_lost_sessions(_vault(request))
    return {
        "sessions": [s.model_dump(mode="json") for s in items],
        "total": len(items),
    }


@router.post("/lost-sessions/{session_id}/import", status_code=201)
async def import_route(
    session_id: str,
    request: Request,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Enqueue an ingest job for a lost session.

    Body may carry ``transcript_path`` directly; otherwise we resolve it via
    the scan. 404 if no matching lost session exists; 503 if the jobs
    subsystem isn't available.
    """
    transcript_path = body.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        items = _scan_via_cache_or_direct(request)
        match = next((i for i in items if i.session_id == session_id), None)
        if match is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "lost_session_not_found",
                    "session_id": session_id,
                },
            )
        transcript_path = match.transcript_path
    else:
        # Body-supplied path: validate the file exists before queuing,
        # mirroring /jobs and /sessions/{sid}/ingest. Without this the
        # worker would dead-letter after MAX_ATTEMPTS retries.
        if not Path(transcript_path).is_file():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "transcript_not_found",
                    "transcript_path": transcript_path,
                },
            )
    primary = _primary(request)
    if primary is None or primary.job_store is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_vault_registered",
                "hint": "Register: mnemos project add NAME --vault PATH",
            },
        )
    store: JobStore = primary.job_store
    job = store.create(kind="ingest", payload={"transcript_path": transcript_path})
    worker = primary.job_worker
    if worker is not None:
        worker.signal_wakeup()
    dumped: dict[str, Any] = job.model_dump(mode="json")
    return dumped


@router.post("/lost-sessions/{session_id}/ignore", status_code=200)
async def ignore_route(
    session_id: str,
    request: Request,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Add a SHA to the ignore list. Resolves SHA via scan when not provided."""
    sha = body.get("sha")
    if not isinstance(sha, str) or not sha:
        items = _scan_via_cache_or_direct(request)
        match = next((i for i in items if i.session_id == session_id), None)
        if match is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "lost_session_not_found",
                    "session_id": session_id,
                },
            )
        sha = match.sha
    primary = _primary(request)
    tracker = getattr(primary, "tracker", None) if primary is not None else None
    ignore = core_lost_sessions.add_to_ignore(_vault(request), sha, tracker=tracker)
    # Invalidate the cache so the now-ignored session disappears from /list.
    cache = getattr(primary, "lost_sessions_cache", None) if primary is not None else None
    if cache is not None:
        cache.invalidate()
    return {"ignored_count": len(ignore.ignored_shas)}
