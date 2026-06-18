from __future__ import annotations

from fastapi import APIRouter, Request

from claude_mnemos.core.snapshots import list_snapshots
from claude_mnemos.core.vault_stats import count_md, vault_size
from claude_mnemos.daemon.routes._helpers import get_runtime
from claude_mnemos.daemon.schemas import VaultInfo
from claude_mnemos.state.activity import ActivityLog
from claude_mnemos.state.manifest import Manifest

router = APIRouter()


@router.get("/vault/{project}", response_model=VaultInfo)
def vault_info(project: str, request: Request) -> VaultInfo:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    activity = ActivityLog.load(vault)
    manifest = Manifest.load(vault)
    raw_chats = count_md(vault / "raw" / "chats")
    wiki_pages = count_md(vault / "wiki")
    snapshots = len(list_snapshots(vault))
    return VaultInfo(
        vault=str(vault),
        raw_chats=raw_chats,
        wiki_pages=wiki_pages,
        manifest_processed=len(manifest.ingested),
        activity_entries=len(activity.entries),
        snapshots=snapshots,
        total_size_bytes=vault_size(vault),
    )
