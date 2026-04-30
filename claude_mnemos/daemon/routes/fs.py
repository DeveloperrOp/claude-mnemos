"""Filesystem browsing endpoints — used by frontend DirectoryPicker.

Daemon binds 127.0.0.1 by default, so these endpoints are local-only;
no path-traversal hardening beyond input validation. List/create directories
on behalf of the user — they already control the machine.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/fs", tags=["fs"])

LIST_LIMIT = 100


@router.get("/home")
def get_home() -> dict[str, str]:
    return {"home": os.path.expanduser("~")}


@router.get("/browse")
def browse(path: str) -> dict[str, object]:
    p = Path(path)
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="path must be absolute")
    try:
        resolved = p.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"path does not exist: {exc}") from exc
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")

    try:
        children = [c for c in resolved.iterdir() if c.is_dir()]
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail=f"permission denied: {exc}"
        ) from exc

    children.sort(key=lambda c: c.name.casefold())
    truncated = len(children) > LIST_LIMIT
    children = children[:LIST_LIMIT]

    parent_path = resolved.parent
    parent_str = str(parent_path) if parent_path != resolved else None

    return {
        "cwd": str(resolved),
        "parent": parent_str,
        "entries": [{"name": c.name, "path": str(c)} for c in children],
        "truncated": truncated,
    }
