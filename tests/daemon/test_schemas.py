from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claude_mnemos.daemon.schemas import (
    HealthResponse,
    SchedulerJobInfo,
    SnapshotInfo,
    UndoApiResult,
    VaultHealth,
    VaultInfo,
    VersionResponse,
)


def test_health_response_minimal():
    r = HealthResponse(status="ok", version="0.0.1", uptime_s=1.5)
    assert r.scheduler_jobs == []
    assert r.vaults == {}


def test_health_response_with_jobs():
    job = SchedulerJobInfo(
        id="daily_snapshot",
        next_run_time=datetime(2026, 4, 27, 4, 0, tzinfo=UTC),
        trigger="cron[hour=4,minute=0]",
    )
    r = HealthResponse(
        status="ok", version="0.0.1", uptime_s=0.1, scheduler_jobs=[job]
    )
    assert len(r.scheduler_jobs) == 1
    assert r.scheduler_jobs[0].id == "daily_snapshot"


def test_health_response_with_vault_dict():
    vh = VaultHealth(
        watchdog_running=True,
        jobs_queued=2,
        jobs_running=1,
        jobs_dead_letter=0,
    )
    r = HealthResponse(
        status="ok",
        version="0.0.1",
        uptime_s=0.0,
        vaults={"alpha": vh},
    )
    assert r.vaults["alpha"].watchdog_running is True
    assert r.vaults["alpha"].jobs_queued == 2


def test_health_response_invalid_status():
    with pytest.raises(ValidationError):
        HealthResponse(status="weird", version="0", uptime_s=0)  # type: ignore[arg-type]


def test_health_response_negative_uptime():
    with pytest.raises(ValidationError):
        HealthResponse(status="ok", version="0", uptime_s=-1.0)


def test_scheduler_job_no_next_run():
    job = SchedulerJobInfo(id="x", next_run_time=None, trigger="cron")
    assert job.next_run_time is None


def test_version_response():
    v = VersionResponse(version="0.0.1", python_version="3.12.8", platform="Windows-11")
    assert v.version == "0.0.1"


def test_vault_info():
    v = VaultInfo(
        vault="/v",
        raw_chats=2,
        wiki_pages=5,
        manifest_processed=2,
        activity_entries=4,
        snapshots=3,
        total_size_bytes=1024,
    )
    assert v.snapshots == 3


def test_vault_info_negative_rejected():
    with pytest.raises(ValidationError):
        VaultInfo(
            vault="/v",
            raw_chats=-1,
            wiki_pages=0,
            manifest_processed=0,
            activity_entries=0,
            snapshots=0,
            total_size_bytes=0,
        )


def test_undo_api_result_defaults():
    r = UndoApiResult(success=True, op_id="abc")
    assert r.restored_pages == []
    assert r.new_entry_id is None


def test_snapshot_info_re_export():
    info = SnapshotInfo(
        name="daily-2026-04-26",
        kind="daily",
        timestamp=datetime(2026, 4, 26, tzinfo=UTC),
        path=".backups/daily-2026-04-26",
    )
    assert info.kind == "daily"
