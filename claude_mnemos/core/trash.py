"""Trash directory parsing — list manually-deleted (and other) trash entries."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)

TRASH_DIRNAME = ".trash"
TRASH_METADATA_FILENAME = ".metadata.json"
TRASH_REASON_FILENAME = ".reason.txt"


class TrashEntryNotFoundError(LookupError):
    """Raised when a trash_id doesn't resolve to a directory inside .trash/."""


class TrashMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    trash_id: str
    original_path: str
    deleted_at: datetime
    operation_id: str
    operation_type: str


class TrashEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trash_id: str
    deleted_at: datetime
    original_path: str | None = None
    operation_type: str | None = None
    page_basename: str | None = None
    restorable: bool = False
    restore_blocked_reason: str | None = None


def read_metadata(trash_dir: Path) -> TrashMetadata | None:
    """Load .metadata.json from a trash subdir. Returns None if missing or invalid."""
    meta_path = trash_dir / TRASH_METADATA_FILENAME
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("trash metadata at %s is invalid JSON", meta_path)
        return None
    try:
        return TrashMetadata.model_validate(data)
    except ValidationError:
        logger.warning("trash metadata at %s fails schema", meta_path)
        return None


def list_trash(vault: Path) -> list[TrashEntry]:
    """Walk <vault>/.trash/, return entries sorted newest-first by deleted_at."""
    trash_root = vault / TRASH_DIRNAME
    if not trash_root.is_dir():
        return []

    entries: list[TrashEntry] = []
    for sub in trash_root.iterdir():
        if not sub.is_dir():
            continue
        meta = read_metadata(sub)
        # Find the page file (first .md not starting with .)
        page_basename: str | None = None
        for f in sub.iterdir():
            if f.is_file() and not f.name.startswith(".") and f.suffix == ".md":
                page_basename = f.name
                break

        if meta is not None:
            restorable = page_basename is not None
            blocked = None if restorable else "page file missing"
            entries.append(
                TrashEntry(
                    trash_id=sub.name,
                    deleted_at=meta.deleted_at,
                    original_path=meta.original_path,
                    operation_type=meta.operation_type,
                    page_basename=page_basename,
                    restorable=restorable,
                    restore_blocked_reason=blocked,
                )
            )
        else:
            # Fallback: dir mtime, marked unrestorable
            try:
                mtime = datetime.fromtimestamp(sub.stat().st_mtime).astimezone()
            except OSError:
                continue
            entries.append(
                TrashEntry(
                    trash_id=sub.name,
                    deleted_at=mtime,
                    original_path=None,
                    operation_type=None,
                    page_basename=page_basename,
                    restorable=False,
                    restore_blocked_reason="missing or invalid metadata",
                )
            )

    entries.sort(key=lambda e: e.deleted_at, reverse=True)
    return entries
