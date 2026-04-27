from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_mnemos.core.atomic import atomic_write

ACTIVITY_FILENAME = ".activity.json"

ActivityStatus = Literal["success"]
ActivityOperationType = Literal[
    "ingest_extracted",
    "ingest_raw_only",
    "manual_restore",
    "ontology_apply",
    "human_edit_detected",
]


class ActivityCorruptError(ValueError):
    """Raised when activity log file is unreadable or fails schema validation."""


class ActivityEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str
    timestamp: datetime
    operation_type: ActivityOperationType
    status: ActivityStatus
    snapshot_path: str | None
    can_undo: bool
    undone: bool = False
    undone_at: datetime | None = None
    undone_by_id: str | None = None
    affected_pages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActivityLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    entries: list[ActivityEntry] = Field(default_factory=list)

    @classmethod
    def load(cls, vault_root: Path) -> ActivityLog:
        path = vault_root / ACTIVITY_FILENAME
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ActivityCorruptError(
                f"activity log at {path} is not valid JSON: {exc}"
            ) from exc
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ActivityCorruptError(
                f"activity log at {path} fails schema: {exc}"
            ) from exc

    def serialize_to_string(self) -> str:
        """Serialize activity log to the exact JSON string we'd write to disk.

        Used by pipeline to put activity content into the staging area before promote.
        """
        return (
            json.dumps(
                self.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=False,
            )
            + "\n"
        )

    def save(self, vault_root: Path) -> None:
        path = vault_root / ACTIVITY_FILENAME
        atomic_write(path, self.serialize_to_string())

    def append(self, entry: ActivityEntry) -> None:
        if self.entries and entry.timestamp < self.entries[-1].timestamp:
            raise ValueError(
                f"activity entries must be appended in chronological order; "
                f"new entry timestamp {entry.timestamp} is older than last "
                f"entry {self.entries[-1].timestamp}"
            )
        if any(e.id == entry.id for e in self.entries):
            raise ValueError(f"activity log already contains entry id {entry.id}")
        self.entries.append(entry)

    def find_by_id(self, op_id: str) -> ActivityEntry | None:
        for e in self.entries:
            if e.id == op_id:
                return e
        return None

    def last_undoable(self) -> ActivityEntry | None:
        for e in reversed(self.entries):
            if e.can_undo and not e.undone:
                return e
        return None
