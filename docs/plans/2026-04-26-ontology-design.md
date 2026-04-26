# Design: Ontology Suggestions + Apply (Plan #8 — NEW)

**Status:** drafted, awaiting Yarik approval before implementation-plan generation.
**Date:** 2026-04-26
**Author:** Claude (with Yarik approval).
**Predecessor:** `2026-04-26-plugin-hooks-design.md` (Plan #7, merged in `427e377`).
**Successor planned:** Plan #9 (Watchdog real-time) → Plan #10 (Lint) → Plan #11 (Jobs+Dead-letter) → Plan #12 (Page edit + Trash) → Plan #13 (Sessions+Settings+Metrics+Multi-vault+adaptive context) → Plan #14 (Dashboard).

---

## 1. Goal

Дать пользователю инфраструктуру для **HITL ontology operations** (Human-in-the-Loop): merge entities, rename, delete pages — всё с preview, approve/reject/defer и atomic apply через существующую защиту 5 слоёв (Plans #3-#4).

После Plan #8 пользователь может:

```bash
# Создать suggestion вручную через CLI
mnemos ontology propose merge \
  --source wiki/entities/file-lock-bug \
  --source wiki/entities/race-condition-bug \
  --target wiki/entities/concurrency-issues \
  --reason "Both pages discuss concurrency bugs"

# Список suggestions
mnemos ontology list

# Утвердить, отклонить, отложить
mnemos ontology approve ont-2026-04-26-001
mnemos ontology reject ont-2026-04-26-001
mnemos ontology defer ont-2026-04-26-001

# Через MCP в Claude Code: LLM сам видит существующие suggestions и может
# приложить или предложить новые
```

### Что НЕ даёт (явно отложено)

- **LLM-driven suggestion generator** (auto-analyze vault + propose merges) → Plan #11+. Suggestion analyzer = отдельный модуль с Claude API call, отдельный prompt — большая работа.
- **Auto-mode operations** (5 из spec'а §8.4 §A) → перенесены:
  - `add_to_index` → **Plan #11+** (нужен `core/index_generator.py`)
  - `fix_broken_wikilinks` → **Plan #10 (Lint)** — естественная часть линта
  - `add_missing_required_frontmatter` → **Plan #10 (Lint)**
  - `auto_stale_after_90_days` → **Plan #11+** (нужен `core/lifecycle.py` per spec §8.7)
  - `regenerate_by_flavor_indexes` → **Plan #11+** (нужен `core/flavor_indexes.py` per spec §11.1)
- **Weekly scheduler для auto-mode** → Plan #11+ (когда auto-mode операции готовы)
- **Suggestion deferred-7-days возврат** → автоматический re-surface через 7 дней — отложено в **Plan #11+**. В Plan #8 `defer` просто меняет статус, без таймера.
- **`consolidate_concepts`, `force_overwrite`, `split_entity`, `fix_broken_wikilinks_low_confidence`** из 7 HITL операций — **отложены в Plan #11+**. В Plan #8 делаю **3 операции:** `merge_entities`, `rename_entity`, `delete_page` — самые частые и базовые.

---

## 2. Scope

### 2.1 In scope

| Компонент | Где |
|---|---|
| Pydantic models для suggestion file (id, operation, status, affected_pages, body) | `claude_mnemos/state/ontology.py` |
| Suggestion file CRUD (`<vault>/.ontology-suggestions/<id>.md` с YAML frontmatter) | `state/ontology.py` |
| Suggestion ID format: `ont-<YYYY-MM-DD>-<6-hex>` | `state/ontology.py` |
| `core/wikilinks.py` — extract + rewrite wikilinks (regex `\[\[([^\]]+)\]\]` minimum) | новый |
| `StagingTransaction.move(src, dst)` extension — атомарно перемещает файл | edit `core/staging.py` |
| `StagingTransaction.delete(path)` extension — атомарно «удаляет» (move в `.trash/`) | edit `core/staging.py` |
| `core/ontology_apply.py` — apply suggestion через `StagingTransaction(operation_type="ontology")` | новый |
| 3 ontology operations: `merge_entities`, `rename_entity`, `delete_page` | `core/ontology_apply.py` |
| `ActivityOperationType` literal + `ontology_apply` value | edit `state/activity.py` |
| Daemon endpoints: `GET /suggestions`, `GET /suggestions/{id}`, `POST /suggestions/{id}/{approve\|reject\|defer}`, `POST /suggestions` (manual create) | `daemon/routes/ontology.py` |
| MCP tools: `list_suggestions`, `apply_ontology_suggestion`, `propose_ontology_change` | `mcp/{read,write}_tools/ontology.py` |
| CLI subcommands: `mnemos ontology {list,approve,reject,defer,propose}` | edit `cli.py` |
| Tests: state + apply + endpoints + MCP + CLI + wikilinks | `tests/state/test_ontology.py`, `tests/test_wikilinks.py`, `tests/test_ontology_apply.py`, `tests/daemon/test_app_ontology.py`, `tests/mcp/test_ontology_tools.py`, `tests/test_cli_ontology.py` |

### 2.2 Out of scope

| Component | План |
|---|---|
| LLM-driven `propose_suggestions(vault)` analyzer | Plan #11+ (нужен новый prompt + LLM call с vault data) |
| Auto-mode whitelist operations (5 шт) | Plans #10, #11+ |
| Other 4 HITL operations: `consolidate_concepts`, `force_overwrite`, `split_entity`, `fix_broken_wikilinks_low_confidence` | Plan #11+ |
| Auto re-surface suggestions через 7 дней | Plan #11+ scheduler |
| Suggestions panel в дашборде с batch approve | Plan #14 (Dashboard) |
| Real wikilinks AST parser (multi-line, nested links, `[[target\|alias]]`) | Plan #11+ — пока regex достаточно |
| Confidence formula 4-factor для suggestions | Plan #11+ — в Plan #8 confidence хранится как plain float, без compute |
| Frontend suggestions UI с diff preview | Plan #14 |

---

## 3. Architecture

### 3.1 Data layout

Vault структура расширяется:

```
<vault>/
├── .ontology-suggestions/
│   ├── ont-2026-04-26-a3b8f1.md       # pending
│   ├── ont-2026-04-25-c2d9e7.md       # pending
│   └── archive/                        # approved/rejected/deferred живут здесь
│       └── ont-2026-04-24-...md
└── .trash/
    └── deleted-<page-slug>-<utc-ts>/   # soft-deleted via ontology delete_page
        ├── <original-page>.md
        └── .reason.txt                 # "deleted via ontology suggestion ont-..."
```

### 3.2 Suggestion file format

```markdown
---
id: "ont-2026-04-26-a3b8f1"
created: 2026-04-26T14:30:00Z
operation: "merge_entities"
status: "pending"
confidence: 0.78
affected_pages:
  - "wiki/entities/file-lock-bug.md"
  - "wiki/entities/race-condition-bug.md"
proposed_target: "wiki/entities/concurrency-issues.md"
reason: "Both pages discuss concurrency-related bugs..."
applied_at: null
applied_op_id: null
---

# Merge proposal

## Reasoning
{free-form markdown reasoning}

## Diff preview
{if computed, otherwise empty}
```

**Status lifecycle:**
- `pending` → `approved` (apply success, file moves to `archive/`)
- `pending` → `rejected` (file moves to `archive/`)
- `pending` → `deferred` (file stays in root, `deferred_until` field set if Plan #11+ adds re-surface)

### 3.3 Pydantic models

```python
# state/ontology.py
SuggestionStatus = Literal["pending", "approved", "rejected", "deferred"]
SuggestionOperation = Literal["merge_entities", "rename_entity", "delete_page"]
# Plan #11+ extends this literal с consolidate_concepts/force_overwrite/split_entity/etc

class SuggestionFrontmatter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^ont-\d{4}-\d{2}-\d{2}-[0-9a-f]{6}$")
    created: datetime
    operation: SuggestionOperation
    status: SuggestionStatus = "pending"
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    affected_pages: list[str]                # vault-relative POSIX paths
    proposed_target: str | None = None       # for merge/rename
    reason: str = ""
    applied_at: datetime | None = None
    applied_op_id: str | None = None         # activity entry id
    deferred_until: datetime | None = None   # Plan #11+ — None в Plan #8


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frontmatter: SuggestionFrontmatter
    body: str

    def serialize(self) -> str: ...
    @classmethod
    def parse(cls, text: str) -> "Suggestion": ...
```

### 3.4 Suggestion store

```python
# state/ontology.py
SUGGESTIONS_DIRNAME = ".ontology-suggestions"
ARCHIVE_DIRNAME = "archive"


class SuggestionStore:
    def __init__(self, vault_root: Path) -> None:
        self.vault = vault_root

    def list(self, *, include_archive: bool = False) -> list[Suggestion]: ...
    def get(self, suggestion_id: str) -> Suggestion | None: ...
    def create(self, suggestion: Suggestion) -> None:
        # Writes <vault>/.ontology-suggestions/<id>.md atomically
        ...
    def archive(self, suggestion_id: str) -> Path:
        # Moves <id>.md to archive/ subdirectory
        ...
    def update_status(
        self,
        suggestion_id: str,
        status: SuggestionStatus,
        *,
        applied_at: datetime | None = None,
        applied_op_id: str | None = None,
    ) -> Suggestion: ...
```

### 3.5 Wikilinks helper

```python
# core/wikilinks.py
WIKILINK_RE = re.compile(r"\[\[([^\[\]\|]+)(?:\|([^\]]+))?\]\]")

def extract_wikilinks(text: str) -> list[Wikilink]:
    """Return list of (target, alias?) pairs found in text."""

def rewrite_wikilinks(text: str, mapping: dict[str, str]) -> str:
    """Replace [[old]] with [[new]] for every old in mapping. Preserves aliases."""

def find_files_referencing(vault: Path, target_slug: str) -> list[Path]:
    """grep .md files for [[target_slug]] or [[target_slug|alias]]."""
```

**Limitations** (acceptable for Plan #8):
- Regex-only, no AST. Multi-line wikilinks, nested brackets — best effort.
- Match is on exact slug (basename without `.md`), not full path. Common case for our naming convention. Plan #11+ refines.
- Doesn't follow Obsidian's case-insensitivity. Slugs are lowercase by our convention (`core/slug.py`).

### 3.6 StagingTransaction extension

```python
# core/staging.py — additions

class StagingTransaction:
    # existing: write(path, content), reject(reason), promote_to_vault(), pre_promote_snapshot_path()

    def move(self, src_relpath: str, dst_relpath: str) -> None:
        """Mark a vault file to be moved on promote.

        Stages the move: copies <vault>/<src_relpath> → <staging>/<dst_relpath>,
        records src_relpath in self._to_remove. On promote, replaces vault paths
        atomically (write dst, delete src — both inside the snapshot's safe window).
        """

    def delete(self, relpath: str, *, to_trash: bool = True) -> None:
        """Mark a vault file for deletion on promote.

        Default: soft-delete (move to <vault>/.trash/deleted-<slug>-<ts>/).
        With to_trash=False: hard delete (used internally for staged files only).
        """
```

**Promote semantics** (extension):
1. After existing «write staged files to vault» step:
2. For each `_to_remove` entry: move `<vault>/<src>` → `<vault>/.trash/deleted-<slug>-<ts>/<filename>` with `.reason.txt`.
3. The pre-op snapshot (created before promote) captures the **pre-move** state — undo restores everything.

### 3.7 Apply pipeline (per operation)

```python
# core/ontology_apply.py
def apply_merge_entities(
    vault: Path,
    suggestion: Suggestion,
    *,
    config: Config,
) -> ApplyResult:
    """
    1. acquire pipeline_lock
    2. with StagingTransaction(vault, op_type="ontology", op_id=suggestion.id):
       a. read all source pages
       b. compose target page (concatenate sections, dedupe wikilinks, merge frontmatter)
       c. txn.write(target_path, target_content)
       d. for each src in affected_pages: txn.delete(src) (soft-delete to trash)
       e. for each .md in vault: rewrite wikilinks to point at target_slug
          (txn.write(updated_path, updated_content))
       f. write activity entry: operation_type=ontology_apply, metadata={suggestion_id, kind=merge}
       g. promote_to_vault
    3. archive suggestion file → status=approved
    return ApplyResult(success=True, target_path, affected_count, activity_id)
    """

def apply_rename_entity(...) -> ApplyResult:
    """
    1. txn.move(old_path, new_path)
    2. rewrite wikilinks across vault
    3. activity entry
    """

def apply_delete_page(...) -> ApplyResult:
    """
    1. txn.delete(path)  # → trash
    2. activity entry
    Wikilinks pointing to deleted page are NOT auto-removed (left as broken).
    Plan #10 (Lint) will catch broken links.
    """
```

### 3.8 Module map

**Новое:**

| Файл | Что |
|---|---|
| `claude_mnemos/state/ontology.py` | `SuggestionFrontmatter`, `Suggestion`, `SuggestionStore`, lifecycle |
| `claude_mnemos/core/wikilinks.py` | `extract_wikilinks`, `rewrite_wikilinks`, `find_files_referencing` |
| `claude_mnemos/core/ontology_apply.py` | `ApplyResult`, `apply_merge_entities`, `apply_rename_entity`, `apply_delete_page`, dispatcher `apply_suggestion(vault, suggestion_id) -> ApplyResult` |
| `claude_mnemos/daemon/routes/ontology.py` | `/suggestions` GET/POST + `/suggestions/{id}` + `/suggestions/{id}/{approve\|reject\|defer}` |
| `claude_mnemos/mcp/read_tools/ontology.py` | `list_suggestions(vault, status?)` |
| `claude_mnemos/mcp/write_tools/ontology.py` | `apply_ontology_suggestion`, `propose_ontology_change` |
| `tests/state/test_ontology.py` | Suggestion CRUD |
| `tests/test_wikilinks.py` | extract/rewrite |
| `tests/test_ontology_apply.py` | merge/rename/delete |
| `tests/daemon/test_app_ontology.py` | endpoints |
| `tests/mcp/test_ontology_tools.py` | MCP tools |
| `tests/test_cli_ontology.py` | CLI subcommands |
| `tests/test_staging_extensions.py` | `txn.move()`, `txn.delete()` |

**Изменяется:**

| Файл | Что |
|---|---|
| `claude_mnemos/state/activity.py` | `ActivityOperationType` literal extends с `"ontology_apply"` |
| `claude_mnemos/core/staging.py` | `move()`, `delete()` методы; promote учитывает `_to_remove` |
| `claude_mnemos/cli.py` | `mnemos ontology {list,approve,reject,defer,propose}` subgroup |
| `claude_mnemos/daemon/app.py` | include ontology router |
| `claude_mnemos/mcp/server.py` | register 3 ontology tools (12 → 12, потом 13 после propose; точное число — через TOOL_DEFS) |
| `tests/state/__init__.py` | empty if not exists |

### 3.9 CLI commands

```bash
# Создать suggestion вручную
mnemos ontology propose merge \
  --source wiki/entities/foo.md \
  --source wiki/entities/bar.md \
  --target wiki/entities/foo-bar.md \
  [--reason "..."] \
  [--confidence 0.78] \
  [--vault PATH]

mnemos ontology propose rename \
  --source wiki/entities/old-name.md \
  --target wiki/entities/new-name.md \
  [--reason "..."] [--vault PATH]

mnemos ontology propose delete \
  --source wiki/entities/orphan.md \
  [--reason "..."] [--vault PATH]

# Список pending
mnemos ontology list [--vault PATH] [--all]
# (--all включает archive)

# Действия
mnemos ontology approve <id> [--vault PATH]
mnemos ontology reject <id> [--vault PATH]
mnemos ontology defer <id> [--vault PATH]
```

Exit codes:
- 81 — `OntologyError` (suggestion not found, already applied, apply failed)
- 0/2/73/74/75/76/77 — как раньше

### 3.10 REST endpoints

```
GET    /suggestions?status=pending|approved|rejected|deferred|all  → list
GET    /suggestions/{id}                                            → single
POST   /suggestions  body={operation, sources, target?, reason?}    → create (201)
POST   /suggestions/{id}/approve                                    → apply
POST   /suggestions/{id}/reject
POST   /suggestions/{id}/defer
```

Apply errors → 409 (e.g. `OntologyApplyError("source page missing")`), 423 (lock timeout), 500 (staging failed).

### 3.11 MCP tools

| Tool | Kind | Что |
|---|---|---|
| `list_suggestions(status?)` | read | Прямой доступ к `<vault>/.ontology-suggestions/` |
| `propose_ontology_change(operation, sources, target?, reason?, confidence?)` | write | POST `/suggestions` к daemon |
| `apply_ontology_suggestion(suggestion_id)` | write | POST `/suggestions/{id}/approve` к daemon |

Sub-skill `skills/mnemos-ontology/SKILL.md` (опционально — пока не делаем; main `mnemos` skill упомянет в behavioral описании).

---

## 4. Activity log integration

Каждый apply пишет ActivityEntry:

```json
{
  "id": "<uuid>",
  "operation_type": "ontology_apply",
  "status": "success",
  "snapshot_path": ".backups/pre-op-<ts>-ontology-<uuid>",
  "can_undo": true,
  "affected_pages": ["wiki/entities/foo.md", "wiki/entities/bar.md", "wiki/entities/concurrency-issues.md"],
  "metadata": {
    "suggestion_id": "ont-2026-04-26-a3b8f1",
    "operation": "merge_entities",
    "wikilinks_rewritten": 5
  }
}
```

`mnemos undo <op_id>` (Plan #4) уже работает — просто использует существующий `restore_from_snapshot`. Никаких изменений в undo не нужно.

---

## 5. Error handling

| Сценарий | Результат |
|---|---|
| `ontology propose merge` source не найден | `OntologyError("source page missing: <path>")`, exit 81 |
| `ontology approve <id>` id не найден | `OntologyError("suggestion not found: <id>")`, exit 81 |
| `ontology approve <id>` уже applied/rejected | `OntologyError("suggestion already <status>")`, exit 81 |
| Apply: target file уже существует (для merge) | `OntologyError("target page exists: <path>")`, exit 81 (suggest user resolve) |
| Apply: pipeline lock timeout | `LockTimeoutError`, exit 73 (existing) |
| Apply: staging promote failed | `StagingPromoteError`, exit 76 (existing) — vault rolled back, suggestion stays pending |
| Apply: wikilinks rewrite failed на одном файле | log warning, продолжаем — best-effort. Detail в metadata.warnings |
| Suggestion file corrupt YAML | `OntologyCorruptError`, exit 74 (consistent с Manifest/ActivityCorrupt) |

---

## 6. Concurrency

- **Apply под `pipeline_lock`** — стандартный pattern (как ingest, undo).
- **Suggestion CRUD** (create/list/get) — без lock'а; читают/пишут отдельные файлы атомарно через `atomic_write`.
- **Race**: одновременное `approve` одного suggestion из CLI и REST → второй увидит status=approved и фейлится с `OntologyError("already approved")`. Не corrupt'ит vault.

---

## 7. Testing strategy

### 7.1 Unit

1. **`state/ontology.py`:**
   - SuggestionFrontmatter validation (id pattern, status enum, confidence 0-1)
   - Suggestion serialize/parse roundtrip
   - SuggestionStore.list empty/with files / status filter / include_archive
   - SuggestionStore.create writes file atomically
   - SuggestionStore.get returns None for missing
   - SuggestionStore.archive moves to archive/
   - SuggestionStore.update_status updates frontmatter, persists
   - Corrupt YAML → OntologyCorruptError

2. **`core/wikilinks.py`:**
   - extract: empty / 1 link / multiple / with alias / nested brackets (best effort) / multi-line
   - rewrite: 1 mapping / multiple / no-op (no matches) / preserves alias / preserves surrounding text
   - find_files_referencing: empty vault / 1 ref / multiple / no refs

3. **`core/staging.py` extensions:**
   - `txn.move(src, dst)` happy path: file moves on promote
   - `txn.move` with src missing → raises
   - `txn.delete(path)` with to_trash=True: file goes to .trash/ on promote
   - Snapshot before promote captures pre-move state — restore restores
   - `txn.delete` with to_trash=False: file just disappears

4. **`core/ontology_apply.py`:**
   - `apply_merge_entities`: 2 sources → target created with concatenated body, sources in trash, wikilinks rewritten in 3rd file
   - `apply_rename_entity`: source moved to new path, wikilinks rewritten
   - `apply_delete_page`: source in trash, wikilinks NOT rewritten (broken links left)
   - On any apply error: vault unchanged (snapshot restore), suggestion stays pending
   - Activity entry written with correct metadata

### 7.2 Integration

5. **Daemon endpoints:**
   - GET /suggestions empty / pending only / status filter / all
   - GET /suggestions/{id} known/404
   - POST /suggestions creates file, returns 201 + body
   - POST /suggestions invalid operation → 422
   - POST /suggestions/{id}/approve → applies, status=approved, archive moved
   - POST /suggestions/{id}/approve already approved → 409
   - POST /suggestions/{id}/reject → status=rejected
   - POST /suggestions/{id}/defer → status=deferred

6. **MCP tools:**
   - list_suggestions returns array
   - propose_ontology_change creates suggestion (mock daemon httpx)
   - apply_ontology_suggestion happy + 409 + daemon offline

7. **CLI:**
   - `mnemos ontology propose merge --source ... --target ... --reason ...` — выполняется, suggestion появляется в `.ontology-suggestions/`
   - `mnemos ontology list` — печатает таблицу
   - `mnemos ontology approve <id>` — apply, печатает summary

8. **End-to-end** (mocked): full cycle propose → list → approve → undo (через `mnemos undo <activity_id>`).

### 7.3 Coverage targets

- 423 текущих + ~70-90 новых → ~500-510.
- ruff + mypy strict чистые.
- Manual smoke: `propose merge` → `approve` → проверить vault: target создан, sources в trash, wikilinks rewritten в каком-нибудь fixture.

---

## 8. Known limitations (для Plans #9+)

1. **Только 3 операции из 7 HITL spec'овских.** `consolidate_concepts`/`force_overwrite`/`split_entity`/`fix_broken_wikilinks_low_confidence` отложены в Plan #11+.
2. **Auto-mode не реализован.** 5 operations из spec §A — каждая требует своего модуля; перенесено в Plans #10/#11+.
3. **Нет LLM-driven suggestion generator.** Пользователь создаёт suggestions вручную через CLI/MCP. LLM может предложить через MCP `propose_ontology_change` — но это не auto-analyzer. Auto-analyzer = Plan #11+.
4. **Wikilinks regex, не AST.** Edge cases: `[[a|b|c]]`, escape sequences, нестрогие multi-line — best effort. Plan #11+ заменит на AST parser.
5. **Slug-based wikilink matching, не path-based.** `[[file-lock-bug]]` находим по basename. Если есть две страницы с одинаковым slug в разных type-папках — конфликт. Plan #11+ добавит unique-slug enforcement или path-aware matching.
6. **Defer не возвращается через 7 дней.** Status просто `deferred` навсегда, пока не approve/reject вручную. Re-surface через scheduler — Plan #11+.
7. **Confidence хранится как plain float, не computed.** 4-factor formula (spec §6.7) — Plan #11+. В Plan #8 defaults to 0.7, можно задать через `--confidence` flag.
8. **Apply делает best-effort на wikilinks rewrite.** Если один файл не записался — логируем warning, не fail'им весь apply. Edge cases (file disappeared mid-apply) — фиксим через snapshot rollback при `StagingPromoteError`.
9. **Soft-delete для merge sources** идёт в `.trash/`. `mnemos undo <activity_id>` восстанавливает через snapshot — не через trash restore. Trash как UI — Plan #12.
10. **Diff preview в suggestion file body не computed automatically.** Поле есть, но генератор diff (для UI) — Plan #14 (Dashboard).

---

## 9. What this enables (#9+ onwards)

- **Plan #9 (Watchdog):** human edit detection логирует через тот же activity log, использует `_our_writes` set который включает наши ontology writes.
- **Plan #10 (Lint):** `fix_broken_wikilinks_high_confidence` и `add_missing_required_frontmatter` строятся на `core/wikilinks.py` (созданном здесь).
- **Plan #11+ (auto-mode + LLM analyzer):** добавится `core/ontology_analyzer.py` который зовёт Claude API и создаёт suggestions через тот же `SuggestionStore.create`. Apply pipeline уже готов.
- **Plan #14 (Dashboard):** `Suggestions` раздел просто читает endpoints + рендерит approve/reject buttons. Diff preview генерируется на frontend по `affected_pages` через `usePages` + клиентский diff lib (или backend pre-computes — будем решать тогда).

---

## 10. Решения, которые я принял сам

| Решение | Альтернатива | Почему |
|---|---|---|
| Только 3 HITL операции (merge/rename/delete) | Все 7 spec'овских | Узкий фокусный план, остальные 4 (consolidate/force_overwrite/split/wikilinks_low_conf) сложнее и реже. Аддитивно в Plan #11+ |
| Suggestions создаются **вручную** (CLI/MCP) | LLM-driven analyzer сразу | Analyzer = отдельная подсистема (LLM call с vault context). Сейчас инфраструктура; analyzer в Plan #11+ |
| Wikilinks через regex, не AST | AST parser (markdown-it / mistune) | Regex покрывает 95% случаев в нашем vault. AST = 200+ строк + dep. Аддитивно в Plan #11+ |
| `txn.move` + `txn.delete` extension в существующий staging.py | Новый `OntologyTransaction` отдельный класс | Поддерживает атомарность через тот же snapshot. Дублирование = риск рассинхрона |
| Soft-delete в `.trash/deleted-<slug>-<ts>/` | Hard delete | Spec явно требует soft. Pre-op snapshot всё равно ловит — но trash даёт UI restore (когда Plan #12 настанет) |
| 3 операции расширяют `ActivityOperationType` literal сразу | Всё через `metadata.operation` без literal | Чистый pattern matching в undo/CLI. Literal расширяется per-plan |
| Suggestion id = `ont-YYYY-MM-DD-6hex` | UUID hex | Читаемо в CLI/UI. Date-prefix помогает sort. Уникальность через random suffix |
| Defer = просто status, без re-surface таймера | Scheduler resurface через 7d | Plan #11+ добавит когда scheduler infra расширим |
| Confidence default 0.7, не computed | 4-factor formula | Spec §6.7 — отдельный модуль. Plan #11+ |
| Wikilinks rewrite best-effort с warnings | Atomic — fail весь apply | Best-effort prevent's обвал на одном corrupt файле. Warnings в metadata, snapshot rollback всё равно работает на серьёзный fail |
| Manual `propose` через CLI flags, не через interactive prompt | Wizard | YAGNI. CLI flags программируемы, LLM может вызвать через MCP |
| Suggestion архивируется (`archive/<id>.md`) после approve/reject, не удаляется | Hard delete | История полезна. 180-day retention — Plan #11+ |
| `apply_delete_page` НЕ удаляет broken wikilinks | Auto-cleanup orphan links | Lint поймает (Plan #10). Auto-cleanup = lossy operation, лучше явный |
| MCP `propose_ontology_change` через REST к daemon | Прямой write в файл | Single-owner pattern (Plan #6 решение): write через daemon |
| 3 operation types в SuggestionOperation literal, расширяется | Plain string | Type safety, IDE autocomplete |

---

## 11. Open questions для имплементации

- **Как target page собирается при merge?** Концептуально: новая `WikiPage` с `frontmatter.title=<derived>`, `body=<concat sections from sources>`. Решу при коде — простейший вариант: front matter копируется с первого source (modify aliases/related), body конкатенируется с разделителями `## From <slug>`.
- **Что если sources имеют разные `type` (entity vs concept)?** Reject в propose с понятным сообщением — кросс-типовый merge неинтуитивен.
- **Frontmatter merge при merge_entities** — какой combine policy? Решу при коде; вероятно: title из target arg, type из первого source, flavor union, sources union, related union, dates max.
- **CLI `propose merge` принимает много `--source` flags** — argparse `action="append"`. Минимум 2 source.
- **Что если after merge кто-то ссылается на теперь-несуществующий source slug, но slug новой target страницы совпадает?** Невозможно если `proposed_target` уникален. Если совпадает (rename to existing) — fail в propose.
- **`apply_rename_entity`: что если rename меняет path только косметически (`wiki/entities/foo.md` → `wiki/entities/Foo.md` на case-insensitive FS)?** Reject в propose — git/FS edge case.
- **REST endpoints prefix:** `/suggestions` без префикса (consistent с `/snapshots`, `/activity`). Сохраняю.
- **`SuggestionStore` thread-safety:** не явный lock; полагаемся на atomic_write для file-level consistency. Apply берёт pipeline_lock — серилизует. Read endpoints читают snapshot файла.

---

## 12. Why this scope

1. **Закрывает Plan-#11+-блокеры.** Plan #14 (Dashboard) Suggestions раздел читает готовые suggestions + кнопки approve/reject — backend готов.
2. **Не блокирует существующий flow.** Если ontology не используется — vault работает как до Plan #8.
3. **Wikilinks helper — побочный полезный артефакт.** Plan #10 (Lint) переиспользует `core/wikilinks.py` для broken-links rule.
4. **StagingTransaction extensions** — open path для будущих операций которые не только пишут (move/delete). Plan #12 (Page edit) и Plan #11+ (auto-mode) переиспользуют.
5. **Cycle time:** ~7-10 дней. Узко по фокусу как Plans #2-#7.
