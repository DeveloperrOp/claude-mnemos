"""Project + global settings persistence under ~/.claude-mnemos/.

Per spec §12.8, nine setting groups go into per-project files
``~/.claude-mnemos/settings/<name>.json``; defaults live in
``~/.claude-mnemos/global-settings.json``. Daemon and CLI consume them
through ``SettingsStore``; daemon owns writes (single-owner per spec
§10.1), CLI reads pass through.
"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.state.projects import (
    SETTINGS_DIRNAME,
    home_config_dir,
)

GLOBAL_SETTINGS_FILENAME = "global-settings.json"


def global_settings_path() -> Path:
    return home_config_dir() / GLOBAL_SETTINGS_FILENAME


class SettingsError(Exception):
    """Base for settings errors."""


class SettingsCorruptError(SettingsError):
    """Raised when a settings JSON file cannot be parsed."""


class AutoIngestSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    mode: Literal["auto", "hybrid", "manual"] = "auto"


class LintSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schedule: str | None = None
    enabled_rules: list[str] | None = None
    autofix_on_save: bool = False


class OntologySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_mode: bool = False
    confidence_min: float = Field(default=0.7, ge=0.0, le=1.0)
    confidence_auto_apply: float = Field(default=0.95, ge=0.0, le=1.0)


class WatchdogSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["strict", "merge", "open"] = "merge"


class SnapshotsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_enabled: bool = True
    retention_days: int = Field(default=180, ge=1)


class LifecycleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_stale_days: int = Field(default=90, ge=1)
    auto_archive: bool = False


class PromptsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    custom_system_path: str | None = None
    custom_extract_user_path: str | None = None


class TelemetrySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opt_in: bool = False


class IngestOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str | None = None
    language_hint: Literal["auto", "uk", "ru", "en"] | None = None
    max_input_tokens: int | None = None
    context_limit: int | None = None


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    locale: Literal["uk", "ru", "en"] | None = None
    auto_ingest: AutoIngestSettings = Field(default_factory=AutoIngestSettings)
    lint: LintSettings = Field(default_factory=LintSettings)
    ontology: OntologySettings = Field(default_factory=OntologySettings)
    watchdog: WatchdogSettings = Field(default_factory=WatchdogSettings)
    snapshots: SnapshotsSettings = Field(default_factory=SnapshotsSettings)
    lifecycle: LifecycleSettings = Field(default_factory=LifecycleSettings)
    prompts: PromptsSettings = Field(default_factory=PromptsSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    ingest: IngestOverrides = Field(default_factory=IngestOverrides)


class GlobalSettings(BaseModel):
    # extra="ignore": forward-compat — silently absorbs β1 files with primary_project.
    model_config = ConfigDict(extra="ignore")
    version: Literal[1] = 1
    locale: Literal["uk", "ru", "en"] = "uk"
    daemon_port: int = Field(default=5757, ge=1, le=65535)
    default_model: str = "claude-sonnet-4-6"
    default_language_hint: Literal["auto", "uk", "ru", "en"] = "auto"
    default_max_input_tokens: int = Field(default=150_000, ge=1024)
    default_retention_days: int = Field(default=180, ge=1)
    # primary_project removed in β2.


def get_by_dot_path(obj: BaseModel, key: str) -> Any:
    cur: Any = obj
    for part in key.split("."):
        cur = getattr(cur, part)
    return cur


def patch_dict_for_dot_path(key: str, value: Any) -> dict[str, Any]:
    parts = key.split(".")
    result: dict[str, Any] = {}
    cur: dict[str, Any] = result
    for p in parts[:-1]:
        cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value
    return result


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Return new dict where ``patch`` is merged into ``base``.

    Nested dicts merge recursively; non-dict values (incl. lists) are
    replaced. Inputs not mutated.
    """
    out = deepcopy(base)
    for k, v in patch.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


# Module-level locks shared by all SettingsStore instances pointing at the
# same root directory (mirrors projects.py pattern).
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(root: Path) -> threading.Lock:
    key = str(Path(root).expanduser().resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


class SettingsStore:
    """Owns writes to per-project + global settings JSON files.

    ``root`` is the directory holding ``settings/<name>.json`` and
    ``global-settings.json``. Defaults to ``~/.claude-mnemos/``.
    """

    def __init__(self, root: Path | None = None) -> None:
        if root is not None:
            self._root = root
        else:
            self._root = home_config_dir()
        self._settings_dir = self._root / SETTINGS_DIRNAME
        self._global_path = self._root / GLOBAL_SETTINGS_FILENAME
        self._lock = _lock_for(self._root)

    @property
    def settings_dir(self) -> Path:
        return self._settings_dir

    @property
    def global_path(self) -> Path:
        return self._global_path

    def _project_file(self, name: str) -> Path:
        return self._settings_dir / f"{name}.json"

    def get_project(self, name: str) -> ProjectSettings:
        path = self._project_file(name)
        if not path.exists():
            return ProjectSettings()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SettingsCorruptError(
                f"project settings at {path} unreadable: {exc}"
            ) from exc
        try:
            return ProjectSettings.model_validate_json(raw)
        except json.JSONDecodeError as exc:
            raise SettingsCorruptError(
                f"project settings at {path} not valid JSON: {exc}"
            ) from exc
        except ValidationError as exc:
            raise SettingsCorruptError(
                f"project settings at {path} fail schema: {exc}"
            ) from exc

    def patch_project(self, name: str, partial: dict[str, Any]) -> ProjectSettings:
        with self._lock:
            current = self.get_project(name)
            merged = deep_merge(current.model_dump(mode="json"), partial)
            validated = ProjectSettings.model_validate(merged)
            self._settings_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(
                self._project_file(name),
                json.dumps(validated.model_dump(mode="json"), indent=2) + "\n",
            )
            return validated

    def reset_project(self, name: str) -> None:
        with self._lock:
            self._project_file(name).unlink(missing_ok=True)

    def get_global(self) -> GlobalSettings:
        if not self._global_path.exists():
            return GlobalSettings()
        try:
            raw = self._global_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SettingsCorruptError(
                f"global settings at {self._global_path} unreadable: {exc}"
            ) from exc
        try:
            return GlobalSettings.model_validate_json(raw)
        except json.JSONDecodeError as exc:
            raise SettingsCorruptError(
                f"global settings at {self._global_path} not valid JSON: {exc}"
            ) from exc
        except ValidationError as exc:
            raise SettingsCorruptError(
                f"global settings at {self._global_path} fail schema: {exc}"
            ) from exc

    def patch_global(self, partial: dict[str, Any]) -> GlobalSettings:
        with self._lock:
            current = self.get_global()
            merged = deep_merge(current.model_dump(mode="json"), partial)
            validated = GlobalSettings.model_validate(merged)
            self._global_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(
                self._global_path,
                json.dumps(validated.model_dump(mode="json"), indent=2) + "\n",
            )
            return validated

    def set_global(self, settings: GlobalSettings) -> GlobalSettings:
        """Overwrite the global settings file with *settings* (full replace)."""
        with self._lock:
            self._global_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(
                self._global_path,
                json.dumps(settings.model_dump(mode="json"), indent=2) + "\n",
            )
            return settings

    def reset_global(self) -> None:
        with self._lock:
            self._global_path.unlink(missing_ok=True)
