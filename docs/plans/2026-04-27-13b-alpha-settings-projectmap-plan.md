# Settings + project-map foundation Implementation Plan (Plan #13b-α)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** Build `~/.claude-mnemos/project-map.json` (cwd → vault routing) + per-project + global settings persistence, with REST/CLI/plugin/hook/MCP integration. Daemon stays single-vault but becomes settings-aware for its own vault.

**Architecture:** Two new state stores (`ProjectStore` over `project-map.json`, `SettingsStore` over `settings/<name>.json` + `global-settings.json`). `ProjectResolver` does cwd → entry lookup via fnmatch glob + most-specific-wins. Two new REST routers (`/api/projects/*`, `/api/settings/*`). Two new CLI subgroups (`mnemos project`, `mnemos settings`). All existing CLI subgroups migrate from `--vault PATH` (env-fallback `MNEMOS_VAULT_ROOT`) to `--project NAME` (auto-resolve from cwd if omitted). Hard-cut on the `MNEMOS_VAULT_ROOT` env var. `MnemosDaemon` reads its own vault's `ProjectSettings` at startup, applies `snapshots.retention_days` + `snapshots.daily_enabled` to the scheduler, and reloads on PATCH.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest. No new third-party deps.

**Design doc:** `docs/plans/2026-04-27-13b-alpha-settings-projectmap-design.md` — read before starting each task.

---

## Files map

**Create:**
- `claude_mnemos/state/projects.py` — `ProjectMapEntry`, `ProjectMap`, `ProjectStore`, exceptions
- `claude_mnemos/state/settings.py` — 9 settings group models + `ProjectSettings` + `GlobalSettings` + `SettingsStore` + dot-path helpers + exceptions
- `claude_mnemos/mapping/__init__.py`
- `claude_mnemos/mapping/resolver.py` — `ProjectResolver`
- `claude_mnemos/daemon/routes/projects.py`
- `claude_mnemos/daemon/routes/settings.py`
- `tests/state/test_projects.py`
- `tests/state/test_settings.py`
- `tests/mapping/__init__.py`
- `tests/mapping/test_resolver.py`
- `tests/daemon/test_routes_projects.py`
- `tests/daemon/test_routes_settings.py`
- `tests/daemon/test_settings_consumption.py`
- `tests/test_cli_project.py`
- `tests/test_cli_settings.py`
- `tests/hooks/__init__.py`
- `tests/hooks/test_session_end_resolver.py`
- `tests/test_pid_file_migration.py`
- `tests/e2e/test_project_settings_e2e.py`

**Modify:**
- `claude_mnemos/daemon/config.py` — `default_pid_file()` and `default_runtime_config_file()` return `~/.claude-mnemos/...`; one-shot migration helper
- `claude_mnemos/daemon/process.py` — load project_settings at init, reload method, build_scheduler call
- `claude_mnemos/daemon/scheduler.py` — accept `snapshots_enabled` parameter
- `claude_mnemos/daemon/app.py` — register new routers + exception handlers
- `claude_mnemos/cli.py` — two new subgroups, all existing `--vault` flags migrate to `--project`, env hard-cut
- `claude_mnemos/mcp/__main__.py` — argparse: mutually-exclusive `--auto-resolve` / `--project` / `--vault`; degraded server when no match
- `claude_mnemos/mcp/config.py` — accept `vault_root: Path | None` for degraded server
- `hooks/session_end.py` — resolve cwd via `ProjectResolver` instead of `MNEMOS_VAULT_ROOT`
- `.mcp.json` — `args` becomes `["-m", "claude_mnemos.mcp", "--auto-resolve"]`
- `tests/test_cli.py`, `tests/test_cli_*.py`, `tests/daemon/*` — all fixtures that use `MNEMOS_VAULT_ROOT` env or `--vault PATH` migrate to `register_project()` conftest fixture
- `tests/conftest.py` — add `register_project` fixture, monkeypatch HOME to tmp
- `tests/daemon/test_lockfile.py` — update to new PID path
- `README.md` — Plan #13b-α status section + migration instructions
- `pyproject.toml` (no version bump in this plan; happens at release time)

**Delete:**
- (none)

---

## Task 1: state/projects.py — `ProjectMap` models, exceptions, `ProjectStore`

**Files:**
- Create: `claude_mnemos/state/projects.py`
- Create: `tests/state/test_projects.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/state/test_projects.py
from __future__ import annotations
from pathlib import Path
import json
import pytest
from pydantic import ValidationError
from claude_mnemos.state.projects import (
    ProjectMapEntry, ProjectMap, ProjectStore,
    ProjectMapCorruptError, ProjectNotFoundError, ProjectNameConflictError,
    HOME_CONFIG_DIRNAME, PROJECT_MAP_FILENAME,
)


def _project_map_path(home: Path) -> Path:
    return home / HOME_CONFIG_DIRNAME / PROJECT_MAP_FILENAME


def test_project_map_entry_valid_name():
    e = ProjectMapEntry(name="claude-mnemos", vault_root=Path("/v"), cwd_patterns=["~/code/cm*"])
    assert e.name == "claude-mnemos"


@pytest.mark.parametrize("bad", ["", "A-B", "_x", "1@", "имя", "x" * 65])
def test_project_map_entry_rejects_bad_name(bad):
    with pytest.raises(ValidationError):
        ProjectMapEntry(name=bad, vault_root=Path("/v"), cwd_patterns=[])


def test_project_map_entry_rejects_extra_field():
    with pytest.raises(ValidationError):
        ProjectMapEntry(
            name="ok", vault_root=Path("/v"), cwd_patterns=[], stranger="x",
        )


def test_project_map_default_empty():
    pm = ProjectMap()
    assert pm.version == 1
    assert pm.projects == []


def test_project_map_round_trip(tmp_path: Path):
    pm = ProjectMap(projects=[
        ProjectMapEntry(name="a", vault_root=tmp_path / "va", cwd_patterns=["~/a*"]),
    ])
    p = tmp_path / "project-map.json"
    p.write_text(json.dumps(pm.model_dump(mode="json")))
    loaded = ProjectMap.model_validate_json(p.read_text())
    assert loaded.projects[0].name == "a"


def test_store_add_creates_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
    store = ProjectStore()
    e = ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=["~/x*"])
    store.add(e)
    f = _project_map_path(tmp_path)
    assert f.is_file()
    data = json.loads(f.read_text())
    assert data["projects"][0]["name"] == "x"


def test_store_add_duplicate_name_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    e = ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=[])
    store.add(e)
    with pytest.raises(ProjectNameConflictError):
        store.add(e)


def test_store_get_missing_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    with pytest.raises(ProjectNotFoundError):
        store.get("nope")


def test_store_update_partial(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    e = ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=["~/x"])
    store.add(e)
    updated = store.update("x", cwd_patterns=["~/y"])
    assert updated.cwd_patterns == ["~/y"]
    assert updated.vault_root == tmp_path / "vx"


def test_store_remove_removes_entry(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    store.add(ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=[]))
    store.remove("x")
    with pytest.raises(ProjectNotFoundError):
        store.get("x")


def test_store_remove_cleans_settings_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    store.add(ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=[]))
    settings_dir = tmp_path / HOME_CONFIG_DIRNAME / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / "x.json"
    settings_file.write_text("{}")
    store.remove("x")
    assert not settings_file.exists()


def test_corrupt_json_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    f = _project_map_path(tmp_path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{not json")
    store = ProjectStore()
    with pytest.raises(ProjectMapCorruptError):
        store.list_all()


def test_missing_file_returns_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = ProjectStore()
    assert store.list_all() == []
```

- [ ] **Step 2: Run tests, confirm fail (module not found)**

```
pytest tests/state/test_projects.py -v
```
Expected: collection error / ImportError.

- [ ] **Step 3: Implement `claude_mnemos/state/projects.py`**

```python
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
```

- [ ] **Step 4: Create `tests/state/__init__.py` if missing, run tests pass**

```
pytest tests/state/test_projects.py -v
```
Expected: all green.

- [ ] **Step 5: ruff + mypy**

```
ruff check claude_mnemos/state/projects.py tests/state/test_projects.py
mypy --strict claude_mnemos/state/projects.py
```

- [ ] **Step 6: Commit**

```
git add claude_mnemos/state/projects.py tests/state/test_projects.py tests/state/__init__.py
git commit -m "feat(state): project-map.json store + ProjectMapEntry/ProjectMap models

Plan #13b-α Task 1. Adds claude_mnemos/state/projects.py with:
- ProjectMapEntry (name validated against [a-z0-9][a-z0-9_-]{0,63})
- ProjectMap container (version=1, projects: list)
- ProjectStore: thread-safe atomic CRUD over ~/.claude-mnemos/project-map.json
- Exceptions: ProjectMapCorruptError, ProjectNotFoundError, ProjectNameConflictError
- Path helpers: home_config_dir, project_map_path, project_settings_path
- Remove cleans up orphan settings/<name>.json file
"
```

---

## Task 2: state/settings.py — settings models, store, dot-path helpers

**Files:**
- Create: `claude_mnemos/state/settings.py`
- Create: `tests/state/test_settings.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/state/test_settings.py
from __future__ import annotations
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from claude_mnemos.state.settings import (
    ProjectSettings, GlobalSettings,
    AutoIngestSettings, LintSettings, OntologySettings, WatchdogSettings,
    SnapshotsSettings, LifecycleSettings, PromptsSettings, TelemetrySettings,
    IngestOverrides,
    SettingsStore, SettingsCorruptError,
    get_by_dot_path, patch_dict_for_dot_path, deep_merge,
)


def test_project_settings_defaults():
    s = ProjectSettings()
    assert s.version == 1
    assert s.locale is None
    assert s.auto_ingest.enabled is True
    assert s.auto_ingest.mode == "auto"
    assert s.lint.enabled_rules is None
    assert s.snapshots.daily_enabled is True
    assert s.snapshots.retention_days == 180
    assert s.lifecycle.auto_stale_days == 90
    assert s.telemetry.opt_in is False


def test_global_settings_defaults():
    g = GlobalSettings()
    assert g.locale == "uk"
    assert g.daemon_port == 5757
    assert g.default_model == "claude-sonnet-4-6"


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        ProjectSettings.model_validate({"foo": "bar"})
    with pytest.raises(ValidationError):
        AutoIngestSettings(enabled=True, mode="auto", extra="x")


def test_round_trip_json():
    s = ProjectSettings(
        locale="ru",
        auto_ingest=AutoIngestSettings(enabled=False, mode="manual"),
    )
    js = s.model_dump_json()
    loaded = ProjectSettings.model_validate_json(js)
    assert loaded.auto_ingest.enabled is False
    assert loaded.locale == "ru"


def test_get_by_dot_path():
    s = ProjectSettings()
    assert get_by_dot_path(s, "lint.enabled_rules") is None
    assert get_by_dot_path(s, "snapshots.retention_days") == 180
    assert get_by_dot_path(s, "auto_ingest.mode") == "auto"
    assert get_by_dot_path(s, "lint") == s.lint


def test_get_by_dot_path_missing():
    s = ProjectSettings()
    with pytest.raises(AttributeError):
        get_by_dot_path(s, "nope")
    with pytest.raises(AttributeError):
        get_by_dot_path(s, "lint.no_such_field")


def test_patch_dict_for_dot_path_simple():
    assert patch_dict_for_dot_path("lint.schedule", "* * * * *") == {
        "lint": {"schedule": "* * * * *"}
    }


def test_patch_dict_for_dot_path_nested_three():
    assert patch_dict_for_dot_path("a.b.c", 42) == {"a": {"b": {"c": 42}}}


def test_deep_merge_basic():
    a = {"x": 1, "y": {"z": 2}}
    b = {"y": {"w": 3}}
    assert deep_merge(a, b) == {"x": 1, "y": {"z": 2, "w": 3}}


def test_deep_merge_overrides_scalar():
    a = {"x": {"y": 1}}
    b = {"x": {"y": 2}}
    assert deep_merge(a, b) == {"x": {"y": 2}}


def test_deep_merge_replaces_lists():
    a = {"x": [1, 2]}
    b = {"x": [3]}
    assert deep_merge(a, b) == {"x": [3]}


def test_settings_store_get_project_returns_defaults_if_missing(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    s = store.get_project("missing")
    assert s == ProjectSettings()


def test_settings_store_patch_project_persists(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    updated = store.patch_project("foo", {"auto_ingest": {"enabled": False}})
    assert updated.auto_ingest.enabled is False
    f = tmp_path / "settings" / "foo.json"
    assert f.is_file()
    data = json.loads(f.read_text())
    assert data["auto_ingest"]["enabled"] is False


def test_settings_store_patch_partial_preserves_others(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    store.patch_project("foo", {"snapshots": {"retention_days": 30}})
    updated = store.patch_project("foo", {"lint": {"autofix_on_save": True}})
    assert updated.snapshots.retention_days == 30
    assert updated.lint.autofix_on_save is True


def test_settings_store_patch_invalid_value_raises(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    with pytest.raises(ValidationError):
        store.patch_project("foo", {"snapshots": {"retention_days": -1}})


def test_settings_store_corrupt_file_raises(tmp_path: Path):
    f = tmp_path / "settings" / "bad.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{not json")
    store = SettingsStore(root=tmp_path)
    with pytest.raises(SettingsCorruptError):
        store.get_project("bad")


def test_settings_store_global_round_trip(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    g = store.patch_global({"locale": "en", "daemon_port": 6000})
    assert g.locale == "en"
    assert g.daemon_port == 6000
    g2 = store.get_global()
    assert g2.locale == "en"


def test_settings_store_global_defaults(tmp_path: Path):
    store = SettingsStore(root=tmp_path)
    assert store.get_global() == GlobalSettings()
```

