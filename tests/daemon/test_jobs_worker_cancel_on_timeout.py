from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from claude_mnemos.daemon.jobs.worker import JobWorker
from claude_mnemos.state.jobs import Job, JobStore


class _SlowHandler:
    """Sleeps forever — emulates a wedged ingest."""

    async def run(self, _job: Job) -> None:  # pragma: no cover — never returns
        await asyncio.sleep(60.0)


@pytest.mark.asyncio
async def test_stop_cancels_task_on_timeout(tmp_path: Path) -> None:
    store = JobStore(tmp_path / ".jobs.db")
    try:
        store.create(kind="ingest", payload={"transcript_path": "x"})
        worker = JobWorker(
            store=store,
            handlers={"ingest": _SlowHandler()},
            scheduler=None,
            poll_interval_s=0.05,
        )
        await worker.start()
        # Let the worker pick up the job and enter the slow handler.
        await asyncio.sleep(0.3)
        await worker.stop(timeout=0.2)
        assert worker._task is not None
        assert worker._task.cancelled() or worker._task.done()
    finally:
        store.close()
