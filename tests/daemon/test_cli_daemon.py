from pathlib import Path

import pytest

from claude_mnemos.cli import build_parser
from claude_mnemos.daemon.runtime_state import DaemonRuntimeState


def test_parser_daemon_start_minimal():
    args = build_parser().parse_args(["daemon", "start"])
    assert args.command == "daemon"
    assert args.daemon_cmd == "start"
    assert args.host is None
    assert args.port is None


def test_parser_daemon_start_vault_flag_rejected(tmp_path: Path):
    """--vault PATH must now hard-exit with code 2 (legacy hard-cut, Task 22)."""
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["daemon", "start", "--vault", str(tmp_path)])
    assert exc.value.code == 2


def test_parser_daemon_foreground_with_overrides():
    args = build_parser().parse_args(
        [
            "daemon",
            "foreground",
            "--port",
            "8080",
            "--host",
            "127.0.0.1",
            "--log-level",
            "debug",
        ]
    )
    assert args.daemon_cmd == "foreground"
    assert args.port == 8080
    assert args.log_level == "debug"


def test_parser_daemon_foreground_vault_flag_rejected(tmp_path: Path):
    """--vault PATH must hard-exit on foreground too (Task 22)."""
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["daemon", "foreground", "--vault", str(tmp_path)])
    assert exc.value.code == 2


def test_parser_daemon_stop_default_timeout():
    args = build_parser().parse_args(["daemon", "stop"])
    assert args.daemon_cmd == "stop"
    assert args.timeout == 10.0


def test_parser_daemon_status():
    args = build_parser().parse_args(["daemon", "status"])
    assert args.daemon_cmd == "status"


def test_parser_daemon_invalid_log_level_rejected(tmp_path: Path):
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["daemon", "start", "--vault", str(tmp_path), "--log-level", "verbose"]
        )


def test_status_when_no_runtime_state_prints_stopped(capsys, monkeypatch, tmp_path: Path):
    from claude_mnemos.cli import _cmd_daemon_status

    pid_file = tmp_path / "no.pid"
    monkeypatch.setattr(
        "claude_mnemos.cli.default_pid_file", lambda: pid_file
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.runtime_state.default_runtime_config_file",
        lambda: tmp_path / "no.config",
    )

    class Args:
        pass

    rc = _cmd_daemon_status(Args())
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out.strip() == "stopped"


def test_runtime_state_roundtrip(tmp_path: Path):
    state = DaemonRuntimeState(
        host="127.0.0.1",
        port=5757,
        pid_file=tmp_path / "daemon.pid",
    )
    path = tmp_path / "config.json"
    state.save(path)
    loaded = DaemonRuntimeState.load(path)
    assert loaded == state
    DaemonRuntimeState.cleanup(path)
    assert not path.exists()
    assert DaemonRuntimeState.load(path) is None


def test_runtime_state_load_corrupt_returns_none(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text("not json", encoding="utf-8")
    assert DaemonRuntimeState.load(path) is None


# ── daemon status with live HTTP — new /health shape ─────────────────────────


def _fake_pid() -> int:
    """Return a sentinel PID value used in status-command tests."""
    return 12345


def _setup_state(monkeypatch, tmp_path: Path, *, host: str, port: int) -> None:
    """Save a DaemonRuntimeState and monkeypatch runtime config path + is_daemon_running."""
    pid_file = tmp_path / "daemon.pid"
    state = DaemonRuntimeState(host=host, port=port, pid_file=pid_file)
    state_path = tmp_path / "state.json"
    state.save(state_path)
    monkeypatch.setattr(
        "claude_mnemos.daemon.runtime_state.default_runtime_config_file",
        lambda: state_path,
    )
    # Bypass real pid-file / process checks
    monkeypatch.setattr("claude_mnemos.cli.is_daemon_running", lambda _pf: _fake_pid())


def test_status_with_vaults_shows_per_vault_lines(
    capsys, monkeypatch, tmp_path: Path
):
    """_cmd_daemon_status formats /health vaults dict as per-vault status lines."""
    import httpx

    from claude_mnemos.cli import _cmd_daemon_status

    _setup_state(monkeypatch, tmp_path, host="127.0.0.1", port=19999)

    health_body = {
        "status": "ok",
        "version": "0.1.0",
        "uptime_s": 42.5,
        "alerts_count": 1,
        "jobs_alert": False,
        "scheduler_jobs": [],
        "vaults": {
            "alpha": {
                "watchdog_running": True,
                "jobs_queued": 2,
                "jobs_running": 1,
                "jobs_dead_letter": 0,
            },
            "beta": {
                "watchdog_running": False,
                "jobs_queued": 0,
                "jobs_running": 0,
                "jobs_dead_letter": 3,
            },
        },
    }

    def fake_get(_url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(200, json=health_body)

    monkeypatch.setattr("claude_mnemos.cli.httpx.get", fake_get)

    class Args:
        pass

    rc = _cmd_daemon_status(Args())
    assert rc == 0

    out = capsys.readouterr().out
    # Header line with host:port
    assert "127.0.0.1:19999" in out
    # Per-vault lines present for both vaults
    assert "alpha" in out
    assert "beta" in out
    # watchdog state labels
    assert "running" in out
    assert "down" in out
    # job counts appear in output
    assert "queued=2" in out
    assert "dead-letter=3" in out
    # Old top-level "vault" key must not appear as a JSON field name
    assert '"vault"' not in out


def test_status_with_empty_vaults(capsys, monkeypatch, tmp_path: Path):
    """_cmd_daemon_status prints '(none mounted)' when vaults dict is empty."""
    import httpx

    from claude_mnemos.cli import _cmd_daemon_status

    _setup_state(monkeypatch, tmp_path, host="127.0.0.1", port=19998)

    health_body = {
        "status": "ok",
        "version": "0.1.0",
        "uptime_s": 5.0,
        "alerts_count": 0,
        "jobs_alert": False,
        "scheduler_jobs": [],
        "vaults": {},
    }

    def fake_get(_url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(200, json=health_body)

    monkeypatch.setattr("claude_mnemos.cli.httpx.get", fake_get)

    class Args:
        pass

    rc = _cmd_daemon_status(Args())
    assert rc == 0
    out = capsys.readouterr().out
    assert "(none mounted)" in out


def test_status_http_unreachable_returns_1(capsys, monkeypatch, tmp_path: Path):
    """When HTTP to /health fails, exit code 1 and error to stderr."""
    import httpx

    from claude_mnemos.cli import _cmd_daemon_status

    _setup_state(monkeypatch, tmp_path, host="127.0.0.1", port=19997)

    def fake_get(_url: str, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("claude_mnemos.cli.httpx.get", fake_get)

    class Args:
        pass

    rc = _cmd_daemon_status(Args())
    assert rc == 1
    err = capsys.readouterr().err
    assert "unreachable" in err
