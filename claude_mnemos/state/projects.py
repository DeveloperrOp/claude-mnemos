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

# Max 64 chars: 1 (leading [a-z0-9]) + 63 (tail [a-z0-9_-]).
PROJECT_NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"


_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(Path(path).expanduser().resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


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
        self._lock = _lock_for(self._path)

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> ProjectMap:
        if not self._path.exists():
            return ProjectMap()
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProjectMapCorruptError(
                f"project-map at {self._path} unreadable: {exc}"
            ) from exc
        try:
            return ProjectMap.model_validate_json(raw)
        except json.JSONDecodeError as exc:
            raise ProjectMapCorruptError(
                f"project-map at {self._path} is not valid JSON: {exc}"
            ) from exc
        except ValidationError as exc:
            raise ProjectMapCorruptError(
                f"project-map at {self._path} fails schema: {exc}"
            ) from exc

    def _save(self, pm: ProjectMap) -> None:
        atomic_write(
            self._path,
            json.dumps(pm.model_dump(mode="json"), indent=2) + "\n",
        )

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
        add_cwd_patterns: list[str] | None = None,
        remove_cwd_patterns: list[str] | None = None,
    ) -> ProjectMapEntry:
        """Update fields of an existing entry.

        ``None`` means "leave unchanged". Pass ``cwd_patterns=[]`` to clear
        all patterns. Raises ``ProjectNotFoundError`` if name absent.

        ``cwd_patterns`` is a full replace.
        ``add_cwd_patterns`` appends entries (preserving order, deduplicating).
        ``remove_cwd_patterns`` removes specific entries.
        Caller should pass either ``cwd_patterns`` OR ``add``/``remove``, not both.
        """
        with self._lock:
            pm = self._load()
            for i, e in enumerate(pm.projects):
                if e.name == name:
                    new_patterns = list(e.cwd_patterns)
                    if cwd_patterns is not None:
                        new_patterns = cwd_patterns
                    else:
                        if add_cwd_patterns:
                            existing = list(new_patterns)
                            for p in add_cwd_patterns:
                                if p not in existing:
                                    existing.append(p)
                            new_patterns = existing
                        if remove_cwd_patterns:
                            remove_set = set(remove_cwd_patterns)
                            new_patterns = [p for p in new_patterns if p not in remove_set]
                    new_e = e.model_copy(
                        update={
                            "vault_root": vault_root if vault_root is not None else e.vault_root,
                            "cwd_patterns": new_patterns,
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
            # Orphan settings file is preferred over a map entry without data.
            # If unlink fails (e.g. PermissionError), the map is already updated;
            # orphan will be overwritten on next add() with the same name.
            sf.unlink(missing_ok=True)
