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
