from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LogLevel = Literal["debug", "info", "warning", "error"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5757
DEFAULT_RETENTION_DAYS = 180
DEFAULT_LOG_LEVEL: LogLevel = "info"


def default_pid_file() -> Path:
    return Path.home() / ".mnemos" / "daemon.pid"


def default_runtime_config_file() -> Path:
    return Path.home() / ".mnemos" / "daemon.config.json"


class DaemonConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault_root: Path
    host: str = DEFAULT_HOST
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    retention_days: int = Field(default=DEFAULT_RETENTION_DAYS, ge=1)
    log_level: LogLevel = DEFAULT_LOG_LEVEL
    pid_file: Path = Field(default_factory=default_pid_file)

    @classmethod
    def from_env(cls, vault_root: Path) -> DaemonConfig:
        host = os.environ.get("MNEMOS_DAEMON_HOST", DEFAULT_HOST)
        port_str = os.environ.get("MNEMOS_DAEMON_PORT")
        port = int(port_str) if port_str else DEFAULT_PORT
        retention_str = os.environ.get("MNEMOS_RETENTION_DAYS")
        retention_days = int(retention_str) if retention_str else DEFAULT_RETENTION_DAYS
        log_level_raw = os.environ.get("MNEMOS_DAEMON_LOG", DEFAULT_LOG_LEVEL).lower()
        if log_level_raw not in ("debug", "info", "warning", "error"):
            raise ValueError(
                f"MNEMOS_DAEMON_LOG must be one of debug/info/warning/error, "
                f"got {log_level_raw!r}"
            )
        log_level: LogLevel = log_level_raw  # type: ignore[assignment]
        pid_file_str = os.environ.get("MNEMOS_DAEMON_PID")
        pid_file = Path(pid_file_str) if pid_file_str else default_pid_file()
        return cls(
            vault_root=vault_root,
            host=host,
            port=port,
            retention_days=retention_days,
            log_level=log_level,
            pid_file=pid_file,
        )
