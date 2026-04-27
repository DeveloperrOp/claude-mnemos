# Design: Lint (Plan #10 — NEW)

**Status:** drafted, awaiting Yarik approval before implementation-plan generation.
**Date:** 2026-04-27
**Author:** Claude (with Yarik approval).
**Predecessor:** `2026-04-27-watchdog-realtime-design.md` (Plan #9, merged in `757b19b`).
**Successor planned:** Plan #11 (Jobs+Dead-letter queue) → Plan #12 (Page edit + Trash) → Plan #13 (Sessions+Settings+Metrics+Multi-vault+adaptive context) → Plan #14 (Dashboard).

---

## 1. Goal

Дать пользователю инструмент проверки здоровья vault'а: **structural lint** + **safe autofix**. Lint находит broken wikilinks, orphans, stale pages, duplicate titles, low-quality provenance, format glitches. Autofix чинит whitelist-набор безопасных проблем под `StagingTransaction` (snapshot + atomic + activity).

После Plan #10:

```bash
# Запустить lint
mnemos lint run --vault <path>
# Output: 23 findings (3 broken wikilinks, 8 orphan pages, ...)

# Просмотреть последний отчёт
mnemos lint results --vault <path>

# Применить безопасные автофиксы
mnemos lint autofix --vault <path>
# Output: snapshot at .backups/pre-op-...; fixed 12 of 14 fixable findings.

# Через MCP — LLM сам видит lint и может прогнать
# Через REST — фронтенд (Plan #14) подтянет результаты в Health раздел
```

### Что НЕ даёт (явно отложено)

- **LLM-powered rules** — `contradictions_between_pages` (требует pairwise LLM-сравнения двух страниц) и `wikilinks_typo_high_confidence` через embedding similarity → Plan #11+. В Plan #10 typo detection через **Levenshtein**, чисто структурный.
- **Auto-stale lifecycle** (`status: draft → stale` после 90 дней) → Plan #11+ (нужен `core/lifecycle.py` per spec §8.7). Lint в Plan #10 только **флажит** stale, не меняет статус.
- **`add_to_index`** — auto-генерация `index.md` после ingest → Plan #11+ (`core/index_generator.py`).
- **Scheduled lint** — APScheduler weekly job → Plan #11+ (когда есть `lint_schedule` в per-project settings, которого тоже нет).
- **`fix_broken_wikilinks` через ontology suggestions** для low-confidence матчей (0.5–0.95) → Plan #11+. В Plan #10 wikilinks autofix только для high-confidence (Levenshtein ≤ 2 + единственный кандидат).
- **Frontmatter автодобавление required-with-default** для произвольных полей — в Plan #10 покроем только `agent_written` и `provenance` (где default обоснован). Остальные required → flag, не autofix.
- **Lint в watchdog real-time** — пока lint работает только on-demand (`mnemos lint run`). Plan #11+ может прицепить lint к watchdog handler.

---

## 2. Scope

### 2.1 In scope

| Компонент | Где |
|---|---|
| `LintSeverity` enum (`error`/`warning`/`info`) | `claude_mnemos/lint/models.py` |
| `LintFinding` Pydantic model (id, rule_id, severity, message, page_path, fixable, fix_kind, metadata) | `lint/models.py` |
| `LintReport` Pydantic model (run_id, started_at, finished_at, vault_root, rule_versions, findings, summary) | `lint/models.py` |
| 9 structural rules (см. §3.2) — `wikilinks_broken`, `wikilinks_typo_fixable`, `orphan_pages`, `stale_pages`, `duplicate_titles`, `provenance_inferred_high`, `provenance_ambiguous_high`, `trailing_whitespace`, `missing_required_frontmatter` | `lint/rules.py` |
| `LintRunner` — итерирует все wiki/*.md, прогоняет правила, собирает `LintReport` | `lint/runner.py` |
| `apply_autofix(vault, report)` — применяет safe-whitelist autofixes под `StagingTransaction` со snapshot'ом | `lint/autofix.py` |
| 3 autofix kinds: `strip_trailing_ws`, `add_default_frontmatter_field`, `fix_wikilink_typo` | `lint/autofix.py` |
| `<vault>/.lint-results.json` CRUD (Pydantic-validated, `LintCorruptError` при corrupt) | `lint/state.py` |
| `ActivityOperationType += "lint_fix"` | edit `state/activity.py` |
| Daemon endpoints: `POST /lint/run`, `GET /lint/results`, `POST /lint/autofix` | новый `daemon/routes/lint.py` + wiring в `app.py` |
| 2 MCP tools: `run_lint()` (write через REST), `get_lint_results()` (read через файл) | `mcp/{write,read}_tools/lint.py` + register в `server.py` |
| CLI subgroup `mnemos lint {run, results, autofix}` | edit `cli.py` |
| Tests: per-rule unit + runner + autofix + state + REST + MCP + CLI | новые в `tests/lint/`, `tests/daemon/`, `tests/mcp/` |

### 2.2 Out of scope

| Component | План | Reason |
|---|---|---|
| LLM-powered `contradictions_between_pages` | Plan #11+ | требует pairwise LLM-сравнения, отдельный prompt+cost |
| Embedding-based wikilinks similarity | Plan #11+ | требует embedding service |
| Auto-stale state transition (`draft → stale`) | Plan #11+ (`core/lifecycle.py`) | spec §8.7 lifecycle отдельная подсистема |
| `add_to_index` auto-generation | Plan #11+ (`core/index_generator.py`) | spec §11.1 flavor_indexes отдельная подсистема |
| Scheduled weekly lint via APScheduler | Plan #11+ | нужен `lint_schedule` в per-project settings |
| Lint в watchdog handler (real-time) | Plan #11+ | watchdog Plan #9 не дёргает lint |
| Per-project Settings (включая `enabled_rules`) | Plan #13 | per-project settings отсутствуют |
| `fix_broken_wikilinks_low_confidence` через ontology suggestion | Plan #11+ | требует confidence formula |
| Custom rule registration (plugin API) | не делаем | все правила hardcoded |
| Spec-rule `frontmatter_sort_tags` (autofix) | не делаем | в `WikiPageFrontmatter` нет field `tags` (только `flavor` — structured list, не нуждается в sort) |
| Spec-rule `frontmatter_type_cast` (autofix) | не делаем | PyYAML делает cast сам; type-mismatch ловится как `PageParseError` через Pydantic validate, попадает в синтетический rule `page_parse_failed` |
| MCP `apply_autofix` tool | не делаем | autofix — destructive операция, через CLI/Dashboard. LLM получает только `run_lint` + `get_lint_results` |

---

## 3. Architecture

### 3.1 Module layout

Новый top-level package `claude_mnemos/lint/` рядом с `core/`, `state/`, `daemon/`. Spec §10.1 размещает lint правила в `backend/core/lint.py`, но в нашей кодовой базе `core/` уже занят примитивами (locks, atomic, snapshots, staging, page_io). Дать lint собственный package чище — он логически отдельный feature, не примитив.

```
claude_mnemos/
├── lint/
│   ├── __init__.py
│   ├── models.py        # LintSeverity, LintFinding, LintReport, LintFixKind
│   ├── rules.py         # 9 rule implementations + RULE_REGISTRY
│   ├── runner.py        # LintRunner.run(vault) -> LintReport
│   ├── autofix.py       # apply_autofix(vault, report, *, tracker=None) -> AutofixResult
│   ├── state.py         # save/load .lint-results.json + LintCorruptError
│   └── exceptions.py    # LintError, LintCorruptError
```

### 3.2 Rules — детально

Каждое правило — функция `(vault: Path, pages: list[ParsedPage]) -> list[LintFinding]`. Runner материализует `pages` один раз (parsed via `core/page_io.read_page`) и переиспользует для всех правил.

#### Structural — 9 rules

| ID | Severity | Что | Fixable? | Fix kind |
|---|---|---|---|---|
| `wikilinks_broken` | warning | `[[X]]` указывает на несуществующий slug | условно | если есть unique Levenshtein≤2 candidate → `fix_wikilink_typo`; иначе нет |
| `orphan_pages` | warning | wiki/{entities,concepts}/X.md без backlink'а из любой другой wiki/* страницы | нет | — |
| `stale_pages` | info | `updated < today - 90` AND `confidence < 0.5` AND `status != verified` | нет | — |
| `duplicate_titles` | warning | две и более страницы имеют одинаковый `title` (case-insensitive) | нет | — |
| `provenance_inferred_high` | info | `provenance.inferred_pct >= 50` | нет | — |
| `provenance_ambiguous_high` | info | `provenance.ambiguous_pct >= 30` | нет | — |
| `trailing_whitespace` | info | в body или yaml-блоке есть trailing spaces (не newline-only EOF) | да | `strip_trailing_ws` |
| `missing_required_frontmatter` | warning | отсутствует обязательное поле frontmatter (`title`, `type`, `created`, `updated`) — обычно не достижимо т.к. ParsedPage validates, но fallback для page без frontmatter | условно | для `agent_written` (default `True`) → autofix; для остальных → нет |
| `wikilinks_typo_fixable` | info | wikilinks_broken который имеет unique Levenshtein≤2 → отдельный finding с `fixable=True` (повтор `wikilinks_broken` для UX clarity) | да | `fix_wikilink_typo` |

> Правило 9 — синтетическое: оно совпадает с `wikilinks_broken` для случаев когда есть fix. Делается чтобы дашборд (Plan #14) мог показать «3 поломанных, 2 фиксятся» отдельной плашкой. Имплементация: fix-аспект встраивается прямо в `wikilinks_broken` через `fixable=True` field — синтетический rule убираем. Простота > дублирование.

**Финальный список — 8 structural rules** (убрал 9-й).

#### Synthetic rule — `page_parse_failed`

Прежде чем 8 rules выше пробежать, runner парсит каждую страницу через `core/page_io.read_page`. Если parse падает (broken YAML, missing required fields):

| ID | Severity | Что | Fixable? | Fix kind |
|---|---|---|---|---|
| `page_parse_failed` | error | страницу не удалось распарсить (frontmatter invalid или body структура нарушена) | нет | — |

Все 8 главных rules **skip'ают** страницы, которые не распарсились (parsed is None в runner'е). Только этот синтетический rule о них знает. `metadata` содержит `error: str` (текст PageParseError).

**Итого:** runner регистрирует **9 rule_ids** = 1 synthetic + 8 structural.

#### Что не реализовано в Plan #10

- LLM-powered `contradictions_between_pages` (need pairwise LLM call) — Plan #11+.
- Lint только wiki/{entities,concepts,sources}/, не raw/. Spec §6.3 говорит raw/ — readonly recordings, не валидируем.

### 3.3 LintFinding format

```python
class LintSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class LintFixKind(str, Enum):
    STRIP_TRAILING_WS = "strip_trailing_ws"
    FIX_WIKILINK_TYPO = "fix_wikilink_typo"
    ADD_DEFAULT_FRONTMATTER_FIELD = "add_default_frontmatter_field"

class LintFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str                          # "<rule_id>:<sha256(page_path+message)[:8]>"
    rule_id: str                     # e.g. "wikilinks_broken"
    severity: LintSeverity
    message: str                     # human-readable
    page_path: str                   # POSIX relative to vault, "wiki/entities/foo.md"
    fixable: bool
    fix_kind: LintFixKind | None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

`metadata` schema по rule_id:

| rule_id | metadata keys |
|---|---|
| `wikilinks_broken` | `target: str` (broken slug), `candidate: str \| null` (если есть Levenshtein≤2 unique) |
| `orphan_pages` | (empty) |
| `stale_pages` | `updated: str` (iso date), `confidence: float`, `status: str` |
| `duplicate_titles` | `title: str`, `other_pages: list[str]` |
| `provenance_inferred_high` | `inferred_pct: int` |
| `provenance_ambiguous_high` | `ambiguous_pct: int` |
| `trailing_whitespace` | `lines: list[int]` (1-indexed line numbers) |
| `missing_required_frontmatter` | `field: str`, `default_value: Any \| null` |

### 3.4 LintReport format

```python
class LintReportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total: int
    by_severity: dict[str, int]
    by_rule: dict[str, int]
    fixable_count: int

class LintReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    run_id: str                       # uuid4 hex
    started_at: datetime              # UTC
    finished_at: datetime             # UTC
    vault_root: str                   # absolute path string
    rule_versions: dict[str, str]     # {"wikilinks_broken": "v1", ...} for cache invalidation
    findings: list[LintFinding]
    summary: LintReportSummary
```

### 3.5 LintRunner

```python
class LintRunner:
    def __init__(self, vault: Path) -> None:
        self.vault = vault

    def run(self) -> LintReport:
        run_id = uuid4().hex
        started = datetime.now(UTC)

        # 1. Iterate all wiki/*.md
        page_paths = sorted(self.vault.glob("wiki/**/*.md"))
        # Skip dotfile dirs and non-files (already excluded by glob).

        # 2. Parse each page (preserving extras via core/page_io)
        # On PageParseError → still record a finding for that page,
        # via a synthetic rule "page_parse_failed" (kept invisible to main 8 rules).
        parsed_pages: list[tuple[Path, ParsedPage | None]] = []
        for p in page_paths:
            try:
                parsed_pages.append((p, read_page(p)))
            except PageParseError as exc:
                parsed_pages.append((p, None))
                # collected as a "page_parse_failed" finding later

        # 3. Run each rule, collect findings
        all_findings: list[LintFinding] = []
        for rule_id, rule_fn in RULE_REGISTRY.items():
            all_findings.extend(rule_fn(self.vault, parsed_pages))

        # 4. Build report
        finished = datetime.now(UTC)
        return LintReport(...)
```

**Rule registry** is a `dict[str, Callable]` populated at module import. Order is deterministic (insertion order guaranteed by dict).

**`page_parse_failed`** — special rule that runs first, finds pages where parsing failed. These are reported as ERROR severity. The main 8 rules then skip pages with `parsed is None`.

So total findings rules: **8 structural + 1 synthetic = 9 rule_ids** in registry.

### 3.6 Autofix pipeline

```python
@dataclass(frozen=True)
class AutofixResult:
    success: bool
    snapshot_path: Path | None
    fixed_findings: list[str]        # finding ids
    skipped_findings: list[str]      # not in safe whitelist
    errors: list[tuple[str, str]]    # (finding_id, error_msg)
    activity_id: str | None

SAFE_FIX_KINDS: set[LintFixKind] = {
    LintFixKind.STRIP_TRAILING_WS,
    LintFixKind.FIX_WIKILINK_TYPO,
    LintFixKind.ADD_DEFAULT_FRONTMATTER_FIELD,
}

def apply_autofix(
    vault: Path,
    report: LintReport,
    *,
    tracker: OurWritesTracker | None = None,
    today: date | None = None,
) -> AutofixResult:
    # 1. Acquire pipeline_lock (sequence with ingest/ontology/undo)
    with pipeline_lock(vault, timeout=cfg.lock_timeout):
        # 2. Filter findings to safe + fixable + with known fix_kind
        applicable = [f for f in report.findings if f.fixable and f.fix_kind in SAFE_FIX_KINDS]

        # 3. Group findings by page; load each page once via read_page
        # 4. Apply fixes in-memory per-page, write to staging via StagingTransaction
        op_id = uuid4().hex
        with StagingTransaction(vault, op_id, operation_type="lint_fix") as txn:
            for page_rel, fixes in grouped:
                parsed = read_page(vault / page_rel)
                new_parsed = parsed
                for f in fixes:
                    new_parsed = _apply_fix(new_parsed, f)
                txn.write(Path(page_rel), serialize_page(new_parsed))

            # Activity entry written into staging too (snapshot points to it)
            snap = txn.pre_promote_snapshot_path()
            activity = ActivityLog.load(vault)
            activity.append(ActivityEntry(
                id=op_id,
                timestamp=datetime.now(UTC),
                operation_type="lint_fix",
                status="success",
                snapshot_path=str(snap.relative_to(vault).as_posix()),
                can_undo=True,
                affected_pages=sorted({f.page_path for f in applicable}),
                metadata={
                    "fixed_finding_ids": [f.id for f in applicable],
                    "rule_breakdown": _count_by_rule(applicable),
                },
            ))
            txn.write(Path(ACTIVITY_FILENAME), activity.serialize_to_string())

            promote = txn.promote_to_vault(tracker=tracker)

        # 5. Build result
        return AutofixResult(
            success=True,
            snapshot_path=promote.snapshot,
            fixed_findings=[f.id for f in applicable],
            skipped_findings=[f.id for f in report.findings
                              if f.fixable and f.fix_kind not in SAFE_FIX_KINDS],
            errors=[],
            activity_id=op_id,
        )
```

**Atomicity:** все изменения через staging — крах посередине → vault не тронут (rollback through restore_from_snapshot). **Undo:** через `mnemos undo <activity_id>` (existing pipeline).

### 3.7 Per-fix logic

```python
def _apply_fix(parsed: ParsedPage, finding: LintFinding) -> ParsedPage:
    if finding.fix_kind == LintFixKind.STRIP_TRAILING_WS:
        new_body = "\n".join(line.rstrip() for line in parsed.body.splitlines())
        if parsed.body.endswith("\n"):
            new_body += "\n"
        return ParsedPage(parsed.frontmatter, parsed.extra_fm, new_body)

    if finding.fix_kind == LintFixKind.FIX_WIKILINK_TYPO:
        target = finding.metadata["target"]
        candidate = finding.metadata["candidate"]
        new_body = rewrite_wikilinks(parsed.body, {target: candidate})
        return ParsedPage(parsed.frontmatter, parsed.extra_fm, new_body)

    if finding.fix_kind == LintFixKind.ADD_DEFAULT_FRONTMATTER_FIELD:
        field = finding.metadata["field"]
        default = finding.metadata["default_value"]
        new_fm = parsed.frontmatter.model_copy(update={field: default})
        return ParsedPage(new_fm, parsed.extra_fm, parsed.body)

    raise NotImplementedError(...)
```

### 3.8 State file `<vault>/.lint-results.json`

Persistent cache of last `LintReport`. Atomically written via `atomic_write`. Loaded on `GET /lint/results`.

```python
class LintCorruptError(ValueError): pass

def load_last_report(vault: Path) -> LintReport | None:
    path = vault / ".lint-results.json"
    if not path.is_file():
        return None
    try:
        return LintReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LintCorruptError(...) from exc

def save_report(vault: Path, report: LintReport, *, tracker=None) -> None:
    path = vault / ".lint-results.json"
    if tracker is not None:
        tracker.add(path)
    try:
        atomic_write(path, report.model_dump_json(indent=2) + "\n")
    finally:
        if tracker is not None:
            tracker.remove(path)
```

`.lint-results.json` — dotfile, watchdog handler skip'ает по dotfile rule. Tracker registration оборонительная.

### 3.9 REST API

```
POST   /lint/run                       — run lint, save .lint-results.json, return LintReport
GET    /lint/results                   — return cached LintReport (404 if no run yet)
POST   /lint/autofix                   — apply safe autofixes on cached report; returns AutofixApiResult
```

`POST /lint/autofix` requires last cached report — if missing, returns 409 with hint to run `/lint/run` first. **Не** делает auto-run внутри (явная двухшаговая семантика для UI).

```python
class AutofixApiResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    success: bool
    snapshot_path: str | None
    fixed_findings: list[str]
    skipped_findings: list[str]
    activity_id: str | None
```

Exception handlers in `app.py`:
- `LintCorruptError` → 503
- `LintError` → 409

### 3.10 MCP tools

| Tool | Kind | Через что |
|---|---|---|
| `run_lint()` | write | REST `POST /lint/run` |
| `get_lint_results()` | read | прямое чтение `.lint-results.json` через `lint/state.py` |

Plan #10 не добавляет MCP tool для autofix — это destructive операция, должна делаться через CLI или дашборд (Plan #14). LLM может только запустить и прочитать.

Server теперь регистрирует **14 tools** (было 12).

### 3.11 CLI

```bash
mnemos lint run [--vault PATH]             # exit 82 на LintError
mnemos lint results [--vault PATH] [--severity error|warning|info]
mnemos lint autofix [--vault PATH] [--dry-run]   # --dry-run печатает что бы починилось
```

Exit codes:
- 82 — LintError (general)
- 83 — LintCorruptError (.lint-results.json broken)
- 84 — UndoError (uses existing infra) — не нужен, уже 77

### 3.12 Wikilinks helper

Существующий `core/wikilinks.py` (Plan #8) даёт `extract_wikilinks`, `rewrite_wikilinks`, `find_files_referencing`. Использую их.

Plan #10 добавит **slug index** helper:

```python
# lint/utils.py
def build_slug_index(vault: Path) -> dict[str, Path]:
    """slug -> first matching wiki/*.md path. Conflicts: prefer entity > concept > source."""
```

Используется `wikilinks_broken` для resolution и Levenshtein lookup.

### 3.13 Levenshtein

Для `fix_wikilink_typo` нужен distance between two strings. Стандартная библиотека Python не имеет. Варианты:

- **Pure-python implementation** — простой DP O(m*n), достаточно для слов до 50 chars × few hundred candidates. **Выбираю.** No new dependency.
- `python-Levenshtein` C lib — быстрее, но new dep + wheels. Откладываю в Plan #11+ если perf будет проблемой.

Реализация ~15 строк в `lint/utils.py`.

---

## 4. Test strategy

### 4.1 Unit (per rule)

`tests/lint/test_rules.py`:
- `wikilinks_broken`: existing target → no finding; broken target → finding; broken with unique candidate → fixable=True with metadata.candidate
- `orphan_pages`: page with backlinks → no finding; isolated entity page → finding; sources never orphan-flagged
- `stale_pages`: `updated > today - 90` AND `confidence < 0.5` AND `status != verified`
- `duplicate_titles`: same title in two pages → both findings; case-insensitive equal
- `provenance_inferred_high` / `provenance_ambiguous_high`: thresholds correct
- `trailing_whitespace`: lines with trailing spaces detected; pure newline-only file → no finding
- `missing_required_frontmatter`: page with broken yaml → handled via page_parse_failed; missing `agent_written` → fixable
- `page_parse_failed`: invalid yaml → ERROR finding

### 4.2 Unit (runner + state + autofix + utils)

- `LintRunner.run`: end-to-end on synthetic vault
- `LintRunner.run` empty vault → 0 findings
- state save/load round-trip; corrupt json → LintCorruptError
- `apply_autofix`: snapshot created; pages mutated; activity entry written; tracker hooks fire
- `apply_autofix` with empty fixable set → no-op (no snapshot, no activity)
- `apply_autofix` undo: `mnemos undo <activity_id>` восстанавливает все trailing whitespace и broken wikilinks
- `levenshtein` distance correctness
- `build_slug_index` conflicts: entity > concept > source

### 4.3 Integration / REST

- `POST /lint/run` returns 200 + report; saves state file
- `GET /lint/results` 200 with last report; 404 if none
- `POST /lint/autofix` 200 with AutofixApiResult; 409 if no cached report
- `LintCorruptError` → 503

### 4.4 MCP

- `run_lint` через REST → success path
- `get_lint_results` reads .lint-results.json directly
- Daemon offline → write tool returns instructive error TextContent

### 4.5 CLI

- `mnemos lint run` exits 0; prints summary
- `mnemos lint results --severity warning` filters output
- `mnemos lint autofix --dry-run` prints planned fixes, no changes
- `mnemos lint autofix` writes through staging, snapshots, activity

---

## 5. Open questions

| # | Q | Решение |
|---|---|---|
| Q1 | Где жить lint package'у — `core/lint.py` (как в spec'е) или отдельный `lint/`? | Отдельный `claude_mnemos/lint/`. `core/` зарезервирован под примитивы; lint = feature module. |
| Q2 | LintReport кешируется только в `.lint-results.json` или ещё in-memory в daemon'е? | Только файл. Daemon stateless по lint'у — `GET /lint/results` всегда читает файл. Просто и понятно. |
| Q3 | `apply_autofix` принимает `report_id` или применяется всегда к последнему? | Только к последнему. Plan #14 (Dashboard) сможет пригнать ID-based dispatch если нужно; на CLI/MCP это излишество. |
| Q4 | Levenshtein threshold = 2. Что если оба candidates равноудалены? | `wikilinks_broken` finding с `fixable=False`. Только если **уникальный** candidate ≤2. |
| Q5 | Wikilinks regex `\[\[([^\]|]+)(?:\|[^\]]+)?\]\]` — handles aliases? | Уже сделано в `core/wikilinks.py` (Plan #8). Используем. |
| Q6 | orphan_pages для sources — flag или skip? | Skip. Sources всегда должны быть orphan (raw chats). |
| Q7 | stale_pages с `status="verified"` — flag или нет? | Skip. Verified никогда не stale автоматически (spec §8.7). |
| Q8 | autofix должен лочиться pipeline_lock'ом? | Да. Конкурентный ingest/ontology/undo читает же страницы — без lock'а гарантий нет. |
| Q9 | autofix через ontology Suggestion — для broken wikilinks low-conf? | Нет в Plan #10. Plan #11+. В Plan #10 wikilinks_broken просто остаётся в findings без fix. |
| Q10 | LintReport summary — при каждом run пересоздаётся, или пересчитывается из findings? | Пересоздаётся при `run`, сохраняется в файл. Чтение быстрое. |

---

## 6. Migration / compatibility

- ActivityOperationType расширяется (`"lint_fix"`) — старые logs парсятся.
- `.lint-results.json` — новый файл, нет миграции.
- Watchdog handler skip'ает `.lint-results.json` (dotfile rule).
- MCP server tools count: 12 → 14.
- CLI exit code 82/83 — новые, не пересекаются с существующими (73, 76, 77, 78, 79, 80, 81).
- Никаких dependency changes (Levenshtein — pure python).

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Lint runs slowly on large vaults (1000+ pages) | Single-pass: parse pages один раз, переиспользуем для всех правил. Targeted rules (slug index O(N), backlink graph O(N) тоже) |
| Levenshtein false positives | Threshold 2 + unique-candidate requirement strict; всё равно user может undo |
| Autofix corrupts page (e.g. fix_wikilink replaces unrelated text) | StagingTransaction snapshot перед apply; undo через activity log; tests |
| `.lint-results.json` race с concurrent run | Plan #10: lint runs only via REST under no lock — but state file write via atomic_write (tracker-aware). Concurrent `run` → last writer wins, который OK для cache. |
| Runner crashes mid-rule | Each rule wrapped in try/except, error → ERROR finding with rule_id, runner continues |
| StagingTransaction.write expects str body — autofix модифицирует frontmatter+body | serialize_page returns full markdown string, OK |

---

## 8. Estimated diff

- New files: 7 prod (`lint/__init__.py`, `models.py`, `rules.py`, `runner.py`, `autofix.py`, `state.py`, `exceptions.py`, `utils.py` actually 8) + `daemon/routes/lint.py` + `mcp/read_tools/lint.py` + `mcp/write_tools/lint.py` = 11 prod files
- New tests: ~9 test files
- Modified: `state/activity.py` (+ literal), `daemon/app.py`, `daemon/schemas.py`, `cli.py`, `mcp/server.py`
- LOC estimate: ~2000 prod + ~1700 tests
- Branch: `feat/lint`
- Expected commits: ~10
