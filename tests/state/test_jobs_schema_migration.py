"""Tests for JobStore v1 -> v2 schema migration.

TDD: these tests must be written before the migration is implemented.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from claude_mnemos.state.jobs import (
    JOBS_DB_FILENAME,
    JobsCorruptError,
    JobStore,
)

# The OLD v1 schema — matches what alpha users have on disk.
# Key differences from v2:
#   - CHECK constraint does NOT include 'cancelled'
#   - schema_meta version = '1'
_V1_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    status          TEXT NOT NULL,
    attempt         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL,
    created_at      REAL NOT NULL,
    started_at      REAL,
    finished_at     REAL,
    error           TEXT,
    error_traceback TEXT,
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'dead_letter')),
    CHECK (attempt >= 0)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_next_at ON jobs (status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_jobs_kind ON jobs (kind);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs (created_at);
"""


def _build_v1_db(db_path: Path) -> tuple[str, str]:
    """Create a v1 DB with one job row; return (db_path, job_id)."""
    import time

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_V1_SCHEMA_SQL)
    conn.execute("INSERT INTO schema_meta (key, value) VALUES ('version', '1')")

    job_id = "aabbccdd" * 4  # 32-char hex
    now_ts = time.time()
    conn.execute(
        """
        INSERT INTO jobs
            (id, kind, payload_json, status, attempt, next_attempt_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (job_id, "ingest", '{"transcript_path": "/test.jsonl"}', "queued", 0, now_ts, now_ts),
    )
    conn.commit()
    conn.close()
    return job_id


def test_migration_v1_to_v2_runs_silently(tmp_path: Path) -> None:
    """Opening a v1 DB must NOT raise — migration should proceed silently."""
    db_path = tmp_path / JOBS_DB_FILENAME
    _build_v1_db(db_path)

    # Should not raise JobsCorruptError
    with JobStore(db_path) as store:
        cur = store._conn.execute("SELECT value FROM schema_meta WHERE key='version'")
        assert cur.fetchone()[0] == "2"


def test_migration_v1_to_v2_preserves_existing_row(tmp_path: Path) -> None:
    """Existing job rows must survive the migration intact."""
    db_path = tmp_path / JOBS_DB_FILENAME
    job_id = _build_v1_db(db_path)

    with JobStore(db_path) as store:
        job = store.get_by_id(job_id)
        assert job is not None
        assert job.id == job_id
        assert job.kind == "ingest"
        assert job.status == "queued"
        assert job.payload == {"transcript_path": "/test.jsonl"}
        assert job.attempt == 0


def test_migration_v1_to_v2_indexes_recreated(tmp_path: Path) -> None:
    """After migration the three indexes must exist on the jobs table."""
    db_path = tmp_path / JOBS_DB_FILENAME
    _build_v1_db(db_path)

    with JobStore(db_path) as store:
        cur = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='jobs'"
        )
        index_names = {row[0] for row in cur.fetchall()}
        assert "idx_jobs_status_next_at" in index_names
        assert "idx_jobs_kind" in index_names
        assert "idx_jobs_created" in index_names


def test_migration_v1_to_v2_allows_cancelled_status(tmp_path: Path) -> None:
    """After migration, 'cancelled' must be a valid CHECK value."""
    db_path = tmp_path / JOBS_DB_FILENAME
    _build_v1_db(db_path)

    with JobStore(db_path) as store:
        # create a job and cancel it
        job = store.create(kind="ingest", payload={"transcript_path": "/x.jsonl"})
        n = store.cancel_all_queued()
        assert n >= 1  # at least the one we just created

        # Must be readable as a Job (pydantic validates status='cancelled')
        cancelled_jobs = [j for j in store.list_by_status(None) if j.id == job.id]
        assert len(cancelled_jobs) == 1
        assert cancelled_jobs[0].status == "cancelled"


def test_unknown_version_above_2_still_raises(tmp_path: Path) -> None:
    """Version '99' (future/unknown) must still raise JobsCorruptError."""
    db_path = tmp_path / JOBS_DB_FILENAME
    # Create a clean v2 DB then manually bump version to 99
    with JobStore(db_path):
        pass
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE schema_meta SET value='99' WHERE key='version'")
    conn.commit()
    conn.close()

    with pytest.raises(JobsCorruptError):
        JobStore(db_path).close()
