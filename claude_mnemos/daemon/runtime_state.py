from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.daemon.config import default_runtime_config_file


class DaemonRuntimeState(BaseModel):
    """Snapshot of the running daemon's effective config — used by `mnemos daemon
    status` and `mnemos daemon stop` to find host/port/pid_file without re-parsing
    env vars in the controlling shell.
    """

    model_config = ConfigDict(extra="forbid")

    vault_root: Path
    host: str
    port: int = Field(ge=1, le=65535)
    pid_file: Path

    @classmethod
    def load(cls, path: Path | None = None) -> DaemonRuntimeState | None:
        path = path or default_runtime_config_file()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            return cls.model_validate(data)
        except Exception:
            return None

    def save(self, path: Path | None = None) -> None:
        path = path or default_runtime_config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

    @classmethod
    def cleanup(cls, path: Path | None = None) -> None:
        path = path or default_runtime_config_file()
        path.unlink(missing_ok=True)
