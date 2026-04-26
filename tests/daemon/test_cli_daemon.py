from pathlib import Path

import pytest

from claude_mnemos.cli import build_parser
from claude_mnemos.daemon.runtime_state import DaemonRuntimeState


def test_parser_daemon_start_minimal(tmp_path: Path):
    args = build_parser().parse_args(["daemon", "start", "--vault", str(tmp_path)])
    assert args.command == "daemon"
    assert args.daemon_cmd == "start"
    assert args.vault == tmp_path
    assert args.host is None
    assert args.port is None


def test_parser_daemon_foreground_with_overrides(tmp_path: Path):
    args = build_parser().parse_args(
        [
            "daemon",
            "foreground",
            "--vault",
            str(tmp_path),
            "--port",
            "8080",
            "--host",
            "127.0.0.1",
            "--retention-days",
            "30",
            "--log-level",
            "debug",
        ]
    )
    assert args.daemon_cmd == "foreground"
    assert args.port == 8080
    assert args.retention_days == 30
    assert args.log_level == "debug"


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
        vault_root=tmp_path / "vault",
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
