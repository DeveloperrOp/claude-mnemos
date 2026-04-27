from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.state.jobs import (
    JOBS_DB_FILENAME,
    MAX_ATTEMPTS,
    RETRY_DELAYS_S,
    Job,
    JobsCorruptError,
    JobStore,
    _ts,
)


def test_constants():
    assert MAX_ATTEMPTS == 4
    assert RETRY_DELAYS_S == [30.0, 120.0, 1200.0]
    assert JOBS_DB_FILENAME == ".jobs.db"


def test_open_creates_db_with_schema(tmp_path: Path):
    db_path = tmp_path / JOBS_DB_FILENAME
    with JobStore(db_path) as store:
        assert db_path.is_file()
        # schema_meta has version 1
        cur = store._conn.execute("SELECT value FROM schema_meta WHERE key='version'")
        assert cur.fetchone()[0] == "1"


def test_create_returns_job_with_uuid(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        job = store.create(kind="ingest", payload={"transcript_path": "/x.jsonl"})
        assert job.id
        assert len(job.id) == 32
        assert job.kind == "ingest"
        assert job.status == "queued"
        assert job.attempt == 0
        assert job.payload == {"transcript_path": "/x.jsonl"}


def test_get_by_id_round_trip(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        created = store.create(kind="ingest", payload={"transcript_path": "/x.jsonl"})
        loaded = store.get_by_id(created.id)
        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.payload == {"transcript_path": "/x.jsonl"}


def test_get_by_id_missing(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        assert store.get_by_id("nonexistent") is None


def test_list_by_status_filter(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        a = store.create(kind="ingest", payload={"transcript_path": "/a"})
        b = store.create(kind="ingest", payload={"transcript_path": "/b"})
        # both queued by default
        all_q = store.list_by_status("queued")
        assert {j.id for j in all_q} == {a.id, b.id}
        # no jobs in 'succeeded'
        assert store.list_by_status("succeeded") == []


def test_list_pagination(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        for i in range(5):
            store.create(kind="ingest", payload={"transcript_path": f"/p{i}"})
        page1 = store.list_by_status("queued", limit=2, offset=0)
        page2 = store.list_by_status("queued", limit=2, offset=2)
        page3 = store.list_by_status("queued", limit=2, offset=4)
        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1
        assert {j.id for j in page1 + page2 + page3} == {
            store.list_by_status(None)[i].id for i in range(5)
        }


def test_count_by_status_buckets(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        for _ in range(3):
            store.create(kind="ingest", payload={"transcript_path": "/x"})
        counts = store.count_by_status()
        assert counts.get("queued") == 3
        assert counts.get("running", 0) == 0


def test_corrupt_db_raises(tmp_path: Path):
    db_path = tmp_path / JOBS_DB_FILENAME
    db_path.write_text("not sqlite", encoding="utf-8")
    with pytest.raises(JobsCorruptError), JobStore(db_path):
        pass


def test_unknown_schema_version_raises(tmp_path: Path):
    db_path = tmp_path / JOBS_DB_FILENAME
    # Initialize then poison version
    with JobStore(db_path):
        pass
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE schema_meta SET value='99' WHERE key='version'")
    conn.commit()
    conn.close()
    with pytest.raises(JobsCorruptError), JobStore(db_path):
        pass


def test_payload_round_trips_unicode(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        payload = {"note": "Український текст 🇺🇦"}
        created = store.create(kind="ingest", payload=payload)
        loaded = store.get_by_id(created.id)
        assert loaded is not None
        assert loaded.payload == payload


def test_close_idempotent(tmp_path: Path):
    store = JobStore(tmp_path / JOBS_DB_FILENAME)
    store.close()
    store.close()  # second close must not raise


def test_claim_next_ready_returns_oldest_ready(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        a = store.create(kind="ingest", payload={"transcript_path": "/a"})
        b = store.create(kind="ingest", payload={"transcript_path": "/b"})
        # 'a' is older
        claimed = store.claim_next_ready(now=datetime.now(UTC))
        assert claimed is not None
        assert claimed.id == a.id
        assert claimed.status == "running"
        assert claimed.started_at is not None
        # second claim returns 'b'
        claimed2 = store.claim_next_ready(now=datetime.now(UTC))
        assert claimed2 is not None
        assert claimed2.id == b.id


def test_claim_next_ready_skips_future(tmp_path: Path):
    """Jobs with next_attempt_at > now must NOT be claimed."""
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        store.create(kind="ingest", payload={"transcript_path": "/future"})
        # Bump next_attempt_at to far future
        store._conn.execute(
            "UPDATE jobs SET next_attempt_at = ?",
            (_ts(datetime(2099, 1, 1, tzinfo=UTC)),),
        )
        claimed = store.claim_next_ready(now=datetime.now(UTC))
        assert claimed is None


def test_claim_next_ready_returns_none_when_empty(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        assert store.claim_next_ready(now=datetime.now(UTC)) is None


def test_mark_succeeded_transitions_state(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        job = store.create(kind="ingest", payload={"transcript_path": "/x"})
        store.claim_next_ready(now=datetime.now(UTC))
        store.mark_succeeded(job.id, finished_at=datetime.now(UTC))
        loaded = store.get_by_id(job.id)
        assert loaded is not None
        assert loaded.status == "succeeded"
        assert loaded.finished_at is not None
        assert loaded.error is None


def test_mark_failed_with_retry_first_failure_requeues(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        job = store.create(kind="ingest", payload={"transcript_path": "/x"})
        store.claim_next_ready(now=datetime.now(UTC))
        finished = datetime.now(UTC)
        updated = store.mark_failed_with_retry(
            job.id, error="boom", traceback="Traceback...", finished_at=finished
        )
        assert updated.status == "queued"
        assert updated.attempt == 1
        # Retry delay = RETRY_DELAYS_S[0] = 30s after finished_at
        delta = (updated.next_attempt_at - finished).total_seconds()
        assert 29.5 < delta < 30.5


def test_mark_failed_with_retry_max_attempts_to_dead_letter(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        job = store.create(kind="ingest", payload={"transcript_path": "/x"})
        # Simulate 3 prior failed retries — set attempt=3 directly
        store._conn.execute("UPDATE jobs SET attempt=3 WHERE id=?", (job.id,))
        store.claim_next_ready(now=datetime.now(UTC))
        updated = store.mark_failed_with_retry(
            job.id, error="boom", traceback="tb", finished_at=datetime.now(UTC)
        )
        # attempt=3 + 1 = 4 = MAX_ATTEMPTS -> dead_letter
        assert updated.status == "dead_letter"
        assert updated.attempt == 4
        assert updated.error == "boom"
        assert updated.error_traceback == "tb"


def test_mark_failed_with_retry_records_error(tmp_path: Path):
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        job = store.create(kind="ingest", payload={"transcript_path": "/x"})
        store.claim_next_ready(now=datetime.now(UTC))
        store.mark_failed_with_retry(
            job.id, error="msg", traceback="tb", finished_at=datetime.now(UTC)
        )
        loaded = store.get_by_id(job.id)
        assert loaded is not None
        assert loaded.error == "msg"
        assert loaded.error_traceback == "tb"


def test_concurrent_claim_returns_distinct(tmp_path: Path):
    """Two parallel claim_next_ready against same DB never return same job."""
    import threading
    with JobStore(tmp_path / JOBS_DB_FILENAME) as store:
        for i in range(10):
            store.create(kind="ingest", payload={"transcript_path": f"/p{i}"})
        results: list[Job] = []
        lock = threading.Lock()

        def worker():
            while True:
                claimed = store.claim_next_ready(now=datetime.now(UTC))
                if claimed is None:
                    return
                with lock:
                    results.append(claimed)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        ids = [j.id for j in results]
        assert len(ids) == 10
        assert len(set(ids)) == 10  # all distinct
