"""REST routes for project-map CRUD + combined ProjectView."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from claude_mnemos.state.projects import (
    PROJECT_NAME_PATTERN,
    ProjectMapEntry,
    ProjectNameConflictError,
    ProjectNotFoundError,
    ProjectStore,
)
from claude_mnemos.state.settings import ProjectSettings, SettingsStore

router = APIRouter()


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=PROJECT_NAME_PATTERN)
    vault_root: Path
    cwd_patterns: list[str] = Field(default_factory=list)


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vault_root: Path | None = None
    cwd_patterns: list[str] | None = None  # full replace
    add_cwd_patterns: list[str] | None = None
    remove_cwd_patterns: list[str] | None = None


class ProjectView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    vault_root: Path
    cwd_patterns: list[str]
    settings: ProjectSettings


def _store() -> ProjectStore:
    return ProjectStore()


def _settings_store() -> SettingsStore:
    return SettingsStore()


@router.get("/projects", response_model=list[ProjectMapEntry])
def list_projects() -> list[ProjectMapEntry]:
    return _store().list_all()


@router.get("/projects/{name}", response_model=ProjectView)
def get_project(name: str) -> ProjectView:
    try:
        entry = _store().get(name)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "name": name},
        ) from exc
    settings = _settings_store().get_project(name)
    return ProjectView(
        name=entry.name,
        vault_root=entry.vault_root,
        cwd_patterns=entry.cwd_patterns,
        settings=settings,
    )


@router.post("/projects", status_code=201)
async def create_project(request: Request, body: ProjectCreate) -> dict[str, Any]:
    store = ProjectStore()
    entry = ProjectMapEntry(
        name=body.name,
        vault_root=body.vault_root,
        cwd_patterns=body.cwd_patterns or [],
    )
    try:
        store.add(entry)
    except ProjectNameConflictError as exc:
        raise HTTPException(
            409, detail={"error": "name_conflict", "detail": str(exc)}
        ) from exc

    daemon = request.app.state.daemon
    if daemon is not None:
        from claude_mnemos.daemon.vault_runtime import VaultMountError

        try:
            await daemon.mount_vault(entry)
        except VaultMountError as exc:
            with contextlib.suppress(Exception):
                store.remove(entry.name)
            raise HTTPException(
                500, detail={"error": "mount_failed", "detail": str(exc)}
            ) from exc

    return entry.model_dump(mode="json")


@router.delete("/projects/{name}", status_code=204)
async def delete_project(
    name: str, request: Request, force: bool = False
) -> Response:
    daemon = request.app.state.daemon
    if daemon is not None and name in daemon.runtimes:
        from claude_mnemos.daemon.vault_runtime import VaultBusyError

        try:
            await daemon.unmount_vault(name, force=force)
        except VaultBusyError as exc:
            raise HTTPException(
                409,
                detail={
                    "error": "vault_busy",
                    "queued": exc.queued,
                    "running": exc.running,
                    "hint": "delete with ?force=true to drain",
                },
            ) from exc

    try:
        ProjectStore().remove(name)
    except ProjectNotFoundError as exc:
        # If not in map and not in runtimes either, it never existed.
        if daemon is None or name not in (e.name for e in ProjectStore().list_all()):
            raise HTTPException(404, detail={"error": "not_found", "name": name}) from exc
    return Response(status_code=204)


@router.patch("/projects/{name}")
async def patch_project(
    name: str, request: Request, body: ProjectPatch
) -> dict[str, Any]:
    daemon = request.app.state.daemon
    new_vault = body.vault_root
    new_patterns = body.cwd_patterns
    add_patterns = body.add_cwd_patterns
    remove_patterns = body.remove_cwd_patterns

    # Pre-flight busy check before touching the map (vault_root change only).
    if daemon is not None and name in daemon.runtimes and new_vault is not None:
        current = daemon.runtimes[name].vault_root
        if current != new_vault:
            counts = daemon.runtimes[name].job_store.count_by_status()
            queued = int(counts.get("queued", 0))
            running = int(counts.get("running", 0))
            if queued or running:
                raise HTTPException(
                    409,
                    detail={
                        "error": "vault_busy",
                        "queued": queued,
                        "running": running,
                        "hint": "drain or cancel jobs before changing vault_root",
                    },
                )

    try:
        new_entry = ProjectStore().update(
            name,
            vault_root=new_vault,
            cwd_patterns=new_patterns,
            add_cwd_patterns=add_patterns,
            remove_cwd_patterns=remove_patterns,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(
            404, detail={"error": "not_found", "name": name}
        ) from exc

    if (
        daemon is not None
        and name in daemon.runtimes
        and new_vault is not None
        and daemon.runtimes[name].vault_root != new_entry.vault_root
    ):
        from claude_mnemos.daemon.vault_runtime import VaultMountError

        try:
            await daemon.remount_vault(new_entry)
        except VaultMountError as exc:
            raise HTTPException(
                500,
                detail={
                    "error": "remount_failed",
                    "detail": str(exc),
                    "hint": "project-map is updated; restart daemon if "
                            "auto-remount keeps failing",
                },
            ) from exc
    return new_entry.model_dump(mode="json")
