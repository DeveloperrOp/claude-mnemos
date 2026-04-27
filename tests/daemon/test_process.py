from pathlib import Path

import pytest

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.fixture
def daemon(tmp_path: Path) -> MnemosDaemon:
    config = DaemonConfig(
        vault_root=tmp_path,
        port=15757,
        retention_days=180,
        pid_file=tmp_path / "daemon.pid",
    )
    return MnemosDaemon(config)


def test_daemon_initializes_scheduler_and_app(daemon: MnemosDaemon):
    assert daemon.scheduler is not None
    assert daemon.app is not None
    # App has our routes registered
    routes = {r.path for r in daemon.app.routes if hasattr(r, "path")}
    assert "/health" in routes
    assert "/version" in routes
    assert "/vault/info" in routes
    assert "/activity" in routes
    assert "/snapshots" in routes


def test_daemon_scheduler_jobs_info(daemon: MnemosDaemon):
    jobs = daemon.scheduler_jobs_info()
    assert len(jobs) == 2
    assert {j.id for j in jobs} == {"daily_snapshot", "backups_cleanup"}


def test_daemon_started_at_zero_before_run(daemon: MnemosDaemon):
    assert daemon.started_at_monotonic == 0.0


def test_daemon_request_shutdown_no_server_safe(daemon: MnemosDaemon):
    # Calling shutdown when server hasn't been created must not raise
    daemon._request_shutdown()
    assert daemon._server is None


# Plan #9 — watchdog wiring


def test_daemon_holds_tracker_and_alerts(daemon: MnemosDaemon):
    from claude_mnemos.daemon.alerts import Alerts
    from claude_mnemos.daemon.our_writes import OurWritesTracker

    assert isinstance(daemon.tracker, OurWritesTracker)
    assert isinstance(daemon.alerts, Alerts)
    assert daemon.observer is None


def test_start_observer_handles_failure_with_alert(
    daemon: MnemosDaemon, monkeypatch: pytest.MonkeyPatch
):
    def boom(self):  # noqa: ANN001
        raise RuntimeError("watcher boom")

    monkeypatch.setattr(
        "claude_mnemos.daemon.watchdog_observer.VaultObserver.start", boom
    )
    daemon._start_observer()
    # Daemon must keep running; failure surfaces as alert.
    assert daemon.observer is None
    items = daemon.alerts.list()
    assert any(a.kind == "handler_error" for a in items)


def test_start_observer_then_stop(daemon: MnemosDaemon, tmp_path: Path):
    daemon._start_observer()
    assert daemon.observer is not None
    assert daemon.observer.is_running
    daemon._stop_observer()
    assert daemon.observer is None


# Plan #11 — jobs subsystem wiring


def test_daemon_initializes_jobs_subsystem(daemon: MnemosDaemon):
    from claude_mnemos.state.jobs import JobStore

    assert isinstance(daemon.job_store, JobStore)
    assert daemon.job_worker is None  # not started yet


async def test_daemon_recovery_runs_on_start(
    daemon: MnemosDaemon, monkeypatch: pytest.MonkeyPatch
):
    from claude_mnemos.state.jobs import RecoveryResult

    calls: list[bool] = []
    real_recover = daemon.job_store.recover_zombie_running

    def spy() -> RecoveryResult:
        calls.append(True)
        return real_recover()

    monkeypatch.setattr(daemon.job_store, "recover_zombie_running", spy)
    await daemon._start_jobs_subsystem()
    try:
        assert calls == [True]
        assert daemon.job_worker is not None
    finally:
        await daemon._stop_jobs_subsystem()


async def test_daemon_jobs_subsystem_failure_is_alert(
    daemon: MnemosDaemon, monkeypatch: pytest.MonkeyPatch
):
    """If JobWorker.start raises, daemon logs alert and continues."""

    async def boom(self):  # noqa: ANN001
        raise RuntimeError("worker boom")

    monkeypatch.setattr(
        "claude_mnemos.daemon.jobs.worker.JobWorker.start", boom
    )
    await daemon._start_jobs_subsystem()
    items = daemon.alerts.list()
    assert any(a.kind == "handler_error" for a in items)
    await daemon._stop_jobs_subsystem()
