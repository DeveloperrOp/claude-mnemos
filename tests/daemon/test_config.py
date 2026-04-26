from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_mnemos.daemon.config import DaemonConfig, default_pid_file


def test_defaults(tmp_path: Path):
    config = DaemonConfig(vault_root=tmp_path)
    assert config.host == "127.0.0.1"
    assert config.port == 5757
    assert config.retention_days == 180
    assert config.log_level == "info"
    assert config.pid_file == default_pid_file()


def test_from_env_picks_up_overrides(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MNEMOS_DAEMON_HOST", "0.0.0.0")
    monkeypatch.setenv("MNEMOS_DAEMON_PORT", "6060")
    monkeypatch.setenv("MNEMOS_RETENTION_DAYS", "30")
    monkeypatch.setenv("MNEMOS_DAEMON_LOG", "debug")
    monkeypatch.setenv("MNEMOS_DAEMON_PID", str(tmp_path / "custom.pid"))

    config = DaemonConfig.from_env(tmp_path)
    assert config.host == "0.0.0.0"
    assert config.port == 6060
    assert config.retention_days == 30
    assert config.log_level == "debug"
    assert config.pid_file == tmp_path / "custom.pid"


def test_from_env_defaults_when_unset(tmp_path: Path, monkeypatch):
    for var in (
        "MNEMOS_DAEMON_HOST",
        "MNEMOS_DAEMON_PORT",
        "MNEMOS_RETENTION_DAYS",
        "MNEMOS_DAEMON_LOG",
        "MNEMOS_DAEMON_PID",
    ):
        monkeypatch.delenv(var, raising=False)

    config = DaemonConfig.from_env(tmp_path)
    assert config.host == "127.0.0.1"
    assert config.port == 5757
    assert config.retention_days == 180
    assert config.log_level == "info"


def test_from_env_invalid_log_level_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MNEMOS_DAEMON_LOG", "verbose")
    with pytest.raises(ValueError):
        DaemonConfig.from_env(tmp_path)


def test_invalid_port_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        DaemonConfig(vault_root=tmp_path, port=0)
    with pytest.raises(ValidationError):
        DaemonConfig(vault_root=tmp_path, port=70000)


def test_invalid_retention_days_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        DaemonConfig(vault_root=tmp_path, retention_days=0)


def test_invalid_log_level_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        DaemonConfig(vault_root=tmp_path, log_level="verbose")  # type: ignore[arg-type]


def test_extra_field_forbidden(tmp_path: Path):
    with pytest.raises(ValidationError):
        DaemonConfig(vault_root=tmp_path, extra_field=42)  # type: ignore[call-arg]
