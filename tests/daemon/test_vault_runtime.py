from __future__ import annotations

import contextlib
from pathlib import Path

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claude_mnemos.daemon.alerts import Alerts
from claude_mnemos.daemon.vault_runtime import (
    VaultBusyError,
    VaultMountError,
    VaultRuntime,
)
from claude_mnemos.state.projects import ProjectMapEntry
from claude_mnemos.state.settings import ProjectSettings


def _entry(tmp_path: Path, name: str = "demo") -> ProjectMapEntry:
    vault = tmp_path / name
    vault.mkdir()
    return ProjectMapEntry(name=name, vault_root=vault, cwd_patterns=[])


def test_construction_does_not_mount(tmp_path: Path) -> None:
    rt = VaultRuntime(project=_entry(tmp_path), settings=ProjectSettings())
    assert rt.is_mounted is False
    assert rt.observer is None
    assert rt.job_worker is None
    assert rt.name == "demo"
    assert rt.vault_root == tmp_path / "demo"
    rt.job_store.close()


def test_busy_error_carries_counts() -> None:
    err = VaultBusyError(name="demo", queued=2, running=1)
    assert err.queued == 2
    assert err.running == 1
    assert err.name == "demo"
    assert "2 queued" in str(err)
    assert "1 running" in str(err)


def test_mount_error_inherits_runtime_error() -> None:
    err = VaultMountError("boom")
    assert isinstance(err, Exception)


@pytest.fixture
def scheduler():
    sch = AsyncIOScheduler(timezone="UTC")
    yield sch
    with contextlib.suppress(Exception):
        sch.shutdown(wait=False)


@pytest.fixture
def alerts():
    return Alerts()


@pytest.mark.asyncio
async def test_mount_starts_observer_and_registers_cron_jobs(
    tmp_path: Path, scheduler, alerts
):
    rt = VaultRuntime(
        project=_entry(tmp_path, "alpha"),
        settings=ProjectSettings(),  # snapshots.daily_enabled defaults True
    )
    try:
        await rt.mount(scheduler=scheduler, alerts=alerts)
        assert rt.is_mounted is True
        assert rt.observer is not None
        assert rt.job_worker is not None

        ids = {j.id for j in scheduler.get_jobs()}
        assert "daily_snapshot:alpha" in ids
        assert "backups_cleanup:alpha" in ids
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_mount_skips_daily_snapshot_when_disabled(
    tmp_path: Path, scheduler, alerts
):
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(
        project=_entry(tmp_path, "noscan"),
        settings=ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=False)),
    )
    try:
        await rt.mount(scheduler=scheduler, alerts=alerts)
        ids = {j.id for j in scheduler.get_jobs()}
        assert "daily_snapshot:noscan" not in ids
        assert "backups_cleanup:noscan" in ids
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_mount_twice_raises(tmp_path: Path, scheduler, alerts):
    rt = VaultRuntime(project=_entry(tmp_path, "x"), settings=ProjectSettings())
    try:
        await rt.mount(scheduler=scheduler, alerts=alerts)
        with pytest.raises(VaultMountError, match="already mounted"):
            await rt.mount(scheduler=scheduler, alerts=alerts)
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_mount_rollback_on_observer_failure(
    tmp_path: Path, scheduler, alerts, monkeypatch
):
    """If observer.start() raises, no scheduler jobs nor JobWorker leak."""

    class _Boom:
        def start(self):
            raise RuntimeError("disk full")

        def stop(self):  # not called, but defensive
            pass

    def _bad_observer(_root, _handler):
        return _Boom()

    monkeypatch.setattr(
        "claude_mnemos.daemon.vault_runtime.VaultObserver", _bad_observer
    )

    rt = VaultRuntime(project=_entry(tmp_path, "rb"), settings=ProjectSettings())
    with pytest.raises(VaultMountError, match="disk full"):
        await rt.mount(scheduler=scheduler, alerts=alerts)
    assert rt.is_mounted is False
    assert rt.observer is None
    assert rt.job_worker is None
    ids = {j.id for j in scheduler.get_jobs()}
    assert "daily_snapshot:rb" not in ids
    assert "backups_cleanup:rb" not in ids
    # Alert should be recorded.
    rt.job_store.close()
    snap = alerts.list()
    assert any("rb" in str(a.message) and "mount failed" in str(a.message) for a in snap)


