from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LogLevel = Literal["debug", "info", "warning", "error"]

DEFAULT_DAEMON_URL = "http://127.0.0.1:5757"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_LOG_LEVEL: LogLevel = "info"


class MCPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault_root: Path | None = None
    daemon_url: str = DEFAULT_DAEMON_URL
    daemon_timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, gt=0.0)
    log_level: LogLevel = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls, vault_root: Path) -> MCPConfig:
        log_level_raw = os.environ.get("MNEMOS_MCP_LOG", DEFAULT_LOG_LEVEL).lower()
        if log_level_raw not in ("debug", "info", "warning", "error"):
            raise ValueError(
                f"MNEMOS_MCP_LOG must be one of debug/info/warning/error, "
                f"got {log_level_raw!r}"
            )
        log_level: LogLevel = log_level_raw  # type: ignore[assignment]
        timeout_raw = os.environ.get("MNEMOS_MCP_TIMEOUT")
        timeout = float(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT_S
        return cls(
            vault_root=vault_root,
            daemon_url=os.environ.get("MNEMOS_DAEMON_URL", DEFAULT_DAEMON_URL),
            daemon_timeout_s=timeout,
            log_level=log_level,
        )
