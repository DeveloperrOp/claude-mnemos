from pathlib import Path

import psutil
import pytest

from claude_mnemos.daemon.lockfile import (
    DAEMON_CMDLINE_MARKER,
    cleanup_pid_file,
    is_daemon_running,
    write_pid_file,
)


def test_missing_pid_file_returns_none(tmp_path: Path):
    assert is_daemon_running(tmp_path / "no.pid") is None


def test_invalid_content_deleted_and_returns_none(tmp_path: Path):
    pf = tmp_path / "daemon.pid"
    pf.write_text("not-a-number", encoding="utf-8")
    assert is_daemon_running(pf) is None
    assert not pf.exists()


def test_dead_pid_deleted_and_returns_none(tmp_path: Path, monkeypatch):
    pf = tmp_path / "daemon.pid"
    pf.write_text("99999", encoding="utf-8")
    monkeypatch.setattr(psutil, "pid_exists", lambda _pid: False)
    assert is_daemon_running(pf) is None
    assert not pf.exists()


def test_pid_alive_without_marker_returns_none(tmp_path: Path, monkeypatch):
    pf = tmp_path / "daemon.pid"
    pf.write_text("123", encoding="utf-8")
    monkeypatch.setattr(psutil, "pid_exists", lambda _pid: True)

    class FakeProc:
        def __init__(self, pid):
            self._pid = pid

        def cmdline(self):
            return ["/usr/bin/python3", "-c", "print('hello')"]

    monkeypatch.setattr(psutil, "Process", FakeProc)
    assert is_daemon_running(pf) is None
    assert not pf.exists()


def test_pid_alive_with_marker_returns_pid(tmp_path: Path, monkeypatch):
    pf = tmp_path / "daemon.pid"
    pf.write_text("123", encoding="utf-8")
    monkeypatch.setattr(psutil, "pid_exists", lambda _pid: True)

    class FakeProc:
        def __init__(self, pid):
            self._pid = pid

        def cmdline(self):
            return ["python", "-m", DAEMON_CMDLINE_MARKER, "run"]

    monkeypatch.setattr(psutil, "Process", FakeProc)
    assert is_daemon_running(pf) == 123
    assert pf.exists()


def test_no_such_process_returns_none(tmp_path: Path, monkeypatch):
    pf = tmp_path / "daemon.pid"
    pf.write_text("123", encoding="utf-8")
    monkeypatch.setattr(psutil, "pid_exists", lambda _pid: True)

    class FakeProc:
        def __init__(self, pid):
            raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr(psutil, "Process", FakeProc)
    assert is_daemon_running(pf) is None
    assert not pf.exists()


def test_access_denied_returns_none(tmp_path: Path, monkeypatch):
    pf = tmp_path / "daemon.pid"
    pf.write_text("123", encoding="utf-8")
    monkeypatch.setattr(psutil, "pid_exists", lambda _pid: True)

    class FakeProc:
        def __init__(self, pid):
            self._pid = pid

        def cmdline(self):
            raise psutil.AccessDenied()

    monkeypatch.setattr(psutil, "Process", FakeProc)
    assert is_daemon_running(pf) is None
    assert not pf.exists()


def test_write_pid_file_creates_parent(tmp_path: Path):
    pf = tmp_path / "nested" / "dirs" / "daemon.pid"
    write_pid_file(pf, 42)
    assert pf.read_text(encoding="utf-8") == "42"


def test_cleanup_pid_file_idempotent(tmp_path: Path):
    pf = tmp_path / "daemon.pid"
    cleanup_pid_file(pf)  # missing — must not raise
    pf.write_text("1", encoding="utf-8")
    cleanup_pid_file(pf)
    assert not pf.exists()


def test_pid_file_with_whitespace(tmp_path: Path, monkeypatch):
    pf = tmp_path / "daemon.pid"
    pf.write_text("  555  \n", encoding="utf-8")
    monkeypatch.setattr(psutil, "pid_exists", lambda _pid: True)

    class FakeProc:
        def __init__(self, pid):
            self.pid = pid

        def cmdline(self):
            return ["python", "-m", DAEMON_CMDLINE_MARKER]

    monkeypatch.setattr(psutil, "Process", FakeProc)
    assert is_daemon_running(pf) == 555


def test_pytest_ensures_psutil_installed():
    """Sanity that psutil module exists in environment."""
    assert hasattr(psutil, "pid_exists")
    assert hasattr(psutil, "Process")
    # ensure pytest module imported (used by other tests)
    _ = pytest
