"""REST routes for per-project + global settings.

Uses bare paths (no /api/ prefix) per existing daemon convention.

Daemon reload trigger: when PATCH /settings/{project} updates the
project whose vault matches the daemon's own ``config.vault_root``, the
daemon's ``reload_settings`` method is invoked with the new instance so
schedulers/observers pick up the change without restart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from claude_mnemos.state.projects import ProjectStore
from claude_mnemos.state.settings import (
    GlobalSettings,
    ProjectSettings,
    SettingsStore,
)

router = APIRouter()


def _settings_store() -> SettingsStore:
    return SettingsStore()


def _project_store() -> ProjectStore:
    return ProjectStore()


# IMPORTANT: /settings/global must be declared BEFORE /settings/{name}
# so FastAPI's path matcher does not capture "global" as a project name.


@router.get("/settings/global", response_model=GlobalSettings)
def get_global_settings() -> GlobalSettings:
    return _settings_store().get_global()


@router.patch("/settings/global", response_model=GlobalSettings)
def patch_global_settings(body: dict[str, Any]) -> GlobalSettings:
    return _settings_store().patch_global(body)


@router.get("/settings/{name}", response_model=ProjectSettings)
def get_project_settings(name: str) -> ProjectSettings:
    return _settings_store().get_project(name)


@router.patch("/settings/{name}", response_model=ProjectSettings)
def patch_project_settings(
    name: str, body: dict[str, Any], request: Request,
) -> ProjectSettings:
    updated = _settings_store().patch_project(name, body)
    daemon = request.app.state.daemon
    if daemon is not None:
        try:
            entry = _project_store().get(name)
        except Exception:  # noqa: BLE001
            entry = None
        if (
            entry is not None
            and Path(entry.vault_root).expanduser().resolve()
            == Path(daemon.config.vault_root).expanduser().resolve()
            and hasattr(daemon, "reload_settings")
        ):
            daemon.reload_settings(updated)
    return updated
