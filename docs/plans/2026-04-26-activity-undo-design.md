# Design: Activity Center + Undo (Plan #4)

**Status:** approved scope, ready for implementation-plan generation.
**Date:** 2026-04-26
**Author:** Claude (with Yarik approval).
**Predecessor:** `2026-04-26-staging-snapshots-design.md` (Plan #3, merged in `f3831dd`).
**Successor planned:** Plan #5+ (daemon, dashboard, retention scheduler) или Plan #6 (ontology).

---

## 1. Goal

Зафиксировать в файле историю операций над vault'ом и дать CLI откатить любую из них через уже существующий `restore_from_snapshot` (Plan #3). После Plan #4 пользователь может:

- `mnemos activity` — увидеть «что я делал в этом vault'е»
- `mnemos undo <op_id>` — откатить конкретную операцию
- `mnemos undo --last` — откатить последнюю операцию

Это первая фича Plan #4 которая **видна пользователю** даже без UI: «история» + «undo» работают через CLI. Дашборд это уже потом просто красиво обернёт.

```
<vault>/
├── .activity.json                  # NEW: append-history с ActivityEntry'ями
├── .manifest.json                  # как в Plan #3
├── .staging/                       # как в Plan #3 (эфемерное)
├── .backups/<pre-op-...>/          # как в Plan #3 (snapshots ссылаются из activity)
├── .trash/                         # как в Plan #3
├── raw/chats/                      # как в Plan #3
└── wiki/{entities,concepts,sources}/   # как в Plan #3
```

---

## 2. Scope

### 2.1 In scope

| Компонент | Где |
|---|---|
| `ActivityEntry` Pydantic с минимальным набором полей | `state/activity.py` |
| `ActivityLog` — load/append/save через `<vault>/.activity.json` (full snapshot, не append-only) | `state/activity.py` |
| `log_activity()` хелпер — добавляет entry и сериализует в строку | `state/activity.py` |
| Pipeline пишет ActivityEntry **через тот же `StagingTransaction`** что и manifest (атомарно с promote) | `ingest/pipeline.py` |
| Запись entry на: `extracted`, `raw_only` | `ingest/pipeline.py` |
| **НЕ** запись на: `already_ingested`, `dry_run`, `failed` (StagingPromoteError — vault уже restored) | `ingest/pipeline.py` |
| `core/undo.py`: `can_undo(entry)`, `undo(vault, entry) -> UndoResult` | `core/undo.py` |
| Undo берёт `pipeline_lock` — нельзя undo во время ingest | `core/undo.py` |
| Undo добавляет в лог запись с `operation_type="manual_restore"` (chain history) | `core/undo.py` |
| Undo `manual_restore` запрещён (выкидывает explicit error) | `core/undo.py` |
| CLI `mnemos activity [--limit N]` — печатает последние N entries в hum-readable форме | `cli.py` |
| CLI `mnemos undo <op_id>` — точечный откат | `cli.py` |
| CLI `mnemos undo --last` — откатить последнюю undo-able entry | `cli.py` |
| Exit code 77 для UndoError (не undo-able / не найдена / restore failed) | `cli.py` |

### 2.2 Out of scope (явно отложено)

| Компонент | План |
|---|---|
| 180-day retention cleanup для activity entries | #5+ daemon |
| Auto-cleanup `.backups/` через scheduler | #5+ daemon |
| Dashboard view с `[Откатить]` кнопкой | #5+ dashboard |
| Полный 11-type vocabulary spec'а (ontology_apply, lint_fix, bulk_update, etc.) | когда соответствующие операции появятся |
| Activity entries для **other** операций (не ingest) | когда их добавим |
| Append-only JSON Lines storage (`.activity.jsonl`) | refactor когда log станет >10K записей |
| Generic post-restore хуки для разных operation_type | YAGNI до 2-го типа undo |
| Team features (`user` поле в entry) | v2.0 |
| `mnemos activity --filter status=failed` etc. | когда нужно |
| `mnemos activity --json` для скриптинга | когда нужно |

---

## 3. Architecture

### 3.1 Activity write path (пишется через staging)

```
pipeline.ingest()
  ├── parse_jsonl
  ├── compute sha
  ├── pipeline_lock
  ├── manifest = Manifest.load
  ├── if sha in manifest → return already_ingested  (NO activity entry written)
  ├── activity = ActivityLog.load(vault)             ← NEW
  │
  ├── with StagingTransaction(vault, op_id=session_id):
  │     ├── txn.write(raw, ...)
  │     ├── (extract path: write source + entities + concepts)
  │     ├── manifest.add(...)
  │     ├── txn.write(".manifest.json", manifest.serialize_to_string())
  │     │
  │     ├── activity.append(ActivityEntry(                                   ← NEW
  │     │     id=str(uuid4()), timestamp=utcnow,
  │     │     operation_type="ingest_extracted" | "ingest_raw_only",
  │     │     status="success",
  │     │     snapshot_path=None,         # filled AFTER promote — see below
  │     │     can_undo=True,
  │     │     affected_pages=[...],       # relative posix paths
  │     │     metadata={"session_id": session_id, "model": cfg.model, "tokens_in": ..., "tokens_out": ...},
  │     │   ))
  │     ├── txn.write(".activity.json", activity.serialize_to_string())
  │     │
  │     ├── if dry_run → txn.reject("dry-run") (returns)
  │     ├── promote = txn.promote_to_vault()                                  ← snapshot here
  │     │
  │     │   PROBLEM: snapshot_path is now known, but already written to staging.
  │     │   FIX: see §3.2 (post-promote rewrite vs pre-snapshot id resolution).
  ├── return IngestResult(...)
```

### 3.2 The snapshot_path chicken-and-egg problem

`ActivityEntry.snapshot_path` references the snapshot dir created during `promote_to_vault`. But we want to write `.activity.json` INTO that staging promote, so the entry is atomic with the rest. Two options:

**A) Predict snapshot path before promote (recommended).** `StagingTransaction` already knows `operation_id` and `operation_type`. The snapshot path format is `<vault>/.backups/pre-op-<utc-ts>-<type>-<id>/`. We can compute it at the same moment `promote_to_vault` would compute it, write activity with that path, then promote. Risk: timestamp drift if promote takes >1s after activity is written. Mitigation: `StagingTransaction.compute_snapshot_path()` method that returns the deterministic path AND `promote_to_vault()` reuses the same precomputed timestamp/path (don't recompute). This makes activity.snapshot_path predictably accurate.

**B) Two-phase write: activity entry written during promote, manifest atomic with pages, activity written AFTER promote.** Loses atomicity — if process crashes between page-promote and activity-write, vault has pages but no activity entry → silent loss of "this happened" record.