@pytest.mark.asyncio
async def test_unmount_clean_path(
    tmp_path: Path, scheduler: AsyncIOScheduler, alerts: Alerts
) -> None:
    rt = VaultRuntime(project=_entry(tmp_path, "u1"), settings=ProjectSettings())
    await rt.mount(scheduler=scheduler, alerts=alerts)
    await rt.unmount(timeout=2.0, force=False)
    assert rt.is_mounted is False
    assert rt.observer is None
    assert rt.job_worker is None
    ids = {j.id for j in scheduler.get_jobs()}
    assert "daily_snapshot:u1" not in ids
    assert "backups_cleanup:u1" not in ids


@pytest.mark.asyncio
async def test_unmount_busy_raises_when_queued(
    tmp_path: Path, scheduler: AsyncIOScheduler, alerts: Alerts
) -> None:
    rt = VaultRuntime(project=_entry(tmp_path, "u2"), settings=ProjectSettings())
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        rt.job_store.create(kind="ingest", payload={"transcript_path": "x"})
        with pytest.raises(VaultBusyError) as exc_info:
            await rt.unmount(timeout=2.0, force=False)
        assert exc_info.value.queued >= 1
        assert rt.is_mounted is True  # still mounted
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_unmount_force_drains_queued(
    tmp_path: Path, scheduler: AsyncIOScheduler, alerts: Alerts
) -> None:
    rt = VaultRuntime(project=_entry(tmp_path, "u3"), settings=ProjectSettings())
    await rt.mount(scheduler=scheduler, alerts=alerts)
    rt.job_store.create(kind="ingest", payload={"transcript_path": "x"})
    rt.job_store.create(kind="ingest", payload={"transcript_path": "y"})
    await rt.unmount(timeout=2.0, force=True)
    assert rt.is_mounted is False
    # Underlying file is closed; can't query rt.job_store. Re-open to verify.
    from claude_mnemos.state.jobs import JobStore
    fresh = JobStore(rt.vault_root / ".jobs.db")
    try:
        statuses = [r["status"] for r in fresh._conn.execute("SELECT status FROM jobs").fetchall()]
        assert all(s in ("cancelled", "succeeded", "failed") for s in statuses)
    finally:
        fresh.close()


@pytest.mark.asyncio
async def test_unmount_idempotent_when_not_mounted(tmp_path: Path) -> None:
    rt = VaultRuntime(project=_entry(tmp_path, "u4"), settings=ProjectSettings())
    # No mount() call. unmount should be a silent no-op.
    await rt.unmount(timeout=1.0, force=False)
    assert rt.is_mounted is False


@pytest.mark.asyncio
async def test_reload_settings_disable_daily_snapshot(
    tmp_path: Path, scheduler: AsyncIOScheduler, alerts: Alerts
) -> None:
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(project=_entry(tmp_path, "rs1"), settings=ProjectSettings())
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        assert scheduler.get_job("daily_snapshot:rs1") is not None
        rt.reload_settings(
            ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=False))
        )
        assert scheduler.get_job("daily_snapshot:rs1") is None
        assert scheduler.get_job("backups_cleanup:rs1") is not None
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_reload_settings_re_enable_daily_snapshot(
    tmp_path: Path, scheduler: AsyncIOScheduler, alerts: Alerts
) -> None:
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(
        project=_entry(tmp_path, "rs2"),
        settings=ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=False)),
    )
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        assert scheduler.get_job("daily_snapshot:rs2") is None
        rt.reload_settings(
            ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=True))
        )
        assert scheduler.get_job("daily_snapshot:rs2") is not None
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_reload_settings_updates_retention_days(
    tmp_path: Path, scheduler: AsyncIOScheduler, alerts: Alerts
) -> None:
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(
        project=_entry(tmp_path, "rs3"),
        settings=ProjectSettings(snapshots=SnapshotsSettings(retention_days=180)),
    )
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        rt.reload_settings(
            ProjectSettings(snapshots=SnapshotsSettings(retention_days=30))
        )
        job = scheduler.get_job("backups_cleanup:rs3")
        assert job is not None
        # args = [vault_root, retention_days]
        assert job.args[1] == 30
    finally:
        await rt.unmount(timeout=2.0, force=True)


def test_reload_settings_when_not_mounted_just_replaces(tmp_path: Path) -> None:
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(project=_entry(tmp_path, "rs4"), settings=ProjectSettings())
    new = ProjectSettings(snapshots=SnapshotsSettings(retention_days=7))
    rt.reload_settings(new)
    assert rt.settings.snapshots.retention_days == 7
    rt.job_store.close()