- [ ] **Step 2: Run, confirm fail**

```
pytest tests/state/test_settings.py -v
```

- [ ] **Step 3: Implement `claude_mnemos/state/settings.py`**

```python
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
    HOME_CONFIG_DIRNAME, SETTINGS_DIRNAME, home_config_dir,
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
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    locale: Literal["uk", "ru", "en"] = "uk"
    daemon_port: int = Field(default=5757, ge=1, le=65535)
    default_model: str = "claude-sonnet-4-6"
    default_language_hint: Literal["auto", "uk", "ru", "en"] = "auto"
    default_max_input_tokens: int = Field(default=150_000, ge=1024)
    default_retention_days: int = Field(default=180, ge=1)


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
    """Return a new dict where ``patch`` is merged into ``base``.

    Nested dicts are merged recursively; non-dict values (including lists)
    are replaced. Inputs are not mutated.
    """
    out = deepcopy(base)
    for k, v in patch.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


class SettingsStore:
    """Owns writes to per-project + global settings JSON files."""

    def __init__(self, root: Path | None = None) -> None:
        # Tests may inject a tmp root (the directory that contains
        # ``settings/<name>.json`` and ``global-settings.json`` directly).
        # Default uses the real ~/.claude-mnemos/ layout.
        if root is not None:
            self._settings_dir = root / SETTINGS_DIRNAME
            self._global_path = root / GLOBAL_SETTINGS_FILENAME
        else:
            self._settings_dir = home_config_dir() / SETTINGS_DIRNAME
            self._global_path = global_settings_path()
        self._lock = threading.Lock()

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
            return ProjectSettings.model_validate_json(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise SettingsCorruptError(
                f"project settings at {path} are corrupt: {exc}"
            ) from exc

    def patch_project(self, name: str, partial: dict[str, Any]) -> ProjectSettings:
        with self._lock:
            current = self.get_project(name)
            merged = deep_merge(current.model_dump(mode="json"), partial)
            validated = ProjectSettings.model_validate(merged)
            self._settings_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(
                self._project_file(name),
                json.dumps(validated.model_dump(mode="json"), indent=2),
            )
            return validated

    def reset_project(self, name: str) -> None:
        with self._lock:
            self._project_file(name).unlink(missing_ok=True)

    def get_global(self) -> GlobalSettings:
        if not self._global_path.exists():
            return GlobalSettings()
        try:
            return GlobalSettings.model_validate_json(
                self._global_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            raise SettingsCorruptError(
                f"global settings at {self._global_path} are corrupt: {exc}"
            ) from exc

    def patch_global(self, partial: dict[str, Any]) -> GlobalSettings:
        with self._lock:
            current = self.get_global()
            merged = deep_merge(current.model_dump(mode="json"), partial)
            validated = GlobalSettings.model_validate(merged)
            self._global_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(
                self._global_path,
                json.dumps(validated.model_dump(mode="json"), indent=2),
            )
            return validated

    def reset_global(self) -> None:
        with self._lock:
            self._global_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests, ruff, mypy**

```
pytest tests/state/test_settings.py -v
ruff check claude_mnemos/state/settings.py tests/state/test_settings.py
mypy --strict claude_mnemos/state/settings.py
```

- [ ] **Step 5: Commit**

```
git add claude_mnemos/state/settings.py tests/state/test_settings.py
git commit -m "feat(state): per-project + global settings store with deep-merge

Plan #13b-α Task 2. Adds claude_mnemos/state/settings.py:
- 9 spec §12.8 setting groups + IngestOverrides
- ProjectSettings + GlobalSettings (version=1, extra='forbid')
- SettingsStore: atomic CRUD over ~/.claude-mnemos/settings/<name>.json
  and ~/.claude-mnemos/global-settings.json
- Helpers: get_by_dot_path, patch_dict_for_dot_path, deep_merge
- Missing project file -> defaults; corrupt -> SettingsCorruptError
- Tests cover defaults, round-trip, deep-merge edge cases, validation
"
```

---

## Task 3: mapping/resolver.py — `ProjectResolver`

**Files:**
- Create: `claude_mnemos/mapping/__init__.py`
- Create: `claude_mnemos/mapping/resolver.py`
- Create: `tests/mapping/__init__.py`
- Create: `tests/mapping/test_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/mapping/test_resolver.py
from __future__ import annotations
import json
import sys
from pathlib import Path
import pytest
from claude_mnemos.state.projects import (
    HOME_CONFIG_DIRNAME, PROJECT_MAP_FILENAME, ProjectMapEntry, ProjectMap,
)
from claude_mnemos.mapping.resolver import ProjectResolver, ResolverAmbiguityError


def _seed_map(home: Path, entries: list[ProjectMapEntry]) -> Path:
    f = home / HOME_CONFIG_DIRNAME / PROJECT_MAP_FILENAME
    f.parent.mkdir(parents=True, exist_ok=True)
    pm = ProjectMap(projects=entries)
    f.write_text(json.dumps(pm.model_dump(mode="json")))
    return f


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_resolve_by_name_hit(tmp_path: Path):
    _seed_map(tmp_path, [
        ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=[]),
    ])
    r = ProjectResolver()
    e = r.resolve_by_name("x")
    assert e is not None and e.name == "x"


def test_resolve_by_name_miss(tmp_path: Path):
    _seed_map(tmp_path, [])
    r = ProjectResolver()
    assert r.resolve_by_name("nope") is None


def test_resolve_by_vault_hit(tmp_path: Path):
    vault = tmp_path / "v"
    vault.mkdir()
    _seed_map(tmp_path, [
        ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]),
    ])
    r = ProjectResolver()
    e = r.resolve_by_vault(vault)
    assert e is not None and e.name == "x"


def test_resolve_by_cwd_no_match_returns_none(tmp_path: Path):
    _seed_map(tmp_path, [
        ProjectMapEntry(name="x", vault_root=tmp_path / "vx", cwd_patterns=["~/code/x*"]),
    ])
    r = ProjectResolver()
    assert r.resolve_by_cwd(tmp_path / "elsewhere") is None


def test_resolve_by_cwd_exact_glob_match(tmp_path: Path):
    cwd = tmp_path / "code" / "foo"
    cwd.mkdir(parents=True)
    _seed_map(tmp_path, [
        ProjectMapEntry(name="foo", vault_root=tmp_path / "v", cwd_patterns=[str(cwd)]),
    ])
    r = ProjectResolver()
    e = r.resolve_by_cwd(cwd)
    assert e is not None and e.name == "foo"


def test_resolve_by_cwd_wildcard(tmp_path: Path):
    project_dir = tmp_path / "code" / "foo-experiments"
    project_dir.mkdir(parents=True)
    _seed_map(tmp_path, [
        ProjectMapEntry(
            name="foo", vault_root=tmp_path / "v",
            cwd_patterns=[str(tmp_path / "code" / "foo*")],
        ),
    ])
    r = ProjectResolver()
    e = r.resolve_by_cwd(project_dir)
    assert e is not None and e.name == "foo"


def test_resolve_by_cwd_most_specific_wins(tmp_path: Path):
    target = tmp_path / "code" / "foo"
    target.mkdir(parents=True)
    _seed_map(tmp_path, [
        ProjectMapEntry(
            name="catchall", vault_root=tmp_path / "vall",
            cwd_patterns=[str(tmp_path / "code" / "*")],
        ),
        ProjectMapEntry(
            name="specific", vault_root=tmp_path / "vfoo",
            cwd_patterns=[str(target)],
        ),
    ])
    r = ProjectResolver()
    e = r.resolve_by_cwd(target)
    assert e is not None and e.name == "specific"


def test_resolve_by_cwd_tie_raises(tmp_path: Path):
    cwd = tmp_path / "code" / "x"
    cwd.mkdir(parents=True)
    p1 = str(tmp_path / "code" / "*")
    p2 = str(tmp_path / "code" / "x")
    # Make patterns the same length to force a real tie
    p3 = "x" * len(p1)
    p4 = "y" * len(p1)
    _seed_map(tmp_path, [
        ProjectMapEntry(name="a", vault_root=tmp_path / "va", cwd_patterns=[p3, str(cwd)]),
        ProjectMapEntry(name="b", vault_root=tmp_path / "vb", cwd_patterns=[p4, str(cwd)]),
    ])
    r = ProjectResolver()
    with pytest.raises(ResolverAmbiguityError):
        r.resolve_by_cwd(cwd)


