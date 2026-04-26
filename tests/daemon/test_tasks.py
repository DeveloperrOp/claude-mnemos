from datetime import date
from pathlib import Path

from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.snapshots import (
    compute_daily_snapshot_path,
    create_daily_snapshot,
)
from claude_mnemos.daemon.tasks import backups_cleanup_task, daily_snapshot_task


def test_daily_snapshot_creates_directory(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()

    snap = daily_snapshot_task(vault, today=date(2026, 4, 26))
    assert snap is not None
    assert snap == compute_daily_snapshot_path(vault, date(2026, 4, 26))
    assert snap.is_dir()


def test_daily_snapshot_idempotent(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    today = date(2026, 4, 26)

    snap1 = daily_snapshot_task(vault, today=today)
    snap2 = daily_snapshot_task(vault, today=today)
    assert snap1 == snap2


def test_daily_snapshot_skips_when_locked(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    today = date(2026, 4, 26)

    with pipeline_lock(vault):
        # Trying to take lock with short timeout should fail and return None
        snap = daily_snapshot_task(vault, today=today, lock_timeout=0.5)
    assert snap is None
    assert not compute_daily_snapshot_path(vault, today).exists()


def test_backups_cleanup_removes_old_keeps_new(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)
    # Old daily snapshot (300 days back)
    compute_daily_snapshot_path(vault, date(2025, 7, 1)).mkdir()
    # New daily snapshot (1 day back)
    compute_daily_snapshot_path(vault, date(2026, 4, 25)).mkdir()

    result = backups_cleanup_task(vault, retention_days=180, today=date(2026, 4, 26))
    assert result is not None
    assert "daily-2025-07-01" in result.pruned
    assert "daily-2026-04-25" not in result.pruned
    assert result.kept == 1
    assert result.errors == []


def test_backups_cleanup_skips_when_locked(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)
    create_daily_snapshot(vault, date(2025, 7, 1))

    with pipeline_lock(vault):
        result = backups_cleanup_task(
            vault, retention_days=180, today=date(2026, 4, 26), lock_timeout=0.5
        )
    assert result is None
    # Snapshot still there because we couldn't acquire lock
    assert compute_daily_snapshot_path(vault, date(2025, 7, 1)).exists()


def test_daily_snapshot_swallows_create_errors(tmp_path: Path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()

    def boom(*args, **kwargs):
        raise OSError("disk on fire")

    monkeypatch.setattr(
        "claude_mnemos.daemon.tasks.daily_snapshot.create_daily_snapshot", boom
    )

    snap = daily_snapshot_task(vault, today=date(2026, 4, 26))
    assert snap is None  # error logged, not raised


def test_backups_cleanup_swallows_errors(tmp_path: Path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / ".backups").mkdir(parents=True)

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(
        "claude_mnemos.daemon.tasks.backups_cleanup.prune_old_backups", boom
    )

    result = backups_cleanup_task(vault, retention_days=180, today=date(2026, 4, 26))
    assert result is None
