from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_mnemos.tray.supervisor import (
    HealthSnapshot,
    Supervisor,
    SupervisorState,
)


@pytest.fixture
def fake_pid_file(tmp_path: Path) -> Path:
    return tmp_path / "daemon.pid"


def test_health_snapshot_defaults() -> None:
    snap = HealthSnapshot(reachable=False)
    assert snap.reachable is False
    assert snap.projects_mounted == 0
    assert snap.uptime_seconds is None


def test_tick_promotes_starting_to_running_on_health_ok(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = MagicMock(poll=MagicMock(return_value=None), pid=1)
    sv._spawned = True
    sv.state = SupervisorState.STARTING
    with patch.object(
        sv, "_check_health",
        return_value=HealthSnapshot(reachable=True, projects_mounted=2, uptime_seconds=5.0),
    ):
        sv.tick(now=10.0)
    assert sv.state == SupervisorState.RUNNING
    assert sv.last_health.projects_mounted == 2


def test_tick_detects_subprocess_crash_and_records(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = MagicMock(poll=MagicMock(return_value=1), pid=1)
    sv._spawned = True
    sv.state = SupervisorState.RUNNING
    with patch.object(sv, "_spawn_daemon") as spawn:
        spawn.return_value = MagicMock(poll=MagicMock(return_value=None), pid=2)
        sv.tick(now=100.0)
    # First crash → restart attempted, state=Starting
    assert sv.limiter.crash_count(now=100.0) == 1
    assert sv.state == SupervisorState.STARTING


def test_tick_does_not_treat_user_stop_as_crash(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = MagicMock(poll=MagicMock(return_value=0), pid=1)
    sv._spawned = True
    sv.state = SupervisorState.STOPPING  # user-initiated
    with patch.object(sv, "_spawn_daemon") as spawn:
        sv.tick(now=100.0)
        spawn.assert_not_called()
    assert sv.limiter.crash_count(now=100.0) == 0


def test_tick_blocks_restart_after_threshold_and_enters_crashed(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = MagicMock(poll=MagicMock(return_value=1), pid=1)
    sv._spawned = True
    sv.state = SupervisorState.RUNNING

    # Pre-load 3 prior crashes
    sv.limiter.record_crash(now=0.0)
    sv.limiter.record_crash(now=1.0)
    sv.limiter.record_crash(now=2.0)
    with patch.object(sv, "_spawn_daemon") as spawn:
        sv.tick(now=3.0)  # 4th crash exceeds threshold
        spawn.assert_not_called()
    assert sv.state == SupervisorState.CRASHED
    assert sv.limiter.crash_count(now=3.0) == 4


def test_tick_does_nothing_for_adopted_daemon_when_pid_alive(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = None
    sv._spawned = False
    sv.state = SupervisorState.RUNNING
    sv.daemon_pid = 9999
    snap = HealthSnapshot(reachable=True, projects_mounted=1)
    with patch("claude_mnemos.tray.supervisor.psutil") as psutil_mod, \
         patch.object(sv, "_check_health", return_value=snap):
        psutil_mod.pid_exists.return_value = True
        sv.tick(now=1.0)
    assert sv.state == SupervisorState.RUNNING


def test_tick_marks_adopted_daemon_crashed_when_pid_gone(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = None
    sv._spawned = False
    sv.state = SupervisorState.RUNNING
    sv.daemon_pid = 9999
    with patch("claude_mnemos.tray.supervisor.psutil") as psutil_mod:
        psutil_mod.pid_exists.return_value = False
        sv.tick(now=1.0)
    # Adopted daemon disappeared — we don't auto-respawn (we don't own it).
    assert sv.state == SupervisorState.CRASHED