def test_resolve_by_cwd_expanduser(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cwd = tmp_path / "x"
    cwd.mkdir()
    _seed_map(tmp_path, [
        ProjectMapEntry(name="x", vault_root=tmp_path / "v", cwd_patterns=["~/x"]),
    ])
    r = ProjectResolver()
    e = r.resolve_by_cwd(cwd)
    assert e is not None and e.name == "x"


def test_resolve_by_cwd_windows_case_insensitive(tmp_path: Path, monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Windows-only behavior")
    cwd = tmp_path / "Code" / "Foo"
    cwd.mkdir(parents=True)
    _seed_map(tmp_path, [
        ProjectMapEntry(
            name="foo", vault_root=tmp_path / "v",
            cwd_patterns=[str(tmp_path / "code" / "foo")],
        ),
    ])
    r = ProjectResolver()
    e = r.resolve_by_cwd(cwd)
    assert e is not None and e.name == "foo"


def test_resolve_by_cwd_handles_corrupt_via_exception(tmp_path: Path):
    f = tmp_path / HOME_CONFIG_DIRNAME / PROJECT_MAP_FILENAME
    f.parent.mkdir(parents=True)
    f.write_text("{invalid")
    r = ProjectResolver()
    from claude_mnemos.state.projects import ProjectMapCorruptError
    with pytest.raises(ProjectMapCorruptError):
        r.resolve_by_cwd(tmp_path / "x")
```

- [ ] **Step 2: Run, fail.**

- [ ] **Step 3: Implement `claude_mnemos/mapping/__init__.py`** — empty file.

- [ ] **Step 4: Implement `claude_mnemos/mapping/resolver.py`**

```python
"""cwd → ProjectMapEntry resolver via fnmatch + most-specific-wins.

Reads ~/.claude-mnemos/project-map.json fresh on each call (no cache in
Plan #13b-α — performance optimization deferred to #13b-β if needed).
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

from claude_mnemos.state.projects import (
    ProjectMapError, ProjectMapEntry, ProjectStore,
)


class ResolverAmbiguityError(ProjectMapError):
    """Two distinct project entries match the same cwd at the same specificity."""


def _normalize(p: str | Path) -> str:
    s = str(Path(p).expanduser().resolve())
    return s.lower() if sys.platform == "win32" else s


class ProjectResolver:
    def __init__(self, store: ProjectStore | None = None) -> None:
        self._store = store if store is not None else ProjectStore()

    def list_all(self) -> list[ProjectMapEntry]:
        return self._store.list_all()

    def resolve_by_name(self, name: str) -> ProjectMapEntry | None:
        for e in self._store.list_all():
            if e.name == name:
                return e
        return None

    def resolve_by_vault(self, vault_root: Path) -> ProjectMapEntry | None:
        target = Path(vault_root).expanduser().resolve()
        for e in self._store.list_all():
            try:
                if Path(e.vault_root).expanduser().resolve() == target:
                    return e
            except OSError:
                continue
        return None

    def resolve_by_cwd(self, cwd: Path) -> ProjectMapEntry | None:
        cwd_norm = _normalize(cwd)
        candidates: list[tuple[ProjectMapEntry, str, int]] = []
        for entry in self._store.list_all():
            for pattern in entry.cwd_patterns:
                pat_norm = _normalize(pattern)
                if fnmatch.fnmatchcase(cwd_norm, pat_norm):
                    candidates.append((entry, pattern, len(pat_norm)))
        if not candidates:
            return None
        candidates.sort(key=lambda t: t[2], reverse=True)
        top_len = candidates[0][2]
        ties = [c for c in candidates if c[2] == top_len]
        unique_names = {c[0].name for c in ties}
        if len(unique_names) > 1:
            raise ResolverAmbiguityError(
                f"cwd {cwd} matches {len(unique_names)} projects at length {top_len}: "
                f"{sorted(unique_names)}"
            )
        return candidates[0][0]
```

- [ ] **Step 5: Run, pass; ruff + mypy.**

- [ ] **Step 6: Commit**

```
feat(mapping): ProjectResolver with fnmatch glob + most-specific wins

Plan #13b-α Task 3. claude_mnemos/mapping/resolver.py:
- resolve_by_name (linear scan)
- resolve_by_vault (path equality after expanduser/resolve)
- resolve_by_cwd (fnmatch glob, longest-pattern wins, tie -> error)
- Windows case-insensitive normalization
- ResolverAmbiguityError for distinct projects matching same-length pattern
```

---

## Task 4: daemon/routes/projects.py — REST CRUD + register in app.py

**Files:**
- Create: `claude_mnemos/daemon/routes/projects.py`
- Create: `tests/daemon/test_routes_projects.py`
- Modify: `claude_mnemos/daemon/app.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/daemon/test_routes_projects.py
from __future__ import annotations
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from claude_mnemos.daemon.app import create_app
from claude_mnemos.state.projects import (
    HOME_CONFIG_DIRNAME, PROJECT_MAP_FILENAME, ProjectMapEntry, ProjectMap,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    app = create_app(vault, daemon=None)
    return TestClient(app), tmp_path


def test_get_projects_empty(client):
    c, _ = client
    r = c.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_post_project_then_get(client):
    c, home = client
    body = {
        "name": "x", "vault_root": str(home / "v"), "cwd_patterns": ["~/code/x*"],
    }
    r = c.post("/api/projects", json=body)
    assert r.status_code == 201, r.text
    r2 = c.get("/api/projects/x")
    assert r2.status_code == 200
    data = r2.json()
    assert data["name"] == "x"
    assert "settings" in data
    assert data["settings"]["snapshots"]["retention_days"] == 180


def test_post_duplicate_returns_409(client):
    c, home = client
    body = {"name": "x", "vault_root": str(home / "v"), "cwd_patterns": []}
    c.post("/api/projects", json=body)
    r = c.post("/api/projects", json=body)
    assert r.status_code == 409


def test_post_invalid_name_returns_422(client):
    c, home = client
    body = {"name": "Bad Name", "vault_root": str(home / "v"), "cwd_patterns": []}
    r = c.post("/api/projects", json=body)
    assert r.status_code == 422


def test_get_unknown_returns_404(client):
    c, _ = client
    assert c.get("/api/projects/nope").status_code == 404


def test_patch_updates_fields(client):
    c, home = client
    c.post("/api/projects", json={
        "name": "x", "vault_root": str(home / "v"), "cwd_patterns": ["~/a"],
    })
    r = c.patch("/api/projects/x", json={"cwd_patterns": ["~/b"]})
    assert r.status_code == 200
    assert r.json()["cwd_patterns"] == ["~/b"]


def test_delete_removes_entry(client):
    c, home = client
    c.post("/api/projects", json={
        "name": "x", "vault_root": str(home / "v"), "cwd_patterns": [],
    })
    r = c.delete("/api/projects/x")
    assert r.status_code == 204
    assert c.get("/api/projects/x").status_code == 404


def test_delete_unknown_returns_404(client):
    c, _ = client
    assert c.delete("/api/projects/nope").status_code == 404


def test_list_returns_all_after_multiple_adds(client):
    c, home = client
    c.post("/api/projects", json={"name": "a", "vault_root": str(home / "va"), "cwd_patterns": []})
    c.post("/api/projects", json={"name": "b", "vault_root": str(home / "vb"), "cwd_patterns": []})
    r = c.get("/api/projects")
    names = sorted(e["name"] for e in r.json())
    assert names == ["a", "b"]
```

- [ ] **Step 2: Run, fail (404 — routes not registered).**

- [ ] **Step 3: Implement `claude_mnemos/daemon/routes/projects.py`**

```python
"""REST routes for project-map CRUD + combined ProjectView."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

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
        raise HTTPException(status_code=404, detail={"error": "not_found", "name": name}) from exc
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
        name=body.name, vault_root=body.vault_root, cwd_patterns=body.cwd_patterns,
    )
    try:
        return _store().add(entry)
    except ProjectNameConflictError as exc:
        raise HTTPException(
            status_code=409, detail={"error": "name_conflict", "name": body.name},
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
        raise HTTPException(status_code=404, detail={"error": "not_found", "name": name}) from exc


@router.delete("/api/projects/{name}", status_code=204)
def delete_project(name: str) -> None:
    try:
        _store().remove(name)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": "not_found", "name": name}) from exc
```

- [ ] **Step 4: Modify `claude_mnemos/daemon/app.py` — register router + exception handlers**

In imports (alphabetical):
```python
from claude_mnemos.daemon.routes.projects import router as projects_router
from claude_mnemos.state.projects import ProjectMapCorruptError, ProjectMapError
```

Inside `create_app`, after existing `app.include_router` calls:
```python
app.include_router(projects_router)
```

Add exception handlers (after existing ones, before `return app`):
```python
@app.exception_handler(ProjectMapCorruptError)
async def _project_map_corrupt(_request: Request, exc: ProjectMapCorruptError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": "project_map_corrupt", "detail": str(exc)},
    )

@app.exception_handler(ProjectMapError)
async def _project_map_error(_request: Request, exc: ProjectMapError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": "project_map_error", "detail": str(exc)},
    )
```

Note: ordering matters — `ProjectMapCorruptError` must be registered before its parent `ProjectMapError`, otherwise FastAPI will route corrupt errors to the parent handler.

- [ ] **Step 5: Run tests pass; ruff + mypy.**

- [ ] **Step 6: Commit**

```
feat(daemon): /api/projects CRUD + ProjectView combined endpoint

Plan #13b-α Task 4. New router claude_mnemos/daemon/routes/projects.py:
- GET /api/projects              list all entries
- GET /api/projects/{name}       combined ProjectView (entry + settings)
- POST /api/projects             create (409 on duplicate, 422 on bad name)
- PATCH /api/projects/{name}     partial update of vault_root / cwd_patterns
- DELETE /api/projects/{name}    remove + cleanup orphan settings file
- ProjectMapCorruptError -> 503, ProjectMapError -> 500
```

---

## Task 5: daemon/routes/settings.py — REST + daemon reload trigger

**Files:**
- Create: `claude_mnemos/daemon/routes/settings.py`
- Create: `tests/daemon/test_routes_settings.py`
- Modify: `claude_mnemos/daemon/app.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/daemon/test_routes_settings.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from claude_mnemos.daemon.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    app = create_app(vault, daemon=None)
    return TestClient(app), tmp_path


def test_get_settings_returns_defaults(client):
    c, _ = client
    r = c.get("/api/settings/foo")
    assert r.status_code == 200
    data = r.json()
    assert data["snapshots"]["retention_days"] == 180
    assert data["auto_ingest"]["enabled"] is True


def test_patch_settings_partial_persists(client):
    c, _ = client
    r = c.patch("/api/settings/foo", json={"snapshots": {"retention_days": 30}})
    assert r.status_code == 200
    assert r.json()["snapshots"]["retention_days"] == 30
    assert r.json()["snapshots"]["daily_enabled"] is True
    r2 = c.get("/api/settings/foo")
    assert r2.json()["snapshots"]["retention_days"] == 30


def test_patch_invalid_value_returns_422(client):
    c, _ = client
    r = c.patch("/api/settings/foo", json={"snapshots": {"retention_days": -1}})
    assert r.status_code == 422


def test_get_global_returns_defaults(client):
    c, _ = client
    r = c.get("/api/settings/global")
    assert r.status_code == 200
    assert r.json()["locale"] == "uk"
    assert r.json()["daemon_port"] == 5757


def test_patch_global_persists(client):
    c, _ = client
    r = c.patch("/api/settings/global", json={"locale": "en"})
    assert r.status_code == 200
    assert r.json()["locale"] == "en"


def test_patch_settings_triggers_daemon_reload_when_matching_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    # Register project pointing at this vault
    from claude_mnemos.state.projects import ProjectStore, ProjectMapEntry
    ProjectStore().add(ProjectMapEntry(name="foo", vault_root=vault, cwd_patterns=[]))
    fake_daemon = MagicMock()
    fake_daemon.reload_settings = MagicMock()
    fake_daemon.config = MagicMock()
    fake_daemon.config.vault_root = vault
    app = create_app(vault, daemon=fake_daemon)
    c = TestClient(app)
    r = c.patch("/api/settings/foo", json={"snapshots": {"daily_enabled": False}})
    assert r.status_code == 200
    fake_daemon.reload_settings.assert_called_once()


def test_patch_other_project_settings_does_not_trigger_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    other_vault = tmp_path / "other_vault"
    other_vault.mkdir()
    from claude_mnemos.state.projects import ProjectStore, ProjectMapEntry
    s = ProjectStore()
    s.add(ProjectMapEntry(name="foo", vault_root=vault, cwd_patterns=[]))
    s.add(ProjectMapEntry(name="bar", vault_root=other_vault, cwd_patterns=[]))
    fake_daemon = MagicMock()
    fake_daemon.reload_settings = MagicMock()
    fake_daemon.config = MagicMock()
    fake_daemon.config.vault_root = vault
    app = create_app(vault, daemon=fake_daemon)
    c = TestClient(app)
    c.patch("/api/settings/bar", json={"snapshots": {"daily_enabled": False}})
    fake_daemon.reload_settings.assert_not_called()
```

- [ ] **Step 2: Run, fail (404).**

- [ ] **Step 3: Implement `claude_mnemos/daemon/routes/settings.py`**

```python
"""REST routes for per-project + global settings.

Daemon reload trigger: when PATCH /api/settings/{project} updates the
project whose vault matches the daemon's own ``config.vault_root``, the
daemon's ``reload_settings`` method is invoked with the new instance so
schedulers/observers pick up the change without restart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.state.projects import ProjectStore
from claude_mnemos.state.settings import (
    GlobalSettings, ProjectSettings, SettingsStore,
)

router = APIRouter()


def _settings_store() -> SettingsStore:
    return SettingsStore()


def _project_store() -> ProjectStore:
    return ProjectStore()


@router.get("/api/settings/global", response_model=GlobalSettings)
def get_global_settings() -> GlobalSettings:
    return _settings_store().get_global()


@router.patch("/api/settings/global", response_model=GlobalSettings)
def patch_global_settings(body: dict[str, Any]) -> GlobalSettings:
    return _settings_store().patch_global(body)


@router.get("/api/settings/{name}", response_model=ProjectSettings)
def get_project_settings(name: str) -> ProjectSettings:
    return _settings_store().get_project(name)


@router.patch("/api/settings/{name}", response_model=ProjectSettings)
def patch_project_settings(name: str, body: dict[str, Any], request: Request) -> ProjectSettings:
    updated = _settings_store().patch_project(name, body)
    daemon = request.app.state.daemon
    if daemon is not None:
        try:
            entry = _project_store().get(name)
        except Exception:
            entry = None
        if (
            entry is not None
            and Path(entry.vault_root).expanduser().resolve()
            == Path(daemon.config.vault_root).expanduser().resolve()
            and hasattr(daemon, "reload_settings")
        ):
            daemon.reload_settings(updated)
    return updated
```

Note: route ordering — `/api/settings/global` must be defined before `/api/settings/{name}` so FastAPI's path matcher does not capture "global" as a project name.

- [ ] **Step 4: Modify `claude_mnemos/daemon/app.py` — register router + exception handlers**

Add import:
```python
from claude_mnemos.daemon.routes.settings import router as settings_router
from claude_mnemos.state.settings import SettingsCorruptError
```

In `create_app`:
```python
app.include_router(settings_router)
```

Exception handler:
```python
@app.exception_handler(SettingsCorruptError)
async def _settings_corrupt(_request: Request, exc: SettingsCorruptError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": "settings_corrupt", "detail": str(exc)},
    )
```

- [ ] **Step 5: Run tests, pass; ruff + mypy.**

- [ ] **Step 6: Commit**

```
feat(daemon): /api/settings/{name} + /api/settings/global routes

Plan #13b-α Task 5. claude_mnemos/daemon/routes/settings.py:
- GET/PATCH /api/settings/{name}     per-project settings (defaults if missing)
- GET/PATCH /api/settings/global     GlobalSettings
- PATCH triggers daemon.reload_settings() when project vault matches daemon's
- /api/settings/global registered before /api/settings/{name} for routing
- SettingsCorruptError -> 503
```

---

## Task 6: PID file + runtime config path migration to `~/.claude-mnemos/`

**Files:**
- Modify: `claude_mnemos/daemon/config.py`
- Create: `tests/test_pid_file_migration.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_pid_file_migration.py
from __future__ import annotations
from pathlib import Path
import pytest
from claude_mnemos.daemon.config import (
    default_pid_file, default_runtime_config_file, migrate_legacy_dotmnemos,
)


def test_default_pid_file_is_in_claude_mnemos(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    p = default_pid_file()
    assert ".claude-mnemos" in p.parts
    assert ".mnemos" not in [x for x in p.parts if x != ".claude-mnemos"]


def test_default_runtime_config_file_is_in_claude_mnemos(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    p = default_runtime_config_file()
    assert ".claude-mnemos" in p.parts


def test_migrate_legacy_dotmnemos_moves_pid(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    legacy = tmp_path / ".mnemos"
    legacy.mkdir()
    (legacy / "daemon.pid").write_text("12345")
    (legacy / "daemon.config.json").write_text("{}")
    migrated = migrate_legacy_dotmnemos()
    assert migrated  # returns truthy when something was migrated
    new = tmp_path / ".claude-mnemos"
    assert (new / "daemon.pid").read_text() == "12345"
    assert (new / "daemon.config.json").read_text() == "{}"
    # Old files removed
    assert not (legacy / "daemon.pid").exists()
    assert not (legacy / "daemon.config.json").exists()


def test_migrate_legacy_does_not_overwrite_new(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    legacy = tmp_path / ".mnemos"
    legacy.mkdir()
    (legacy / "daemon.pid").write_text("OLD")
    new = tmp_path / ".claude-mnemos"
    new.mkdir()
    (new / "daemon.pid").write_text("NEW")
    migrate_legacy_dotmnemos()
    assert (new / "daemon.pid").read_text() == "NEW"


def test_migrate_legacy_idempotent_when_no_legacy(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # No ~/.mnemos at all
    assert migrate_legacy_dotmnemos() is False
```

- [ ] **Step 2: Run, fail.**

- [ ] **Step 3: Modify `claude_mnemos/daemon/config.py`**

Replace existing `default_pid_file` / `default_runtime_config_file` and add `migrate_legacy_dotmnemos`:

```python
LEGACY_HOME_DIRNAME = ".mnemos"
HOME_DIRNAME = ".claude-mnemos"


def default_pid_file() -> Path:
    return Path.home() / HOME_DIRNAME / "daemon.pid"


def default_runtime_config_file() -> Path:
    return Path.home() / HOME_DIRNAME / "daemon.config.json"


def migrate_legacy_dotmnemos() -> bool:
    """One-shot: move pid/config from ~/.mnemos to ~/.claude-mnemos.

    Returns True if any file was moved. New-location files are never
    overwritten (presumed to be the source of truth post-migration).
    """
    legacy_dir = Path.home() / LEGACY_HOME_DIRNAME
    if not legacy_dir.is_dir():
        return False
    new_dir = Path.home() / HOME_DIRNAME
    new_dir.mkdir(parents=True, exist_ok=True)
    moved = False
    for name in ("daemon.pid", "daemon.config.json"):
        src = legacy_dir / name
        dst = new_dir / name
        if src.is_file() and not dst.exists():
            try:
                dst.write_bytes(src.read_bytes())
                src.unlink()
                moved = True
            except OSError:
                continue
    return moved
```

- [ ] **Step 4: Run tests, pass.**

- [ ] **Step 5: ruff + mypy.**

- [ ] **Step 6: Commit**

```
feat(daemon): migrate PID file path to ~/.claude-mnemos/

Plan #13b-α Task 6. claude_mnemos/daemon/config.py:
- default_pid_file/default_runtime_config_file now return ~/.claude-mnemos/...
  matching spec §5.5/§13.1.
- New migrate_legacy_dotmnemos(): one-shot move from ~/.mnemos/ if present.
  Never overwrites new-location files. Returns True iff anything moved.
- Test coverage for path, migration, idempotence, no-clobber.
```

---

## Task 7: daemon/process.py — settings consumption + reload + scheduler extension

**Files:**
- Modify: `claude_mnemos/daemon/process.py`
- Modify: `claude_mnemos/daemon/scheduler.py`
- Create: `tests/daemon/test_settings_consumption.py`

- [ ] **Step 1: Read current `claude_mnemos/daemon/scheduler.py` to understand `build_scheduler` signature.**

```
read claude_mnemos/daemon/scheduler.py
```

- [ ] **Step 2: Write failing tests**

```python
# tests/daemon/test_settings_consumption.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch
import pytest
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.state.projects import ProjectStore, ProjectMapEntry
from claude_mnemos.state.settings import (
    SettingsStore, ProjectSettings, SnapshotsSettings,
)


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_daemon_uses_settings_when_vault_registered(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))
    SettingsStore().patch_project("x", {"snapshots": {"retention_days": 7}})
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    assert d.project_settings.snapshots.retention_days == 7
    assert d.project_entry is not None and d.project_entry.name == "x"


def test_daemon_falls_back_to_defaults_when_unregistered(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    assert d.project_entry is None
    assert d.project_settings == ProjectSettings()
    assert any("not registered in project-map" in a.message for a in d.alerts.list())


def test_daemon_reload_swaps_settings(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    new = ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=False, retention_days=10))
    d.reload_settings(new)
    assert d.project_settings.snapshots.daily_enabled is False
    assert d.project_settings.snapshots.retention_days == 10


def test_daemon_reload_reschedules_snapshot_job(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))
    SettingsStore().patch_project("x", {"snapshots": {"daily_enabled": True}})
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    initial_jobs = {j.id for j in d.scheduler.get_jobs()}
    assert any("snapshot" in jid for jid in initial_jobs)
    new = ProjectSettings(snapshots=SnapshotsSettings(daily_enabled=False))
    d.reload_settings(new)
    after_jobs = {j.id for j in d.scheduler.get_jobs()}
    assert not any("daily_snapshot" in jid for jid in after_jobs)


def test_daemon_alerts_on_unregistered_use_handler_error_kind(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    d = MnemosDaemon(DaemonConfig(vault_root=vault))
    alerts = [a for a in d.alerts.list() if "not registered" in a.message]
    assert alerts and alerts[0].kind == "handler_error"
```

- [ ] **Step 3: Run, fail.**

- [ ] **Step 4: Modify `claude_mnemos/daemon/scheduler.py` — accept `snapshots_enabled`**

Locate `build_scheduler(vault_root, retention_days)` and extend signature:

```python
def build_scheduler(
    vault_root: Path,
    retention_days: int,
    *,
    snapshots_enabled: bool = True,
) -> AsyncIOScheduler:
    sched = AsyncIOScheduler()
    if snapshots_enabled:
        sched.add_job(
            daily_snapshot_task,
            "cron",
            hour=4, minute=0,
            id="daily_snapshot",
            args=(vault_root,),
            replace_existing=True,
        )
    sched.add_job(
        backups_cleanup_task,
        "cron",
        hour=5, minute=0,
        id="backups_cleanup",
        args=(vault_root, retention_days),
        replace_existing=True,
    )
    return sched
```

If existing job IDs differ, keep them — only add `snapshots_enabled` parameter and conditional registration of the daily-snapshot job. Pass `id="daily_snapshot"` so reload can find it.

- [ ] **Step 5: Modify `claude_mnemos/daemon/process.py`**

In imports (alphabetical):
```python
from claude_mnemos.mapping.resolver import ProjectResolver
from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
from claude_mnemos.state.settings import ProjectSettings, SettingsStore
```

In `MnemosDaemon.__init__`, after `self.alerts = Alerts()`:

```python
        self.project_store = ProjectStore()
        self.settings_store = SettingsStore()
        self.global_settings = self.settings_store.get_global()
        self.project_entry: ProjectMapEntry | None = None
        try:
            self.project_entry = ProjectResolver(self.project_store).resolve_by_vault(
                config.vault_root
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("project resolver failed at startup")
            self.alerts.add(
                kind="handler_error",
                path=str(config.vault_root),
                message=f"project resolver failed: {exc}",
                detected_at=datetime.now(UTC),
            )
        if self.project_entry is None:
            self.project_settings = ProjectSettings()
            self.alerts.add(
                kind="handler_error",
                path=str(config.vault_root),
                message=(
                    f"daemon vault {config.vault_root} not registered in "
                    "project-map; using built-in defaults"
                ),
                detected_at=datetime.now(UTC),
            )
        else:
            self.project_settings = self.settings_store.get_project(self.project_entry.name)
```

Then update scheduler construction (replace existing `self.scheduler = build_scheduler(...)`):

```python
        self.scheduler: AsyncIOScheduler = build_scheduler(
            config.vault_root,
            self.project_settings.snapshots.retention_days,
            snapshots_enabled=self.project_settings.snapshots.daily_enabled,
        )
```

Add reload method (after `_stop_jobs_subsystem`):

```python
    def reload_settings(self, new_settings: ProjectSettings) -> None:
        """Apply new settings; reschedule snapshot jobs as needed.

        Called by PATCH /api/settings/{project} when the patched project
        is the daemon's own vault. Lint schedule reload deferred to
        Plan #11+ when the scheduled lint runner exists.
        """
        old = self.project_settings
        self.project_settings = new_settings

        if old.snapshots.daily_enabled != new_settings.snapshots.daily_enabled:
            existing = self.scheduler.get_job("daily_snapshot")
            if new_settings.snapshots.daily_enabled and existing is None:
                self.scheduler.add_job(
                    daily_snapshot_task,
                    "cron",
                    hour=4, minute=0,
                    id="daily_snapshot",
                    args=(self.config.vault_root,),
                    replace_existing=True,
                )
            elif not new_settings.snapshots.daily_enabled and existing is not None:
                self.scheduler.remove_job("daily_snapshot")

        if old.snapshots.retention_days != new_settings.snapshots.retention_days:
            self.scheduler.add_job(
                backups_cleanup_task,
                "cron",
                hour=5, minute=0,
                id="backups_cleanup",
                args=(self.config.vault_root, new_settings.snapshots.retention_days),
                replace_existing=True,
            )
```

Add necessary imports for the methods you reference (`daily_snapshot_task`, `backups_cleanup_task` — wherever they currently live). If they're internal to `scheduler.py`, import them at module top.

- [ ] **Step 6: Run tests pass; ruff + mypy.**

- [ ] **Step 7: Commit**

```
feat(daemon): consume project settings + reload on PATCH

Plan #13b-α Task 7.
- daemon/scheduler.py: build_scheduler accepts snapshots_enabled
- daemon/process.py: MnemosDaemon now resolves itself in project-map at
  startup, loads ProjectSettings, applies snapshots.retention_days +
  snapshots.daily_enabled to the scheduler.
- Unregistered vault: alerts.add(kind=handler_error) + defaults.
- New reload_settings(new) method: swaps in-memory copy + reschedules
  daily_snapshot/backups_cleanup jobs as appropriate.
```

---

## Task 8: CLI `mnemos project` subgroup

**Files:**
- Modify: `claude_mnemos/cli.py`
- Create: `tests/test_cli_project.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli_project.py
from __future__ import annotations
import json
from pathlib import Path
import pytest
from claude_mnemos.cli import main as cli_main
from claude_mnemos.state.projects import (
    HOME_CONFIG_DIRNAME, PROJECT_MAP_FILENAME,
)


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("MNEMOS_VAULT_ROOT", raising=False)


def test_project_add_writes_map(tmp_path, capsys):
    rc = cli_main([
        "project", "add",
        "--name", "claude-mnemos",
        "--vault", str(tmp_path / "v"),
        "--cwd-pattern", "~/code/cm*",
    ])
    assert rc == 0
    f = tmp_path / HOME_CONFIG_DIRNAME / PROJECT_MAP_FILENAME
    data = json.loads(f.read_text())
    assert data["projects"][0]["name"] == "claude-mnemos"
    assert data["projects"][0]["cwd_patterns"] == ["~/code/cm*"]


def test_project_add_duplicate_returns_error(tmp_path):
    cli_main(["project", "add", "--name", "x", "--vault", str(tmp_path / "v"), "--cwd-pattern", "~/x"])
    rc = cli_main(["project", "add", "--name", "x", "--vault", str(tmp_path / "v2"), "--cwd-pattern", "~/y"])
    assert rc != 0


def test_project_add_invalid_name_returns_error(tmp_path):
    rc = cli_main(["project", "add", "--name", "Bad Name", "--vault", str(tmp_path / "v")])
    assert rc != 0


def test_project_list_empty(capsys):
    rc = cli_main(["project", "list", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert json.loads(out) == []


def test_project_list_after_add(tmp_path, capsys):
    cli_main(["project", "add", "--name", "x", "--vault", str(tmp_path / "v"), "--cwd-pattern", "~/x"])
    capsys.readouterr()
    cli_main(["project", "list", "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["name"] == "x"


def test_project_show_returns_view(tmp_path, capsys):
    cli_main(["project", "add", "--name", "x", "--vault", str(tmp_path / "v"), "--cwd-pattern", "~/x"])
    capsys.readouterr()
    cli_main(["project", "show", "x", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "x"
    assert "settings" in data
    assert data["settings"]["snapshots"]["retention_days"] == 180


def test_project_update_replaces_cwd_patterns(tmp_path):
    cli_main(["project", "add", "--name", "x", "--vault", str(tmp_path / "v"), "--cwd-pattern", "~/old"])
    rc = cli_main(["project", "update", "x", "--add-cwd-pattern", "~/new", "--remove-cwd-pattern", "~/old"])
    assert rc == 0
    from claude_mnemos.state.projects import ProjectStore
    e = ProjectStore().get("x")
    assert e.cwd_patterns == ["~/new"]


def test_project_remove_cleans_settings(tmp_path):
    from claude_mnemos.state.projects import project_settings_path
    cli_main(["project", "add", "--name", "x", "--vault", str(tmp_path / "v"), "--cwd-pattern", "~/x"])
    sp = project_settings_path("x")
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text("{}")
    rc = cli_main(["project", "remove", "x", "--yes"])
    assert rc == 0
    assert not sp.exists()


def test_project_resolve_with_explicit_cwd(tmp_path, capsys):
    cwd = tmp_path / "code" / "x"
    cwd.mkdir(parents=True)
    cli_main(["project", "add", "--name", "x", "--vault", str(tmp_path / "v"), "--cwd-pattern", str(cwd)])
    capsys.readouterr()
    rc = cli_main(["project", "resolve", "--cwd", str(cwd), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "x"


def test_project_resolve_no_match_nonzero(tmp_path, capsys):
    rc = cli_main(["project", "resolve", "--cwd", str(tmp_path / "elsewhere"), "--json"])
    assert rc != 0
```

- [ ] **Step 2: Run, fail.**

- [ ] **Step 3: Modify `claude_mnemos/cli.py` — add `project` subparser**

Add to `build_parser`, after existing subparsers (e.g., after `metrics`):

```python
    # ----- project -----
    project_p = sub.add_parser("project", help="Manage project-map.json entries")
    project_sub = project_p.add_subparsers(dest="project_command", required=True)

    pa = project_sub.add_parser("add", help="Add a project entry")
    pa.add_argument("--name", required=True)
    pa.add_argument("--vault", required=True, type=Path)
    pa.add_argument("--cwd-pattern", action="append", default=[],
                    help="May be repeated; glob pattern matched against cwd")

    project_sub.add_parser("list", help="List all projects").add_argument(
        "--json", action="store_true",
    )

    ps = project_sub.add_parser("show", help="Show combined view (entry + settings)")
    ps.add_argument("name")
    ps.add_argument("--json", action="store_true")

    pu = project_sub.add_parser("update", help="Update fields on an existing project")
    pu.add_argument("name")
    pu.add_argument("--vault", type=Path, default=None)
    pu.add_argument("--add-cwd-pattern", action="append", default=[])
    pu.add_argument("--remove-cwd-pattern", action="append", default=[])

    pr = project_sub.add_parser("remove", help="Remove a project entry")
    pr.add_argument("name")
    pr.add_argument("--yes", action="store_true")

    pres = project_sub.add_parser("resolve", help="Debug: which project matches the cwd")
    pres.add_argument("--cwd", type=Path, default=Path.cwd())
    pres.add_argument("--json", action="store_true")
```

Add dispatch in `main` after existing branches:

```python
    if args.command == "project":
        from claude_mnemos.cli_project import handle as project_handle
        return project_handle(args)
```

- [ ] **Step 4: Implement `claude_mnemos/cli_project.py`** (new module — keeps cli.py manageable)

```python
"""CLI subgroup ``mnemos project`` — project-map CRUD.

Read commands hit the file system directly; write commands go through
the daemon's REST API to respect single-owner state-file ownership
(per spec §10.1). When the daemon is offline we fall back to direct
ProjectStore writes — single-user dev convenience until #13b-β makes
the daemon truly multi-vault.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from claude_mnemos.mapping.resolver import ProjectResolver, ResolverAmbiguityError
from claude_mnemos.state.projects import (
    ProjectMapEntry, ProjectNameConflictError, ProjectNotFoundError, ProjectStore,
)
from claude_mnemos.state.settings import SettingsStore

EXIT_PROJECT_MAP_ERROR = 94
EXIT_RESOLVER_AMBIGUITY = 96
EXIT_PROJECT_NOT_FOUND = 97
EXIT_DAEMON_UNREACHABLE = 84  # reused from jobs


def _daemon_url() -> str:
    import os
    return os.environ.get("MNEMOS_DAEMON_URL", "http://127.0.0.1:5757")


def handle(args: argparse.Namespace) -> int:
    cmd = args.project_command
    if cmd == "add":
        return _handle_add(args)
    if cmd == "list":
        return _handle_list(args)
    if cmd == "show":
        return _handle_show(args)
    if cmd == "update":
        return _handle_update(args)
    if cmd == "remove":
        return _handle_remove(args)
    if cmd == "resolve":
        return _handle_resolve(args)
    print(f"unknown project command: {cmd}", file=sys.stderr)
    return 2


def _handle_add(args: argparse.Namespace) -> int:
    body = {
        "name": args.name,
        "vault_root": str(args.vault),
        "cwd_patterns": args.cwd_pattern,
    }
    try:
        r = httpx.post(f"{_daemon_url()}/api/projects", json=body, timeout=2.0)
        if r.status_code == 201:
            print(f"added project {args.name!r}")
            return 0
        if r.status_code == 409:
            print(f"project {args.name!r} already exists", file=sys.stderr)
            return EXIT_PROJECT_MAP_ERROR
        if r.status_code == 422:
            print(f"validation error: {r.text}", file=sys.stderr)
            return EXIT_PROJECT_MAP_ERROR
        print(f"daemon error {r.status_code}: {r.text}", file=sys.stderr)
        return EXIT_PROJECT_MAP_ERROR
    except (httpx.ConnectError, httpx.TimeoutException):
        # Fallback to direct store (single-user dev)
        try:
            ProjectStore().add(ProjectMapEntry(
                name=args.name, vault_root=args.vault, cwd_patterns=args.cwd_pattern,
            ))
            print(f"added project {args.name!r} (offline)")
            return 0
        except ProjectNameConflictError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_PROJECT_MAP_ERROR


def _handle_list(args: argparse.Namespace) -> int:
    entries = ProjectStore().list_all()
    if getattr(args, "json", False):
        print(json.dumps([e.model_dump(mode="json") for e in entries], indent=2))
    else:
        if not entries:
            print("(no projects)")
        for e in entries:
            patterns = ",".join(e.cwd_patterns) or "-"
            print(f"{e.name}\t{e.vault_root}\t{patterns}")
    return 0


def _handle_show(args: argparse.Namespace) -> int:
    try:
        entry = ProjectStore().get(args.name)
    except ProjectNotFoundError:
        print(f"project {args.name!r} not found", file=sys.stderr)
        return EXIT_PROJECT_NOT_FOUND
    settings = SettingsStore().get_project(args.name)
    view = {
        "name": entry.name,
        "vault_root": str(entry.vault_root),
        "cwd_patterns": entry.cwd_patterns,
        "settings": settings.model_dump(mode="json"),
    }
    print(json.dumps(view, indent=2) if getattr(args, "json", False) else _pretty(view))
    return 0


def _pretty(view: dict) -> str:
    out = [
        f"name:        {view['name']}",
        f"vault_root:  {view['vault_root']}",
        f"cwd_patterns: {', '.join(view['cwd_patterns']) or '-'}",
        "settings:",
        json.dumps(view["settings"], indent=2),
    ]
    return "\n".join(out)


def _handle_update(args: argparse.Namespace) -> int:
    try:
        entry = ProjectStore().get(args.name)
    except ProjectNotFoundError:
        print(f"project {args.name!r} not found", file=sys.stderr)
        return EXIT_PROJECT_NOT_FOUND
    new_patterns = list(entry.cwd_patterns)
    for p in args.add_cwd_pattern:
        if p not in new_patterns:
            new_patterns.append(p)
    new_patterns = [p for p in new_patterns if p not in args.remove_cwd_pattern]
    body: dict = {}
    if args.vault is not None:
        body["vault_root"] = str(args.vault)
    body["cwd_patterns"] = new_patterns
    try:
        r = httpx.patch(f"{_daemon_url()}/api/projects/{args.name}", json=body, timeout=2.0)
        if r.status_code == 200:
            print(f"updated project {args.name!r}")
            return 0
        print(f"daemon error {r.status_code}: {r.text}", file=sys.stderr)
        return EXIT_PROJECT_MAP_ERROR
    except (httpx.ConnectError, httpx.TimeoutException):
        ProjectStore().update(
            args.name, vault_root=args.vault, cwd_patterns=new_patterns,
        )
        print(f"updated project {args.name!r} (offline)")
        return 0


def _handle_remove(args: argparse.Namespace) -> int:
    if not args.yes:
        print(f"Remove project {args.name!r}? [y/N] ", end="", flush=True)
        ans = sys.stdin.readline().strip().lower()
        if ans not in ("y", "yes"):
            print("aborted")
            return 0
    try:
        r = httpx.delete(f"{_daemon_url()}/api/projects/{args.name}", timeout=2.0)
        if r.status_code in (200, 204):
            print(f"removed project {args.name!r}")
            return 0
        if r.status_code == 404:
            print(f"project {args.name!r} not found", file=sys.stderr)
            return EXIT_PROJECT_NOT_FOUND
        print(f"daemon error {r.status_code}: {r.text}", file=sys.stderr)
        return EXIT_PROJECT_MAP_ERROR
    except (httpx.ConnectError, httpx.TimeoutException):
        try:
            ProjectStore().remove(args.name)
            print(f"removed project {args.name!r} (offline)")
            return 0
        except ProjectNotFoundError:
            print(f"project {args.name!r} not found", file=sys.stderr)
            return EXIT_PROJECT_NOT_FOUND


def _handle_resolve(args: argparse.Namespace) -> int:
    try:
        entry = ProjectResolver().resolve_by_cwd(args.cwd)
    except ResolverAmbiguityError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_RESOLVER_AMBIGUITY
    if entry is None:
        print(f"no project matches cwd {args.cwd}", file=sys.stderr)
        return EXIT_PROJECT_NOT_FOUND
    if getattr(args, "json", False):
        print(json.dumps(entry.model_dump(mode="json"), indent=2))
    else:
        print(f"{entry.name}\t{entry.vault_root}")
    return 0
```

- [ ] **Step 5: Run tests, pass.**

- [ ] **Step 6: ruff + mypy + commit**

```
feat(cli): mnemos project {add,list,show,update,remove,resolve}

Plan #13b-α Task 8. Adds claude_mnemos/cli_project.py + parser branch.
Writes go through daemon REST first, fall back to direct ProjectStore
when daemon is offline (single-user dev convenience). Reads always
direct. New exit codes 84 (daemon offline), 94 (project_map_error),
96 (resolver ambiguity), 97 (project not found).
```

---

## Task 9: CLI `mnemos settings` subgroup

**Files:**
- Modify: `claude_mnemos/cli.py`
- Create: `claude_mnemos/cli_settings.py`
- Create: `tests/test_cli_settings.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli_settings.py
from __future__ import annotations
import json
from pathlib import Path
import pytest
from claude_mnemos.cli import main as cli_main


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("MNEMOS_VAULT_ROOT", raising=False)


def test_settings_get_returns_defaults(tmp_path, capsys):
    rc = cli_main(["settings", "get", "--project", "foo", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["snapshots"]["retention_days"] == 180


def test_settings_get_dot_path_scalar(tmp_path, capsys):
    rc = cli_main(["settings", "get", "--project", "foo", "snapshots.retention_days"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "180"


def test_settings_set_scalar(tmp_path, capsys):
    rc = cli_main([
        "settings", "set", "--project", "foo", "snapshots.retention_days", "30",
    ])
    assert rc == 0
    capsys.readouterr()
    cli_main(["settings", "get", "--project", "foo", "snapshots.retention_days"])
    assert capsys.readouterr().out.strip() == "30"


def test_settings_set_list(tmp_path):
    rc = cli_main([
        "settings", "set", "--project", "foo",
        "lint.enabled_rules", '["frontmatter_required"]',
    ])
    assert rc == 0
    from claude_mnemos.state.settings import SettingsStore
    s = SettingsStore().get_project("foo")
    assert s.lint.enabled_rules == ["frontmatter_required"]


def test_settings_set_invalid_json(tmp_path):
    rc = cli_main(["settings", "set", "--project", "foo", "lint.schedule", "not json"])
    assert rc != 0


def test_settings_set_invalid_value_type(tmp_path):
    # retention_days < 1 violates ge=1
    rc = cli_main(["settings", "set", "--project", "foo", "snapshots.retention_days", "-5"])
    assert rc != 0


def test_settings_reset_field(tmp_path):
    cli_main(["settings", "set", "--project", "foo", "snapshots.retention_days", "30"])
    rc = cli_main(["settings", "reset", "--project", "foo", "snapshots.retention_days"])
    assert rc == 0
    from claude_mnemos.state.settings import SettingsStore
    assert SettingsStore().get_project("foo").snapshots.retention_days == 180


def test_settings_reset_all(tmp_path):
    cli_main(["settings", "set", "--project", "foo", "snapshots.retention_days", "30"])
    rc = cli_main(["settings", "reset", "--project", "foo"])
    assert rc == 0
    from claude_mnemos.state.settings import SettingsStore
    assert SettingsStore().get_project("foo").snapshots.retention_days == 180


def test_settings_global_get_set(tmp_path, capsys):
    rc = cli_main(["settings", "get", "--global", "--json"])
    assert rc == 0
    cli_main(["settings", "set", "--global", "locale", '"en"'])
    capsys.readouterr()
    cli_main(["settings", "get", "--global", "locale"])
    assert capsys.readouterr().out.strip() == "en"
```

- [ ] **Step 2: Run, fail.**

- [ ] **Step 3: Add `settings` subparser to `cli.py` `build_parser`** (after `project`):

```python
    settings_p = sub.add_parser("settings", help="Per-project + global settings")
    settings_sub = settings_p.add_subparsers(dest="settings_command", required=True)

    sg = settings_sub.add_parser("get", help="Read a setting (or all)")
    sg_target = sg.add_mutually_exclusive_group(required=True)
    sg_target.add_argument("--project", type=str)
    sg_target.add_argument("--global", dest="is_global", action="store_true")
    sg.add_argument("key", nargs="?", default=None,
                    help="Dot-path; omit to dump everything")
    sg.add_argument("--json", action="store_true")

    ss = settings_sub.add_parser("set", help="Write a setting (value parsed as JSON)")
    ss_target = ss.add_mutually_exclusive_group(required=True)
    ss_target.add_argument("--project", type=str)
    ss_target.add_argument("--global", dest="is_global", action="store_true")
    ss.add_argument("key")
    ss.add_argument("value", help="JSON-encoded value: 30 / true / \"foo\" / [\"a\"]")

    sr = settings_sub.add_parser("reset", help="Reset a field to default (or whole project)")
    sr_target = sr.add_mutually_exclusive_group(required=True)
    sr_target.add_argument("--project", type=str)
    sr_target.add_argument("--global", dest="is_global", action="store_true")
    sr.add_argument("key", nargs="?", default=None)
```

Add dispatch in `main`:
```python
    if args.command == "settings":
        from claude_mnemos.cli_settings import handle as settings_handle
        return settings_handle(args)
```

- [ ] **Step 4: Implement `claude_mnemos/cli_settings.py`**

```python
"""CLI subgroup ``mnemos settings`` — get/set/reset per-project + global.

Reads always direct file access. Writes go through daemon REST when
available; fall back to direct SettingsStore when daemon is offline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

from claude_mnemos.state.settings import (
    GlobalSettings, ProjectSettings, SettingsStore,
    deep_merge, get_by_dot_path, patch_dict_for_dot_path,
)

EXIT_SETTINGS_ERROR = 95


def _daemon_url() -> str:
    return os.environ.get("MNEMOS_DAEMON_URL", "http://127.0.0.1:5757")


def handle(args: argparse.Namespace) -> int:
    cmd = args.settings_command
    if cmd == "get":
        return _handle_get(args)
    if cmd == "set":
        return _handle_set(args)
    if cmd == "reset":
        return _handle_reset(args)
    print(f"unknown settings command: {cmd}", file=sys.stderr)
    return 2


def _handle_get(args: argparse.Namespace) -> int:
    store = SettingsStore()
    if getattr(args, "is_global", False):
        s: GlobalSettings | ProjectSettings = store.get_global()
    else:
        s = store.get_project(args.project)
    if args.key is None:
        if getattr(args, "json", False):
            print(json.dumps(s.model_dump(mode="json"), indent=2))
        else:
            print(json.dumps(s.model_dump(mode="json"), indent=2))
        return 0
    try:
        value = get_by_dot_path(s, args.key)
    except AttributeError as exc:
        print(f"unknown setting key: {args.key} ({exc})", file=sys.stderr)
        return EXIT_SETTINGS_ERROR
    if hasattr(value, "model_dump"):
        print(json.dumps(value.model_dump(mode="json"), indent=2))
    elif getattr(args, "json", False) or isinstance(value, list | dict):
        print(json.dumps(value))
    else:
        print(value)
    return 0


def _handle_set(args: argparse.Namespace) -> int:
    try:
        parsed: Any = json.loads(args.value)
    except json.JSONDecodeError as exc:
        print(f"value is not valid JSON: {exc}", file=sys.stderr)
        return EXIT_SETTINGS_ERROR
    patch = patch_dict_for_dot_path(args.key, parsed)
    target_global = getattr(args, "is_global", False)
    url = (
        f"{_daemon_url()}/api/settings/global"
        if target_global
        else f"{_daemon_url()}/api/settings/{args.project}"
    )
    try:
        r = httpx.patch(url, json=patch, timeout=2.0)
        if r.status_code == 200:
            return 0
        if r.status_code == 422:
            print(f"validation error: {r.text}", file=sys.stderr)
            return EXIT_SETTINGS_ERROR
        print(f"daemon error {r.status_code}: {r.text}", file=sys.stderr)
        return EXIT_SETTINGS_ERROR
    except (httpx.ConnectError, httpx.TimeoutException):
        store = SettingsStore()
        try:
            if target_global:
                store.patch_global(patch)
            else:
                store.patch_project(args.project, patch)
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"settings error: {exc}", file=sys.stderr)
            return EXIT_SETTINGS_ERROR


def _handle_reset(args: argparse.Namespace) -> int:
    store = SettingsStore()
    target_global = getattr(args, "is_global", False)
    if args.key is None:
        # Whole-thing reset: delete file
        if target_global:
            store.reset_global()
        else:
            store.reset_project(args.project)
        return 0
    # Field-level reset: read defaults, take dot-path value, PATCH it back
    if target_global:
        defaults: GlobalSettings | ProjectSettings = GlobalSettings()
    else:
        defaults = ProjectSettings()
    try:
        default_value = get_by_dot_path(defaults, args.key)
    except AttributeError as exc:
        print(f"unknown setting key: {args.key} ({exc})", file=sys.stderr)
        return EXIT_SETTINGS_ERROR
    if hasattr(default_value, "model_dump"):
        default_value = default_value.model_dump(mode="json")
    patch = patch_dict_for_dot_path(args.key, default_value)
    if target_global:
        store.patch_global(patch)
    else:
        store.patch_project(args.project, patch)
    return 0
```

- [ ] **Step 5: Run tests, pass; ruff + mypy + commit.**

```
feat(cli): mnemos settings {get,set,reset} for project + global

Plan #13b-α Task 9. claude_mnemos/cli_settings.py:
- get/set/reset with dot-path keys (snapshots.retention_days etc.)
- VALUE parsed as JSON (30 / true / "foo" / ["a"])
- --project NAME or --global mutually exclusive
- Writes via daemon REST, fall back to direct SettingsStore offline
- reset without KEY removes file (full reset to defaults)
- Exit 95 (settings_error)
```

---

## Task 10: Existing CLI subgroups — `--vault PATH` → `--project NAME` migration + env hard-cut

**Files:**
- Modify: `claude_mnemos/cli.py` (~25 occurrences of `--vault, default=os.environ.get("MNEMOS_VAULT_ROOT")`)
- Modify: existing tests that rely on `MNEMOS_VAULT_ROOT` or pass `--vault` literally

This task is **mechanical** — replace each `--vault` flag with `--project`, build a helper that resolves `--project NAME` to a vault path, and cut the env fallback. `mnemos daemon start` keeps `--vault PATH` (single-vault until #13b-β). `mnemos ingest` keeps `vault` positional in α (it's invoked from hook subprocess fallback with `--project` which the dispatcher converts to vault — but for now the simplest cut is to switch the positional to `--project`).

- [ ] **Step 1: Survey all `--vault` callers in `claude_mnemos/cli.py`**

```
grep -n -- "--vault" claude_mnemos/cli.py
```

For each caller: keep `mnemos daemon start --vault PATH`; for the rest, replace with `--project`.

- [ ] **Step 2: Add a shared helper at top of `cli.py`**

```python
def _resolve_vault_from_project_arg(project_name: str | None, *, ctx: str) -> Path | None:
    """Map --project NAME to vault_root via project-map; auto-resolve from cwd
    if name is None. Returns None and prints to stderr on miss.
    """
    from claude_mnemos.mapping.resolver import ProjectResolver, ResolverAmbiguityError
    from claude_mnemos.state.projects import ProjectStore
    resolver = ProjectResolver()
    if project_name is not None:
        entry = resolver.resolve_by_name(project_name)
        if entry is None:
            print(
                f"{ctx}: project {project_name!r} not registered; "
                "registered projects: "
                + ", ".join(sorted(e.name for e in ProjectStore().list_all()) or ["(none)"]),
                file=sys.stderr,
            )
            return None
        return Path(entry.vault_root)
    try:
        entry = resolver.resolve_by_cwd(Path.cwd())
    except ResolverAmbiguityError as exc:
        print(f"{ctx}: ambiguous project for cwd: {exc}", file=sys.stderr)
        return None
    if entry is None:
        print(
            f"{ctx}: --project NAME required, or run from a registered project. "
            "Add one: mnemos project add --name NAME --vault PATH --cwd-pattern PATTERN",
            file=sys.stderr,
        )
        return None
    return Path(entry.vault_root)
```

- [ ] **Step 3: For each existing subgroup that previously used `--vault` env-default, replace with `--project NAME` (None default) and call the helper**

Example transformation, applied to each affected subparser. Old:

```python
sessions_list_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))
```

becomes:

```python
sessions_list_p.add_argument("--project", default=None)
```

In dispatch (find each handler in `main`), old:

```python
vault = Path(args.vault) if args.vault else None
if vault is None:
    print("vault not provided", file=sys.stderr)
    return 1
```

becomes:

```python
vault = _resolve_vault_from_project_arg(args.project, ctx="sessions list")
if vault is None:
    return 97
```

Apply to `lint`, `jobs`, `page`, `trash`, `sessions`, `lost-sessions`, `metrics`, `ontology`. The `mnemos ingest` positional arg also flips to `--project`:

```python
p.add_argument("jsonl", type=Path)
p.add_argument("--project", default=None)  # was: positional "vault"
```

In dispatch:
```python
vault = _resolve_vault_from_project_arg(args.project, ctx="ingest")
if vault is None:
    return 97
ingest(args.jsonl, vault, ...)
```

- [ ] **Step 4: Update existing tests**

Add to `tests/conftest.py`:

```python
import pytest
from pathlib import Path
from claude_mnemos.state.projects import ProjectStore, ProjectMapEntry


@pytest.fixture
def register_project(tmp_path, monkeypatch):
    """Register a project pointing at a tmp vault and isolate ~/.claude-mnemos/."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("MNEMOS_VAULT_ROOT", raising=False)

    def _register(name: str, vault: Path, *, cwd_patterns: list[str] | None = None) -> None:
        vault.mkdir(parents=True, exist_ok=True)
        ProjectStore().add(ProjectMapEntry(
            name=name, vault_root=vault, cwd_patterns=cwd_patterns or [],
        ))

    return _register
```

For each existing test that called `cli_main(["lint", "run", "--vault", str(vault)])`, replace with:

```python
register_project("p", vault)
cli_main(["lint", "run", "--project", "p"])
```

Existing tests touching `MNEMOS_VAULT_ROOT` env: delete those lines.

This is mechanical — locate via:
```
grep -nl "MNEMOS_VAULT_ROOT\|--vault" tests/
```

Apply same pattern across each match.

- [ ] **Step 5: Run full test suite (fast)**

```
pytest -q -x
```

Expected: green or red on tests yet to be migrated. Iterate fixing tests until green.

- [ ] **Step 6: ruff + mypy on cli.py**

- [ ] **Step 7: Commit**

```
refactor(cli): existing subgroups migrate from --vault PATH to --project NAME

Plan #13b-α Task 10. Hard cut on MNEMOS_VAULT_ROOT env (per design §2.6
and spec §13 explicit setup model). All read/write subgroups (lint, jobs,
page, trash, sessions, lost-sessions, metrics, ontology, ingest) now
take --project NAME and resolve vault via project-map. Auto-resolves
from cwd when --project omitted. mnemos daemon start keeps --vault PATH
for single-vault mode (becomes --project NAME[, NAME]... in #13b-β).
Tests migrated to register_project() conftest fixture.
```

---

## Task 11: Hook resolver integration

**Files:**
- Modify: `hooks/session_end.py`
- Create: `tests/hooks/test_session_end_resolver.py`

- [ ] **Step 1: Read current `hooks/session_end.py` to understand existing flow.**

- [ ] **Step 2: Write failing tests**

```python
# tests/hooks/test_session_end_resolver.py
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest


HOOK = Path(__file__).resolve().parents[2] / "hooks" / "session_end.py"


def _run_hook(payload: dict, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload).encode("utf-8"),
        env=env,
        capture_output=True,
        timeout=10,
    )


@pytest.fixture
def isolated_home(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env.pop("MNEMOS_VAULT_ROOT", None)
    return tmp_path, env


def test_hook_silent_skip_when_cwd_unmatched(isolated_home):
    home, env = isolated_home
    transcript = home / "x.jsonl"
    transcript.write_text("{}")
    cwd = home / "elsewhere"
    cwd.mkdir()
    payload = {"transcript_path": str(transcript), "cwd": str(cwd)}
    r = _run_hook(payload, env)
    assert r.returncode == 0
    assert b"not registered" in r.stderr or b"lost-sessions" in r.stderr


def test_hook_resolves_match_and_falls_back_to_subprocess(isolated_home, tmp_path):
    home, env = isolated_home
    # Pre-seed project-map
    from claude_mnemos.state.projects import ProjectStore, ProjectMapEntry
    # Run via subprocess so HOME applies — but we need to use the env's HOME
    # by invoking python with that env to add the project. Simpler: write the
    # JSON file directly.
    map_dir = home / ".claude-mnemos"
    map_dir.mkdir()
    (map_dir / "project-map.json").write_text(json.dumps({
        "version": 1,
        "projects": [{
            "name": "x",
            "vault_root": str(home / "v"),
            "cwd_patterns": [str(home / "code" / "x")],
        }],
    }))
    cwd = home / "code" / "x"
    cwd.mkdir(parents=True)
    transcript = home / "t.jsonl"
    transcript.write_text("{}")
    # No daemon running -> hook should fall back to subprocess.
    payload = {"transcript_path": str(transcript), "cwd": str(cwd)}
    r = _run_hook(payload, env)
    # Hook itself returns 0 (it never blocks). The subprocess it spawned
    # is detached; we only assert hook printed something useful or exited 0.
    assert r.returncode == 0
```

(More tests can be added to mock httpx.post for the daemon-online path, but end-to-end is captured by the slow E2E in Task 15.)

- [ ] **Step 3: Modify `hooks/session_end.py`**

Replace existing `MNEMOS_VAULT_ROOT` lookup with project resolution. New skeleton:

```python
"""SessionEnd hook: resolve cwd via project-map -> POST /api/jobs or fallback subprocess.

Never blocks. Silent skip + stderr message on:
- ambiguous cwd (config bug)
- no matching project (transcript stays in lost-sessions)
- daemon offline AND subprocess fallback fails
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Hook lives outside the package; allow it to import from claude_mnemos.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from claude_mnemos.mapping.resolver import ProjectResolver, ResolverAmbiguityError  # noqa: E402
from claude_mnemos.state.settings import SettingsStore  # noqa: E402

DEFAULT_PORT = 5757


def main() -> int:
    if os.environ.get("MNEMOS_INGEST_RUNNING") == "1":
        return 0  # recursion guard
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(f"mnemos session_end: invalid stdin payload: {exc}", file=sys.stderr)
        return 0
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        print("mnemos session_end: missing transcript_path", file=sys.stderr)
        return 0
    cwd_raw = payload.get("cwd") or os.getcwd()
    cwd = Path(cwd_raw)

    try:
        entry = ProjectResolver().resolve_by_cwd(cwd)
    except ResolverAmbiguityError as exc:
        print(f"mnemos session_end: ambiguous project for cwd {cwd}: {exc}", file=sys.stderr)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"mnemos session_end: resolver failed: {exc}", file=sys.stderr)
        return 0

    if entry is None:
        print(
            f"mnemos session_end: cwd {cwd} not in project-map; "
            "transcript остаётся в lost-sessions",
            file=sys.stderr,
        )
        return 0

    port = _daemon_port()
    daemon_url = os.environ.get("MNEMOS_DAEMON_URL", f"http://127.0.0.1:{port}")
    if _try_post_jobs(daemon_url, transcript_path, entry.name):
        return 0

    _fallback_subprocess(transcript_path, entry.name)
    return 0


def _daemon_port() -> int:
    try:
        return SettingsStore().get_global().daemon_port
    except Exception:  # noqa: BLE001
        return DEFAULT_PORT


def _try_post_jobs(url: str, transcript_path: str, project_name: str) -> bool:
    try:
        import httpx
        r = httpx.post(
            f"{url}/api/jobs",
            json={
                "kind": "ingest",
                "payload": {"transcript_path": transcript_path, "project_name": project_name},
            },
            timeout=2.0,
        )
        return r.status_code < 300
    except Exception:  # noqa: BLE001
        return False


def _fallback_subprocess(transcript_path: str, project_name: str) -> None:
    env = {**os.environ, "MNEMOS_INGEST_RUNNING": "1"}
    try:
        subprocess.Popen(
            [sys.executable, "-m", "claude_mnemos", "ingest",
             transcript_path, "--project", project_name],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as exc:
        print(f"mnemos session_end: subprocess fallback failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, pass.**

- [ ] **Step 5: ruff + commit**

```
feat(hook): session_end resolves cwd via project-map

Plan #13b-α Task 11. hooks/session_end.py:
- Reads cwd from payload (fallback os.getcwd()).
- Resolves project via ProjectResolver. No match -> silent skip + stderr
  notice ("transcript остаётся в lost-sessions"). Plan #13a's
  lost-sessions механизм поднимет file later.
- Match -> POST /api/jobs to daemon (port from GlobalSettings.daemon_port).
- Daemon offline -> detached subprocess `mnemos ingest --project NAME`.
- Recursion guard via MNEMOS_INGEST_RUNNING=1.
- Hook never blocks (returns 0 unconditionally).
```

---

## Task 12: MCP server — `--auto-resolve` / `--project` / degraded mode

**Files:**
- Modify: `claude_mnemos/mcp/__main__.py`
- Modify: `claude_mnemos/mcp/config.py`
- Add tests to: `tests/mcp/test_main.py` (or create one if missing)

- [ ] **Step 1: Read current `claude_mnemos/mcp/__main__.py`** to understand how server is built today.

- [ ] **Step 2: Write failing tests**

```python
# tests/mcp/test_main_resolver.py (create)
from __future__ import annotations
from pathlib import Path
import pytest
from claude_mnemos.mcp.__main__ import resolve_vault_for_mcp, parse_args


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_explicit_vault(tmp_path):
    args = parse_args(["--vault", str(tmp_path / "v")])
    vault, err = resolve_vault_for_mcp(args)
    assert vault == tmp_path / "v"
    assert err is None


def test_explicit_project_unknown(tmp_path):
    args = parse_args(["--project", "nope"])
    vault, err = resolve_vault_for_mcp(args)
    assert vault is None
    assert err and "not registered" in err


def test_auto_resolve_no_match_returns_error_not_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = parse_args(["--auto-resolve"])
    vault, err = resolve_vault_for_mcp(args)
    assert vault is None
    assert err is not None


def test_auto_resolve_hit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from claude_mnemos.state.projects import ProjectStore, ProjectMapEntry
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[str(tmp_path)]))
    args = parse_args(["--auto-resolve"])
    v, err = resolve_vault_for_mcp(args)
    assert v == vault
    assert err is None


def test_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        parse_args(["--vault", str(tmp_path), "--project", "x"])
```

- [ ] **Step 3: Modify `claude_mnemos/mcp/__main__.py`**

Replace argparse + main with:

```python
"""MCP server entrypoint.

Resolution order (mutually exclusive flags):
  --vault PATH       direct vault path (legacy escape hatch)
  --project NAME     resolve via ~/.claude-mnemos/project-map.json
  --auto-resolve     resolve cwd via project-map (default in plugin .mcp.json)

When --auto-resolve / --project produce no match, the server still starts
in *degraded mode*: every tool call returns a single error TextContent
with a hint how to fix the config. Crashing on startup is worse — Claude
Code re-spawns crashed servers, which leads to a tight error loop.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from claude_mnemos.mapping.resolver import ProjectResolver, ResolverAmbiguityError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="claude_mnemos.mcp")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--vault", type=Path, help="Direct vault path (legacy)")
    group.add_argument("--project", type=str, help="Project name in ~/.claude-mnemos/project-map.json")
    group.add_argument("--auto-resolve", action="store_true",
                       help="Resolve vault from cwd via project-map.json")
    return parser.parse_args(argv)


def resolve_vault_for_mcp(args: argparse.Namespace) -> tuple[Path | None, str | None]:
    if args.vault is not None:
        return args.vault, None
    resolver = ProjectResolver()
    if args.project:
        entry = resolver.resolve_by_name(args.project)
        if entry is None:
            return None, f"project {args.project!r} not registered in project-map"
        return Path(entry.vault_root), None
    # default + auto-resolve
    cwd = Path.cwd()
    try:
        entry = resolver.resolve_by_cwd(cwd)
    except ResolverAmbiguityError as exc:
        return None, str(exc)
    if entry is None:
        return None, (
            f"cwd {cwd} not registered in project-map. "
            "Run: mnemos project add --name NAME --vault PATH "
            "--cwd-pattern \"<cwd_glob>\""
        )
    return Path(entry.vault_root), None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault, error = resolve_vault_for_mcp(args)
    if error or vault is None:
        from claude_mnemos.mcp.degraded import build_degraded_server
        server = build_degraded_server(error or "no vault resolved")
    else:
        from claude_mnemos.mcp.server import build_server  # existing module
        server = build_server(vault)
    asyncio.run(_serve(server))
    return 0


async def _serve(server) -> None:
    from mcp.server.stdio import stdio_server
    async with stdio_server() as streams:
        await server.run(*streams, server.create_initialization_options())


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Create `claude_mnemos/mcp/degraded.py`**

```python
"""Degraded MCP server: started when vault resolution fails. Every tool
returns a single TextContent with the failure reason and a fix hint.
"""

from __future__ import annotations

from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool


def build_degraded_server(error_message: str) -> Server:
    server: Server = Server("claude-mnemos-mcp")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        # Mirror the production tool list shapes minimally so the LLM sees
        # consistent names, even though they all error.
        return [
            Tool(name=t, description=f"(degraded) {error_message}", inputSchema={"type": "object"})
            for t in (
                "list_pages", "read_page", "search_pages", "get_status",
                "get_recent_activity", "undo_operation", "create_snapshot",
                "restore_snapshot", "delete_snapshot", "run_lint",
                "get_lint_results", "list_suggestions",
                "apply_ontology_suggestion", "propose_ontology_change",
            )
        ]

    @server.call_tool()
    async def _call_tool(_name: str, _arguments: dict[str, Any]) -> list[TextContent]:
        return [TextContent(
            type="text",
            text=(
                "claude-mnemos MCP is in degraded mode: " + error_message + ". "
                "Fix project-map.json and restart Claude Code."
            ),
        )]

    return server
```

If the existing tool registry exposes a list of tool names, import that to keep them in sync rather than hardcoding the literal list — adjust this block to whatever is canonical in `claude_mnemos/mcp/server.py`.

- [ ] **Step 5: Modify `claude_mnemos/mcp/config.py` — make `vault_root` optional for degraded server**

Change `vault_root: Path` to `vault_root: Path | None = None`. Adjust call sites that read `cfg.vault_root` to handle None gracefully (or only construct `MCPConfig` in non-degraded path).

- [ ] **Step 6: Run tests, pass; ruff + mypy + commit**

```
feat(mcp): --auto-resolve / --project flags + degraded mode

Plan #13b-α Task 12. claude_mnemos/mcp/__main__.py + degraded.py:
- Mutually exclusive: --vault PATH | --project NAME | --auto-resolve.
- Default in plugin .mcp.json: --auto-resolve (cwd via project-map).
- No match -> degraded server: tools registered with names but every
  call returns TextContent with the error + fix hint. Avoids the
  re-spawn loop that crashing causes in Claude Code.
- mcp/config.py: vault_root now Path | None (degraded path).
```

---

## Task 13: Update `.mcp.json` plugin manifest

**Files:**
- Modify: `.mcp.json`

- [ ] **Step 1: Read current `.mcp.json`.**

- [ ] **Step 2: Edit args**

Replace the existing `args` array entry that contains `--vault ${MNEMOS_VAULT_ROOT}` with `--auto-resolve`. Resulting:

```json
{
  "mcpServers": {
    "mnemos": {
      "command": "python",
      "args": ["-m", "claude_mnemos.mcp", "--auto-resolve"]
    }
  }
}
```

- [ ] **Step 3: Commit**

```
feat(plugin): MCP server uses --auto-resolve via project-map

Plan #13b-α Task 13. .mcp.json now passes --auto-resolve instead of
--vault ${MNEMOS_VAULT_ROOT}. The MCP server resolves the vault from
the cwd of the Claude Code session via project-map.json. Falls back
to degraded mode when cwd is unregistered (per Task 12).
```

---

## Task 14: README + CHANGELOG migration section

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md` (create if missing)

- [ ] **Step 1: Add Plan #13b-α status block to `README.md`**

After the existing "Status" / "What's done" section, append:

```markdown
### Plan #13b-α — Settings + project-map foundation (2026-04-27)

- `~/.claude-mnemos/project-map.json` now routes cwd → vault.
- Per-project settings: `~/.claude-mnemos/settings/<project>.json` (9 spec §12.8 groups).
- Global settings: `~/.claude-mnemos/global-settings.json`.
- New CLI: `mnemos project {add,list,show,update,remove,resolve}`,
  `mnemos settings {get,set,reset} --project NAME | --global`.
- All other CLI commands now take `--project NAME` (auto-resolves via cwd if omitted).
- Daemon at startup applies `snapshots.retention_days` + `snapshots.daily_enabled`
  for its registered vault; PATCH /api/settings/{project} reloads live.
- MCP server defaults to `--auto-resolve` (cwd → project-map). Degraded mode if no match.
- SessionEnd hook resolves cwd → project; unmatched cwd → silent skip + lost-sessions.
- One-shot migration: PID file moved from `~/.mnemos/` to `~/.claude-mnemos/`.

#### Migration from previous versions

If you previously set `MNEMOS_VAULT_ROOT`, register your vault explicitly:

\```bash
mnemos project add \
  --name claude-mnemos \
  --vault $MNEMOS_VAULT_ROOT \
  --cwd-pattern "$(dirname $MNEMOS_VAULT_ROOT)/*"
unset MNEMOS_VAULT_ROOT
\```

Then restart any running daemon so it can read your project's settings.

The `MNEMOS_VAULT_ROOT` env var is no longer read by anything (CLI, hook,
MCP server, daemon).
```

- [ ] **Step 2: Add CHANGELOG entry**

Append to top of `CHANGELOG.md`:

```markdown
## [Unreleased] — Plan #13b-α

### Added
- `~/.claude-mnemos/project-map.json` (cwd → vault routing)
- Per-project + global settings persistence
- `mnemos project` and `mnemos settings` CLI subgroups
- `/api/projects/*` and `/api/settings/*` REST endpoints
- MCP `--auto-resolve` / `--project` flags + degraded mode

### Changed
- All existing CLI subgroups: `--vault PATH` → `--project NAME`
- `.mcp.json` uses `--auto-resolve` instead of `--vault ${MNEMOS_VAULT_ROOT}`
- Daemon applies project's `snapshots` settings at startup; reloads on PATCH
- PID file moved from `~/.mnemos/` to `~/.claude-mnemos/` (one-shot migration)

### Removed
- `MNEMOS_VAULT_ROOT` env var support (hard cut — see migration in README)
```

- [ ] **Step 3: Commit**

```
docs(13b-alpha): README + CHANGELOG for project-map + settings

Plan #13b-α Task 14. Documents the public surface, migration steps from
MNEMOS_VAULT_ROOT, and the one-shot PID-file move.
```

---

## Task 15: Slow E2E coverage

**Files:**
- Create: `tests/e2e/test_project_settings_e2e.py`

- [ ] **Step 1: Write failing tests** (subprocess daemon + REST round-trip)

```python
# tests/e2e/test_project_settings_e2e.py
from __future__ import annotations
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
import httpx
import pytest


pytestmark = pytest.mark.slow


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_ready(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{url}/api/health", timeout=0.5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"daemon at {url} did not become ready within {timeout}s")


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return tmp_path


def test_e2e_register_project_then_patch_settings(isolated_home):
    home = isolated_home
    vault = home / "v"
    vault.mkdir()
    port = _free_port()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["MNEMOS_DAEMON_PORT"] = str(port)
    proc = subprocess.Popen(
        [sys.executable, "-m", "claude_mnemos.daemon", "--vault", str(vault)],
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        _wait_until_ready(url)

        r = httpx.post(f"{url}/api/projects", json={
            "name": "myvault",
            "vault_root": str(vault),
            "cwd_patterns": [str(home / "code" / "*")],
        }, timeout=2.0)
        assert r.status_code == 201, r.text

        r = httpx.patch(f"{url}/api/settings/myvault", json={
            "snapshots": {"retention_days": 7, "daily_enabled": False},
        }, timeout=2.0)
        assert r.status_code == 200
        assert r.json()["snapshots"]["retention_days"] == 7

        # Persistence: file exists on disk
        sf = home / ".claude-mnemos" / "settings" / "myvault.json"
        data = json.loads(sf.read_text())
        assert data["snapshots"]["retention_days"] == 7
    finally:
        if sys.platform == "win32":
            import psutil
            try:
                psutil.Process(proc.pid).terminate()
            except Exception:
                proc.kill()
        else:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_e2e_resolve_via_cli(isolated_home, tmp_path):
    home = isolated_home
    vault = home / "v"
    vault.mkdir()
    cwd = home / "code" / "myproj"
    cwd.mkdir(parents=True)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env.pop("MNEMOS_VAULT_ROOT", None)

    # add project (offline; daemon not running)
    r = subprocess.run(
        [sys.executable, "-m", "claude_mnemos", "project", "add",
         "--name", "myproj", "--vault", str(vault), "--cwd-pattern", str(cwd)],
        env=env, capture_output=True, timeout=10,
    )
    assert r.returncode == 0, r.stderr.decode()

    # resolve from cwd
    r = subprocess.run(
        [sys.executable, "-m", "claude_mnemos", "project", "resolve",
         "--cwd", str(cwd), "--json"],
        env=env, capture_output=True, timeout=10,
    )
    assert r.returncode == 0, r.stderr.decode()
    data = json.loads(r.stdout.decode())
    assert data["name"] == "myproj"
```

- [ ] **Step 2: Run with `-m slow` marker**

```
pytest -m slow tests/e2e/test_project_settings_e2e.py -v
```

Expected: green.

- [ ] **Step 3: Commit**

```
test(e2e): subprocess daemon + project/settings REST round-trip

Plan #13b-α Task 15. tests/e2e/test_project_settings_e2e.py:
- Spin up daemon on a free port -> POST /api/projects ->
  PATCH /api/settings/{name} -> verify on-disk JSON.
- CLI offline path: `mnemos project add` then `mnemos project resolve`
  end-to-end via subprocess.
- Marked @pytest.mark.slow.
```

---

## Final review pass

- [ ] **Run full fast suite:** `pytest -q`
- [ ] **Run slow suite:** `pytest -q -m slow`
- [ ] **ruff + mypy strict:** `ruff check . && mypy --strict claude_mnemos`
- [ ] **Grep for remaining `MNEMOS_VAULT_ROOT`** in production code (tests may still reference for legacy assertions, but `claude_mnemos/` and `hooks/` and `.mcp.json` must be clean):

```
grep -rn "MNEMOS_VAULT_ROOT" claude_mnemos/ hooks/ .mcp.json
```
Expected: no matches.

- [ ] **Grep for remaining `~/.mnemos`** references in production code:

```
grep -rn '"\.mnemos"\|/.mnemos/' claude_mnemos/
```
Expected: only the legacy migration helper.

- [ ] **Confirm acceptance criteria from design §12** are all green by walking through them.

- [ ] **Code review subagent** (`general-purpose` or `code-reviewer` agent) over the diff `main..feat/13b-alpha-settings-projectmap`. Apply hotfixes before merge.

- [ ] **Merge non-FF to main:** `git checkout main && git merge --no-ff feat/13b-alpha-settings-projectmap` with summary commit message describing all 15 tasks. Push (if remote exists). Delete the feature branch locally.

---

## Open notes for implementing engineer

- `state/projects.py` and `state/settings.py` use `Path.home()` — this is monkeypatch-friendly via `HOME` / `USERPROFILE`. All tests use that pattern already.
- `Pydantic Path` field auto-coerces from string in JSON body, but emits as string in `model_dump(mode="json")` — compare carefully in assertions.
- `fnmatch.fnmatchcase` does NOT treat `**` specially — it matches `**` as two literal asterisks. If the user writes a deep glob like `~/projects/**/repo`, it will NOT recurse. Document this in `mnemos project add --help` and accept it as a Plan #13b-α limitation. (Plan #13b-β can switch to `pathlib.PurePath.match` if needed.)
- For tests that monkeypatch HOME on Windows, also monkeypatch USERPROFILE — `Path.home()` consults USERPROFILE first on Windows.
- `MnemosDaemon._reload_settings_lint_schedule_TODO` is intentionally absent — Plan #11+ owns scheduled lint. When that lands, extend `reload_settings` to handle it.
- `subprocess` for the hook fallback needs `close_fds=True` on POSIX and `creationflags=subprocess.DETACHED_PROCESS` on Windows for proper detachment. The Plan #11 hook already does this — copy the exact incantation from there if needed.

---

## Self-review checklist (post-write)

- [x] Spec §10.1 (single-owner state files) — daemon owns writes via REST; CLI fallbacks documented.
- [x] Spec §10.3 endpoints — `/api/projects/*` (Task 4) + `/api/settings/*` (Task 5).
- [x] Spec §12.8 (9 setting groups) — `state/settings.py` covers all of them.
- [x] Spec §13 onboarding flag (`~/.claude-mnemos/onboarding-complete`) — out of scope (Plan #14).
- [x] Spec §5.5 PID file location — Task 6 fixes the legacy `~/.mnemos/` path.
- [x] No placeholders ("TBD"/"add error handling"/etc.) — every step has concrete code or commands.
- [x] Type consistency — exception names (`ProjectMapCorruptError`, `ProjectNameConflictError`, `ResolverAmbiguityError`, `SettingsCorruptError`) match across tasks; helper names (`get_by_dot_path`, `patch_dict_for_dot_path`, `deep_merge`) match across tasks.
- [x] Dependency order — state models → resolver → REST → daemon consumption → CLI → hook/MCP → docs → E2E. No task references something not yet defined.
- [x] Migration path — Task 6 + README in Task 14.
