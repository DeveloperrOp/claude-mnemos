from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request, Response

from claude_mnemos.state.jobs import JobStore

router = APIRouter()


def _store(request: Request) -> JobStore:
    """Used by GET / DELETE handlers — returns primary runtime's JobStore.

    Returns 503 when no primary runtime is registered.
    """
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(503, detail={"error": "jobs_subsystem_unavailable"})
    primary = getattr(daemon, "primary_runtime", None)
    if primary is None or getattr(primary, "job_store", None) is None:
        raise HTTPException(503, detail={"error": "no_vault_registered"})
    store: JobStore = primary.job_store
    return store


@router.post("/jobs", status_code=201)
async def create_job(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(503, detail={"error": "daemon_unavailable"})

    kind = body.get("kind")
    payload = body.get("payload", {})
    if kind != "ingest":
        raise HTTPException(400, detail={"error": "unknown_kind", "kind": kind})
    if not isinstance(payload, dict):
        raise HTTPException(400, detail={"error": "payload_must_be_object"})

    project_name = payload.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(400, detail={"error": "missing_project_name"})

    runtimes = getattr(daemon, "runtimes", None)
    if runtimes is None:
        raise HTTPException(503, detail={"error": "jobs_subsystem_unavailable"})

    runtime = runtimes.get(project_name)
    if runtime is None:
        raise HTTPException(
            400,
            detail={"error": "unknown_project", "project_name": project_name},
        )

    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        raise HTTPException(400, detail={"error": "missing_transcript_path"})
    if not Path(transcript_path).is_file():
        raise HTTPException(
            400,
            detail={
                "error": "transcript_not_found",
                "transcript_path": transcript_path,
            },
        )

    try:
        job = runtime.job_store.create(kind=kind, payload=payload)
    except sqlite3.ProgrammingError as exc:
        raise HTTPException(
            503,
            detail={
                "error": "vault_unavailable",
                "project_name": project_name,
                "detail": str(exc),
            },
        ) from exc
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    return cast(dict[str, Any], job.model_dump(mode="json"))


@router.get("/jobs")
async def list_jobs(
    request: Request,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    store = _store(request)
    jobs = store.list_by_status(status, limit=limit, offset=offset)  # type: ignore[arg-type]
    counts = store.count_by_status()
    return {
        "jobs": [j.model_dump(mode="json") for j in jobs],
        "counts": counts,
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    store = _store(request)
    job = store.get_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return job.model_dump(mode="json")


@router.delete("/jobs/{job_id}", status_code=204)
async def cancel_job(job_id: str, request: Request) -> Response:
    store = _store(request)
    job = store.get_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    if job.status != "queued":
        raise HTTPException(
            status_code=409,
            detail={"error": "not_queued", "current_status": job.status},
        )
    if not store.cancel_queued(job_id):
        raise HTTPException(status_code=409, detail={"error": "race_lost"})
    return Response(status_code=204)
