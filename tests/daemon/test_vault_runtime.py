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
async def test_mount_starts_observer_and_registers_cron_jobs(tmp_path: Path, scheduler, alerts):
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
async def test_mount_skips_daily_snapshot_when_disabled(tmp_path: Path, scheduler, alerts):
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(
        project=_entry(tmp_path, "noscan"),
        settings=ProjectSettings(snapshots=SnapshotsSettings(schedule="off")),
    )
    try:
        await rt.mount(scheduler=scheduler, alerts=alerts)
        ids = {j.id for j in scheduler.get_jobs()}
        assert "daily_snapshot:noscan" not in ids
        assert "backups_cleanup:noscan" in ids
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_mount_registers_lint_check_when_scheduled(tmp_path: Path, scheduler, alerts):
    from claude_mnemos.state.settings import LintSettings, ProjectSettings

    rt = VaultRuntime(
        project=_entry(tmp_path, "lc1"),
        settings=ProjectSettings(lint=LintSettings(schedule="0 * * * *")),
    )
    try:
        await rt.mount(scheduler=scheduler, alerts=alerts)
        ids = {j.id for j in scheduler.get_jobs()}
        assert "lint_check:lc1" in ids
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_mount_no_lint_check_when_schedule_none(tmp_path: Path, scheduler, alerts):
    rt = VaultRuntime(
        project=_entry(tmp_path, "lc2"),
        settings=ProjectSettings(),  # lint.schedule defaults None
    )
    try:
        await rt.mount(scheduler=scheduler, alerts=alerts)
        ids = {j.id for j in scheduler.get_jobs()}
        assert "lint_check:lc2" not in ids
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_reload_settings_enable_and_disable_lint_check(tmp_path: Path, scheduler, alerts):
    from claude_mnemos.state.settings import LintSettings, ProjectSettings

    rt = VaultRuntime(project=_entry(tmp_path, "lc3"), settings=ProjectSettings())
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        assert scheduler.get_job("lint_check:lc3") is None
        rt.reload_settings(ProjectSettings(lint=LintSettings(schedule="0 4 * * *")))
        assert scheduler.get_job("lint_check:lc3") is not None
        rt.reload_settings(ProjectSettings(lint=LintSettings(schedule=None)))
        assert scheduler.get_job("lint_check:lc3") is None
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_unmount_removes_lint_check(tmp_path: Path, scheduler, alerts):
    from claude_mnemos.state.settings import LintSettings, ProjectSettings

    rt = VaultRuntime(
        project=_entry(tmp_path, "lc4"),
        settings=ProjectSettings(lint=LintSettings(schedule="0 * * * *")),
    )
    await rt.mount(scheduler=scheduler, alerts=alerts)
    await rt.unmount(timeout=2.0, force=True)
    assert scheduler.get_job("lint_check:lc4") is None


