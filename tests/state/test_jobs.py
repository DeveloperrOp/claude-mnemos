from pathlib import Path

import pytest

from claude_mnemos.state.jobs import (
    JOBS_DB_FILENAME,
    MAX_ATTEMPTS,
    RETRY_DELAYS_S,
    JobsCorruptError,
    JobStore,
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
