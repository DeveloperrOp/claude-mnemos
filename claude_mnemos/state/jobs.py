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
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

JOBS_DB_FILENAME = ".jobs.db"
SCHEMA_VERSION = "2"

MAX_ATTEMPTS = 4
RETRY_DELAYS_S: list[float] = [30.0, 120.0, 1200.0]

JobStatus = Literal["queued", "running", "succeeded", "failed", "dead_letter", "cancelled"]
JobKind = Literal["ingest"]


class JobsCorruptError(ValueError):
    """Raised when .jobs.db is unreadable or has an unknown schema version."""


@dataclass(frozen=True)
class RecoveryResult:
    requeued: int = 0
    moved_to_dead_letter: int = 0


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
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'dead_letter', 'cancelled')),
    CHECK (attempt >= 0)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_next_at ON jobs (status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_jobs_kind ON jobs (kind);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs (created_at);

CREATE TABLE IF NOT EXISTS job_queue_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    paused_until TEXT
);
INSERT OR IGNORE INTO job_queue_state (id, paused_until) VALUES (1, NULL);
"""

# SQL fragments used by the v1→v2 migration (separate from _SCHEMA_SQL so they
# can be executed inside a manual transaction rather than via executescript).
_MIGRATION_V1_V2_NEW_TABLE = """
CREATE TABLE jobs_new (
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
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'dead_letter', 'cancelled')),
    CHECK (attempt >= 0)
)
"""

_MIGRATION_V1_V2_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_jobs_status_next_at ON jobs (status, next_attempt_at)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_kind ON jobs (kind)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs (created_at)",
]


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """In-place upgrade of a v1 .jobs.db to v2.

    SQLite does not support ALTER TABLE … DROP CONSTRAINT, so we
    recreate the table with the new CHECK constraint via the standard
    rename-dance: create jobs_new, copy data, drop old table, rename.
    """
    try:
        conn.execute("BEGIN")
        conn.execute(_MIGRATION_V1_V2_NEW_TABLE)
        conn.execute(
            "INSERT INTO jobs_new SELECT "
            "id, kind, payload_json, status, attempt, next_attempt_at, "
            "created_at, started_at, finished_at, error, error_traceback "
            "FROM jobs"
        )
        conn.execute("DROP TABLE jobs")
        conn.execute("ALTER TABLE jobs_new RENAME TO jobs")
        for idx_sql in _MIGRATION_V1_V2_INDEXES:
            conn.execute(idx_sql)
        conn.execute(
            "UPDATE schema_meta SET value='2' WHERE key='version'"
        )
        conn.execute("COMMIT")
    except Exception as exc:
        conn.execute("ROLLBACK")
        raise JobsCorruptError(f"migration v1→v2 failed: {exc}") from exc


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

        # Version check / write / migrate
        cur = conn.execute("SELECT value FROM schema_meta WHERE key='version'")
        row = cur.fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('version', ?)",
                (SCHEMA_VERSION,),
            )
        elif row[0] == "1":
            # α→β1 one-step migration: extend CHECK constraint to include 'cancelled'
            try:
                _migrate_v1_to_v2(conn)
            except JobsCorruptError:
                conn.close()
                raise
        elif row[0] != SCHEMA_VERSION:
            conn.close()
            raise JobsCorruptError(
                f"unknown jobs DB schema version {row[0]!r}; expected {SCHEMA_VERSION}"
            )

        self._conn = conn
        self._closed = False
        # Serializes transactional methods (claim_next_ready, mark_*) on this
        # connection. sqlite3 with isolation_level=None still auto-starts
        # implicit transactions on DML, so cross-thread calls can collide on
        # BEGIN IMMEDIATE; this lock keeps the test contract simple.
        self._tx_lock = threading.Lock()

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

    def list_running_kinds(self) -> list[tuple[str, str]]:
        cur = self._conn.execute(
            "SELECT id, kind FROM jobs WHERE status='running'"
        )
        return [(str(r["id"]), str(r["kind"])) for r in cur.fetchall()]

    def claim_next_ready(self, *, now: datetime) -> Job | None:
        """Pull the oldest queued job with next_attempt_at <= now and mark it
        running. Atomic via BEGIN IMMEDIATE — concurrent claimers never get the
        same row."""
        with self._tx_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    """
                    SELECT * FROM jobs
                    WHERE status='queued' AND next_attempt_at <= ?
                    ORDER BY created_at
                    LIMIT 1
                    """,
                    (_ts(now),),
                ).fetchone()
                if row is None:
                    self._conn.execute("COMMIT")
                    return None
                self._conn.execute(
                    "UPDATE jobs SET status='running', started_at=? WHERE id=?",
                    (_ts(now), row["id"]),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

        # Re-read row with running fields populated
        return self.get_by_id(row["id"])

    def mark_succeeded(self, job_id: str, *, finished_at: datetime) -> None:
        self._conn.execute(
            """
            UPDATE jobs
            SET status='succeeded', finished_at=?, error=NULL, error_traceback=NULL
            WHERE id=?
            """,
            (_ts(finished_at), job_id),
        )

    def mark_dead_letter(
        self,
        job_id: str,
        *,
        error: str,
        traceback: str = "",
        finished_at: datetime,
    ) -> Job:
        """Terminally dead-letter a job in one step, bypassing the retry ladder.

        Used for *deterministic* failures (e.g. a transcript too large for the
        model context) where retrying with the same input cannot succeed.
        Sets status='dead_letter' and attempt=MAX_ATTEMPTS so the job is never
        re-queued. ``error`` is stored verbatim (machine-readable code for the
        dashboard). Does NOT pause the queue — that is rate-limit-only.
        """
        with self._tx_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT id FROM jobs WHERE id=?", (job_id,)
                ).fetchone()
                if row is None:
                    self._conn.execute("COMMIT")
                    raise KeyError(job_id)
                self._conn.execute(
                    """
                    UPDATE jobs
                    SET status='dead_letter', attempt=?, finished_at=?,
                        error=?, error_traceback=?
                    WHERE id=?
                    """,
                    (
                        MAX_ATTEMPTS,
                        _ts(finished_at),
                        error,
                        traceback,
                        job_id,
                    ),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

        result = self.get_by_id(job_id)
        assert result is not None
        return result

    def mark_failed_with_retry(
        self,
        job_id: str,
        *,
        error: str,
        traceback: str,
        finished_at: datetime,
    ) -> Job:
        """Increment attempt; if attempt >= MAX_ATTEMPTS, mark dead_letter
        else mark queued with next_attempt_at += backoff(attempt-1)."""
        with self._tx_lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT attempt FROM jobs WHERE id=?", (job_id,)
                ).fetchone()
                if row is None:
                    self._conn.execute("COMMIT")
                    raise KeyError(job_id)
                new_attempt = int(row["attempt"]) + 1
                if new_attempt >= MAX_ATTEMPTS:
                    self._conn.execute(
                        """
                        UPDATE jobs
                        SET status='dead_letter', attempt=?, finished_at=?,
                            error=?, error_traceback=?
                        WHERE id=?
                        """,
                        (new_attempt, _ts(finished_at), error, traceback, job_id),
                    )
                else:
                    # retry: pick delay based on attempt index (0-based into RETRY_DELAYS_S)
                    delay_idx = min(new_attempt - 1, len(RETRY_DELAYS_S) - 1)
                    next_at = _ts(finished_at) + RETRY_DELAYS_S[delay_idx]
                    self._conn.execute(
                        """
                        UPDATE jobs
                        SET status='queued', attempt=?, next_attempt_at=?,
                            finished_at=?, error=?, error_traceback=?,
                            started_at=NULL
                        WHERE id=?
                        """,
                        (
                            new_attempt,
                            next_at,
                            _ts(finished_at),
                            error,
                            traceback,
                            job_id,
                        ),
                    )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

        result = self.get_by_id(job_id)
        assert result is not None
        return result

    # — recovery + admin —

    def recover_zombie_running(self) -> RecoveryResult:
        """Called once on daemon startup. For each status=running job:
        - if attempt + 1 < MAX_ATTEMPTS → status=queued, attempt+=1, next_attempt_at=now
        - else → status=dead_letter, error='daemon crashed during execution'.
        """
        now_dt = datetime.now(UTC)
        requeued = 0
        moved = 0
        with self._tx_lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                rows = self._conn.execute(
                    "SELECT id, attempt FROM jobs WHERE status='running'"
                ).fetchall()
                for row in rows:
                    new_attempt = int(row["attempt"]) + 1
                    if new_attempt >= MAX_ATTEMPTS:
                        self._conn.execute(
                            """
                            UPDATE jobs
                            SET status='dead_letter', attempt=?, finished_at=?,
                                error=?, error_traceback=NULL
                            WHERE id=?
                            """,
                            (
                                new_attempt,
                                _ts(now_dt),
                                "daemon crashed during execution",
                                row["id"],
                            ),
                        )
                        moved += 1
                    else:
                        self._conn.execute(
                            """
                            UPDATE jobs
                            SET status='queued', attempt=?, next_attempt_at=?,
                                started_at=NULL
                            WHERE id=?
                            """,
                            (new_attempt, _ts(now_dt), row["id"]),
                        )
                        requeued += 1
                self._conn.execute("COMMIT")
            except Exception:
                with contextlib.suppress(Exception):
                    self._conn.execute("ROLLBACK")
                raise
        return RecoveryResult(requeued=requeued, moved_to_dead_letter=moved)

    def cancel_all_queued(self) -> int:
        """Mark every 'queued' job as 'cancelled'. Returns count cancelled.

        Used by VaultRuntime.unmount(force=True) to drain pending work.
        """
        with self._tx_lock:
            cur = self._conn.execute(
                "UPDATE jobs SET status='cancelled', finished_at=? "
                "WHERE status='queued'",
                (_ts(datetime.now(UTC)),),
            )
            return cur.rowcount

    def cancel_queued(self, job_id: str) -> bool:
        with self._tx_lock:
            cur = self._conn.execute(
                "DELETE FROM jobs WHERE id=? AND status='queued'", (job_id,)
            )
            return cur.rowcount > 0

    def restore_from_dead_letter(self, job_id: str) -> Job:
        with self._tx_lock:
            row = self._conn.execute(
                "SELECT status FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] != "dead_letter":
                raise ValueError(
                    f"job {job_id} is in status {row['status']!r}, not dead_letter"
                )
            now = datetime.now(UTC)
            self._conn.execute(
                """
                UPDATE jobs
                SET status='queued', attempt=0, next_attempt_at=?,
                    started_at=NULL, finished_at=NULL,
                    error=NULL, error_traceback=NULL
                WHERE id=?
                """,
                (_ts(now), job_id),
            )
        result = self.get_by_id(job_id)
        assert result is not None
        return result

    def dismiss_dead_letter(self, job_id: str) -> bool:
        with self._tx_lock:
            cur = self._conn.execute(
                "DELETE FROM jobs WHERE id=? AND status='dead_letter'", (job_id,)
            )
            return cur.rowcount > 0

    # — queue pause (rate-limit) —

    def pause_queue(self, *, until: datetime) -> None:
        """Pause job dequeue until *until* (UTC). Existing pause is overwritten."""
        iso = until.astimezone(UTC).isoformat()
        with self._tx_lock:
            self._conn.execute(
                "UPDATE job_queue_state SET paused_until = ? WHERE id = 1",
                (iso,),
            )

    def resume_queue(self) -> None:
        with self._tx_lock:
            self._conn.execute(
                "UPDATE job_queue_state SET paused_until = NULL WHERE id = 1"
            )

    def paused_until(self) -> datetime | None:
        row = self._conn.execute(
            "SELECT paused_until FROM job_queue_state WHERE id = 1"
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(row[0])

    def is_paused(self, *, now: datetime | None = None) -> bool:
        until = self.paused_until()
        if until is None:
            return False
        ref = now or datetime.now(UTC)
        return until > ref