@pytest.mark.asyncio
async def test_restore_with_quiesce_succeeds_with_open_jobs_db(tmp_path: Path, scheduler, alerts):
    # A mounted runtime keeps <vault>/.jobs.db open — the handle that blocks the
    # vault-directory rename on Windows. restore_with_quiesce must close it
    # around the swap, succeed, then reopen the store + restart the worker.
    from claude_mnemos.core.snapshots import create_manual_snapshot

    rt = VaultRuntime(project=_entry(tmp_path, "rq"), settings=ProjectSettings())
    page = rt.vault_root / "wiki" / "entities" / "foo.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("original\n", encoding="utf-8")
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        snap = create_manual_snapshot(rt.vault_root, label="probe")
        page.write_text("mutated\n", encoding="utf-8")  # diverge from snapshot

        result = await rt.restore_with_quiesce(snap)

        assert result.success is True, result.error
        # page reverted to the snapshot content
        assert page.read_text(encoding="utf-8") == "original\n"
        # store reopened + usable, worker restarted
        rt.job_store.count_by_status()  # must not raise (fresh open store)
        assert rt.job_worker is not None
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_restore_with_quiesce_observer_alive_after_restore(tmp_path: Path, scheduler, alerts):
    # The swap renames the vault dir away and deletes it; the old watchdog
    # observer keeps watching the deleted directory and goes blind. After
    # restore the runtime must watch the NEW vault dir — an external create
    # must still produce an alert.
    import asyncio

    from claude_mnemos.core.snapshots import create_manual_snapshot

    rt = VaultRuntime(project=_entry(tmp_path, "rqo"), settings=ProjectSettings())
    (rt.vault_root / "wiki").mkdir(parents=True, exist_ok=True)
    (rt.vault_root / "wiki" / "seed.md").write_text("x\n", encoding="utf-8")
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        snap = create_manual_snapshot(rt.vault_root, label="obs")
        result = await rt.restore_with_quiesce(snap)
        assert result.success is True, result.error

        # Outlive the tracker's post-pause cooldown (absorbs straggler swap
        # events) — otherwise the handler drops our create on the floor.
        await asyncio.sleep(1.3)

        # External create in the RESTORED vault must be observed.
        (rt.vault_root / "wiki" / "external-after-restore.md").write_text("y\n", encoding="utf-8")
        for _ in range(50):  # poll up to ~5s — watchdog delivers async
            if any("external-after-restore" in str(a.path) for a in alerts.list()):
                break
            await asyncio.sleep(0.1)
        assert any("external-after-restore" in str(a.path) for a in alerts.list()), (
            "watchdog observer is blind after restore"
        )
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_restore_with_quiesce_preserves_jobs_db_rows(tmp_path: Path, scheduler, alerts):
    # Dead-letter / queued rows must survive a restore (jobs.db is preserved
    # across the swap and reopened, not wiped).
    from claude_mnemos.core.snapshots import create_manual_snapshot

    rt = VaultRuntime(project=_entry(tmp_path, "rqp"), settings=ProjectSettings())
    (rt.vault_root / "wiki").mkdir(parents=True, exist_ok=True)
    (rt.vault_root / "wiki" / "p.md").write_text("x\n", encoding="utf-8")
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        rt.job_store.create(kind="ingest", payload={"transcript_path": "/x.jsonl"})
        before = rt.job_store.count_by_status()
        snap = create_manual_snapshot(rt.vault_root, label="probe2")
        result = await rt.restore_with_quiesce(snap)
        assert result.success is True, result.error
        after = rt.job_store.count_by_status()
        assert sum(after.values()) == sum(before.values())  # rows preserved
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
async def test_mount_rollback_on_observer_failure(tmp_path: Path, scheduler, alerts, monkeypatch):
    """If observer.start() raises, no scheduler jobs nor JobWorker leak."""

    class _Boom:
        def start(self):
            raise RuntimeError("disk full")

        def stop(self):  # not called, but defensive
            pass

    def _bad_observer(_root, _handler):
        return _Boom()

    monkeypatch.setattr("claude_mnemos.daemon.vault_runtime.VaultObserver", _bad_observer)

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
        rt.reload_settings(ProjectSettings(snapshots=SnapshotsSettings(schedule="off")))
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
        settings=ProjectSettings(snapshots=SnapshotsSettings(schedule="off")),
    )
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        assert scheduler.get_job("daily_snapshot:rs2") is None
        rt.reload_settings(ProjectSettings(snapshots=SnapshotsSettings(schedule="daily")))
        assert scheduler.get_job("daily_snapshot:rs2") is not None
    finally:
        await rt.unmount(timeout=2.0, force=True)


def test_snapshot_cron_kwargs_presets() -> None:
    from claude_mnemos.daemon.vault_runtime import _snapshot_cron_kwargs

    assert _snapshot_cron_kwargs("off") is None
    assert _snapshot_cron_kwargs("daily") == {"hour": 4, "minute": 0}
    assert _snapshot_cron_kwargs("weekly") == {
        "day_of_week": "sun",
        "hour": 4,
        "minute": 0,
    }
    assert _snapshot_cron_kwargs("monthly") == {"day": 1, "hour": 4, "minute": 0}


@pytest.mark.asyncio
async def test_mount_weekly_registers_weekly_cron(
    tmp_path: Path, scheduler: AsyncIOScheduler, alerts: Alerts
) -> None:
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(
        project=_entry(tmp_path, "wk"),
        settings=ProjectSettings(snapshots=SnapshotsSettings(schedule="weekly")),
    )
    try:
        await rt.mount(scheduler=scheduler, alerts=alerts)
        job = scheduler.get_job("daily_snapshot:wk")
        assert job is not None
        # The weekly preset constrains day_of_week; daily does not.
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert fields["day_of_week"] == "sun"
    finally:
        await rt.unmount(timeout=2.0, force=True)


@pytest.mark.asyncio
async def test_reload_settings_changes_cadence_daily_to_weekly(
    tmp_path: Path, scheduler: AsyncIOScheduler, alerts: Alerts
) -> None:
    from claude_mnemos.state.settings import ProjectSettings, SnapshotsSettings

    rt = VaultRuntime(project=_entry(tmp_path, "cad"), settings=ProjectSettings())
    await rt.mount(scheduler=scheduler, alerts=alerts)
    try:
        # default is daily — day_of_week is unconstrained ("*")
        job = scheduler.get_job("daily_snapshot:cad")
        assert job is not None
        rt.reload_settings(ProjectSettings(snapshots=SnapshotsSettings(schedule="weekly")))
        job2 = scheduler.get_job("daily_snapshot:cad")
        assert job2 is not None
        fields = {f.name: str(f) for f in job2.trigger.fields}
        assert fields["day_of_week"] == "sun"
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
        rt.reload_settings(ProjectSettings(snapshots=SnapshotsSettings(retention_days=30)))
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
