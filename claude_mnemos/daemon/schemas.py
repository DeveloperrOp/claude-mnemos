from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.core.snapshots import SnapshotInfo

__all__ = [
    "HealthResponse",
    "SchedulerJobInfo",
    "SnapshotInfo",
    "UndoApiResult",
    "VaultInfo",
    "VersionResponse",
]


class SchedulerJobInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    next_run_time: datetime | None
    trigger: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    version: str
    vault: str
    uptime_s: float = Field(ge=0.0)
    scheduler_jobs: list[SchedulerJobInfo] = Field(default_factory=list)


class VersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    python_version: str
    platform: str


class VaultInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault: str
    raw_chats: int = Field(ge=0)
    wiki_pages: int = Field(ge=0)
    manifest_processed: int = Field(ge=0)
    activity_entries: int = Field(ge=0)
    snapshots: int = Field(ge=0)
    total_size_bytes: int = Field(ge=0)


class UndoApiResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    op_id: str
    restored_pages: list[str] = Field(default_factory=list)
    new_entry_id: str | None = None
