from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_mnemos.core.snapshots import list_snapshots
from claude_mnemos.state.activity import ActivityLog
from claude_mnemos.state.manifest import Manifest


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


def get_status(vault: Path) -> dict[str, Any]:
    """Same shape as the daemon's GET /vault/info, but read directly.

    Raises ActivityCorruptError / ManifestCorruptError on bad state files —
    handler converts to error TextContent.
    """
    activity = ActivityLog.load(vault)
    manifest = Manifest.load(vault)
    return {
        "vault": str(vault),
        "raw_chats": _count_md(vault / "raw" / "chats"),
        "wiki_pages": _count_md(vault / "wiki"),
        "manifest_processed": len(manifest.ingested),
        "activity_entries": len(activity.entries),
        "snapshots": len(list_snapshots(vault)),
        "total_size_bytes": _vault_size(vault),
    }
