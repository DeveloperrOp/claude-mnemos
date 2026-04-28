from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core.snapshots import list_snapshots
from claude_mnemos.daemon.schemas import VaultInfo
from claude_mnemos.state.activity import ActivityLog
from claude_mnemos.state.manifest import Manifest

router = APIRouter()


def _vault(request: Request) -> Path:
    vault = request.app.state.vault_root
    if vault is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_vault_registered",
                "hint": "Register: mnemos project add NAME --vault PATH",
            },
        )
    assert isinstance(vault, Path)
    return vault


def _count_md(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for p in root.rglob("*.md") if p.is_file())


def _vault_size(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return total


@router.get("/vault/info", response_model=VaultInfo)
def vault_info(request: Request) -> VaultInfo:
    vault = _vault(request)
    activity = ActivityLog.load(vault)
    manifest = Manifest.load(vault)
    raw_chats = _count_md(vault / "raw" / "chats")
    wiki_pages = _count_md(vault / "wiki")
    snapshots = len(list_snapshots(vault))
    return VaultInfo(
        vault=str(vault),
        raw_chats=raw_chats,
        wiki_pages=wiki_pages,
        manifest_processed=len(manifest.ingested),
        activity_entries=len(activity.entries),
        snapshots=snapshots,
        total_size_bytes=_vault_size(vault),
    )
