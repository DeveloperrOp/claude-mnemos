"""REST routes for project-map CRUD + combined ProjectView."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
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


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vault_root: Path | None = None
    cwd_patterns: list[str] | None = None


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


@router.get("/api/projects", response_model=list[ProjectMapEntry])
def list_projects() -> list[ProjectMapEntry]:
    return _store().list_all()


@router.get("/api/projects/{name}", response_model=ProjectView)
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


@router.post("/api/projects", response_model=ProjectMapEntry, status_code=201)
def create_project(body: ProjectCreate) -> ProjectMapEntry:
    entry = ProjectMapEntry(
        name=body.name,
        vault_root=body.vault_root,
        cwd_patterns=body.cwd_patterns,
    )
    try:
        return _store().add(entry)
    except ProjectNameConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "name_conflict", "name": body.name},
        ) from exc


@router.patch("/api/projects/{name}", response_model=ProjectMapEntry)
def update_project(name: str, body: ProjectUpdate) -> ProjectMapEntry:
    try:
        return _store().update(
            name,
            vault_root=body.vault_root,
            cwd_patterns=body.cwd_patterns,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "name": name},
        ) from exc


@router.delete("/api/projects/{name}", status_code=204)
def delete_project(name: str) -> None:
    try:
        _store().remove(name)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "name": name},
        ) from exc
