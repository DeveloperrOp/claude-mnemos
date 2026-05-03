"""Tests for the 7 semantic health detectors."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_mnemos.core.health_checks import (
    check_auto_dump_overdue,
    check_daemon_uptime_warning,
    check_disk_low,
    check_hook_silence,
    check_ingest_failure_streak,
    check_project_map_broken,
    check_runaway_jobs,
    run_all_checks,
)
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── Fakes ──────────────────────────────────────────────────


class _FakeRuntime:
    def __init__(self, name: str, vault: Path) -> None:
        self.name = name
        self.vault_root = vault
        self.job_store = JobStore(vault / JOBS_DB_FILENAME)


class _FakeDaemon:
    def __init__(self, started_seconds_ago: float = 3600.0) -> None:
        self.started_at_monotonic = time.monotonic() - started_seconds_ago


def _make_scheduler(*, has_job: bool = True, next_run_in_seconds: float | None = 1800):
    sched = MagicMock()
    if not has_job:
        sched.get_job.return_value = None
        return sched
    job = MagicMock()
    if next_run_in_seconds is None:
        job.next_run_time = None
    else:
        job.next_run_time = _utcnow() + timedelta(seconds=next_run_in_seconds)
    sched.get_job.return_value = job
    return sched


# ─── 1. auto_dump_overdue ───────────────────────────────────


def test_auto_dump_overdue_healthy() -> None:
    sched = _make_scheduler(next_run_in_seconds=1800)
    assert check_auto_dump_overdue(sched) is None


def test_auto_dump_overdue_missing_job() -> None:
    sched = _make_scheduler(has_job=False)
    a = check_auto_dump_overdue(sched)
    assert a is not None and a.severity == "warning"
    assert a.id == "auto_dump_overdue"


def test_auto_dump_overdue_triggers_when_3h_late() -> None:
    sched = _make_scheduler(next_run_in_seconds=-3 * 3600)
    a = check_auto_dump_overdue(sched)
    assert a is not None
    assert a.severity == "warning"
    assert "overdue" in a.message.lower()


def test_auto_dump_overdue_quiet_when_no_next_run_time() -> None:
    sched = _make_scheduler(next_run_in_seconds=None)
    assert check_auto_dump_overdue(sched) is None


# ─── 2. ingest_failure_streak ───────────────────────────────


def _seed_finished_job(
    store: JobStore, *, status: str, finished_at: datetime
) -> None:
    job = store.create(kind="ingest", payload={"path": "x"})
    # Direct DB poke since the mark_* helpers move through the state machine.
    ts = finished_at.timestamp()
    store._conn.execute(
        "UPDATE jobs SET status=?, finished_at=?, started_at=? WHERE id=?",
        (status, ts, ts - 1, job.id),
    )


def test_ingest_failure_streak_triggers(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    now = _utcnow()
    for i in range(3):
        _seed_finished_job(
            rt.job_store, status="failed", finished_at=now - timedelta(minutes=i)
        )
    a = check_ingest_failure_streak({"alpha": rt}, now=now)
    assert a is not None
    assert a.severity == "critical"


def test_ingest_failure_streak_silent_with_one_success(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    now = _utcnow()
    _seed_finished_job(rt.job_store, status="failed", finished_at=now - timedelta(minutes=2))
    _seed_finished_job(rt.job_store, status="succeeded", finished_at=now - timedelta(minutes=1))
    _seed_finished_job(rt.job_store, status="failed", finished_at=now)
    assert check_ingest_failure_streak({"alpha": rt}, now=now) is None


def test_ingest_failure_streak_silent_below_three(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    now = _utcnow()
    _seed_finished_job(rt.job_store, status="failed", finished_at=now)
    _seed_finished_job(rt.job_store, status="failed", finished_at=now - timedelta(minutes=1))
    assert check_ingest_failure_streak({"alpha": rt}, now=now) is None


def test_ingest_failure_streak_excludes_old_jobs(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    now = _utcnow()
    for _ in range(3):
        _seed_finished_job(rt.job_store, status="failed", finished_at=now - timedelta(hours=48))
    assert check_ingest_failure_streak({"alpha": rt}, now=now) is None


# ─── 3. runaway_jobs ────────────────────────────────────────


def test_runaway_jobs_triggers(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    now = _utcnow()
    job = rt.job_store.create(kind="ingest", payload={"path": "x"})
    started_ts = (now - timedelta(minutes=45)).timestamp()
    rt.job_store._conn.execute(
        "UPDATE jobs SET status='running', started_at=? WHERE id=?",
        (started_ts, job.id),
    )
    a = check_runaway_jobs({"alpha": rt}, now=now)
    assert a is not None
    assert a.severity == "warning"
    assert a.context["jobs"][0]["project"] == "alpha"


def test_runaway_jobs_quiet_under_30_min(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    now = _utcnow()
    job = rt.job_store.create(kind="ingest", payload={"path": "x"})
    started_ts = (now - timedelta(minutes=10)).timestamp()
    rt.job_store._conn.execute(
        "UPDATE jobs SET status='running', started_at=? WHERE id=?",
        (started_ts, job.id),
    )
    assert check_runaway_jobs({"alpha": rt}, now=now) is None


# ─── 4. hook_silence ────────────────────────────────────────


def test_hook_silence_triggers_with_recent_jsonl_no_ingest(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    pd = tmp_path / "claude-projects"
    sub = pd / "abc"
    sub.mkdir(parents=True)
    (sub / "session.jsonl").write_text("{}", encoding="utf-8")
    a = check_hook_silence({"alpha": rt}, projects_dir=pd)
    assert a is not None
    assert a.severity == "warning"


def test_hook_silence_quiet_with_recent_success(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    pd = tmp_path / "claude-projects"
    sub = pd / "abc"
    sub.mkdir(parents=True)
    (sub / "session.jsonl").write_text("{}", encoding="utf-8")
    now = _utcnow()
    _seed_finished_job(rt.job_store, status="succeeded", finished_at=now - timedelta(minutes=30))
    assert check_hook_silence({"alpha": rt}, now=now, projects_dir=pd) is None


def test_hook_silence_quiet_with_no_jsonl(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    pd = tmp_path / "claude-projects-empty"
    pd.mkdir()
    assert check_hook_silence({"alpha": rt}, projects_dir=pd) is None


def test_hook_silence_quiet_when_dir_missing(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    assert check_hook_silence({"alpha": rt}, projects_dir=tmp_path / "missing") is None


# ─── 5. disk_low ────────────────────────────────────────────


def test_disk_low_triggers(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    fake_usage = MagicMock(total=1000, free=10, used=990)  # 1% free
    with patch("claude_mnemos.core.health_checks.shutil.disk_usage", return_value=fake_usage):
        a = check_disk_low({"alpha": rt})
    assert a is not None
    assert a.severity == "critical"
    assert a.context["vaults"][0]["project"] == "alpha"


def test_disk_low_quiet_when_plenty(tmp_path: Path) -> None:
    rt = _FakeRuntime("alpha", tmp_path / "vault")
    rt.vault_root.mkdir(parents=True, exist_ok=True)
    fake_usage = MagicMock(total=1000, free=900, used=100)
    with patch("claude_mnemos.core.health_checks.shutil.disk_usage", return_value=fake_usage):
        assert check_disk_low({"alpha": rt}) is None


# ─── 6. project_map_broken ──────────────────────────────────


def test_project_map_broken_quiet_on_clean_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    assert check_project_map_broken() is None


def test_project_map_broken_alerts_on_corrupt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    cm = home / ".claude-mnemos"
    cm.mkdir(parents=True)
    (cm / "project-map.json").write_text("garbage{{{", encoding="utf-8")
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    a = check_project_map_broken()
    assert a is not None
    assert a.severity == "critical"


# ─── 7. daemon_uptime_warning ───────────────────────────────


def test_daemon_uptime_warning_triggers_when_just_started() -> None:
    daemon = _FakeDaemon(started_seconds_ago=10.0)
    a = check_daemon_uptime_warning(daemon)
    assert a is not None
    assert a.severity == "info"


def test_daemon_uptime_warning_quiet_after_threshold() -> None:
    daemon = _FakeDaemon(started_seconds_ago=300.0)
    assert check_daemon_uptime_warning(daemon) is None


def test_daemon_uptime_warning_quiet_when_not_started() -> None:
    daemon = _FakeDaemon()
    daemon.started_at_monotonic = 0.0
    assert check_daemon_uptime_warning(daemon) is None


# ─── run_all_checks ─────────────────────────────────────────


def test_run_all_checks_continues_after_failing_detector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    daemon = _FakeDaemon(started_seconds_ago=10.0)  # uptime warning fires
    sched = MagicMock()
    sched.get_job.side_effect = RuntimeError("boom")
    alerts = run_all_checks(daemon=daemon, scheduler=sched, runtimes={})
    # The crashing detector is dropped; uptime detector still fires.
    ids = {a.id for a in alerts}
    assert "daemon_uptime_warning" in ids
    assert "auto_dump_overdue" not in ids


def test_run_all_checks_returns_only_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    daemon = _FakeDaemon(started_seconds_ago=3600.0)
    sched = _make_scheduler(next_run_in_seconds=1800)
    alerts = run_all_checks(daemon=daemon, scheduler=sched, runtimes={})
    assert all(isinstance(a.id, str) for a in alerts)
