from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.core.snapshots import SnapshotInfo

__all__ = [
    "AutofixApiResult",
    "HealthResponse",
    "LintReportResponse",
    "SchedulerJobInfo",
    "SnapshotInfo",
    "UndoApiResult",
    "VaultInfo",
    "VersionResponse",
    "WatchdogAlertResponse",
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
    watchdog_running: bool = False
    alerts_count: int = Field(default=0, ge=0)


class WatchdogAlertResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal[
        "external_create",
        "external_rename",
        "lock_timeout",
        "parse_failed",
        "handler_error",
    ]
    path: str
    message: str
    detected_at: datetime


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


class LintReportResponse(BaseModel):
    """Pass-through alias around lint.models.LintReport for the REST surface."""

    model_config = ConfigDict(extra="allow")
    # Body follows lint.models.LintReport — defined here as opaque pass-through
    # so /lint/results can serve any future-additive field without schema work.


class AutofixApiResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    snapshot_path: str | None
    fixed_findings: list[str] = Field(default_factory=list)
    skipped_findings: list[str] = Field(default_factory=list)
    activity_id: str | None
