from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_mnemos.core.snapshots import list_snapshots
from claude_mnemos.core.vault_stats import count_md, vault_size
from claude_mnemos.state.activity import ActivityLog
from claude_mnemos.state.manifest import Manifest


def get_status(vault: Path) -> dict[str, Any]:
    """Same shape as the daemon's GET /vault/info, but read directly.

    Raises ActivityCorruptError / ManifestCorruptError on bad state files —
    handler converts to error TextContent.
    """
    activity = ActivityLog.load(vault)
    manifest = Manifest.load(vault)
    return {
        "vault": str(vault),
        "raw_chats": count_md(vault / "raw" / "chats"),
        "wiki_pages": count_md(vault / "wiki"),
        "manifest_processed": len(manifest.ingested),
        "activity_entries": len(activity.entries),
        "snapshots": len(list_snapshots(vault)),
        "total_size_bytes": vault_size(vault),
    }
