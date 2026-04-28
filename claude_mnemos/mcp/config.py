from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.daemon_url import daemon_base_url

LogLevel = Literal["debug", "info", "warning", "error"]

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_LOG_LEVEL: LogLevel = "info"


class MCPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault_root: Path | None = None
    daemon_url: str = Field(default_factory=daemon_base_url)
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
        env_url = os.environ.get("MNEMOS_DAEMON_URL")
        return cls(
            vault_root=vault_root,
            daemon_url=env_url if env_url is not None else daemon_base_url(),
            daemon_timeout_s=timeout,
            log_level=log_level,
        )
