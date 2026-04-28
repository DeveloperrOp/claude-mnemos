from __future__ import annotations

from pathlib import Path

from claude_mnemos.state.jobs import JobStore


def _open(path: Path) -> JobStore:
    return JobStore(path / ".jobs.db")


def test_cancel_all_queued_zero_when_empty(tmp_path: Path):
    s = _open(tmp_path)
    try:
        assert s.cancel_all_queued() == 0
    finally:
        s.close()


def test_cancel_all_queued_marks_only_queued(tmp_path: Path):
    s = _open(tmp_path)
    try:
        s.create(kind="ingest", payload={"transcript_path": "a"})
        s.create(kind="ingest", payload={"transcript_path": "b"})
        s.create(kind="ingest", payload={"transcript_path": "c"})
        # Mark one as running so it's not affected.
        rows = s._conn.execute("SELECT id FROM jobs ORDER BY created_at").fetchall()
        s._conn.execute(
            "UPDATE jobs SET status='running' WHERE id=?", (rows[0]["id"],)
        )
        s._conn.commit()

        n = s.cancel_all_queued()
        assert n == 2

        statuses = {
            r["id"]: r["status"]
            for r in s._conn.execute("SELECT id, status FROM jobs").fetchall()
        }
        assert statuses[rows[0]["id"]] == "running"
        assert statuses[rows[1]["id"]] == "cancelled"
        assert statuses[rows[2]["id"]] == "cancelled"
    finally:
        s.close()
