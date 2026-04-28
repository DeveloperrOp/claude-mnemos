"""REST routes for session lifecycle (Plan #13b-β2 §3.1 Task 2).

Per-project endpoints under ``/sessions/{project}/...``. The project name is
resolved to a ``VaultRuntime`` via :func:`get_runtime`; unknown projects yield
HTTP 404 ``unknown_project`` (not 503).

Read paths (list, get) use only ``runtime.vault_root`` and are safe even when
the job subsystem is not running. The ingest endpoint requires
``runtime.job_store`` and returns 503 when it is absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core import sessions as core_sessions
from claude_mnemos.daemon.routes._helpers import get_runtime
from claude_mnemos.state.jobs import JobStore

router = APIRouter()


@router.get("/sessions/{project}")
async def list_sessions_route(
    project: str,
    request: Request,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List session views for *project*, optionally filtered by status.

    ``total`` reflects the size *after* status filtering but *before* the
    limit cut so the dashboard can display "showing N of M".
    """
    runtime = get_runtime(request, project)
    items = core_sessions.list_sessions(runtime.vault_root)
    if status:
        items = [s for s in items if s.status.value == status]
    return {
        "sessions": [s.model_dump(mode="json") for s in items[:limit]],
        "total": len(items),
    }


@router.get("/sessions/{project}/{session_id}")
async def get_session_route(
    project: str,
    session_id: str,
    request: Request,
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    try:
        session = core_sessions.get_session(runtime.vault_root, session_id)
    except core_sessions.SessionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "session_id": session_id},
        ) from exc
    return session.model_dump(mode="json")


@router.post("/sessions/{project}/{session_id}/ingest", status_code=201)
async def ingest_session_route(
    project: str,
    session_id: str,
    request: Request,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Enqueue an ingest job for *session_id* within *project*.

    Body must contain ``transcript_path`` pointing to an existing file. The
    ``session_id`` path parameter is informational — the actual session_id is
    derived downstream from the transcript filename — but is preserved in the
    URL for symmetry with GET.
    """
    del session_id  # informational only; payload carries the path
    runtime = get_runtime(request, project)
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
    if runtime.job_store is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "vault_unavailable", "project": project},
        )
    store: JobStore = runtime.job_store
    job = store.create(kind="ingest", payload={"transcript_path": transcript_path})
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    dumped: dict[str, Any] = job.model_dump(mode="json")
    return dumped
