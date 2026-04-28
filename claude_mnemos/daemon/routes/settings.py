"""REST routes for per-project + global settings.

Uses bare paths (no /api/ prefix) per existing daemon convention.

Daemon reload trigger: after a successful PATCH the daemon's hot-reload
methods are called so in-memory scheduler jobs and primary-runtime
selection update immediately without restart.

  PATCH /settings/{name}   → daemon.reload_project_settings(name, new)
  PATCH /settings/global   → daemon.reload_global_settings(new)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from claude_mnemos.state.settings import (
    GlobalSettings,
    ProjectSettings,
    SettingsStore,
)

router = APIRouter()


def _settings_store() -> SettingsStore:
    return SettingsStore()


# IMPORTANT: /settings/global must be declared BEFORE /settings/{name}
# so FastAPI's path matcher does not capture "global" as a project name.


@router.get("/settings/global", response_model=GlobalSettings)
def get_global_settings() -> GlobalSettings:
    return _settings_store().get_global()


@router.patch("/settings/global", response_model=GlobalSettings)
async def patch_global_settings(
    request: Request, body: dict[str, Any]
) -> GlobalSettings:
    store = _settings_store()
    try:
        new = store.patch_global(body)
    except ValidationError as exc:
        raise HTTPException(
            422, detail={"error": "validation_error", "detail": exc.errors()}
        ) from exc

    daemon = request.app.state.daemon
    if daemon is not None:
        await daemon.reload_global_settings(new)
    return new


@router.get("/settings/{name}", response_model=ProjectSettings)
def get_project_settings(name: str) -> ProjectSettings:
    return _settings_store().get_project(name)


@router.patch("/settings/{name}", response_model=ProjectSettings)
async def patch_project_settings(
    name: str, request: Request, body: dict[str, Any]
) -> ProjectSettings:
    store = _settings_store()
    try:
        new = store.patch_project(name, body)
    except ValidationError as exc:
        raise HTTPException(
            422, detail={"error": "validation_error", "detail": exc.errors()}
        ) from exc

    daemon = request.app.state.daemon
    if daemon is not None:
        await daemon.reload_project_settings(name, new)
    return new