**Decision: A.** Add a `pre_promote_snapshot_path() -> Path` method to `StagingTransaction`: it locks in the snapshot timestamp early (on first call), `promote_to_vault` reuses it. Caller writes `.activity.json` into staging using this path, then calls promote. If snapshot already exists at the locked-in path on promote — `SnapshotError` (matches existing behavior).

### 3.3 Module map

**Новые:**
| Файл | Ответственность |
|---|---|
| `claude_mnemos/state/activity.py` | `ActivityEntry`, `ActivityLog`, `ActivityCorruptError`, `serialize_to_string` |
| `claude_mnemos/core/undo.py` | `UndoError`, `UndoResult`, `can_undo()`, `undo()` |

**Изменяемые:**
| Файл | Что |
|---|---|
| `claude_mnemos/core/staging.py` | Добавить `pre_promote_snapshot_path() -> Path` — стабильный путь, который `promote_to_vault` потом использует |
| `claude_mnemos/core/snapshots.py` | Добавить `create_snapshot_at(vault, snapshot_path, op_id, op_type)` — версия принимающая готовый путь (для §3.2) |
| `claude_mnemos/ingest/pipeline.py` | Создать activity log entry через staging; добавить `activity_id: str | None` в `IngestResult` (для UX) |
| `claude_mnemos/cli.py` | Subcommands `activity`, `undo`; новый exit code 77 (UndoError) |
| Tests везде | Расширить покрытие |

---

## 4. ActivityEntry contract

