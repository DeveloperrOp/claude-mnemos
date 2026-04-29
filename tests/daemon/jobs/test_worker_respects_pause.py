from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.daemon.jobs.worker import JobWorker
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, Job, JobStore


class _FakeHandler:
    def __init__(self) -> None:
        self.runs: list[Job] = []

    async def run(self, job: Job) -> None:
        self.runs.append(job)


def test_worker_try_dequeue_one_returns_none_when_paused(tmp_path: Path) -> None:
    """try_dequeue_one is the single dequeue gate — when paused it must
    return None even if jobs exist."""
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    try:
        store.create(kind="ingest", payload={"transcript_path": "/x"})
        store.pause_queue(until=datetime.now(UTC) + timedelta(minutes=10))

        worker = JobWorker(
            store=store,
            handlers={"ingest": _FakeHandler()},
            scheduler=None,
            poll_interval_s=0.1,
        )
        result = worker.try_dequeue_one()
        assert result is None
    finally:
        store.close()


def test_worker_try_dequeue_one_returns_job_when_not_paused(tmp_path: Path) -> None:
    """When not paused, try_dequeue_one delegates to claim_next_ready."""
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    try:
        job = store.create(kind="ingest", payload={"transcript_path": "/x"})

        worker = JobWorker(
            store=store,
            handlers={"ingest": _FakeHandler()},
            scheduler=None,
            poll_interval_s=0.1,
        )
        result = worker.try_dequeue_one()
        assert result is not None
        assert result.id == job.id
        assert result.status == "running"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_worker_loop_skips_jobs_while_paused(tmp_path: Path) -> None:
    """Integration: run the worker loop with a queued job + active pause —
    handler.run() must not be called."""
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    handler = _FakeHandler()
    job = store.create(kind="ingest", payload={"transcript_path": "/x"})
    store.pause_queue(until=datetime.now(UTC) + timedelta(minutes=10))

    worker = JobWorker(
        store=store,
        handlers={"ingest": handler},
        scheduler=None,
        poll_interval_s=0.05,
    )

    await worker.start()
    # Let a few poll cycles run.
    await asyncio.sleep(0.4)
    await worker.stop(timeout=2.0)

    assert handler.runs == []
    # Sanity: job is still queued
    final = store.get_by_id(job.id)
    assert final is not None
    assert final.status == "queued"
    store.close()
