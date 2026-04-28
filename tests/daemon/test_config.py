from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_mnemos.daemon.config import BootFilter, DaemonConfig, default_pid_file


def test_daemon_config_defaults():
    c = DaemonConfig(pid_file=Path("/tmp/p.pid"))
    assert c.host == "127.0.0.1"
    assert c.port == 5757
    assert c.boot_filter is None  # None == "all"


def test_daemon_config_rejects_legacy_vault_root():
    with pytest.raises(ValidationError):
        DaemonConfig(pid_file=Path("/tmp/p.pid"), vault_root=Path("/v"))  # type: ignore[call-arg]


def test_daemon_config_rejects_legacy_retention_days():
    with pytest.raises(ValidationError):
        DaemonConfig(pid_file=Path("/tmp/p.pid"), retention_days=180)  # type: ignore[call-arg]


def test_boot_filter_all_default_false():
    f = BootFilter()
    assert f.all is False
    assert f.names == []


def test_boot_filter_round_trip():
    f = BootFilter(all=False, names=["a", "b"])
    assert f.model_dump() == {"all": False, "names": ["a", "b"]}


def test_from_env_picks_up_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("MNEMOS_DAEMON_HOST", "0.0.0.0")
    monkeypatch.setenv("MNEMOS_DAEMON_PORT", "6060")
    monkeypatch.setenv("MNEMOS_DAEMON_LOG", "debug")
    monkeypatch.setenv("MNEMOS_DAEMON_PID", str(tmp_path / "custom.pid"))

    config = DaemonConfig.from_env()
    assert config.host == "0.0.0.0"
    assert config.port == 6060
    assert config.log_level == "debug"
    assert config.pid_file == tmp_path / "custom.pid"


def test_from_env_defaults_when_unset(monkeypatch: pytest.MonkeyPatch):
    for var in (
        "MNEMOS_DAEMON_HOST",
        "MNEMOS_DAEMON_PORT",
        "MNEMOS_DAEMON_LOG",
        "MNEMOS_DAEMON_PID",
    ):
        monkeypatch.delenv(var, raising=False)

    config = DaemonConfig.from_env()
    assert config.host == "127.0.0.1"
    assert config.port == 5757
    assert config.log_level == "info"


def test_from_env_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MNEMOS_DAEMON_LOG", "verbose")
    with pytest.raises(ValueError):
        DaemonConfig.from_env()


def test_invalid_port_rejected():
    with pytest.raises(ValidationError):
        DaemonConfig(pid_file=Path("/tmp/p.pid"), port=0)
    with pytest.raises(ValidationError):
        DaemonConfig(pid_file=Path("/tmp/p.pid"), port=70000)


def test_invalid_log_level_rejected():
    with pytest.raises(ValidationError):
        DaemonConfig(pid_file=Path("/tmp/p.pid"), log_level="verbose")  # type: ignore[arg-type]


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        DaemonConfig(pid_file=Path("/tmp/p.pid"), extra_field=42)  # type: ignore[call-arg]


def test_default_pid_file_uses_home():
    result = default_pid_file()
    assert result.name == "daemon.pid"
    assert ".claude-mnemos" in str(result)
