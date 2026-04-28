from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from claude_mnemos.state.jobs import JobStore

router = APIRouter()


def _store(request: Request) -> JobStore:
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(
            status_code=503, detail={"error": "jobs_subsystem_unavailable"}
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
    store: JobStore = primary.job_store
    return store


def _job_worker(request: Request) -> Any:
    daemon = request.app.state.daemon
    if daemon is None:
        return None
    primary = getattr(daemon, "primary_runtime", None)
    return primary.job_worker if primary is not None else None


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
    worker = _job_worker(request)
    if worker is not None:
        worker.signal_wakeup()
    return restored.model_dump(mode="json")


@router.delete("/dead-letter/{job_id}", status_code=204)
async def dismiss_dead_letter(job_id: str, request: Request) -> Response:
    store = _store(request)
    if not store.dismiss_dead_letter(job_id):
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return Response(status_code=204)