```python
ActivityStatus = Literal["success"]  # Plan #4 пишет только success entries; failed добавим позже
ActivityOperationType = Literal[
    "ingest_extracted",
    "ingest_raw_only",
    "manual_restore",
]
# (Plan #4 поддерживает 3; spec'овский 11-type vocabulary — когда соответствующие операции появятся.)


class ActivityEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str  # UUID hex
    timestamp: datetime  # UTC aware
    operation_type: ActivityOperationType
    status: ActivityStatus
    snapshot_path: str | None  # relative to vault root, e.g. ".backups/pre-op-...-ingest-abc"
    can_undo: bool
    undone: bool = False
    undone_at: datetime | None = None
    undone_by_id: str | None = None  # id of the manual_restore entry that undid this
    affected_pages: list[str] = Field(default_factory=list)  # relative posix paths
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActivityLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    entries: list[ActivityEntry] = Field(default_factory=list)

    @classmethod
    def load(cls, vault_root: Path) -> "ActivityLog": ...

    def serialize_to_string(self) -> str: ...

    def save(self, vault_root: Path) -> None:
        # Goes through atomic_write — same pattern as Manifest.save
        ...

    def append(self, entry: ActivityEntry) -> None:
        # ID uniqueness check; raises ValueError on duplicate
        ...

    def find_by_id(self, op_id: str) -> ActivityEntry | None: ...

    def last_undoable(self) -> ActivityEntry | None:
        # Iterate entries from newest to oldest; return first where can_undo=True and not undone.
        ...
```

