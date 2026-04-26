# Design: Staging + Snapshots (Plan #3)

**Status:** approved scope, ready for implementation-plan generation.
**Date:** 2026-04-26
**Author:** Claude (with Yarik approval).
**Predecessor:** `2026-04-26-llm-extraction-design.md` (Plan #2, merged in `77251c3`).
**Successor planned:** Plan #4 (Activity Center / Layer 5).

---

## 1. Goal

Закрыть partial-write window из Plan #2 через Layer 2 (`StagingTransaction`) и Layer 4 (snapshots + restore). После Plan #3 ingest pipeline становится транзакционным: либо все страницы и manifest появляются в vault'е атомарно, либо ничего — всегда с возможностью откатить vault к pre-operation snapshot.

Это **не** добавляет новых пользовательских фич — оно превращает уже работающий pipeline из «обычно работает, при крахе посередине будет беда» в «никогда не оставит vault сломанным».

```
<vault>/
├── .manifest.json                  # как в Plan #2
├── .staging/                       # NEW: транзакционная зона
│   └── <operation_id>/             # эфемерное; cleanup после promote
├── .backups/                       # NEW: snapshots
│   └── pre-op-<ts>-<type>-<id>/    # full vault copy + .meta.json
├── raw/chats/<sid>.md              # как в Plan #2
└── wiki/{entities,concepts,sources}/<slug>.md    # как в Plan #2
```

CLI и vault layout с точки зрения пользователя не меняются (помимо двух новых служебных директорий). Ingest-команда та же.

---

## 2. Scope

### 2.1 In scope

| Компонент | Где |
|---|---|
| `StagingTransaction(vault, operation_id)` контекст-менеджер | `core/staging.py` |
| `staging.write(relative_path, content)` — пишет в `.staging/<op_id>/<rel>` | `core/staging.py` |
| `staging.promote_to_vault()` — snapshot → atomic moves staging→vault → cleanup staging; on error → restore_from_snapshot | `core/staging.py` |
| `staging.reject(reason)` — move staging → `.trash/rejected-<op_id>/`, не тронуть vault | `core/staging.py` |
| `create_snapshot(vault, operation_id, operation_type) -> Path` | `core/snapshots.py` |
| `restore_from_snapshot(vault, snapshot) -> RestoreResult` — copy-first/atomic-swap | `core/snapshots.py` |
| Snapshot `.meta.json` (timestamp, operation_id, operation_type, page_count, vault_size_bytes) | `core/snapshots.py` |
| Pipeline.ingest рефакторинг: все writes через `StagingTransaction` | `ingest/pipeline.py` |
| `IngestResult.snapshot_path: Path | None` — где snapshot для возможного rollback | `ingest/pipeline.py` |
| Новый exit code 76 для StagingPromoteError | `cli.py` |
| Тесты: staging contract, snapshot create/restore, pipeline-уровень transaction (включая crash mid-promote → rollback) | `tests/` |

### 2.2 Out of scope (явно отложено)

| Компонент | План |
|---|---|
| Daily snapshots (scheduler) | #5+ daemon |
| 180-day retention cleanup | #5+ daemon |
| `daemon_pause()` во время restore | #5+ daemon |
| Pre-promote validation: lint check | #3.5 / #6 |
| Pre-promote validation: ontology safety check | #6 ontology |
| Quarantine для invalid staging | требует validation |
| Restore UI / `Restore` button | #5+ dashboard |
| Activity Center log_rejection / log_promote | #4 |
| Incremental snapshots (только diff) | v1.x |
| Snapshot compression (zip/tar) | v1.x |
| `--restore <snapshot>` CLI команда | возможно #4, пока вручную |

---

## 3. Architecture

### 3.1 Data flow после #3

```
mnemos ingest <jsonl> <vault> [flags]
   │
   ▼
parse_jsonl
   │
   ▼
acquire pipeline_lock(vault)
   │
   ▼
manifest = Manifest.load(vault)
if sha in manifest.ingested → return already_ingested  (no staging needed)
   │
   ▼
With StagingTransaction(vault, operation_id=session_id) as txn:
   │
   ▼
  txn.write(raw_relative, raw_body)                       # raw/chats/<sid>.md
   │
   ▼
  IF --no-llm:
     manifest.add(...) (in-memory)
     txn.write(".manifest.json", serialize(manifest))      # обновлённый manifest
  ELSE:
     extracted = extract_wiki_pages(...)
     check source page collision (HARD FAIL → txn auto-cleanup)
     check extracted collisions → split to to_write / skipped
     for p in to_write: txn.write(p.relative_path, p.serialize())
     manifest.add(IngestRecord(...))
     txn.write(".manifest.json", serialize(manifest))
   │
   ▼
  IF --dry-run:
     txn.reject("dry-run")  → moves staging into .trash/rejected-...
     return IngestResult(status="dry_run", ...)
   │
   ▼
  txn.promote_to_vault():
     snapshot_path = create_snapshot(vault, operation_id, "ingest")
     try:
         for staged_file in staging.rglob(*):
             atomic_write(vault / relative, staged_file.read_text())
         shutil.rmtree(staging_dir)
     except Exception:
         restore_from_snapshot(vault, snapshot_path)
         raise StagingPromoteError(...)
     return PromoteResult(snapshot=snapshot_path)
   │
   ▼
return IngestResult(status="extracted"|"raw_only", snapshot_path=..., ...)
```

### 3.2 Module map

**Новые:**
| Файл | Ответственность |
|---|---|
| `claude_mnemos/core/staging.py` | `StagingTransaction` контекст-менеджер, `PromoteResult` dataclass, `StagingPromoteError` |
| `claude_mnemos/core/snapshots.py` | `create_snapshot`, `restore_from_snapshot`, `SnapshotMeta` Pydantic, `RestoreResult` dataclass, `SnapshotError` |

**Изменяемые:**
| Файл | Что |
|---|---|
| `claude_mnemos/ingest/pipeline.py` | Все vault-writes идут через `StagingTransaction`. Manifest update теперь часть транзакции, не отдельный шаг. `IngestResult` получает поле `snapshot_path: Path \| None`. Source-collision check переезжает внутрь staging (HARD FAIL вызывает выход из `with` без promote → staging cleanup автоматический) |
| `claude_mnemos/cli.py` | Новый exit code 76 для `StagingPromoteError` |
| `tests/test_pipeline.py` | Дополнить тестами: snapshot создаётся, promote переносит файлы, mid-promote crash → restore, --dry-run → reject path, snapshot_path в IngestResult |

### 3.3 StagingTransaction contract

```python
class StagingTransaction:
    def __init__(self, vault: Path, operation_id: str, operation_type: str = "ingest") -> None: ...

    def __enter__(self) -> "StagingTransaction":
        # mkdir .staging/<operation_id>/
        ...

    def __exit__(self, exc_type, exc, tb) -> bool:
        # if exc → reject (cleanup staging without promoting)
        # if no exc and not promoted → reject (caller forgot to call promote)
        # return False (don't suppress)
        ...

    def write(self, relative_path: Path, content: str) -> None:
        """Write to staging area. NOT to vault."""

    def promote_to_vault(self) -> PromoteResult:
        """Snapshot → atomic move staging→vault → cleanup. On error → restore."""

    def reject(self, reason: str) -> None:
        """Move staging dir → .trash/rejected-<op_id>-<ts>/ with reason file."""
```

State machine: `created` → (`promoted` | `rejected`). Каждый instance используется ровно один раз.

### 3.4 Snapshot format

```
<vault>/.backups/pre-op-<YYYY-MM-DD-HH-MM-SS>-<operation_type>-<operation_id>/
  ├── .meta.json                    # SnapshotMeta
  ├── .manifest.json                # копия (если был)
  ├── raw/chats/...                 # копия (если есть)
  └── wiki/...                      # копия (если есть)
```

`.meta.json`:
```json
{
  "timestamp": "2026-04-26T14:30:00+00:00",
  "operation_id": "abc-123",
  "operation_type": "ingest",
  "vault_size_bytes": 4096,
  "page_count": 5
}
```

Что **не** попадает в snapshot: `.staging/`, `.backups/`, `.trash/`, `.pipeline.lock`. Используем `shutil.ignore_patterns(...)`.

---

## 4. Error handling и rollback semantics

### 4.1 Промежуточные состояния

| Стадия | Crash здесь → что в vault'е | Что делает наш код |
|---|---|---|
| До `with StagingTransaction(...):` | vault не тронут | — |
| Внутри `with` block, перед `promote_to_vault()` | vault не тронут (всё в `.staging/`) | `__exit__` (с exc или без) → `reject()` → перенос staging в `.trash/rejected-...` |
| `create_snapshot` упал | vault не тронут | `StagingPromoteError` поднимается из `promote_to_vault()`; `__exit__` ловит exception → `reject()` → staging уходит в `.trash/rejected-<op_id>/` (для разбора). Простое и единообразное правило: всё, что не promoted, уезжает в trash. |
| Mid-promote (часть файлов уже moved) | vault в полусостоянии | `restore_from_snapshot(vault, snapshot)` — copy-first/atomic-swap; vault приведён к pre-op состоянию; `StagingPromoteError` поднимается |
| После promote, до `shutil.rmtree(staging)` | vault корректен, staging висит | log warning; staging cleanup на следующем ingest или вручную |

### 4.2 RestoreResult

```python
@dataclass(frozen=True)
class RestoreResult:
    success: bool
    vault_intact: bool             # True если staging упал ДО touching vault
    vault_possibly_corrupted: bool  # True если atomic swap сломался посередине
    error: str | None
    recovery_hint: str | None      # человекочитаемая инструкция при partial failure
```

### 4.3 Без daemon_pause

Spec §7.4 говорит про `daemon_pause()` во время `restore_from_snapshot` чтобы избежать гонки с активным ingest. У нас демона нет — pipeline-level FileLock уже сериализует все ingest операции. Restore вызывается ВНУТРИ того же FileLock'а (он держится до конца `with pipeline_lock(...):`), так что параллельный ingest невозможен. Когда появится демон (Plan #5+), добавим `daemon_pause()` отдельно.

### 4.4 Один snapshot per ingest, даже на --no-llm

Любой promote порождает snapshot, даже если writes тривиальны. Это даёт пользователю единообразный rollback опыт независимо от режима. Cost: extra full vault copy на каждый ingest. Для маленьких vault (наша целевая аудитория solo developer'ов с десятками-сотнями pages) — ок. Когда vault разрастётся, придёт incremental snapshots (v1.x).

---

## 5. Pipeline integration

Перед: `pipeline.ingest` имел три точки прямой записи в vault:
1. `atomic_write(raw_target, raw_body)` — raw chat
2. цикл `for p in to_write: atomic_write(target, p.serialize())` — wiki pages
3. `manifest.save(vault_root)` — manifest

После: все три через `txn.write(...)`. Финальный `txn.promote_to_vault()` атомарно переносит всё.

`Manifest.save(vault)` остаётся в API манифеста — но pipeline его НЕ зовёт напрямую. Вместо этого pipeline сериализует manifest через `Manifest.serialize_to_string()` (новый метод) и пишет через `txn.write(".manifest.json", content)`. Это означает добавить в `state/manifest.py` метод-сериализатор, отделённый от записи на диск.

`IngestResult` расширяется одним полем:
```python
@dataclass(frozen=True)
class IngestResult:
    ...  # существующие поля
    snapshot_path: Path | None = None
```
- `extracted` / `raw_only` → `snapshot_path` указывает на созданный snapshot.
- `already_ingested` / `dry_run` → `snapshot_path = None`.

CLI печатает snapshot_path в success message:
```
extracted: session_id=abc-123 pages=5 skipped=0 tokens_in=1000 tokens_out=200
snapshot: /vault/.backups/pre-op-2026-04-26-14-30-00-ingest-abc-123/
```

---

## 6. New exit code

| Code | Cause | Source |
|---|---|---|
| 76 | StagingPromoteError | NEW |

Все остальные exit codes — без изменений.

`StagingPromoteError` поднимается когда:
- `create_snapshot` упал (vault intact, можно retry)
- mid-promote ошибка + restore прошёл успешно (vault восстановлен)
- mid-promote ошибка + restore тоже сломался (vault в полусостоянии — message содержит recovery_hint)

Различить эти три случая можно через прикреплённый `RestoreResult`. Достаточно ли одного exit code 76 для всех трёх? Да — пользователю всё равно нужно посмотреть в stderr для деталей; отдельные коды добавляются если нужна автоматическая обработка script'ом, чего пока нет.

---

## 7. Testing strategy

### 7.1 Уровни

1. **Unit (staging.py):**
   - `test_staging_init_creates_dir`
   - `test_write_creates_relative_path_in_staging`
   - `test_write_does_not_touch_vault`
   - `test_promote_moves_files_to_vault`
   - `test_promote_creates_snapshot`
   - `test_promote_cleans_up_staging`
   - `test_promote_returns_promote_result`
   - `test_promote_twice_raises`
   - `test_reject_moves_staging_to_trash`
   - `test_exit_without_promote_rejects`
   - `test_exit_with_exception_rejects`
   - `test_promote_failure_restores_from_snapshot` (mock os.replace to raise mid-promote)

2. **Unit (snapshots.py):**
   - `test_create_snapshot_copies_vault_contents`
   - `test_create_snapshot_excludes_staging_backups_trash_lock`
   - `test_create_snapshot_writes_meta_json`
   - `test_create_snapshot_with_empty_vault`
   - `test_restore_swaps_vault_atomically`
   - `test_restore_preserves_old_state_on_failure`
   - `test_restore_returns_recovery_hint_on_partial_failure`

3. **Integration (pipeline.py rewrite):**
   - Все 12 текущих pipeline-тестов остаются зелёными после рефакторинга.
   - Новые тесты:
     - `test_ingest_extracted_creates_snapshot` — IngestResult.snapshot_path указывает на существующую директорию с pages
     - `test_ingest_no_llm_creates_snapshot`
     - `test_ingest_dry_run_no_snapshot_no_writes` — dry_run rejects staging
     - `test_ingest_already_ingested_no_snapshot`
     - `test_ingest_promote_failure_restores_vault` — mock atomic_write to fail mid-promote, assert vault contents == pre-op state
     - `test_ingest_creates_staging_then_cleans_up` — после успеха `.staging/` пуст
     - `test_ingest_failure_in_with_block_rejects_staging` — exception между write и promote → staging уехал в `.trash/rejected-...`

4. **CLI:**
   - `test_cli_prints_snapshot_path` — успешный ingest содержит "snapshot:" в stdout

### 7.2 Coverage targets

- 112 текущих + ~25 новых.
- mypy strict + ruff чистые.

---

## 8. Known limitations

1. **Snapshot — full copy.** При vault'е в десятки тысяч страниц каждый ingest скопирует всё целиком. Incremental — v1.x.
2. **Snapshot никогда не удаляются автоматически.** До #5+ daemon. Пользователь видит как `.backups/` растёт; может удалить вручную.
3. **`raw/chats/` копируется в каждый snapshot.** Транскрипты могут быть жирными. Включаем сейчас, потом подумаем про exclude (но это означает rollback не вернёт удалённые transcripts).
4. **Restore CLI отсутствует.** Если promote сам не восстановил (rare partial failure case) — пользователь читает `recovery_hint` в stderr и копирует файлы вручную. CLI команда `--restore <snapshot>` — Plan #4 или позже.
5. **Snapshot performance.** На каждом ingest полная `shutil.copytree` всего vault'а. Для маленьких vault (наша аудитория) — ок (миллисекунды). Для будущих больших vault — bottleneck; mitigation в v1.x.
6. **No daemon_pause.** OK для CLI-only режима под FileLock. Когда появится демон — добавится.
7. **Quarantine отсутствует.** Plan #3 без validation — нечего отвергать программно. `reject()` есть но используется только для dry-run и __exit__-on-error.

---

## 9. What this enables (#4 onwards)

После Plan #3 vault **транзакционен** для ingest операций. Это разблокирует:

- **Plan #4 (Activity Center):** `.activity.json` log с `op_id`, `snapshot_path`, `restore_command`. Undo button в будущем дашборде сводится к "найти запись в activity log → restore_from_snapshot".
- **Plan #6 (Ontology):** ontology-merge операция тоже использует `StagingTransaction(operation_type="ontology")` — staging позволит preview merge'а до commit'а.
- **Plan #5+ (Daemon/Dashboard):** daily snapshots становятся одной строкой в scheduler'е (зовут `create_snapshot(vault, "daily", "scheduled")`).

---

## 10. Решения, которые я принял сам (для протокола)

| Решение | Альтернатива | Почему выбрал |
|---|---|---|
| Snapshot включает manifest.json | manifest вне snapshot | Без manifest в snapshot restore сделает pages консистентными со старым manifest, но pages-from-staging не запишутся → manifest и vault рассинхронизируются. Включение даёт целостность. |
| Manifest update идёт через staging.write | прямой `manifest.save(vault)` после promote | Если promote прошёл но manifest.save упал — vault с pages, но без manifest entry → следующий ingest перепишет (в Plan #2 это OK с skip-collision). С Plan #3 хочется атомарности — manifest либо есть для всех, либо нет ни для одной. |
| `operation_id = session_id` | UUID per operation | Session ID уже стабильный per-session. Использование того же ID делает snapshot имя предсказуемым (`pre-op-...-ingest-<sid>`) — легко найти. |
| Snapshot per ingest, всегда | Только при `--snapshot` flag / только при extract path | Единообразие безопасности. Пользователь не должен помнить включить snapshot. Cost (full copy) приемлем для целевых vault размеров. |
| RestoreResult вместо raise | Бросать исключение вместо возвращать структуру | Restore часто вызывается из except-блока promote. Возврат структуры даёт promote'у решать что делать (raise StagingPromoteError с recovery_hint в message). Восстановление **частично сломавшегося** vault'а — не та ошибка, которую можно бросить и забыть. |
| `__exit__` reject если promote не вызывали | требовать explicit reject() / fail loud | Programmer-friendly. Если caller забыл promote (или произошёл exception) — staging автоматически уезжает в `.trash/`, vault не тронут. Forgetting to commit txn в DB — известная боль; not fail loud, just clean up. |
| Без daemon_pause | имитировать его через FileLock | FileLock уже есть. daemon_pause в spec'е специфически для случая когда демон параллельно слушает файловые события и может прервать restore. Без демона это не нужно. |
| Включаем `raw/chats/` в snapshot | Исключать (только wiki/ + manifest) | Семантика "rollback к pre-op state" должна означать **полный** state. Если бы мы исключили raw/chats, после restore удалённые транскрипты не вернулись бы. Это не фича, это сюрприз. |
| Один exit code 76 для всех staging ошибок | Отдельные для restore_ok / restore_failed / vault_corrupt | Скрипт сейчас не различает; пользователь читает stderr. Можно расщепить позже когда появится автоматизация. |

---

## 11. Open questions для имплементации (не блокеры)

- Где именно хранить `_promote_attempted` / `_rejected` флаги: instance attrs или enum state? Решу при коде, склоняюсь к простым bool'ам.
- `shutil.copytree` на Windows может падать с PermissionError на файлах под антивирусом. Нужно ли retry-обёртывать? Скорее всего да, по тому же паттерну что `atomic_write`. Решу при имплементации.
- Тест `test_restore_returns_recovery_hint_on_partial_failure` требует мокать `Path.rename` посередине — моковать через `monkeypatch.setattr`. Детали — в плане.
