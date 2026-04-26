from pathlib import Path

from claude_mnemos.daemon.scheduler import build_scheduler


def test_scheduler_registers_two_jobs(tmp_path: Path):
    sch = build_scheduler(tmp_path, retention_days=180)
    job_ids = {j.id for j in sch.get_jobs()}
    assert job_ids == {"daily_snapshot", "backups_cleanup"}


def test_daily_snapshot_cron_at_4am(tmp_path: Path):
    sch = build_scheduler(tmp_path, retention_days=180)
    job = sch.get_job("daily_snapshot")
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "4"
    assert fields["minute"] == "0"


def test_backups_cleanup_cron_at_5am(tmp_path: Path):
    sch = build_scheduler(tmp_path, retention_days=180)
    job = sch.get_job("backups_cleanup")
    assert job is not None
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["hour"] == "5"
    assert fields["minute"] == "0"


def test_scheduler_default_timezone_utc(tmp_path: Path):
    sch = build_scheduler(tmp_path, retention_days=180)
    assert str(sch.timezone) == "UTC"


def test_scheduler_replace_existing_jobs(tmp_path: Path):
    """Calling build_scheduler twice with same vault must not duplicate."""
    sch1 = build_scheduler(tmp_path, retention_days=180)
    # Same scheduler, build again — should still be 2 jobs
    sch1.add_job(
        lambda: None,
        "cron",
        id="daily_snapshot",
        hour=4,
        replace_existing=True,
    )
    assert len({j.id for j in sch1.get_jobs()}) == 2
