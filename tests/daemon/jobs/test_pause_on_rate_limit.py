from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.daemon.jobs.handlers import IngestHandler
from claude_mnemos.ingest.llm.rate_limit import RateLimitError
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, Job, JobStore


def _job(payload: dict) -> Job:
    return Job(
        id="abc",
        kind="ingest",
        payload=payload,
        status="running",
        attempt=0,
        next_attempt_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
    )


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / JOBS_DB_FILENAME)


@pytest.mark.asyncio
async def test_ingest_handler_pauses_queue_on_rate_limit(
    tmp_path: Path, store: JobStore
) -> None:
    reset = datetime.now(UTC) + timedelta(hours=5)
    rate_err = RateLimitError("limited", reset_at=reset)

    def boom(*args, **kwargs):
        raise rate_err

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: object(),
        ingest_fn=boom,
        job_store=store,
    )

    # Run one ingest job — should propagate RateLimitError after pausing the queue.
    with pytest.raises(RateLimitError):
        await handler.run(_job({"transcript_path": str(tmp_path / "s.jsonl")}))

    paused = store.paused_until()
    assert paused is not None
    assert abs((paused - reset).total_seconds()) < 2


@pytest.mark.asyncio
async def test_ingest_handler_without_job_store_propagates_rate_limit(
    tmp_path: Path,
) -> None:
    """If job_store is None, IngestHandler still raises RateLimitError —
    just no pause is recorded (defensive: backward-compat for tests / callers
    that don't supply job_store)."""
    reset = datetime.now(UTC) + timedelta(hours=5)

    def boom(*args, **kwargs):
        raise RateLimitError("limited", reset_at=reset)

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=lambda: object(),
        llm_factory=lambda cfg: object(),
        ingest_fn=boom,
    )
    with pytest.raises(RateLimitError):
        await handler.run(_job({"transcript_path": str(tmp_path / "s.jsonl")}))
