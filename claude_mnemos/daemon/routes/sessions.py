"""REST routes for session lifecycle (Plan #13a §3.5 Task 6).

Exposes a unified view over manifest-succeeded ingests and in-flight jobs,
plus an ingest entrypoint that enqueues a job. Read paths use only the
vault root and are safe even when the daemon is not running its job
subsystem; the ingest endpoint requires ``daemon.job_store`` and returns
503 otherwise (mirrors :mod:`claude_mnemos.daemon.routes.jobs`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core import sessions as core_sessions
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


@router.get("/sessions")
async def list_sessions_route(
    request: Request,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List session views, optionally filtered by status, capped by ``limit``.

    ``total`` reflects the size *after* status filtering but *before* the
    limit cut so the dashboard can display "showing N of M".
    """
    vault = _vault(request)
    items = core_sessions.list_sessions(vault)
    if status:
        items = [s for s in items if s.status.value == status]
    return {
        "sessions": [s.model_dump(mode="json") for s in items[:limit]],
        "total": len(items),
    }


@router.get("/sessions/{session_id}")
async def get_session_route(session_id: str, request: Request) -> dict[str, Any]:
    vault = _vault(request)
    try:
        session = core_sessions.get_session(vault, session_id)
    except core_sessions.SessionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "session_id": session_id},
        ) from exc
    return session.model_dump(mode="json")


@router.post("/sessions/{session_id}/ingest", status_code=201)
async def ingest_session_route(
    session_id: str,
    request: Request,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Enqueue an ingest job for ``session_id``.

    Body must contain ``transcript_path`` pointing to an existing file. The
    ``session_id`` path parameter is informational — the actual session_id
    is derived downstream from the transcript filename — but is preserved
    in the URL for symmetry with GET.
    """
    del session_id  # currently informational only; payload carries the path
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "jobs_subsystem_unavailable"},
        )
    primary = getattr(daemon, "primary_runtime", None)
    if primary is None or primary.job_store is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_vault_registered",
                "hint": "Register: mnemos project add NAME --vault PATH",
            },
        )
    transcript_path = body.get("transcript_path")
    if (
        not isinstance(transcript_path, str)
        or not transcript_path
        or not Path(transcript_path).is_file()
    ):
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_or_invalid_transcript_path"},
        )
    store: JobStore = primary.job_store
    job = store.create(kind="ingest", payload={"transcript_path": transcript_path})
    worker = primary.job_worker
    if worker is not None:
        worker.signal_wakeup()
    dumped: dict[str, Any] = job.model_dump(mode="json")
    return dumped
