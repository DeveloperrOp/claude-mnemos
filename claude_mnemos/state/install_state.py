"""Tiny singleton state file for install-level UX flags.

Stored at ~/.claude-mnemos/install-state.json. Used by the onboarding
flow + first-session celebration + autostart-default-on logic.

Schema is intentionally tiny — fields can be added later, missing
fields default. No version bump expected for the foreseeable future.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from claude_mnemos.core.atomic import atomic_write

_STATE_PATH: Path = Path.home() / ".claude-mnemos" / "install-state.json"
_LOCK = threading.RLock()


class InstallState(BaseModel):
    first_run_ts: datetime | None = None
    autostart_decision: Literal["accepted", "declined"] | None = None
    window_close_action: Literal["hide", "quit"] | None = None

    def save(self) -> None:
        with _LOCK:
            _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(
                _STATE_PATH,
                self.model_dump_json(indent=2),
            )


def load_install_state() -> InstallState:
    """Load the singleton; return defaults if file missing or unreadable."""
    with _LOCK:
        if not _STATE_PATH.exists():
            return InstallState()
        try:
            data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            return InstallState.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            return InstallState()
