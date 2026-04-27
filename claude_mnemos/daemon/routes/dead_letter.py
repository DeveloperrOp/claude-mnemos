from __future__ import annotations

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


@router.get("/dead-letter")
async def list_dead_letter(
    request: Request, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    store = _store(request)
    jobs = store.list_by_status("dead_letter", limit=limit, offset=offset)
    return {"jobs": [j.model_dump(mode="json") for j in jobs]}


@router.post("/dead-letter/{job_id}/retry")
async def retry_dead_letter(job_id: str, request: Request) -> dict[str, Any]:
    store = _store(request)
    job = store.get_by_id(job_id)
    if job is None or job.status != "dead_letter":
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    restored = store.restore_from_dead_letter(job_id)
    daemon = request.app.state.daemon
    worker = getattr(daemon, "job_worker", None)
    if worker is not None:
        worker.signal_wakeup()
    return restored.model_dump(mode="json")


@router.delete("/dead-letter/{job_id}", status_code=204)
async def dismiss_dead_letter(job_id: str, request: Request) -> Response:
    store = _store(request)
    if not store.dismiss_dead_letter(job_id):
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return Response(status_code=204)
