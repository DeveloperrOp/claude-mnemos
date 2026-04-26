from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_mnemos.mcp.config import MCPConfig


def test_defaults(tmp_path: Path):
    c = MCPConfig(vault_root=tmp_path)
    assert c.vault_root == tmp_path
    assert c.daemon_url == "http://127.0.0.1:5757"
    assert c.daemon_timeout_s == 30.0
    assert c.log_level == "info"


def test_from_env_overrides(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MNEMOS_DAEMON_URL", "http://10.0.0.1:9999")
    monkeypatch.setenv("MNEMOS_MCP_TIMEOUT", "5")
    monkeypatch.setenv("MNEMOS_MCP_LOG", "debug")
    c = MCPConfig.from_env(tmp_path)
    assert c.daemon_url == "http://10.0.0.1:9999"
    assert c.daemon_timeout_s == 5.0
    assert c.log_level == "debug"


def test_from_env_defaults_when_unset(tmp_path: Path, monkeypatch):
    for var in ("MNEMOS_DAEMON_URL", "MNEMOS_MCP_TIMEOUT", "MNEMOS_MCP_LOG"):
        monkeypatch.delenv(var, raising=False)
    c = MCPConfig.from_env(tmp_path)
    assert c.daemon_url == "http://127.0.0.1:5757"


def test_from_env_invalid_log_level(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MNEMOS_MCP_LOG", "verbose")
    with pytest.raises(ValueError):
        MCPConfig.from_env(tmp_path)


def test_invalid_timeout_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        MCPConfig(vault_root=tmp_path, daemon_timeout_s=0)
    with pytest.raises(ValidationError):
        MCPConfig(vault_root=tmp_path, daemon_timeout_s=-1)


def test_invalid_log_level_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        MCPConfig(vault_root=tmp_path, log_level="verbose")  # type: ignore[arg-type]


def test_extra_field_forbidden(tmp_path: Path):
    with pytest.raises(ValidationError):
        MCPConfig(vault_root=tmp_path, foo=42)  # type: ignore[call-arg]
