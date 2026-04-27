from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from claude_mnemos.state.jobs import JobStore

router = APIRouter()


def _store(request: Request) -> JobStore:
    daemon = request.app.state.daemon
    if daemon is None or getattr(daemon, "job_store", None) is None:
        raise HTTPException(
            status_code=503, detail={"error": "jobs_subsystem_unavailable"}
        )
    store: JobStore = daemon.job_store
    return store


@router.post("/jobs", status_code=201)
async def create_job(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    store = _store(request)
    kind = body.get("kind")
    payload = body.get("payload", {})
    if kind not in ("ingest",):
        raise HTTPException(
            status_code=400, detail={"error": "unknown_kind", "kind": kind}
        )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400, detail={"error": "payload_must_be_object"}
        )
    if kind == "ingest":
        transcript_path = payload.get("transcript_path")
        if not isinstance(transcript_path, str) or not transcript_path:
            raise HTTPException(
                status_code=400,
                detail={"error": "missing_transcript_path", "kind": kind},
            )
        # File-existence check is best-effort — daemon may run on a different
        # machine than the caller in future; for now we're single-host.
        if not Path(transcript_path).is_file():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "transcript_not_found",
                    "transcript_path": transcript_path,
                },
            )
    job = store.create(kind=kind, payload=payload)
    if hasattr(request.app.state.daemon, "job_worker"):
        worker = request.app.state.daemon.job_worker
        if worker is not None:
            worker.signal_wakeup()
    return job.model_dump(mode="json")


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
