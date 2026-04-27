"""Project map: ~/.claude-mnemos/project-map.json — cwd→vault routing.

Single-owner state-file (per spec §10.1): writes go through ``ProjectStore``
guarded by an in-process lock; reads happen anywhere via ``ProjectMap``
loaded fresh from disk.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_mnemos.core.atomic import atomic_write

HOME_CONFIG_DIRNAME = ".claude-mnemos"
PROJECT_MAP_FILENAME = "project-map.json"
SETTINGS_DIRNAME = "settings"

PROJECT_NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"


def home_config_dir() -> Path:
    return Path.home() / HOME_CONFIG_DIRNAME


def project_map_path() -> Path:
    return home_config_dir() / PROJECT_MAP_FILENAME


def project_settings_path(name: str) -> Path:
    return home_config_dir() / SETTINGS_DIRNAME / f"{name}.json"


class ProjectMapError(Exception):
    """Base for project-map errors."""


class ProjectMapCorruptError(ProjectMapError):
    """Raised when project-map.json cannot be parsed."""


class ProjectNotFoundError(ProjectMapError):
    """Raised when a project name is not in the map."""


class ProjectNameConflictError(ProjectMapError):
    """Raised when adding a project with a name that already exists."""


class ProjectMapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=PROJECT_NAME_PATTERN)
    vault_root: Path
    cwd_patterns: list[str] = Field(default_factory=list)


class ProjectMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    projects: list[ProjectMapEntry] = Field(default_factory=list)


class ProjectStore:
    """Owns writes to project-map.json. Reads are atomic via fresh load each call."""

    def __init__(self, map_path: Path | None = None) -> None:
        self._path = map_path if map_path is not None else project_map_path()
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> ProjectMap:
        if not self._path.exists():
            return ProjectMap()
        try:
            raw = self._path.read_text(encoding="utf-8")
            return ProjectMap.model_validate_json(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProjectMapCorruptError(
                f"project-map at {self._path} is corrupt: {exc}"
            ) from exc

    def _save(self, pm: ProjectMap) -> None:
        atomic_write(self._path, json.dumps(pm.model_dump(mode="json"), indent=2))

    def list_all(self) -> list[ProjectMapEntry]:
        return list(self._load().projects)

    def get(self, name: str) -> ProjectMapEntry:
        for e in self._load().projects:
            if e.name == name:
                return e
        raise ProjectNotFoundError(f"project {name!r} not found in project-map")

    def add(self, entry: ProjectMapEntry) -> ProjectMapEntry:
        with self._lock:
            pm = self._load()
            if any(e.name == entry.name for e in pm.projects):
                raise ProjectNameConflictError(
                    f"project name {entry.name!r} already exists"
                )
            pm.projects.append(entry)
            self._save(pm)
            return entry

    def update(
        self,
        name: str,
        *,
        vault_root: Path | None = None,
        cwd_patterns: list[str] | None = None,
    ) -> ProjectMapEntry:
        with self._lock:
            pm = self._load()
            for i, e in enumerate(pm.projects):
                if e.name == name:
                    new_e = e.model_copy(
                        update={
                            "vault_root": vault_root if vault_root is not None else e.vault_root,
                            "cwd_patterns": (
                                cwd_patterns if cwd_patterns is not None else e.cwd_patterns
                            ),
                        }
                    )
                    pm.projects[i] = new_e
                    self._save(pm)
                    return new_e
            raise ProjectNotFoundError(f"project {name!r} not found")

    def remove(self, name: str) -> None:
        with self._lock:
            pm = self._load()
            new_projects = [e for e in pm.projects if e.name != name]
            if len(new_projects) == len(pm.projects):
                raise ProjectNotFoundError(f"project {name!r} not found")
            pm.projects = new_projects
            self._save(pm)
            # Cleanup orphan settings file
            sf = project_settings_path(name)
            sf.unlink(missing_ok=True)
