"""SQLite-backed persistent job queue for the daemon.

The store owns the connection and writes; reads can also be done by external
callers (CLI list/show) by opening their own JobStore.

Schema is versioned via schema_meta('version') and a mismatch raises
JobsCorruptError so we don't silently work against an incompatible DB.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

JOBS_DB_FILENAME = ".jobs.db"
SCHEMA_VERSION = "1"

MAX_ATTEMPTS = 4
RETRY_DELAYS_S: list[float] = [30.0, 120.0, 1200.0]

JobStatus = Literal["queued", "running", "succeeded", "failed", "dead_letter"]
JobKind = Literal["ingest"]


class JobsCorruptError(ValueError):
    """Raised when .jobs.db is unreadable or has an unknown schema version."""


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: JobKind
    payload: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus
    attempt: int = Field(ge=0)
    next_attempt_at: datetime
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    error_traceback: str | None = None


_SCHEMA_SQL = """
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


def _ts(dt: datetime) -> float:
    return dt.timestamp()


def _from_ts(value: float | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=UTC)


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        kind=row["kind"],
        payload=json.loads(row["payload_json"]),
        status=row["status"],
        attempt=row["attempt"],
        next_attempt_at=datetime.fromtimestamp(row["next_attempt_at"], tz=UTC),
        created_at=datetime.fromtimestamp(row["created_at"], tz=UTC),
        started_at=_from_ts(row["started_at"]),
        finished_at=_from_ts(row["finished_at"]),
        error=row["error"],
        error_traceback=row["error_traceback"],
    )


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(
                str(db_path),
                isolation_level=None,
                check_same_thread=False,
            )
        except sqlite3.Error as exc:
            raise JobsCorruptError(f"cannot open {db_path}: {exc}") from exc
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA_SQL)
        except sqlite3.DatabaseError as exc:
            conn.close()
            raise JobsCorruptError(f"schema init failed for {db_path}: {exc}") from exc

        # Version check / write
        cur = conn.execute("SELECT value FROM schema_meta WHERE key='version'")
        row = cur.fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('version', ?)",
                (SCHEMA_VERSION,),
            )
        elif row[0] != SCHEMA_VERSION:
            conn.close()
            raise JobsCorruptError(
                f"unknown jobs DB schema version {row[0]!r}; expected {SCHEMA_VERSION}"
            )

        self._conn = conn
        self._closed = False

    def __enter__(self) -> JobStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> Literal[False]:
        self.close()
        return False

    def close(self) -> None:
        if self._closed:
            return
        with contextlib.suppress(sqlite3.Error):
            self._conn.close()
        self._closed = True

    # — write —

    def create(self, *, kind: JobKind, payload: dict[str, Any]) -> Job:
        now = datetime.now(UTC)
        job = Job(
            id=uuid4().hex,
            kind=kind,
            payload=payload,
            status="queued",
            attempt=0,
            next_attempt_at=now,
            created_at=now,
        )
        self._conn.execute(
            """
            INSERT INTO jobs (id, kind, payload_json, status, attempt, next_attempt_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id,
                job.kind,
                json.dumps(job.payload, ensure_ascii=False),
                job.status,
                job.attempt,
                _ts(job.next_attempt_at),
                _ts(job.created_at),
            ),
        )
        return job

    # — read —

    def get_by_id(self, job_id: str) -> Job | None:
        cur = self._conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        row = cur.fetchone()
        return _row_to_job(row) if row is not None else None

    def list_by_status(
        self,
        status: JobStatus | None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        if status is None:
            cur = self._conn.execute(
                "SELECT * FROM jobs ORDER BY created_at LIMIT ? OFFSET ?",
                (limit, offset),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY created_at LIMIT ? OFFSET ?",
                (status, limit, offset),
            )
        return [_row_to_job(r) for r in cur.fetchall()]

    def count_by_status(self) -> dict[str, int]:
        cur = self._conn.execute(
            "SELECT status, COUNT(*) FROM jobs GROUP BY status"
        )
        return {row[0]: int(row[1]) for row in cur.fetchall()}
