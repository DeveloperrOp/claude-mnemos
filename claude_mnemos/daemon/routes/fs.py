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
