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

# Trailing-wildcard suffixes the resolver recognises (see mapping/resolver.py).
# Order matters: longer suffixes first, otherwise stripping `\*` from `\**`
# loses information.
_CWD_SUFFIXES: tuple[str, ...] = ("\\**", "/**", "\\*", "/*")


def _cwd_base(pattern: str) -> tuple[str, str | None]:
    """Split a pattern into (base, suffix). Suffix is one of _CWD_SUFFIXES or None."""
    for suffix in _CWD_SUFFIXES:
        if pattern.endswith(suffix):
            return pattern[: -len(suffix)], suffix
    return pattern, None


def _dedupe_cwd_patterns(patterns: list[str]) -> list[str]:
    """Collapse the legacy [base, base/*, base/**] triplet produced by the
    Onboarding wizard into a single recursive entry. When multiple forms of
    the same base coexist, the recursive form wins (resolver already treats
    \\*, \\**, and the bare path identically as 'this folder and below').

    A base with only one form is left untouched so we don't override a
    user's deliberate choice. Exact duplicates are always removed.
    """
    by_base: dict[str, set[str]] = {}
    order: list[str] = []
    for p in patterns:
        base, suffix = _cwd_base(p)
        if base not in by_base:
            by_base[base] = set()
            order.append(base)
        by_base[base].add(suffix or "plain")
    out: list[str] = []
    for base in order:
        forms = by_base[base]
        # Two-or-more-forms case: artefact of the old Onboarding triplet —
        # collapse to recursive `\**` (or `/**` for posix bases).
        if len(forms) > 1 or "\\**" in forms or "/**" in forms:
            sep = "\\" if "\\" in base else "/"
            out.append(f"{base}{sep}**")
        elif "\\*" in forms or "/*" in forms:
            sep = "\\" if "\\" in base else "/"
            out.append(f"{base}{sep}*")
        else:
            out.append(base)
    return out


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
    display_name: str | None = None
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
        return [self._canonicalize(e) for e in self._load().projects]

    def get(self, name: str) -> ProjectMapEntry:
        for e in self._load().projects:
            if e.name == name:
                return self._canonicalize(e)
        raise ProjectNotFoundError(f"project {name!r} not found in project-map")

    @staticmethod
    def _canonicalize(e: ProjectMapEntry) -> ProjectMapEntry:
        """Collapse legacy cwd_patterns triplets on read. File-on-disk stays
        as-is; users running PATCH /projects/{name} with new patterns store
        the new list verbatim."""
        canon = _dedupe_cwd_patterns(e.cwd_patterns)
        if canon == e.cwd_patterns:
            return e
        return e.model_copy(update={"cwd_patterns": canon})

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
        display_name: str | None = None,
    ) -> ProjectMapEntry:
        """Update fields of an existing entry.

        ``None`` means "leave unchanged". Pass ``cwd_patterns=[]`` to clear
        all patterns. Raises ``ProjectNotFoundError`` if name absent.

        ``cwd_patterns`` is a full replace.
        ``add_cwd_patterns`` appends entries (preserving order, deduplicating).
        ``remove_cwd_patterns`` removes specific entries.
        Caller should pass either ``cwd_patterns`` OR ``add``/``remove``, not both.
        ``display_name`` semantics: leave ``None`` to keep current value;
        pass an empty string ``""`` to clear it back to ``None``; any other
        non-empty string sets the new value. (Empty string as "clear" is a
        pragmatic API convention since JSON has no Optional[Optional[T]] —
        callers wanting to clear it just send an empty string.)
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
                    if display_name is None:
                        new_display = e.display_name
                    elif display_name == "":
                        new_display = None
                    else:
                        new_display = display_name
                    new_e = e.model_copy(
                        update={
                            "vault_root": vault_root if vault_root is not None else e.vault_root,
                            "cwd_patterns": new_patterns,
                            "display_name": new_display,
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
