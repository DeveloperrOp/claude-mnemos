"""Pydantic schemas for lint findings and reports."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LintSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class LintFixKind(StrEnum):
    STRIP_TRAILING_WS = "strip_trailing_ws"
    FIX_WIKILINK_TYPO = "fix_wikilink_typo"
    ADD_DEFAULT_FRONTMATTER_FIELD = "add_default_frontmatter_field"


class LintFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rule_id: str
    severity: LintSeverity
    message: str
    page_path: str
    fixable: bool
    fix_kind: LintFixKind | None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LintReportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_rule: dict[str, int] = Field(default_factory=dict)
    fixable_count: int = Field(ge=0)


class LintReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    run_id: str
    started_at: datetime
    finished_at: datetime
    vault_root: str
    rule_versions: dict[str, str] = Field(default_factory=dict)
    findings: list[LintFinding] = Field(default_factory=list)
    summary: LintReportSummary
