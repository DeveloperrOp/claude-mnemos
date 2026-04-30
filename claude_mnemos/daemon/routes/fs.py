"""Filesystem browsing endpoints — used by frontend DirectoryPicker.

Daemon binds 127.0.0.1 by default, so these endpoints are local-only;
no path-traversal hardening beyond input validation. List/create directories
on behalf of the user — they already control the machine.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/fs", tags=["fs"])

LIST_LIMIT = 100


@router.get("/home")
def get_home() -> dict[str, str]:
    return {"home": os.path.expanduser("~")}


@router.get("/browse")
def browse(path: str, include_files: bool = False) -> dict[str, object]:
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
        all_children = list(resolved.iterdir())
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail=f"permission denied: {exc}"
        ) from exc

    if include_files:
        children = [c for c in all_children if c.is_dir() or c.is_file()]
    else:
        children = [c for c in all_children if c.is_dir()]

    children.sort(key=lambda c: (not c.is_dir(), c.name.casefold()))
    truncated = len(children) > LIST_LIMIT
    children = children[:LIST_LIMIT]

    parent_path = resolved.parent
    parent_str = str(parent_path) if parent_path != resolved else None

    return {
        "cwd": str(resolved),
        "parent": parent_str,
        "entries": [
            {
                "name": c.name,
                "path": str(c),
                "type": "directory" if c.is_dir() else "file",
            }
            for c in children
        ],
        "truncated": truncated,
    }


@router.get("/drives")
def drives() -> dict[str, list[dict[str, str]]]:
    """List top-level filesystem roots.

    On Windows, returns each existing drive letter (C:\\, D:\\, ...).
    On POSIX, returns a single root entry.
    """
    if sys.platform == "win32":
        result: list[dict[str, str]] = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive_path = Path(f"{letter}:\\")
            if drive_path.exists():
                result.append({"name": f"{letter}:", "path": str(drive_path)})
        return {"drives": result}
    return {"drives": [{"name": "/", "path": "/"}]}


class MkdirRequest(BaseModel):
    path: str


@router.post("/mkdir")
def mkdir(req: MkdirRequest) -> dict[str, str]:
    p = Path(req.path)
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="path must be absolute")
    if p.exists():
        raise HTTPException(status_code=400, detail=f"path already exists: {p}")
    if not p.parent.exists():
        raise HTTPException(
            status_code=400, detail=f"parent directory does not exist: {p.parent}"
        )
    try:
        p.mkdir(parents=False, exist_ok=False)
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail=f"permission denied: {exc}"
        ) from exc
    return {"path": str(p.resolve())}