**Field semantics:**
- `id` — opaque UUID. Used for `mnemos undo <op_id>`. NOT same as session_id (что в metadata).
- `snapshot_path` — relative to vault. Stored as string for portability. Resolved against `vault_root` at undo time.
- `can_undo: bool` — set at log write time. False for `failed` ops (no snapshot was created), False for `manual_restore` (можно делать undo, но не undo'нуть undo).
- `undone` / `undone_at` / `undone_by_id` — заполняются при undo. Это **изменение существующей entry**: log переписывается целиком (full snapshot pattern).

---

## 5. Undo semantics

```python
class UndoError(RuntimeError): ...

@dataclass(frozen=True)
class UndoResult:
    success: bool
    restored_pages: list[str]
    new_entry_id: str | None  # id of the manual_restore entry created by this undo
    error: str | None = None
    recovery_hint: str | None = None


def can_undo(entry: ActivityEntry, vault_root: Path) -> bool:
    """Чисто-функциональная проверка."""
    if entry.undone:
        return False
    if not entry.can_undo:
        return False
    if entry.snapshot_path is None:
        return False
    return (vault_root / entry.snapshot_path).is_dir()


def undo(vault_root: Path, op_id: str, *, lock_timeout: float = 60.0) -> UndoResult:
    """Откатить операцию по op_id.

    Атомарность: всё под pipeline_lock. Шаги:
    1. Load activity log → найти entry по op_id.
    2. Проверить can_undo(); если нет — UndoError с конкретной причиной.
    3. restore_from_snapshot(vault, entry.snapshot_path).
       На failure — UndoError с recovery_hint.
    4. Создать новую ActivityEntry с operation_type="manual_restore",
       status="success", snapshot_path=None, can_undo=False.
    5. Пометить старую entry как undone (с undone_at + undone_by_id=новый_id).
    6. activity.save(vault_root)  -- через atomic_write.
       (Здесь без StagingTransaction — undo не пишет page файлы.
       restore_from_snapshot уже свопает vault целиком; activity.json после restore
       нужно перезаписать вручную, потому что snapshot вернул его к старой версии.)

    Returns UndoResult(success=True, restored_pages=entry.affected_pages, new_entry_id=...).
    """
```

**Важная деталь:** `restore_from_snapshot` swap'ает весь vault, включая `.activity.json` — оно вернётся к pre-op версии (где новая entry ещё не была записана). После restore'а нам надо **сразу** перезаписать `.activity.json` в новый vault: добавить старую entry с `undone=True` и новую entry `manual_restore`. Это значит:

1. `entry_being_undone` существует в текущем (post-op) логе.
2. После `restore_from_snapshot` — текущий лог это pre-op версия. В ней `entry_being_undone` **отсутствует** (она была написана как часть op, который сейчас откатываем).
3. Нам надо создать чистый лог: `pre-op log + entry_being_undone (with undone=True) + manual_restore_entry`.
4. Записать через `atomic_write` (без staging — нечего staging'овать кроме одного файла).

**Why no StagingTransaction for undo?** Undo пишет только один файл (`.activity.json`). Staging+snapshot был бы overkill. Если activity.save упал — vault уже в restored состоянии, просто log не отражает undo. Пользователь увидит "забытую" old entry без undone=True; следующий undo на ту же entry скажет «already undone» (нет, сначала проверит — а undone=False, значит попробует ещё раз; restore вернёт vault в то же состояние; new manual_restore запишется). Это идемпотентно safe.

---

## 6. CLI commands

### 6.1 `mnemos activity [--limit N] [--vault <path>]`

Print last N entries (default 20) in human-readable form, newest first:

```
2026-04-26 14:35:12 UTC  ingest_extracted  abc123 — 5 pages, 1 collision   [undo: a8f2…]
2026-04-26 14:30:00 UTC  ingest_raw_only   def456 — 1 raw chat             [undo: 3c91…]
2026-04-26 13:55:00 UTC  manual_restore                                    [chain]
2026-04-26 13:50:42 UTC  ingest_extracted  abc123 — 5 pages          [UNDONE 13:55]
2026-04-25 20:11:00 UTC  ingest_extracted  xyz789 — 3 pages          [snapshot missing]
```

Suffix decides:
- `[undo: <id>]` — entry can_undo and not undone — show short id for `mnemos undo <id>`
- `[UNDONE <ts>]` — entry already undone
- `[chain]` — manual_restore entry (own op_id can be looked up via id field but не undoable)
- `[snapshot missing]` — entry can_undo but snapshot dir gone (manually deleted)

`--vault <path>` — if not given, use current directory.

### 6.2 `mnemos undo <op_id> [--vault <path>]`

Lookup entry by id (full UUID or short prefix — match by `startswith`, error if ambiguous), call `undo()`, print result:

Success:
```
undone: <op_type> from <timestamp>
restored 5 pages from snapshot <snapshot_path>
new activity entry: <new_id> (manual_restore)
```

Failure (UndoError):
```
error: cannot undo: <reason>
```
Exit 77.

### 6.3 `mnemos undo --last [--vault <path>]`

`activity_log.last_undoable()` → if None → exit 77 with "no undoable operation found". Otherwise same flow as `undo <op_id>`.

### 6.4 `mnemos activity --vault` is required argument or default-cwd?

Default: cwd. If user not in vault dir, they pass `--vault <path>`. Same convention as future `mnemos status` / `mnemos list` etc.

---

## 7. Pipeline integration changes

`pipeline.ingest`:

1. Load activity log alongside manifest (after lock acquired).
2. Compute `op_type` based on extract flag and dry_run flag (only `extracted` and `raw_only` paths reach the activity-write code).
3. Inside `with StagingTransaction(...)`:
   - After all manifest+pages writes:
   - Get snapshot_path from `txn.pre_promote_snapshot_path()` (locks the timestamp).
   - Build ActivityEntry (id=uuid4, timestamp=utcnow, status="success", snapshot_path=relative, can_undo=True, affected_pages, metadata).
   - Append to activity log; `txn.write(".activity.json", activity.serialize_to_string())`.
   - On dry_run → `txn.reject(...)` BEFORE writing activity (no activity entry for dry runs).
   - On promote_to_vault success → IngestResult(activity_id=entry.id).
4. **On `StagingPromoteError` during promote:** catch in pipeline (or let propagate?), write a separate `failed` activity entry in a fresh transaction (or directly via atomic_write since vault was restored).
   - **Decision:** for Plan #4 — let StagingPromoteError propagate to CLI. CLI caller doesn't get an activity entry for the failed op. **Why:** writing failed entry requires a second transaction (we're in restored-state), and adds complexity. Failed ops are observable via stderr + exit 76. Trade-off: no historical record of "I tried X and it failed". Acceptable for #4; can add in a follow-up.

**`IngestResult` extension:**
```python
@dataclass(frozen=True)
class IngestResult:
    ...  # existing fields
    activity_id: str | None = None  # id of the ActivityEntry created by this ingest
```

---

## 8. New exit code

| Code | Cause | Source |
|---|---|---|
| 77 | UndoError (entry not found, can't undo, restore failed) | NEW |

Все остальные exit codes — без изменений.

---

## 9. Error handling matrix

| Сценарий | Поведение |
|---|---|
| `mnemos undo <id>` где id не найден | UndoError("entry not found"), exit 77 |
| `mnemos undo <prefix>` где prefix matches multiple ids | UndoError("ambiguous prefix; matches N entries"), exit 77 |
| Entry exists but `can_undo=False` (e.g., manual_restore entry) | UndoError("entry not undoable"), exit 77 |
| Entry exists but `undone=True` | UndoError("entry already undone at <timestamp>"), exit 77 |
| Entry exists but snapshot_path file missing | UndoError("snapshot at <path> not found"), exit 77 |
| `restore_from_snapshot` fails partial | UndoError + recovery_hint в stderr, exit 77 |
| `mnemos undo --last` и нет undoable entries | UndoError("no undoable operation in activity log"), exit 77 |
| `.activity.json` corrupt (bad JSON / bad schema) | ActivityCorruptError → exit 74 (reuse ManifestCorruptError код для consistency) |
| activity.save fails after restore in undo() | log warning to stderr, return UndoResult(success=True), exit 0 — undo сам сработал, лог просто не обновлён |

---

## 10. Testing strategy

### 10.1 Уровни

1. **Unit (`activity.py`):**
   - load missing → empty log (with version=1, entries=[])
   - serialize_to_string roundtrip
   - append duplicate id → ValueError
   - find_by_id missing → None
   - find_by_id present → entry
   - last_undoable iterates from newest, skips undone, skips can_undo=False, returns None if none
   - corrupt JSON → ActivityCorruptError
   - corrupt schema → ActivityCorruptError

2. **Unit (`undo.py`):**
   - can_undo: undone → False
   - can_undo: can_undo=False → False
   - can_undo: snapshot missing → False
   - can_undo: all good → True
   - undo: entry not found → UndoError
   - undo: cannot undo → UndoError with explicit reason
   - undo: success → restores files (mock restore_from_snapshot), marks undone, appends manual_restore entry
   - undo: restore_from_snapshot fails → UndoError with recovery_hint
   - undo: activity.save fails after successful restore → return success=True, log warning (test stderr capture)

3. **Unit (`staging.py` extension):**
   - `pre_promote_snapshot_path()` returns deterministic path with locked timestamp
   - calling twice returns same path
   - `promote_to_vault` uses precomputed path

4. **Integration (`pipeline.py`):**
   - Successful ingest writes activity entry
   - activity entry has correct snapshot_path matching actual created snapshot
   - already_ingested → no new activity entry
   - dry_run → no activity entry
   - StagingPromoteError → no activity entry (vault restored, log unchanged)

5. **End-to-end CLI:**
   - `mnemos activity` shows recent entries
   - `mnemos activity --limit 5` limits output
   - `mnemos undo <id>` round-trips: ingest → activity → undo → vault state restored
   - `mnemos undo --last` undoes most recent undoable
   - `mnemos undo` non-existent id → exit 77

### 10.2 Coverage targets

- 144 текущих + ~25 новых.
- ruff + mypy strict чистые.
- Manual smoke в Task последний: ingest → activity (печатает) → undo (vault restored, новая entry в log) → activity (undone суффикс).

---

## 11. Known limitations

1. **Failed ops НЕ логируются.** `StagingPromoteError` не создаёт activity entry. Нет исторического записи "я попробовал X и оно упало". Acceptable trade-off.
2. **Activity log full-snapshot rewrite на каждую запись.** Для тысяч entries — performance issue. Refactor на JSON Lines когда станет проблемой.
3. **Snapshot и activity log могут рассинхронизироваться.** `undo` вызывает `restore_from_snapshot` (vault целиком вернулся) и потом перезаписывает `.activity.json`. Между этими двумя шагами — окно где log из старого snapshot. Если activity.save упал → пользователь видит «забытую» entry. Не критично.
4. **Нет 180-day retention cleanup.** Activity log растёт. `.backups/` тоже. Пока нет демона/scheduler'а — пользователь чистит вручную.
5. **Undo собственного manual_restore запрещён.** Если пользователь сделал undo неправильной операции — единственный способ откатить это назад — ручной `restore_from_snapshot` другого snapshot'а. Не очень UX, но защита от циклов.
6. **op_id prefix matching не unique-prefix-aware.** Если две entries: `a8f2...` и `a8f3...`, `mnemos undo a8` → ambiguous. Пользователь должен дать больше символов. По UX, можно показать ambiguous list — реализуем как warning + список вариантов.
7. **`mnemos activity` без `--vault` использует cwd.** Если запущен не из vault dir — мусорно.

---

## 12. What this enables (#5+ onwards)

- **Plan #5+ (daemon/dashboard):** dashboard просто читает `.activity.json` и рендерит таблицу с кнопкой `[Undo]` которая зовёт REST endpoint, который зовёт `core/undo.undo()`. Никакой новой логики.
- **Plan #5+ (scheduler):** retention cleanup для activity entries и snapshots — общий 180-day rule.
- **Plan #6 (ontology):** ontology operations пишут в тот же activity log с `operation_type="ontology_apply"`. Generic undo работает для них без изменений (если они через StagingTransaction → snapshot → restore работает).

---

## 13. Решения, которые я принял сам (для протокола)

| Решение | Альтернатива | Почему выбрал |
|---|---|---|
| Activity log пишется через `StagingTransaction.write` атомарно с pages+manifest | Отдельный atomic_write после promote | Атомарность: либо всё (pages+manifest+activity), либо ничего. Иначе risk: pages написаны, activity нет → undo через manifest невозможен. |
| `pre_promote_snapshot_path()` lock'ает timestamp заранее | Записать activity без snapshot_path и потом patch'ить | Двойной write = двойная сложность + risk рассинхрона. Lock timestamp решает изящнее. |
| Failed ops не логируются | Логировать с status="failed" | Требует второго pass'а после restored vault. Сложность не оправдана для Plan #4. Failed visible через stderr+exit 76. |
| Undo пишет лог напрямую через atomic_write (не через StagingTransaction) | Через staging | Undo пишет только 1 файл. StagingTransaction = snapshot + atomic move = overkill. atomic_write достаточен. |
| Undo собственного manual_restore запрещён | Разрешить → потенциальный цикл | Защита. Если неправильно undo — пользователь делает руками. |
| Op_id это UUID hex, не session_id | Использовать session_id как id | Session_id может повториться (тот же ingest дважды — Plan #5 hooks). UUID гарантирует уникальность. session_id остаётся в metadata. |
| `affected_pages` это list[str] относительных путей, не wikilinks | Wikilinks `[[...]]` | Plan #4 без UI — текстовое отображение в CLI лучше через relative paths. Wikilinks — когда дашборд появится. |
| Single activity log per vault (`<vault>/.activity.json`) | Per-day файлы / sharding | Yagni. Простота. Refactor когда станет огромным. |
| `mnemos undo --last` — отдельный flag, не дефолт без аргументов | `mnemos undo` без аргументов = `--last` | Защита от опечатки. Явный `--last` намерение явное. |
| `mnemos activity` default --limit 20 | Печатать всё | Vault может содержать сотни entries. Дефолт читаемый, `--limit 0` = всё. |
| Записывать `manual_restore` entry в лог после успешного undo | Не записывать | Chain history полезен: «вижу что ingest был, вижу что я его откатил». Без записи — undo выглядит как "удаление" из истории. |

---

## 14. Open questions для имплементации (не блокеры)

- Реализация `pre_promote_snapshot_path` в StagingTransaction: лазить ли в `_timestamp()` snapshot модуля или дублировать формат? Решу при коде.
- `mnemos activity` форматирование суффиксов: точная грамматика "undo: a8f2…" vs "undo with: a8f2…". Косметика.
- Что если `.activity.json` живёт но `.manifest.json` отсутствует? Возможно после ручного редактирования. Pipeline всё равно работает (manifest=empty → no dedup), activity append'ит. Edge case, не блокер.
- ActivityEntry.metadata — `dict[str, Any]` или typed (отдельные поля для session_id, model, tokens)? Сейчас `dict[str, Any]` — для extensibility. Решу при коде.
