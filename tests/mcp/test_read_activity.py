from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from claude_mnemos.mcp.read_tools.activity import get_recent_activity
from claude_mnemos.state.activity import ActivityEntry, ActivityLog


def _entry(hour: int, op_type: str = "ingest_extracted") -> ActivityEntry:
    return ActivityEntry(
        id=uuid4().hex,
        timestamp=datetime(2026, 4, 26, hour, 0, tzinfo=UTC),
        operation_type=op_type,  # type: ignore[arg-type]
        status="success",
        snapshot_path=None,
        can_undo=True,
    )


def test_empty_vault(tmp_path: Path):
    assert get_recent_activity(tmp_path) == []


def test_returns_newest_first(tmp_path: Path):
    log = ActivityLog()
    e1 = _entry(10)
    e2 = _entry(11)
    log.append(e1)
    log.append(e2)
    log.save(tmp_path)

    items = get_recent_activity(tmp_path)
    assert len(items) == 2
    assert items[0]["id"] == e2.id
    assert items[1]["id"] == e1.id


def test_limit_applied(tmp_path: Path):
    log = ActivityLog()
    for hour in range(5):
        log.append(_entry(hour))
    log.save(tmp_path)

    items = get_recent_activity(tmp_path, limit=2)
    assert len(items) == 2
