"""Active-sessions scanner — projection of transcript_scanner restricted
to recent jsonls (mtime > now - cooling_threshold) that are not yet
ingested in any vault. Status hot vs cooling for UI bins.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from claude_mnemos.core.transcript_scanner import scan_transcripts
from claude_mnemos.mapping.resolver import (
    ProjectResolver,
    ResolverAmbiguityError,
)
from claude_mnemos.state.manifest import Manifest

if TYPE_CHECKING:
    from claude_mnemos.daemon.vault_runtime import VaultRuntime

UNASSIGNED_PROJECT = "__unassigned__"
HOT_THRESHOLD_MIN = 30
COOLING_THRESHOLD_HOURS = 24


class ActiveSession(BaseModel):
    session_id: str
    transcript_path: str
    sha: str
    project_name: str
    cwd: str | None
    preview: str | None
    mtime: datetime
    size_bytes: int
    status: Literal["hot", "cooling"]
    auto_dump_at: datetime | None


def _global_ingested_shas(runtimes: list["VaultRuntime"]) -> set[str]:
    out: set[str] = set()
    for rt in runtimes:
        try:
            manifest = Manifest.load(rt.vault_root)
        except Exception:
            continue
        out.update(manifest.ingested.keys())
    return out


async def scan_active_sessions(
    runtimes: list["VaultRuntime"],
    *,
    cooling_threshold_hours: int = COOLING_THRESHOLD_HOURS,
    transcripts_root: Path | None = None,
) -> list[ActiveSession]:
    entries = await scan_transcripts(transcripts_root=transcripts_root)
    if not entries:
        return []

    now = datetime.now(tz=UTC)
    cutoff = now - timedelta(hours=cooling_threshold_hours)
    hot_cutoff = now - timedelta(minutes=HOT_THRESHOLD_MIN)
    ingested = _global_ingested_shas(runtimes)
    resolver = ProjectResolver()

    out: list[ActiveSession] = []
    for e in entries:
        if e.mtime < cutoff:
            continue
        if e.sha in ingested:
            continue
        project_name = UNASSIGNED_PROJECT
        if e.cwd:
            try:
                entry = resolver.resolve_by_cwd(Path(e.cwd))
                if entry is not None:
                    project_name = entry.name
            except (ResolverAmbiguityError, OSError):
                pass
        status: Literal["hot", "cooling"] = (
            "hot" if e.mtime >= hot_cutoff else "cooling"
        )
        auto_dump_at = (
            e.mtime + timedelta(hours=cooling_threshold_hours)
            if project_name != UNASSIGNED_PROJECT
            else None
        )
        out.append(
            ActiveSession(
                session_id=e.session_id,
                transcript_path=e.transcript_path,
                sha=e.sha,
                project_name=project_name,
                cwd=e.cwd,
                preview=e.preview,
                mtime=e.mtime,
                size_bytes=e.size_bytes,
                status=status,
                auto_dump_at=auto_dump_at,
            )
        )
    out.sort(key=lambda s: s.mtime, reverse=True)
    return out
