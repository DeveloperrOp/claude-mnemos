import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.daemon.jobs.worker import JobWorker
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, Job, JobStore


class _FakeHandler:
    def __init__(self):
        self.runs: list[Job] = []
        self.boom_on_id: str | None = None

    async def run(self, job: Job) -> None:
        self.runs.append(job)
        if job.id == self.boom_on_id:
            raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_worker_runs_queued_job(tmp_path: Path):
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    handler = _FakeHandler()
    worker = JobWorker(
        store=store,
        handlers={"ingest": handler},
        scheduler=None,
        poll_interval_s=0.1,
    )
    job = store.create(kind="ingest", payload={"transcript_path": "/x"})

    await worker.start()
    try:
        for _ in range(40):
            if handler.runs:
                break
            await asyncio.sleep(0.1)
    finally:
        await worker.stop(timeout=5.0)
        store.close()

    assert len(handler.runs) == 1
    assert handler.runs[0].id == job.id
    loaded = JobStore(tmp_path / JOBS_DB_FILENAME).get_by_id(job.id)
    assert loaded is not None
    assert loaded.status == "succeeded"


@pytest.mark.asyncio
async def test_worker_marks_failed_with_retry_on_handler_exception(tmp_path: Path):
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    handler = _FakeHandler()
    job = store.create(kind="ingest", payload={"transcript_path": "/x"})
    handler.boom_on_id = job.id

    worker = JobWorker(
        store=store,
        handlers={"ingest": handler},
        scheduler=None,
        poll_interval_s=0.1,
    )

    await worker.start()
    try:
        for _ in range(40):
            current = store.get_by_id(job.id)
            if current and current.status == "queued" and current.attempt == 1:
                break
            await asyncio.sleep(0.1)
    finally:
        await worker.stop(timeout=5.0)
        store.close()

    final = JobStore(tmp_path / JOBS_DB_FILENAME).get_by_id(job.id)
    assert final is not None
    assert final.attempt == 1
    # Either still queued (waiting backoff) or moved on, but error recorded
    assert final.error is not None
    assert "boom" in final.error


@pytest.mark.asyncio
async def test_worker_unknown_kind_marks_failed(tmp_path: Path):
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    job_row_kind = "not_in_handlers"
    # Bypass JobKind literal at insertion time
    store._conn.execute(
        "INSERT INTO jobs (id, kind, payload_json, status, attempt, next_attempt_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("nokind", job_row_kind, "{}", "queued", 0,
         datetime.now(UTC).timestamp(), datetime.now(UTC).timestamp()),
    )

    worker = JobWorker(
        store=store,
        handlers={"ingest": _FakeHandler()},
        scheduler=None,
        poll_interval_s=0.1,
    )

    await worker.start()
    try:
        for _ in range(30):
            row = store._conn.execute(
                "SELECT status, error FROM jobs WHERE id='nokind'"
            ).fetchone()
            if row and row["status"] != "queued" or (row and row["error"]):
                break
            await asyncio.sleep(0.1)
    finally:
        await worker.stop(timeout=5.0)
        store.close()

    row = JobStore(tmp_path / JOBS_DB_FILENAME)._conn.execute(
        "SELECT error FROM jobs WHERE id='nokind'"
    ).fetchone()
    assert row is not None
    assert "no handler" in (row["error"] or "").lower()


@pytest.mark.asyncio
async def test_worker_stop_is_graceful_when_idle(tmp_path: Path):
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    worker = JobWorker(
        store=store,
        handlers={"ingest": _FakeHandler()},
        scheduler=None,
        poll_interval_s=0.1,
    )
    await worker.start()
    await worker.stop(timeout=2.0)
    store.close()
