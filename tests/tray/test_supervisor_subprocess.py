from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_mnemos.tray.supervisor import Supervisor, SupervisorState


@pytest.fixture
def fake_pid_file(tmp_path: Path) -> Path:
    return tmp_path / "daemon.pid"


def _make_popen(pid: int = 4242, alive: bool = True) -> MagicMock:
    proc = MagicMock()
    proc.pid = pid
    proc.poll.return_value = None if alive else 0
    return proc


def test_start_spawns_subprocess_and_transitions_to_starting(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    fake_proc = _make_popen()
    with patch("claude_mnemos.tray.supervisor.subprocess.Popen", return_value=fake_proc) as popen, \
         patch.object(sv, "_is_existing_daemon_running", return_value=False):
        sv.start()
    assert sv.state == SupervisorState.STARTING
    assert sv.daemon_pid == 4242
    assert sv._spawned is True
    popen.assert_called_once()
    cmd = popen.call_args[0][0]
    assert "claude_mnemos.daemon" in " ".join(cmd)
    assert "foreground" in cmd
    assert "--all" in cmd


def test_start_adopts_existing_daemon_without_spawning(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    with patch("claude_mnemos.tray.supervisor.subprocess.Popen") as popen, \
         patch.object(sv, "_is_existing_daemon_running", return_value=9999):
        sv.start()
    assert sv.state == SupervisorState.RUNNING  # adopted = already up
    assert sv.daemon_pid == 9999
    assert sv._spawned is False
    popen.assert_not_called()


def test_mark_running_transitions_starting_to_running(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv.state = SupervisorState.STARTING
    sv.mark_running()
    assert sv.state == SupervisorState.RUNNING


def test_stop_terminates_spawned_subprocess(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    fake_proc = _make_popen()
    sv._proc = fake_proc
    sv._spawned = True
    sv.state = SupervisorState.RUNNING

    sv.stop(grace_seconds=0.01)
    assert sv.state == SupervisorState.STOPPED
    fake_proc.terminate.assert_called_once()


def test_stop_does_not_kill_adopted_daemon(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    fake_proc = _make_popen()
    sv._proc = fake_proc
    sv._spawned = False  # adopted
    sv.state = SupervisorState.RUNNING

    sv.stop(grace_seconds=0.01)
    assert sv.state == SupervisorState.STOPPED
    fake_proc.terminate.assert_not_called()
    fake_proc.kill.assert_not_called()


def test_stop_kills_after_grace_timeout(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    fake_proc = _make_popen()
    fake_proc.wait.side_effect = __import__("subprocess").TimeoutExpired(cmd="x", timeout=0.01)
    sv._proc = fake_proc
    sv._spawned = True
    sv.state = SupervisorState.RUNNING

    sv.stop(grace_seconds=0.01)
    fake_proc.terminate.assert_called_once()
    fake_proc.kill.assert_called_once()


def test_restart_only_works_when_spawned(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = _make_popen()
    sv._spawned = False  # adopted
    sv.state = SupervisorState.RUNNING

    with pytest.raises(RuntimeError, match="adopted"):
        sv.restart()


def test_restart_spawns_new_subprocess(fake_pid_file: Path) -> None:
    sv = Supervisor(daemon_pid_file=fake_pid_file)
    sv._proc = _make_popen()
    sv._spawned = True
    sv.state = SupervisorState.RUNNING

    new_proc = _make_popen(pid=5555)
    with patch("claude_mnemos.tray.supervisor.subprocess.Popen", return_value=new_proc):
        sv.restart()
    assert sv.daemon_pid == 5555
    assert sv.state == SupervisorState.STARTING
    # Crash counter must reset on manual restart
    assert sv.limiter.crash_count() == 0
