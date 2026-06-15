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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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
    """Per-project ingest automation toggles.

    Three independent yes/no decisions, all default OFF (manual). Override the
    same-named fields on ``GlobalSettings.auto_ingest_defaults`` per-project,
    or leave them as ``None`` to inherit the global default.

    Why three booleans, not one mode enum:
      - dump_on_session_end (cheap, 0 tokens) and extract_after_dump
        ($$$ tokens via ``claude -p``) are different cost classes and users
        sensibly want them controlled independently.
      - dump_stale_after_24h is a safety net that fires on a different
        timer (cron) and should be opt-in separately from the per-/exit hook.
    """
    # extra="ignore" silently absorbs legacy v0.0.9 fields (`enabled`,
    # `mode`) from old on-disk JSON — dropped in v0.0.31 because they
    # were never read by any code path. The three real toggles below are
    # tri-state; None = inherit from GlobalSettings.auto_ingest_defaults.
    model_config = ConfigDict(extra="ignore")
    dump_on_session_end: bool | None = None
    dump_stale_after_24h: bool | None = None
    extract_after_dump: bool | None = None


class AutoIngestDefaults(BaseModel):
    """Global defaults for ``AutoIngestSettings`` — applied to any project
    that doesn't override a given field.

    Defaults rationale (per user policy):
      * ``dump_*`` = True: copying the .jsonl into the project vault is free
        (no LLM, just file IO) and saves the user from manual import for
        every session. The user can still flip it off per-project if they
        truly want zero auto-writes.
      * ``extract_after_dump`` = False: LLM extraction is the only step that
        consumes subscription tokens / hits rate limits — must be opt-in.
    """
    model_config = ConfigDict(extra="forbid")
    dump_on_session_end: bool = True
    dump_stale_after_24h: bool = True
    extract_after_dump: bool = False


class LintSettings(BaseModel):
    # extra="ignore" so legacy on-disk settings keep loading after fields
    # are dropped. `autofix_on_save` (dropped v0.0.31) was placebo — no
    # daemon code ever read it; users could still run autofix manually
    # from the Lint page.
    model_config = ConfigDict(extra="ignore")
    schedule: str | None = None
    enabled_rules: list[str] | None = None


SnapshotSchedule = Literal["off", "daily", "weekly", "monthly"]


class SnapshotsSettings(BaseModel):
    # extra="forbid" keeps schema tight, but a model_validator below first
    # migrates the legacy v0.0.38 `daily_enabled` boolean so old on-disk
    # files keep loading instead of tripping the forbid rule.
    model_config = ConfigDict(extra="forbid")
    # v0.0.39: `daily_enabled: bool` → `schedule` preset. The job always
    # produces a `daily-<date>` snapshot; the preset only controls how
    # often the scheduler fires it ("off" = no automatic snapshots).
    schedule: SnapshotSchedule = "daily"
    retention_days: int = Field(default=180, ge=1)

    @model_validator(mode="before")
    @classmethod
    def _migrate_daily_enabled(cls, data: Any) -> Any:
        """Convert the legacy `daily_enabled` boolean to `schedule`.

        v0.0.38- on-disk files store ``daily_enabled: true|false``. Pop it
        before field validation (extra="forbid" would otherwise reject it)
        and map True→"daily", False→"off". An explicit ``schedule`` already
        present in the payload always wins.
        """
        if isinstance(data, dict) and "daily_enabled" in data:
            data = dict(data)
            legacy = data.pop("daily_enabled")
            data.setdefault("schedule", "daily" if legacy else "off")
        return data


class ProjectSettings(BaseModel):
    # extra="ignore": forward-compat — silently absorbs old v0.0.11- groups
    # (watchdog/ontology/lifecycle/prompts/telemetry/ingest, dropped v0.0.12)
    # and the per-project `locale` (dropped v0.0.31 — locale is global-only).
    model_config = ConfigDict(extra="ignore")
    version: Literal[1] = 1
    auto_ingest: AutoIngestSettings = Field(default_factory=AutoIngestSettings)
    lint: LintSettings = Field(default_factory=LintSettings)
    snapshots: SnapshotsSettings = Field(default_factory=SnapshotsSettings)


class GlobalSettings(BaseModel):
    # extra="ignore": forward-compat — silently absorbs β1 files with primary_project.
    model_config = ConfigDict(extra="ignore")
    version: Literal[1] = 1
    locale: Literal["uk", "ru", "en"] = "uk"
    daemon_port: int = Field(default=5757, ge=1, le=65535)
    default_model: str = "claude-sonnet-4-6"
    default_language_hint: Literal["auto", "uk", "ru", "en"] = "auto"
    default_max_input_tokens: int = Field(default=800_000, ge=1024)
    default_retention_days: int = Field(default=180, ge=1)
    # primary_project removed in β2.
    # v0.0.10: defaults for ProjectSettings.auto_ingest. All three are
    # opt-in (default OFF) so a fresh install never copies transcripts into
    # a vault or burns LLM tokens without an explicit user toggle.
    auto_ingest_defaults: AutoIngestDefaults = Field(default_factory=AutoIngestDefaults)


def resolve_ingest_flags(
    project: ProjectSettings | None,
    glob: GlobalSettings,
) -> tuple[bool, bool, bool]:
    """Resolve the effective (dump_on_session_end, dump_stale_after_24h,
    extract_after_dump) tuple for a project.

    Per-field override precedence: project-level non-None wins; else fall
    back to ``glob.auto_ingest_defaults``. ``project=None`` (e.g. a hook
    with no project context) reads the globals only.

    Used by hooks/session_end, core/auto_dump, and the ingest job worker
    so a single source of truth controls when things actually run.
    """
    pi = project.auto_ingest if project is not None else None
    defaults = glob.auto_ingest_defaults
    dump_exit = (
        pi.dump_on_session_end
        if pi is not None and pi.dump_on_session_end is not None
        else defaults.dump_on_session_end
    )
    dump_stale = (
        pi.dump_stale_after_24h
        if pi is not None and pi.dump_stale_after_24h is not None
        else defaults.dump_stale_after_24h
    )
    extract = (
        pi.extract_after_dump
        if pi is not None and pi.extract_after_dump is not None
        else defaults.extract_after_dump
    )
    return dump_exit, dump_stale, extract


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
            raw = path.read_text(encoding="utf-8-sig")  # tolerate BOM
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
            raw = self._global_path.read_text(encoding="utf-8-sig")  # tolerate BOM
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
