from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_mnemos.state.ontology import SuggestionStore


def list_suggestions(
    vault: Path,
    *,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List ontology suggestions, optionally filtered by status.

    Statuses include "pending" (default behaviour when status=None: pending only),
    "approved", "rejected", "deferred", or "all" (every status).
    """
    store = SuggestionStore(vault)
    include_archive = status in ("approved", "rejected", "all")
    items = store.list(include_archive=include_archive)
    if status and status != "all":
        items = [s for s in items if s.frontmatter.status == status]
    elif status is None:
        items = [s for s in items if s.frontmatter.status == "pending"]
    return [
        {"frontmatter": s.frontmatter.model_dump(mode="json"), "body": s.body}
        for s in items
    ]
