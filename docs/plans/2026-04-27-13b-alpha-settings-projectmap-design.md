# Design: Settings + project-map foundation (Plan #13b-α)

**Status:** drafted, awaiting Yarik's review.
**Date:** 2026-04-27
**Author:** Claude.
**Predecessor:** `2026-04-27-sessions-metrics-design.md` (Plan #13a, merged in `958dcf4` + 3 hotfixes).
**Successor planned:** Plan #13b-β (Multi-vault daemon refactor + cross-vault metrics aggregation) → Plan #13c (SessionStart adaptive context) → Plan #14 (Dashboard + Onboarding wizard).

**Decomposition note:** spec'овский мега-Plan #13b разделён на два sub-plan'а:

- **#13b-α (этот)** — foundation: `~/.claude-mnemos/project-map.json` + per-project + global settings persistence + REST/CLI/plugin integration. Daemon остаётся single-vault, но становится settings-aware для своего vault'а.
- **#13b-β** — multi-vault daemon (один daemon владеет N vault'ами одновременно с per-vault scheduler/observer/jobs) + real `/api/metrics/usage/by-project` aggregation across vaults.

Между α и β код в `main` остаётся живым и работающим: один daemon на один vault, но с persisted settings и project-map'ом готовым к multi-vault expansion.

---

## 1. Goal

Дать инфраструктуру конфигурации и роутинга, которая:

1. Заменяет один env `MNEMOS_VAULT_ROOT` явной map'ой `~/.claude-mnemos/project-map.json` (cwd → vault routing).
2. Персистит per-project settings (9 групп spec'а §12.8) + global settings — даже те поля, чьи consumers пока не реализованы (foundation для Plan #13b-β/#13c/#14).
3. Резолвит cwd новой Claude Code сессии в правильный vault через project-map (используется SessionEnd hook + MCP server `--auto-resolve`).
4. Обрабатывает unmatched cwd через уже существующий lost-sessions механизм (Plan #13a) — silent skip + транскрипт автоматически попадает в `mnemos lost-sessions list`.

После Plan #13b-α:

```bash
# Project map CRUD (writes via daemon REST, reads direct)
mnemos project add --name claude-mnemos --vault D:/code/claude-mnemos --cwd-pattern "~/code/claude-mnemos*"
mnemos project list                                    # table: name, vault, patterns
mnemos project show claude-mnemos                      # entry + settings combined
mnemos project update claude-mnemos --add-cwd-pattern "~/code/cm-fork*"
mnemos project remove old-project --yes
mnemos project resolve [--cwd PATH]                    # debug: какой project matched

# Settings CRUD (per-project + global)
mnemos settings get --project claude-mnemos
mnemos settings get --project claude-mnemos lint.enabled_rules
mnemos settings set --project claude-mnemos lint.enabled_rules '["frontmatter_required","wikilink_target_exists"]'
mnemos settings reset --project claude-mnemos lint
mnemos settings get --global
mnemos settings set --global default_model "claude-haiku-4-5-20251001"
```

REST для daemon'а:

```
GET    /api/projects                         list ProjectMapEntry
GET    /api/projects/{name}                  entry + settings combined view
POST   /api/projects                         add (validates name uniqueness, resolves vault_root)
PATCH  /api/projects/{name}                  update fields в map
DELETE /api/projects/{name}                  remove + cleanup settings/<name>.json

GET    /api/settings/{name}                  ProjectSettings JSON
PATCH  /api/settings/{name}                  partial merge
GET    /api/settings/global                  GlobalSettings JSON
PATCH  /api/settings/global                  partial merge
```

### Что НЕ даёт (явно отложено)

- **Multi-vault daemon refactor** (один daemon владеет N vault'ами, per-vault observer/scheduler/jobs) → **Plan #13b-β**.
- **Cross-vault `/api/metrics/usage/by-project` aggregation** → **Plan #13b-β** (в α остаётся single-entry stub из Plan #13a).
- **Auto-discovery scan** (`mnemos project scan`) — итерация `~/.claude/projects/` + `~/Documents/Obsidian/` для предложения unregistered projects → **Plan #14** (часть onboarding wizard'а §13.2 шаг 3).
- **Frontend Settings View** (vertical tabs §12.8) → **Plan #14**.
- **Onboarding wizard** (`~/.claude-mnemos/onboarding-complete` flag, `POST /api/onboarding/complete`) → **Plan #14**.
- **Реальное использование `lifecycle`, `prompts`, `telemetry`, `ontology.auto_mode`, `watchdog.mode` settings** consumers'ами кода — будущие планы. В α: persistence + REST CRUD + CLI surface, чтение этих полей кодом — нет (write-only foundation для consumers, которые появятся позже).
- **Lookup performance** (in-memory cache project-map с TTL/inotify) — α использует direct file read на каждом resolve. Если станет узким местом → Plan #13b-β.

---

## 2. Architectural choices

### 2.1 Storage layout — split files (not single inline JSON)

```
~/.claude-mnemos/
  project-map.json           # routing only: name + vault_root + cwd_patterns
  settings/
    <project_name>.json      # per-project ProjectSettings (9 spec'овских групп)
  global-settings.json       # GlobalSettings (locale, daemon_port, default_*)
  daemon.pid                 # existing
  onboarding-complete        # Plan #14 wizard flag
```

**Rationale:**

- Spec API в §10.3 разделяет `/api/projects/{name}` (routing/metadata) и `/api/settings/{project}` (behavior config) — два endpoint tree'а указывают на split storage.
- Spec вводит `/api/settings/global` (третий слой) — естественный home в отдельном `global-settings.json`.
- Isolation: dashboard PATCH'ит settings одного project'а без блокировки чтения map'а; concurrent edits по разным проектам не конфликтуют.
- Spec model `Project` в §10.2 включает settings inline — это model в памяти (компонуется при чтении через `load_project_view(name) → ProjectView`), не physical storage.
- Атомарность writes — через существующий `core/atomic.py` (write-then-rename на Windows safe).

**Trade-off accepted:** для рендера combined view (`mnemos project show NAME` или `GET /api/projects/{name}`) нужно прочитать два файла — копеечный overhead для maps на 5–20 проектов.

### 2.2 Home directory — `~/.claude-mnemos/` (not `~/.mnemos/`)

Spec явно использует `~/.claude-mnemos/` в §5.5 (`PID_FILE = Path.home() / ".claude-mnemos" / "daemon.pid"`) и §13.1 (`~/.claude-mnemos/onboarding-complete` flag). Имя self-describing, низкая вероятность collision с другими `mnemos`-tools.

Текущий `daemon.pid` уже лежит в `~/.claude-mnemos/` (см. `claude_mnemos/daemon/lockfile.py`) — миграции не требуется.

### 2.3 Project identifier — user-supplied `name` (string slug)

Spec API во всех endpoints ссылается на `{name}` (`/api/projects/{name}`, `/api/settings/{project}`, `/api/lint/{project}`) — name is the contract.

Validation: `^[a-z0-9][a-z0-9_-]{0,63}$` (URL-safe, FS-safe для settings/<name>.json, REST-path-safe).

CLI offer'ит default slug from `vault_root.name.lower()` (`/d/code/claude-mnemos` → `claude-mnemos`), но user может override через `--name`. Уникальность enforce в storage layer (load → check duplicates → `ProjectNameConflictError → 409`).

### 2.4 cwd_patterns matching — glob (fnmatch) + most-specific wins

Algorithm:

1. Для каждого `ProjectMapEntry`, для каждого `pattern` в `cwd_patterns`:
   - Expand `~` + `Path.resolve()` обе стороны (cwd и pattern).
   - На Windows — lowercase обе стороны перед matching (case-insensitive paths).
   - `fnmatch.fnmatchcase(normalized_cwd, normalized_pattern)`.
2. Собрать все `(entry, pattern, len(normalized_pattern))` matches.
3. Если пусто → return `None`.
4. Если один → return entry.
5. Если несколько → sort по `len(pattern)` desc, take first. Если top-2 имеют equal length и они из разных entries → `ResolverAmbiguityError` (config bug).

**Rationale:**

- Glob покрывает ~95% real cases: exact prefix как degenerate `~/code/claude-mnemos` (без wildcards), prefix wildcard `~/code/foo*`, deep glob `~/projects/**/repo`.
- Most-specific wins детерминистично: `~/code/claude-mnemos` побеждает `~/code/*` для cwd `/code/claude-mnemos/sub`. Tie на одинаковой длине из разных entries — это user config bug, fail loudly.
- Regex отвергнут: overkill, error-prone (escape Windows backslashes), пользователь должен знать regex.
- Exact prefix отвергнут: не покрывает «все vault'ы под `~/projects/*`» одним правилом.

### 2.5 Settings scope — full spec §12.8 (9 groups)

Принято решение **«все поля как в spec'е»**, даже те у кого нет consumer'а в Plan #13b-α. Trade-off: ~60% полей будут write-only до близких планов (lifecycle/prompts/telemetry/ontology/watchdog mode), но schema evolution дешевле сейчас (один shot) чем потом (множественные migrations при каждом новом consumer'е).

См. §3 ниже за полной Pydantic model'ью.

### 2.6 Backwards compat — hard cut на `MNEMOS_VAULT_ROOT`

После Plan #13b-α env `MNEMOS_VAULT_ROOT` не читается **нигде** (CLI, hook, MCP, daemon).

**Rationale:**

- Single user (Yarik), нет deployed installed base — clean break дёшев.
- Spec §13 onboarding wizard описывает explicit setup flow (vault location step + detected projects scan), не auto-magic env fallback.
- Mixed mode (env как fallback) накапливает technical debt; в Plan #13b-β multi-vault routing станет ещё запутаннее с двумя источниками истины.

**Migration path:** документированная one-shot команда в README + CHANGELOG:

```bash
mnemos project add --name claude-mnemos \
  --vault $MNEMOS_VAULT_ROOT \
  --cwd-pattern "~/code/claude-mnemos*"
unset MNEMOS_VAULT_ROOT
```

После этого daemon/hook/MCP резолвят vault через project-map.

### 2.7 Daemon в α — settings-aware для своего vault'а, но всё ещё single-vault

Daemon продолжает запускаться `mnemos daemon start --vault PATH` (single vault hardcoded). Multi-vault refactor — Plan #13b-β.

При старте daemon:

1. Читает `~/.claude-mnemos/project-map.json`.
2. Ищет entry где `vault_root == config.vault_root` (через `ProjectResolver.resolve_by_vault`).
3. Если нашёл → загружает `<project_name>.json` settings → применяет:
   - `snapshots.retention_days` → override `DaemonConfig.retention_days` (existing field, used by `backups_cleanup_task`).
   - `snapshots.daily_enabled` → если False → не регистрирует daily snapshot scheduler job (или регистрирует и `pause`'ит).
   - `lint.schedule` → если задан + Plan #11 scheduled lint существует, регистрирует. На момент Plan #13b-α scheduled lint runner не реализован → ignored, но логируется как «scheduled lint not yet implemented (Plan #11+)».
   - Остальные поля settings — exposed через `/api/settings/{project}` GET для clients, но daemon сам их не consum'ит сейчас (foundation для β/c).
4. Если project не найден → daemon работает на defaults (как сейчас) + добавляет `Alerts.add(kind="handler_error", path=str(vault_root), message="daemon vault not registered in project-map; using built-in defaults")`. Это soft warning, daemon живой.

**Reload semantics:** PATCH `/api/settings/{project}` → daemon после write проверяет совпадает ли `{project}` со своим vault'ом, и если да:

- Reload in-memory `ProjectSettings` instance.
- Reschedule snapshot/lint jobs через `scheduler.modify_job` / `remove_job + add_job`.
- Прочие vaults daemon игнорирует (он single-vault).

### 2.8 Hook / MCP / CLI integration

**SessionEnd hook (`hooks/session_end.py`):**

- Резолвит `Path.cwd()` через `ProjectResolver.resolve_by_cwd`.
- Match → POST `/api/jobs` к daemon с `{kind: "ingest", payload: {transcript_path, project_name}}`. Если daemon offline / non-2xx / timeout → fallback на subprocess `mnemos ingest --project NAME <transcript>` (как Plan #11 fallback, но с `--project` вместо `--vault`).
- No match → silent skip + stderr message `"cwd <path> not registered in project-map; transcript остаётся в lost-sessions"`. Транскрипт остаётся на диске в `~/.claude/projects/<projid>/<sid>.jsonl`, и `mnemos lost-sessions scan` подхватит его (Plan #13a механизм). User потом вручную `mnemos lost-sessions import <sid> --project NAME`.

**MCP server (`claude_mnemos/mcp/__main__.py`):**

- Старый CLI: `python -m claude_mnemos.mcp --vault PATH` (required).
- Новый: `python -m claude_mnemos.mcp [--auto-resolve | --project NAME | --vault PATH]` (mutually exclusive).
- `--auto-resolve` (default в plugin `.mcp.json`): резолвит `Path.cwd()` через map. Если no match → MCP server **не crash'ится на startup** (Claude Code не любит crashing MCP servers — теряются tools). Instead: server возвращает один special TextContent на каждый tool call: `"MCP server: cwd <path> not registered in project-map. Run: mnemos project add --name NAME --vault PATH --cwd-pattern \"<cwd_glob>\""`.
- `--project NAME` — explicit override для тестов и non-plugin usage (e.g. dev iteration).
- `--vault PATH` — escape hatch для legacy и тестов которые крутят MCP без map'а. Deprecated в α, удалится в β.

**`.mcp.json` plugin manifest** (Plan #7) обновляется:

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

**CLI commands:**

Все existing `--vault PATH` flags → `--project NAME` (вызывают `ProjectResolver.resolve_by_name → entry.vault_root`). Если `--project` не передан, CLI пытается auto-resolve через cwd. Если ни то ни другое → user-friendly error:

```
Error: --project NAME required, or run from registered project directory.
Registered projects: <name1>, <name2>, ...
Or add new: mnemos project add --name NAME --vault PATH --cwd-pattern PATTERN
```

---

## 3. Pydantic models — детально

### 3.1 `claude_mnemos/state/projects.py`

```python
from __future__ import annotations
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

PROJECT_NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"

class ProjectMapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=PROJECT_NAME_PATTERN)
    vault_root: Path                 # absolute, expanded
    cwd_patterns: list[str]          # glob patterns, expanded at match-time

class ProjectMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    projects: list[ProjectMapEntry] = []

class ProjectMapError(Exception): ...
class ProjectNotFoundError(ProjectMapError): ...
class ProjectNameConflictError(ProjectMapError): ...
class ProjectMapCorruptError(ProjectMapError): ...
class ResolverAmbiguityError(ProjectMapError):
    """Two entries with same-length matching pattern for same cwd."""
```

### 3.2 `claude_mnemos/state/settings.py`

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class AutoIngestSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    mode: Literal["auto", "hybrid", "manual"] = "auto"

class LintSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schedule: str | None = None      # cron expression — used by Plan #11+ scheduler
    enabled_rules: list[str] | None = None  # None = all rules
    autofix_on_save: bool = False    # used by Plan #11+ watchdog autofix

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
    custom_system_path: str | None = None        # path relative to vault, or absolute
    custom_extract_user_path: str | None = None

class TelemetrySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opt_in: bool = False

class IngestOverrides(BaseModel):
    """Override Config defaults from claude_mnemos/config.py per-project."""
    model_config = ConfigDict(extra="forbid")
    model: str | None = None
    language_hint: Literal["auto", "uk", "ru", "en"] | None = None
    max_input_tokens: int | None = None
    context_limit: int | None = None  # for Plan #13c adaptive context

class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    locale: Literal["uk", "ru", "en"] | None = None  # None = use global
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

class SettingsError(Exception): ...
class SettingsNotFoundError(SettingsError): ...
class SettingsCorruptError(SettingsError): ...
```

### 3.3 Combined view (in-memory composition, не storage)

```python
# state/projects.py

class ProjectView(BaseModel):
    """Combined view: ProjectMapEntry + ProjectSettings.
    Returned by `mnemos project show NAME` and `GET /api/projects/{name}`.
    """
    model_config = ConfigDict(extra="forbid")
    name: str
    vault_root: Path
    cwd_patterns: list[str]
    settings: ProjectSettings
```

---

## 4. Resolver — `claude_mnemos/mapping/resolver.py`

```python
from __future__ import annotations
import fnmatch
import sys
from pathlib import Path
from claude_mnemos.state.projects import (
    ProjectMap, ProjectMapEntry, ProjectMapCorruptError,
    ResolverAmbiguityError,
)
from claude_mnemos.state.atomic import atomic_read_json  # via core/atomic
# ... constants
HOME_CONFIG = Path.home() / ".claude-mnemos"
PROJECT_MAP_PATH = HOME_CONFIG / "project-map.json"

def _normalize_for_match(p: str | Path) -> str:
    s = str(Path(p).expanduser().resolve())
    return s.lower() if sys.platform == "win32" else s

class ProjectResolver:
    def __init__(self, map_path: Path = PROJECT_MAP_PATH):
        self.map_path = map_path

    def _load(self) -> ProjectMap:
        if not self.map_path.exists():
            return ProjectMap()
        try:
            data = json.loads(self.map_path.read_text(encoding="utf-8"))
            return ProjectMap.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProjectMapCorruptError(...) from exc

    def list_all(self) -> list[ProjectMapEntry]: ...
    def resolve_by_name(self, name: str) -> ProjectMapEntry | None: ...
    def resolve_by_vault(self, vault_root: Path) -> ProjectMapEntry | None: ...
    def resolve_by_cwd(self, cwd: Path) -> ProjectMapEntry | None:
        cwd_norm = _normalize_for_match(cwd)
        candidates: list[tuple[ProjectMapEntry, str, int]] = []
        for entry in self._load().projects:
            for pattern in entry.cwd_patterns:
                pat_norm = _normalize_for_match(pattern)
                if fnmatch.fnmatchcase(cwd_norm, pat_norm):
                    candidates.append((entry, pattern, len(pat_norm)))
        if not candidates:
            return None
        candidates.sort(key=lambda t: t[2], reverse=True)
        # Tie check
        top_len = candidates[0][2]
        ties = [c for c in candidates if c[2] == top_len]
        unique_entries = {id(c[0]) for c in ties}
        if len(unique_entries) > 1:
            raise ResolverAmbiguityError(...)
        return candidates[0][0]
```

`ProjectStore` (write-side, single-owner via daemon):

```python
class ProjectStore:
    """Owns writes to project-map.json. Used only inside daemon REST handlers."""
    def __init__(self, map_path: Path = PROJECT_MAP_PATH):
        self.map_path = map_path
        self._lock = threading.Lock()

    def add(self, entry: ProjectMapEntry) -> None:
        with self._lock:
            current = self._load_or_empty()
            if any(e.name == entry.name for e in current.projects):
                raise ProjectNameConflictError(...)
            current.projects.append(entry)
            atomic_write_json(self.map_path, current.model_dump(mode="json"))

    def update(self, name: str, *, vault_root: Path | None = None,
               cwd_patterns: list[str] | None = None) -> ProjectMapEntry: ...
    def remove(self, name: str) -> None:
        with self._lock:
            current = self._load_or_empty()
            if not any(e.name == name for e in current.projects):
                raise ProjectNotFoundError(...)
            current.projects = [e for e in current.projects if e.name != name]
            atomic_write_json(self.map_path, current.model_dump(mode="json"))
            # Cleanup settings file (orphan would be confusing)
            settings_path = HOME_CONFIG / "settings" / f"{name}.json"
            settings_path.unlink(missing_ok=True)
```

`SettingsStore`:

```python
class SettingsStore:
    """Owns writes to settings/<name>.json + global-settings.json."""
    def __init__(self, root: Path = HOME_CONFIG):
        self.settings_dir = root / "settings"
        self.global_path = root / "global-settings.json"
        self._lock = threading.Lock()

    def get_project(self, name: str) -> ProjectSettings:
        path = self.settings_dir / f"{name}.json"
        if not path.exists():
            return ProjectSettings()  # all defaults
        try:
            return ProjectSettings.model_validate_json(path.read_text())
        except ValidationError as exc:
            raise SettingsCorruptError(...) from exc

    def patch_project(self, name: str, partial: dict) -> ProjectSettings:
        with self._lock:
            current = self.get_project(name)
            merged = current.model_copy(update=partial, deep=True)
            # Re-validate by round-trip
            validated = ProjectSettings.model_validate(merged.model_dump())
            self.settings_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.settings_dir / f"{name}.json",
                              validated.model_dump(mode="json"))
            return validated

    def get_global(self) -> GlobalSettings: ...
    def patch_global(self, partial: dict) -> GlobalSettings: ...
```

**Note on partial merge:** `model_copy(update=partial, deep=True)` shallow-merges top-level keys. Для nested partial (e.g. `{"lint": {"schedule": "..."}}`) requires deep merge — implement dedicated `_deep_merge_dicts` helper применяемый к `current.model_dump()` перед `model_validate(merged_dict)`. Это explicit pattern в `core/atomic.py` или нем оный module.

---

## 5. CLI surface — `claude_mnemos/cli.py`

### 5.1 `mnemos project` subgroup

```
mnemos project add --name NAME --vault PATH [--cwd-pattern PATTERN ...]
mnemos project list [--json]
mnemos project show NAME [--json]            # combined ProjectView
mnemos project update NAME [--vault PATH] [--add-cwd-pattern PATTERN ...] [--remove-cwd-pattern PATTERN ...]
mnemos project remove NAME [--yes]           # confirmation prompt unless --yes
mnemos project resolve [--cwd PATH] [--name NAME]  # debug
```

Read commands (`list`, `show`, `resolve`) — direct file access (zero daemon dep).
Write commands (`add`, `update`, `remove`) — POST/PATCH/DELETE через REST к daemon'у. Если daemon offline → exit 84 (existing code от Plan #11).

### 5.2 `mnemos settings` subgroup

```
mnemos settings get --project NAME [KEY] [--json]
mnemos settings set --project NAME KEY VALUE   # VALUE парсится как JSON (string in quotes)
mnemos settings reset --project NAME [KEY]     # KEY=None → reset all to defaults
mnemos settings get --global [KEY] [--json]
mnemos settings set --global KEY VALUE
mnemos settings reset --global [KEY]
```

`KEY` — dot-path: `lint.enabled_rules`, `snapshots.retention_days`, `ingest.model`. Resolution:

```python
def _get_by_dot_path(obj: BaseModel, key: str) -> Any:
    parts = key.split(".")
    cur = obj
    for p in parts:
        cur = getattr(cur, p)
    return cur

def _patch_dict_for_dot_path(key: str, value: Any) -> dict:
    """For 'lint.enabled_rules', return {'lint': {'enabled_rules': value}}."""
    parts = key.split(".")
    result = {}
    cur = result
    for p in parts[:-1]:
        cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value
    return result
```

`VALUE` — JSON-parsed: `'["a","b"]'` → list, `'true'` → bool, `'42'` → int, `'"foo"'` → string. CLI prints stderr help if parse fails.

### 5.3 Existing CLI commands — migration

Все subgroups, которые принимают `--vault PATH`, теперь принимают `--project NAME`:

- `mnemos ingest <jsonl> --project NAME [--model ...]` (was `<vault>` positional)
- `mnemos sessions {list, show, ingest} --project NAME` (was `--vault PATH`)
- `mnemos lost-sessions {...} --project NAME`
- `mnemos metrics {...} --project NAME`
- `mnemos page {edit, verify, archive, delete} --project NAME`
- `mnemos trash {list, restore, dismiss, empty} --project NAME`
- `mnemos lint {run, results, autofix} --project NAME`
- `mnemos jobs {...} --project NAME`
- `mnemos ontology {...} --project NAME`

Auto-resolve: если `--project` не передан, CLI пытается резолвить cwd. Match → use entry.vault_root. No match → error message со списком зарегистрированных projects + hint.

`mnemos daemon start` — остаётся `--vault PATH` (single-vault в α). В Plan #13b-β станет `--all` или `--project N1,N2,...`.

### 5.4 New exit codes

- **94** — `ProjectMapError` / `ProjectMapCorruptError`
- **95** — `SettingsError` / `SettingsCorruptError`
- **96** — `ResolverAmbiguityError` (config bug)
- **97** — `ProjectNotFoundError` (CLI auto-resolve failed)

(84 reused for daemon offline; 87 reused от jobs.)

---

## 6. REST endpoints — `claude_mnemos/daemon/routes/projects.py` + `settings.py`

```python
# routes/projects.py
@router.get("/api/projects", response_model=list[ProjectMapEntry])
def list_projects(...): ...

@router.get("/api/projects/{name}", response_model=ProjectView)
def get_project(name: str, ...): ...   # combined view

@router.post("/api/projects", response_model=ProjectMapEntry, status_code=201)
def create_project(body: ProjectCreate, ...): ...

@router.patch("/api/projects/{name}", response_model=ProjectMapEntry)
def update_project(name: str, body: ProjectUpdate, ...): ...

@router.delete("/api/projects/{name}", status_code=204)
def delete_project(name: str, ...): ...

# routes/settings.py
@router.get("/api/settings/{project}", response_model=ProjectSettings)
def get_project_settings(project: str, ...): ...

@router.patch("/api/settings/{project}", response_model=ProjectSettings)
def patch_project_settings(project: str, body: dict, ...):
    # Body — partial settings dict, deep-merge applied
    ...

@router.get("/api/settings/global", response_model=GlobalSettings)
def get_global_settings(...): ...

@router.patch("/api/settings/global", response_model=GlobalSettings)
def patch_global_settings(body: dict, ...): ...
```

**Exception handlers (`app.py`):**

- `ProjectMapCorruptError`, `SettingsCorruptError` → 503 (data integrity)
- `ProjectNotFoundError`, `SettingsNotFoundError` → 404
- `ProjectNameConflictError` → 409
- `ResolverAmbiguityError` → 409 (config conflict)
- `ValidationError` (Pydantic) → 422

**Daemon side-effect on PATCH:** `patch_project_settings` после atomic write проверяет: `if request.app.state.daemon_vault == ProjectStore.resolve_by_name(project).vault_root: daemon._reload_settings(new_settings)`. Reload swaps in-memory `ProjectSettings` instance + reschedules snapshot/lint jobs.

---

## 7. Daemon integration — `claude_mnemos/daemon/process.py`

`MnemosDaemon.__init__` дополняется:

```python
def __init__(self, config: DaemonConfig) -> None:
    self.config = config
    # Existing fields (scheduler, tracker, alerts, job_store, ...)
    
    # New (Plan #13b-α):
    self.project_store = ProjectStore()
    self.settings_store = SettingsStore()
    self.global_settings: GlobalSettings = self.settings_store.get_global()
    
    # Resolve self via project-map
    resolver = ProjectResolver()
    self.project_entry: ProjectMapEntry | None = resolver.resolve_by_vault(config.vault_root)
    if self.project_entry is None:
        # Fallback: built-in defaults
        self.project_settings: ProjectSettings = ProjectSettings()
        self.alerts.add(
            kind="handler_error",
            path=str(config.vault_root),
            message=f"daemon vault {config.vault_root} not registered in project-map; using defaults",
            detected_at=datetime.now(UTC),
        )
    else:
        self.project_settings = self.settings_store.get_project(self.project_entry.name)
    
    # Apply settings to scheduler (overrides DaemonConfig defaults)
    effective_retention = self.project_settings.snapshots.retention_days
    self.scheduler = build_scheduler(
        config.vault_root,
        retention_days=effective_retention,
        snapshots_enabled=self.project_settings.snapshots.daily_enabled,
    )
```

`build_scheduler` extended:

```python
def build_scheduler(vault_root: Path, retention_days: int, *, snapshots_enabled: bool = True):
    sched = AsyncIOScheduler()
    if snapshots_enabled:
        sched.add_job(...)  # daily snapshot at 04:00
    # backups cleanup всегда зарегистрирован (даже если snapshots off — нужно чистить старые)
    sched.add_job(...)  # backups cleanup at 05:00
    return sched
```

`reload_settings` method:

```python
def reload_settings(self, new_settings: ProjectSettings) -> None:
    """Called by PATCH /api/settings/{project} when project matches our vault."""
    old_retention = self.project_settings.snapshots.retention_days
    old_enabled = self.project_settings.snapshots.daily_enabled
    self.project_settings = new_settings
    
    if old_retention != new_settings.snapshots.retention_days:
        # Reschedule cleanup with new retention via job replace
        ...
    if old_enabled != new_settings.snapshots.daily_enabled:
        # Add or remove daily snapshot job
        ...
```

---

## 8. Plugin / hook / MCP changes

### 8.1 `.mcp.json`

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

### 8.2 `hooks/session_end.py`

```python
def main():
    payload = json.loads(sys.stdin.read())
    transcript_path = Path(payload["transcript_path"])
    cwd = Path(payload.get("cwd", os.getcwd()))
    
    resolver = ProjectResolver()
    try:
        entry = resolver.resolve_by_cwd(cwd)
    except ResolverAmbiguityError as exc:
        print(f"mnemos session_end: ambiguous project for cwd {cwd}: {exc}", file=sys.stderr)
        return  # silent skip — user fixes config later
    
    if entry is None:
        print(f"mnemos session_end: cwd {cwd} not in project-map; transcript остаётся в lost-sessions", file=sys.stderr)
        return  # silent skip — Plan #13a lost-sessions подхватит
    
    # Try POST /api/jobs first, fallback subprocess
    try:
        resp = requests.post(
            f"http://127.0.0.1:{global_settings.daemon_port}/api/jobs",
            json={"kind": "ingest", "payload": {"transcript_path": str(transcript_path), "project_name": entry.name}},
            timeout=2.0,
        )
        if resp.status_code < 300:
            return
    except (requests.ConnectionError, requests.Timeout):
        pass
    
    # Fallback subprocess
    subprocess.Popen(
        [sys.executable, "-m", "claude_mnemos", "ingest", str(transcript_path),
         "--project", entry.name],
        env={**os.environ, "MNEMOS_INGEST_RUNNING": "1"},
        ...
    )
```

### 8.3 MCP server `claude_mnemos/mcp/__main__.py`

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--auto-resolve", action="store_true",
                       help="Resolve vault from cwd via project-map.json")
    group.add_argument("--project", type=str, help="Resolve vault by project name")
    group.add_argument("--vault", type=Path, help="Direct vault path (legacy)")
    return parser.parse_args()

def resolve_vault(args) -> tuple[Path | None, str | None]:
    """Returns (vault_path, error_message)."""
    if args.vault:
        return args.vault, None
    resolver = ProjectResolver()
    if args.project:
        entry = resolver.resolve_by_name(args.project)
        if entry is None:
            return None, f"project {args.project!r} not registered"
        return entry.vault_root, None
    # auto-resolve
    cwd = Path.cwd()
    try:
        entry = resolver.resolve_by_cwd(cwd)
    except ResolverAmbiguityError as exc:
        return None, str(exc)
    if entry is None:
        return None, f"cwd {cwd} not registered in project-map"
    return entry.vault_root, None

def main():
    args = parse_args()
    vault_path, error = resolve_vault(args)
    
    if error:
        # Don't crash. Server starts; tools return error TextContent.
        server = build_degraded_server(error)
    else:
        server = build_server(vault_path)
    
    asyncio.run(stdio_server(server))
```

`build_degraded_server` — все registered tools return single TextContent с error message. Это намного лучше чем crash (Claude Code re-spawns crashed servers, что приводит к loop).

---

## 9. Migration — README/CHANGELOG section

```markdown
## Migration to Plan #13b-α

If you previously used `MNEMOS_VAULT_ROOT` env var, register your vault explicitly:

\```bash
mnemos project add \
  --name claude-mnemos \
  --vault $MNEMOS_VAULT_ROOT \
  --cwd-pattern "$(dirname $MNEMOS_VAULT_ROOT)/*"
unset MNEMOS_VAULT_ROOT
\```

After this, the `MNEMOS_VAULT_ROOT` env is no longer read by anything (CLI, plugin hook, MCP server, daemon).

If you run the daemon, restart it after registering the project so it can apply per-project settings.
```

---

## 10. Testing strategy

### 10.1 Unit tests

- `tests/state/test_projects.py` (~15 tests):
  - `ProjectMap` load/save round-trip
  - `ProjectStore.add` happy path + duplicate name → `ProjectNameConflictError`
  - `update` partial fields
  - `remove` cleanup orphan settings file
  - Schema validation (bad name pattern, missing required fields)
  - Corrupt JSON → `ProjectMapCorruptError`
  - Empty file / missing file → empty `ProjectMap()`

- `tests/state/test_settings.py` (~20 tests):
  - `ProjectSettings`/`GlobalSettings` defaults equality
  - Round-trip JSON load/save
  - Partial deep-merge (top-level + nested)
  - `ProjectSettings.model_validate` rejects bad enums
  - `SettingsStore.get_project` для незарегистрированного → returns defaults
  - Corrupt JSON → `SettingsCorruptError`
  - `_get_by_dot_path` / `_patch_dict_for_dot_path` helpers

- `tests/mapping/test_resolver.py` (~15 tests):
  - `resolve_by_name` happy + miss
  - `resolve_by_vault` happy + miss
  - `resolve_by_cwd` exact prefix glob
  - `resolve_by_cwd` wildcard glob (`~/code/*`)
  - `resolve_by_cwd` deep glob (`~/projects/**/repo`)
  - `resolve_by_cwd` most-specific wins (longer pattern)
  - `resolve_by_cwd` tie на одинаковой длине → `ResolverAmbiguityError`
  - `resolve_by_cwd` no match → `None`
  - `resolve_by_cwd` Windows case-insensitive (mock platform)
  - `resolve_by_cwd` `~` expansion
  - `resolve_by_cwd` symlink resolution

### 10.2 CLI tests (~30 tests)

- `tests/cli/test_cli_project.py`:
  - `add` happy + missing args + bad name + duplicate
  - `list` empty + populated + `--json`
  - `show` happy + missing + `--json`
  - `update` add/remove cwd patterns
  - `remove` with confirmation prompt + `--yes`
  - `resolve` debug command

- `tests/cli/test_cli_settings.py`:
  - `get` full project + dot-path + `--json`
  - `set` simple value (string, int, bool, list)
  - `set` invalid JSON → stderr error + exit code
  - `reset` field + reset all
  - `--global` analogues

### 10.3 REST tests (~25 tests)

- `tests/daemon/test_routes_projects.py`:
  - GET /api/projects empty + list
  - GET /api/projects/{name} returns ProjectView
  - POST /api/projects validation errors → 422
  - POST duplicate name → 409
  - PATCH update vault_root / cwd_patterns
  - DELETE removes entry + settings

- `tests/daemon/test_routes_settings.py`:
  - GET /api/settings/{project} returns defaults if no file
  - PATCH partial merge (top-level + nested)
  - PATCH triggers daemon reload if matches own vault (mock daemon._reload)
  - GET/PATCH /api/settings/global

### 10.4 Daemon integration (~6 tests)

- `tests/daemon/test_settings_consumption.py`:
  - Daemon at startup loads settings of registered vault
  - Daemon at startup adds alert if vault not registered
  - PATCH retention_days → daemon reschedules cleanup
  - PATCH daily_enabled false → daemon removes daily snapshot job
  - PATCH for other project's settings — daemon ignores (single-vault)

### 10.5 Hook tests (~5 tests)

- `tests/hooks/test_session_end_resolver.py`:
  - Hook with cwd matching project → POST /api/jobs called
  - Hook with cwd no match → silent skip + stderr message
  - Hook with daemon offline → fallback to subprocess
  - Hook with ambiguous cwd → silent skip + stderr message

### 10.6 Slow E2E (~2 tests)

- `tests/e2e/test_project_settings_e2e.py`:
  - Subprocess daemon start with vault → register project via REST → PATCH settings → verify daemon reload (check /api/health for new retention)
  - Hook fired with cwd → manifest gets new entry с правильным project_name

**Total:** ~120 новых тестов + обновление ~20 existing tests на новый CLI API (`--vault PATH` → `--project NAME`).

---

## 11. Open questions / risks

### 11.1 Deep merge semantics for PATCH /api/settings/{project}

Body — partial dict. Current proposal: deep-merge применяется к `current.model_dump()` + `model_validate(merged)`. Edge case: пользователь хочет clear list field — например `lint.enabled_rules: null`. Deep-merge с `null` value трактуется как «set to None» (по умолчанию rejects если field non-nullable). Мы должны явно разрешить `None` для nullable fields в Pydantic schema.

**Decision:** explicit nullable type (`list[str] | None`) — установка `null` через PATCH = «use defaults» (None в нашей model). Strict.

### 11.2 Project rename

CLI `mnemos project rename OLD NEW` — out of scope в α. Workflow: `remove OLD` (cleans settings/<old>.json) → `add NEW`. Если settings нужно сохранить — pre-extract через `mnemos settings get --project OLD --json > settings.json`, потом `mnemos settings set --project NEW ...`. Будем добавлять `rename` в Plan #13b-β если запрос придёт.

### 11.3 Concurrent CLI writes

Если две CLI инстанции пишут project-map одновременно (без daemon) — race на atomic_write. `ProjectStore._lock` это in-process lock; не помогает. **Mitigation:** writes допустимы только через daemon REST. CLI без daemon → direct file lock (`filelock`?) для writes. Для α: CLI writes требуют daemon (exit 84 если offline). Это согласуется с Plan #11/#12 pattern.

### 11.4 Migration path for existing tests

Все existing tests которые passing `vault=tmp_path` фикстурой — должны быть обновлены. Подход: добавить `register_project(name, vault, cwd_pattern)` fixture в `conftest.py`, который автоматически сетапит project-map в `~/.claude-mnemos/`. Использует `monkeypatch.setenv("HOME", tmp_path)` для изоляции. ~20 existing test files затронуто.

### 11.5 MCP plugin server reload

MCP server `--auto-resolve` резолвит vault раз на startup. Если пользователь изменяет project-map во время работающей Claude Code сессии — MCP не подхватит изменения до следующего spawn'а server'а. Acceptable trade-off в α — MCP server уже spawn'ится per-session.

### 11.6 Lost-sessions integration

Plan #13a `core/lost_sessions.py` сейчас scan'ит транскрипты у `~/.claude/projects/<projid>/<sid>.jsonl` — без знания о project. `lost_sessions list` в #13b-α — должен ли group'ить по project (matched / unmatched cwd)? Out of scope α — добавим в #13b-β после full multi-vault aggregation.

---

## 12. Acceptance criteria

Plan #13b-α считается выполненным когда:

1. `mnemos project add --name X --vault P --cwd-pattern Y` создаёт запись в `~/.claude-mnemos/project-map.json`.
2. `mnemos project show X` возвращает combined view (map entry + settings).
3. `mnemos settings set --project X lint.enabled_rules '["foo"]'` персистится в `~/.claude-mnemos/settings/X.json`.
4. SessionEnd hook резолвит cwd через project-map; no-match → silent skip + lost-sessions подхватывает.
5. MCP server `--auto-resolve` стартует без crash даже если cwd не зарегистрирован (degraded mode).
6. Daemon при старте применяет `snapshots.retention_days` + `snapshots.daily_enabled` settings своего vault'а; если vault не зарегистрирован — alert + defaults.
7. PATCH /api/settings/{project} триггерит daemon reload для своего vault'а.
8. `MNEMOS_VAULT_ROOT` env не читается нигде (grep verified).
9. README/CHANGELOG имеют migration section.
10. ~120 новых тестов + ~20 обновлённых проходят (ruff + mypy strict clean, fast suite < 60s).
11. 2 slow E2E прохода (subprocess daemon) — green.

---

## 13. Outline of implementation order (для Plan doc)

1. `state/projects.py` (ProjectMapEntry/ProjectMap + exceptions + ProjectStore) + tests
2. `state/settings.py` (ProjectSettings/GlobalSettings + SettingsStore + helpers) + tests
3. `mapping/resolver.py` (ProjectResolver) + tests
4. `daemon/routes/projects.py` + tests
5. `daemon/routes/settings.py` (incl. daemon reload trigger) + tests
6. `daemon/process.py` (settings consumption, build_scheduler extension) + tests
7. CLI `mnemos project` subgroup + tests
8. CLI `mnemos settings` subgroup + tests
9. CLI migration: existing subgroups `--vault PATH` → `--project NAME` + tests
10. `hooks/session_end.py` resolver integration + tests
11. `mcp/__main__.py` `--auto-resolve` / `--project` / degraded mode + tests
12. `.mcp.json` plugin manifest update
13. README + CHANGELOG migration section
14. Slow E2E coverage
15. Final review pass + cleanup

Каждый шаг — отдельный task в Plan doc с acceptance check.
