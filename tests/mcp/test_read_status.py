from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from claude_mnemos.mcp.read_tools.status import get_status
from claude_mnemos.state.activity import ActivityCorruptError, ActivityEntry, ActivityLog
from claude_mnemos.state.manifest import (
    IngestRecord,
    Manifest,
    ManifestCorruptError,
)


def test_get_status_empty(tmp_path: Path):
    s = get_status(tmp_path)
    assert s["raw_chats"] == 0
    assert s["wiki_pages"] == 0
    assert s["manifest_processed"] == 0
    assert s["activity_entries"] == 0
    assert s["snapshots"] == 0
    assert s["total_size_bytes"] == 0
    assert s["vault"] == str(tmp_path)


def test_get_status_counts(tmp_path: Path):
    (tmp_path / "raw/chats").mkdir(parents=True)
    (tmp_path / "raw/chats/a.md").write_text("x", encoding="utf-8")
    (tmp_path / "wiki/entities").mkdir(parents=True)
    (tmp_path / "wiki/entities/foo.md").write_text("y", encoding="utf-8")

    manifest = Manifest()
    manifest.add(
        "sha-1",
        IngestRecord(
            session_id="s1",
            ingested_at=datetime(2026, 4, 26, tzinfo=UTC),
            raw_path="raw/chats/a.md",
            source_path=None,
            model=None,
            input_tokens=None,
            output_tokens=None,
        ),
    )
    manifest.save(tmp_path)

    log = ActivityLog()
    log.append(
        ActivityEntry(
            id=uuid4().hex,
            timestamp=datetime(2026, 4, 26, tzinfo=UTC),
            operation_type="ingest_extracted",
            status="success",
            snapshot_path=None,
            can_undo=True,
        )
    )
    log.save(tmp_path)

    s = get_status(tmp_path)
    assert s["raw_chats"] == 1
    assert s["wiki_pages"] == 1
    assert s["manifest_processed"] == 1
    assert s["activity_entries"] == 1
    assert s["total_size_bytes"] > 0


def test_get_status_corrupt_activity_raises(tmp_path: Path):
    (tmp_path / ".activity.json").write_text("not json", encoding="utf-8")
    with pytest.raises(ActivityCorruptError):
        get_status(tmp_path)


def test_get_status_corrupt_manifest_raises(tmp_path: Path):
    (tmp_path / ".manifest.json").write_text("not json", encoding="utf-8")
    with pytest.raises(ManifestCorruptError):
        get_status(tmp_path)
