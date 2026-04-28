from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from claude_mnemos.daemon.routes._helpers import all_runtimes
from claude_mnemos.daemon.vault_runtime import VaultRuntime
from claude_mnemos.state.jobs import Job

router = APIRouter()


@router.get("/dead-letter")
async def list_dead_letter(
    request: Request, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    aggregated: list[dict[str, Any]] = []
    for runtime in all_runtimes(request):
        store = runtime.job_store
        if store is None:
            continue
        for j in store.list_by_status("dead_letter", limit=limit, offset=offset):
            d = j.model_dump(mode="json")
            d["project_name"] = runtime.name
            aggregated.append(d)
    aggregated.sort(key=lambda x: x.get("finished_at") or "", reverse=True)
    return {"jobs": aggregated[:limit]}


def _find_dead_letter_owner(request: Request, job_id: str) -> tuple[VaultRuntime, Job]:
    for runtime in all_runtimes(request):
        store = runtime.job_store
        if store is None:
            continue
        job = store.get_by_id(job_id)
        if job is not None and job.status == "dead_letter":
            return runtime, job
    raise HTTPException(status_code=404, detail={"error": "not_found", "id": job_id})


@router.get("/dead-letter/{job_id}")
async def get_dead_letter(job_id: str, request: Request) -> dict[str, Any]:
    runtime, job = _find_dead_letter_owner(request, job_id)
    d = job.model_dump(mode="json")
    d["project_name"] = runtime.name
    return d


@router.post("/dead-letter/{job_id}/retry")
async def retry_dead_letter(job_id: str, request: Request) -> dict[str, Any]:
    runtime, _ = _find_dead_letter_owner(request, job_id)
    store = runtime.job_store
    assert store is not None  # guaranteed by _find_dead_letter_owner
    restored = store.restore_from_dead_letter(job_id)
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    d = restored.model_dump(mode="json")
    d["project_name"] = runtime.name
    return d


@router.delete("/dead-letter/{job_id}", status_code=204)
async def dismiss_dead_letter(job_id: str, request: Request) -> Response:
    runtime, _ = _find_dead_letter_owner(request, job_id)
    store = runtime.job_store
    assert store is not None  # guaranteed by _find_dead_letter_owner
    if not store.dismiss_dead_letter(job_id):
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return Response(status_code=204)
