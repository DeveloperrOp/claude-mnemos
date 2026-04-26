# Activity Center + Undo Implementation Plan (Plan #4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.activity.json` log записи на каждую успешную ingest операцию плюс CLI команды `mnemos activity` (показать историю) и `mnemos undo <op_id>` / `mnemos undo --last` (откатить через уже существующий `restore_from_snapshot`).

**Architecture:** См. design doc `docs/plans/2026-04-26-activity-undo-design.md` (commit `1ff4a42`). Activity entry пишется **через тот же `StagingTransaction`** что и pages+manifest — атомарно с promote. `StagingTransaction.pre_promote_snapshot_path()` лочит timestamp до promote, чтобы в activity записать предсказуемый snapshot_path. Generic `undo()` зовёт `restore_from_snapshot` под `pipeline_lock`, потом перезаписывает activity log напрямую через `atomic_write` (vault уже restored, snapshot+staging излишен для одного файла).

**Tech Stack:** Python 3.12, Pydantic v2, filelock, pytest+ruff+mypy strict.

---

## Что НЕ делаем в этом плане

См. §2.2 design doc'а — 180-day retention cleanup, dashboard view, полный 11-type vocabulary spec'а, failed activity entries, append-only JSONL storage, generic post-restore хуки, team `user` field, advanced filters в `mnemos activity`, `--json` output. Всё это планы #5+ и #6.

---

## Files map

**Создаём:**

| Файл | Ответственность |
|---|---|
| `claude_mnemos/state/activity.py` | `ActivityEntry`, `ActivityLog`, `ActivityCorruptError`, `ACTIVITY_FILENAME` |
| `claude_mnemos/core/undo.py` | `UndoError`, `UndoResult`, `can_undo`, `undo` |
| `tests/test_activity.py` | |
| `tests/test_undo.py` | |

**Изменяем:**

| Файл | Что |
|---|---|
| `claude_mnemos/core/snapshots.py` | Добавить `create_snapshot_at(vault, snapshot_path, *, operation_id, operation_type)` — версия принимающая готовый путь. Существующий `create_snapshot(...)` переписать как тонкий wrapper что вычисляет ts и зовёт `create_snapshot_at`. |
| `claude_mnemos/core/staging.py` | Добавить `pre_promote_snapshot_path() -> Path` — лочит timestamp при первом вызове, `promote_to_vault` переиспользует через `create_snapshot_at`. |
| `claude_mnemos/ingest/pipeline.py` | Добавить activity entry в staging перед promote. `IngestResult.activity_id: str \| None` поле. |
| `claude_mnemos/cli.py` | Subcommands `activity` и `undo`; новый exit code 77 (UndoError) |
| `tests/test_snapshots.py` | Добавить тест для `create_snapshot_at` (что path передаваемый используется буквально) |
| `tests/test_staging.py` | Добавить тест для `pre_promote_snapshot_path` (детерминированность, lock timestamp) |
| `tests/test_pipeline.py` | Добавить тесты на activity_id и snapshot_path consistency |
| `tests/test_cli.py` | Добавить тесты на `mnemos activity` и `mnemos undo` |

---

## Зависимости между задачами

```
Task 1 (activity module) ─────┐
                              │
Task 2 (snapshots+staging extension) ─┐
                              │       │
Task 3 (undo module) ←────────┘       │
                                      │
Task 4 (pipeline integration) ←───────┘ ← uses 1, 2
    ↓
Task 5 (CLI subcommands) ← uses 1, 3, 4
    ↓
Task 6 (manual smoke + verification)
```

---

## Task 1: Activity module

**Files:**
- Create: `claude_mnemos/state/activity.py`
- Test: `tests/test_activity.py`

**Why:** Pydantic-валидируемый log с `ActivityEntry` и `ActivityLog`. Загружается/сохраняется как single JSON file `<vault>/.activity.json`. Используется Task 4 (pipeline пишет entry через staging) и Task 3 (undo читает + помечает undone).

- [ ] **Step 1: Падающие тесты**

`tests/test_activity.py`:

```python
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from claude_mnemos.state.activity import (
    ACTIVITY_FILENAME,
    ActivityCorruptError,
    ActivityEntry,
    ActivityLog,
)


def _entry(
    *,
    op_type: str = "ingest_extracted",
    can_undo: bool = True,
    undone: bool = False,
    snapshot_path: str | None = ".backups/pre-op-2026-04-26-14-30-00-ingest-abc",
) -> ActivityEntry:
    return ActivityEntry(
        id=uuid4().hex,
        timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
        operation_type=op_type,
        status="success",
        snapshot_path=snapshot_path,
        can_undo=can_undo,
        undone=undone,
        affected_pages=["wiki/entities/foo.md"],
        metadata={"session_id": "abc-123"},
    )


def test_load_missing_file_returns_empty_log(tmp_path: Path):
    log = ActivityLog.load(tmp_path)
    assert log.version == 1
    assert log.entries == []


def test_save_then_load_roundtrip(tmp_path: Path):
    log = ActivityLog()
    log.append(_entry(op_type="ingest_extracted"))
    log.save(tmp_path)

    assert (tmp_path / ACTIVITY_FILENAME).exists()

    loaded = ActivityLog.load(tmp_path)
    assert len(loaded.entries) == 1
    assert loaded.entries[0].operation_type == "ingest_extracted"
    assert loaded.entries[0].metadata["session_id"] == "abc-123"


def test_serialize_to_string_matches_save_output(tmp_path: Path):
    log = ActivityLog()
    log.append(_entry())

    serialized = log.serialize_to_string()
    log.save(tmp_path)
    on_disk = (tmp_path / ACTIVITY_FILENAME).read_text(encoding="utf-8")

    assert serialized == on_disk


def test_load_corrupt_json_raises(tmp_path: Path):
    (tmp_path / ACTIVITY_FILENAME).write_text("not json {", encoding="utf-8")
    with pytest.raises(ActivityCorruptError):
        ActivityLog.load(tmp_path)


def test_load_invalid_schema_raises(tmp_path: Path):
    (tmp_path / ACTIVITY_FILENAME).write_text(
        '{"version":1,"entries":[{"unknown_field":1}]}',
        encoding="utf-8",
    )
    with pytest.raises(ActivityCorruptError):
        ActivityLog.load(tmp_path)


def test_load_unknown_top_level_field_raises(tmp_path: Path):
    (tmp_path / ACTIVITY_FILENAME).write_text(
        '{"version":1,"entries":[],"unknown":1}',
        encoding="utf-8",
    )
    with pytest.raises(ActivityCorruptError):
        ActivityLog.load(tmp_path)


def test_append_duplicate_id_raises():
    log = ActivityLog()
    e = _entry()
    log.append(e)
    with pytest.raises(ValueError):
        log.append(_entry(op_type="ingest_raw_only").model_copy(update={"id": e.id}))


def test_find_by_id_present():
    log = ActivityLog()
    e = _entry()
    log.append(e)
    found = log.find_by_id(e.id)
    assert found is not None
    assert found.id == e.id


def test_find_by_id_missing():
    log = ActivityLog()
    log.append(_entry())
    assert log.find_by_id("nonexistent") is None


def test_last_undoable_returns_newest_undoable():
    log = ActivityLog()
    e_old = _entry()
    log.append(e_old)
    # Newer entry but not undoable
    e_mid = _entry(can_undo=False).model_copy(
        update={"id": uuid4().hex, "timestamp": datetime(2026, 4, 26, 15, 0, 0, tzinfo=UTC)}
    )
    log.append(e_mid)
    # Newest undoable
    e_new = _entry().model_copy(
        update={"id": uuid4().hex, "timestamp": datetime(2026, 4, 26, 16, 0, 0, tzinfo=UTC)}
    )
    log.append(e_new)

    found = log.last_undoable()
    assert found is not None
    assert found.id == e_new.id


def test_last_undoable_returns_none_when_all_undone():
    log = ActivityLog()
    log.append(_entry(undone=True))
    log.append(_entry(can_undo=False).model_copy(update={"id": uuid4().hex}))
    assert log.last_undoable() is None


def test_save_uses_atomic_write_no_partial_file(tmp_path: Path, monkeypatch):
    log = ActivityLog()
    log.append(_entry())

    def boom(*args, **kwargs):
        raise RuntimeError("simulated mid-write crash")

    monkeypatch.setattr("claude_mnemos.core.atomic.os.replace", boom)
    with pytest.raises(RuntimeError):
        log.save(tmp_path)

    leftovers = list(tmp_path.glob(f"{ACTIVITY_FILENAME}*"))
    assert leftovers == []


def test_entry_with_none_snapshot_path():
    """manual_restore entries have snapshot_path=None."""
    e = ActivityEntry(
        id=uuid4().hex,
        timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
        operation_type="manual_restore",
        status="success",
        snapshot_path=None,
        can_undo=False,
        affected_pages=[],
        metadata={"undone_id": "abc"},
    )
    assert e.snapshot_path is None
    assert e.can_undo is False
```

- [ ] **Step 2: Запустить — упадут**

```bash
cd /d/code/claude-mnemos && .venv/Scripts/python.exe -m pytest tests/test_activity.py -v
```

Ожидаем: ImportError.

- [ ] **Step 3: Реализовать `claude_mnemos/state/activity.py`**

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_mnemos.core.atomic import atomic_write

ACTIVITY_FILENAME = ".activity.json"

ActivityStatus = Literal["success"]
ActivityOperationType = Literal[
    "ingest_extracted",
    "ingest_raw_only",
    "manual_restore",
]


class ActivityCorruptError(ValueError):
    """Raised when activity log file is unreadable or fails schema validation."""


class ActivityEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    timestamp: datetime
    operation_type: ActivityOperationType
    status: ActivityStatus
    snapshot_path: str | None
    can_undo: bool
    undone: bool = False
    undone_at: datetime | None = None
    undone_by_id: str | None = None
    affected_pages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActivityLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    entries: list[ActivityEntry] = Field(default_factory=list)

    @classmethod
    def load(cls, vault_root: Path) -> ActivityLog:
        path = vault_root / ACTIVITY_FILENAME
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ActivityCorruptError(
                f"activity log at {path} is not valid JSON: {exc}"
            ) from exc
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ActivityCorruptError(
                f"activity log at {path} fails schema: {exc}"
            ) from exc

    def serialize_to_string(self) -> str:
        return (
            json.dumps(
                self.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=False,
            )
            + "\n"
        )

    def save(self, vault_root: Path) -> None:
        path = vault_root / ACTIVITY_FILENAME
        atomic_write(path, self.serialize_to_string())

    def append(self, entry: ActivityEntry) -> None:
        if any(e.id == entry.id for e in self.entries):
            raise ValueError(f"activity log already contains entry id {entry.id}")
        self.entries.append(entry)

    def find_by_id(self, op_id: str) -> ActivityEntry | None:
        for e in self.entries:
            if e.id == op_id:
                return e
        return None

    def last_undoable(self) -> ActivityEntry | None:
        for e in reversed(self.entries):
            if e.can_undo and not e.undone:
                return e
        return None
```

- [ ] **Step 4: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_activity.py -v
```

Ожидаем: 12 passed.

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное (144 + 12 = 156 + 1 skipped).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/state/activity.py tests/test_activity.py
git commit -m "feat(state): activity log with append-only entries and atomic save"
```

---

## Task 2: pre_promote_snapshot_path + create_snapshot_at

**Files:**
- Modify: `claude_mnemos/core/snapshots.py` (add `create_snapshot_at`, refactor `create_snapshot` to delegate)
- Modify: `claude_mnemos/core/staging.py` (add `pre_promote_snapshot_path`, use precomputed path in `promote_to_vault`)
- Modify: `tests/test_snapshots.py` (add test for `create_snapshot_at`)
- Modify: `tests/test_staging.py` (add test for `pre_promote_snapshot_path`)

**Why:** Pipeline'у нужен предсказуемый snapshot_path до того как `promote_to_vault` его создаст — чтобы записать в activity entry правильный путь и закоммитить эту entry атомарно вместе с pages в том же staging promote.

- [ ] **Step 1: Падающие тесты**

В `tests/test_snapshots.py` дописать в конец:

```python
def test_create_snapshot_at_uses_provided_path(tmp_path: Path):
    """create_snapshot_at writes to the exact path provided, not auto-generated."""
    from claude_mnemos.core.snapshots import create_snapshot_at

    vault = tmp_path / "vault"
    _populate_vault(vault)

    custom_path = vault / ".backups" / "custom-name-here"
    snap = create_snapshot_at(
        vault, custom_path, operation_id="abc-123", operation_type="ingest"
    )

    assert snap == custom_path
    assert snap.exists()
    assert (snap / ".meta.json").exists()
    assert (snap / "wiki" / "entities" / "foo.md").exists()


def test_create_snapshot_at_collision_raises(tmp_path: Path):
    """Reuses spec'd 'collision raises' behavior."""
    from claude_mnemos.core.snapshots import SnapshotError, create_snapshot_at

    vault = tmp_path / "vault"
    _populate_vault(vault)
    target = vault / ".backups" / "fixed-name"
    create_snapshot_at(vault, target, operation_id="abc", operation_type="ingest")

    with pytest.raises(SnapshotError):
        create_snapshot_at(vault, target, operation_id="abc", operation_type="ingest")


def test_create_snapshot_delegates_to_create_snapshot_at(tmp_path: Path):
    """create_snapshot still works (back-compat) and produces same shape as before."""
    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_snapshot(vault, operation_id="abc", operation_type="ingest")

    assert snap.parent == vault / ".backups"
    assert snap.name.startswith("pre-op-")
    assert snap.name.endswith("-abc")
    assert (snap / ".meta.json").exists()
```

В `tests/test_staging.py` дописать в конец:

```python
def test_pre_promote_snapshot_path_is_deterministic(tmp_path: Path):
    """First call locks the path; subsequent calls return the same path."""
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        path1 = txn.pre_promote_snapshot_path()
        path2 = txn.pre_promote_snapshot_path()
        assert path1 == path2
        assert path1.parent == vault / ".backups"
        assert path1.name.endswith("-ingest-op-1")
        txn.promote_to_vault()


def test_promote_uses_pre_computed_snapshot_path(tmp_path: Path):
    """If pre_promote_snapshot_path is called first, promote uses that exact path."""
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-2") as txn:
        txn.write(Path("a.md"), "x")
        locked = txn.pre_promote_snapshot_path()
        result = txn.promote_to_vault()
        assert result.snapshot == locked


def test_promote_without_pre_promote_call_still_works(tmp_path: Path):
    """If caller never calls pre_promote_snapshot_path, promote auto-computes."""
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-3") as txn:
        txn.write(Path("a.md"), "x")
        result = txn.promote_to_vault()
        assert result.snapshot is not None
        assert result.snapshot.parent == vault / ".backups"
        assert result.snapshot.name.endswith("-ingest-op-3")
```

- [ ] **Step 2: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_snapshots.py tests/test_staging.py -v
```

Ожидаем: 3+3 fail (ImportError на `create_snapshot_at`, AttributeError на `pre_promote_snapshot_path`).

- [ ] **Step 3: Расширить `claude_mnemos/core/snapshots.py`**

Заменить `create_snapshot` на пару функций (`create_snapshot_at` core + `create_snapshot` тонкая обёртка), не меняя поведение существующих вызовов:

В файле `claude_mnemos/core/snapshots.py`, после `_vault_size` функции и перед `create_snapshot`, добавить:

```python
def create_snapshot_at(
    vault: Path,
    snap_path: Path,
    *,
    operation_id: str,
    operation_type: str,
) -> Path:
    """Create a snapshot at the exact path provided.

    Same exclusion rules and meta.json behavior as create_snapshot, but the
    target path is dictated by the caller (used by StagingTransaction to lock
    in a snapshot path before promote, so activity entries can reference it).
    """
    if snap_path.exists():
        raise SnapshotError(f"snapshot already exists: {snap_path}")

    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.mkdir(parents=True)

    if vault.exists():
        for item in vault.iterdir():
            if item.name in _EXCLUDED_DIRS or item.name in _EXCLUDED_FILES:
                continue
            dest = snap_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, ignore=_ignore_internal)
            else:
                shutil.copy2(item, dest)

    page_count = _count_pages(snap_path)
    size_bytes = _vault_size(snap_path)

    meta = SnapshotMeta(
        timestamp=datetime.now(UTC).isoformat(),
        operation_id=operation_id,
        operation_type=operation_type,
        page_count=page_count,
        vault_size_bytes=size_bytes,
    )
    (snap_path / META_FILENAME).write_text(
        json.dumps(meta.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    return snap_path
```

И заменить существующую `create_snapshot` на тонкую обёртку:

```python
def create_snapshot(
    vault: Path,
    *,
    operation_id: str,
    operation_type: str,
) -> Path:
    """Create a snapshot with auto-generated UTC timestamp in the path."""
    ts = _timestamp()
    snap_name = f"pre-op-{ts}-{operation_type}-{operation_id}"
    snap_path = vault / SNAPSHOTS_DIRNAME / snap_name
    return create_snapshot_at(
        vault, snap_path, operation_id=operation_id, operation_type=operation_type
    )
```

- [ ] **Step 4: Расширить `claude_mnemos/core/staging.py`**

В `class StagingTransaction`:

В `__init__` добавить инициализацию:
```python
        self._locked_snapshot_path: Path | None = None
```

Добавить метод (после `__enter__` / `__exit__`, перед `write`):

```python
    def pre_promote_snapshot_path(self) -> Path:
        """Lock in and return the snapshot path that promote_to_vault will use.

        First call computes the path from current UTC time + op_id + op_type.
        Subsequent calls return the same path. promote_to_vault re-uses it.

        Used by callers (e.g. pipeline) that need to write the snapshot path
        into a staged file (e.g. activity log entry) BEFORE the snapshot
        is actually created.
        """
        if self._locked_snapshot_path is None:
            from claude_mnemos.core.snapshots import SNAPSHOTS_DIRNAME, _timestamp
            ts = _timestamp()
            snap_name = f"pre-op-{ts}-{self.operation_type}-{self.operation_id}"
            self._locked_snapshot_path = self.vault / SNAPSHOTS_DIRNAME / snap_name
        return self._locked_snapshot_path
```

В `promote_to_vault`, заменить:

```python
        # 1. Snapshot vault BEFORE moving anything.
        try:
            snapshot = create_snapshot(
                self.vault,
                operation_id=self.operation_id,
                operation_type=self.operation_type,
            )
        except Exception as exc:
            raise StagingPromoteError(
                f"snapshot creation failed: {exc}"
            ) from exc
```

на:

```python
        # 1. Snapshot vault BEFORE moving anything. Use precomputed path if
        # caller invoked pre_promote_snapshot_path() — guarantees activity
        # entries written into staging reference the correct snapshot.
        try:
            if self._locked_snapshot_path is not None:
                from claude_mnemos.core.snapshots import create_snapshot_at
                snapshot = create_snapshot_at(
                    self.vault,
                    self._locked_snapshot_path,
                    operation_id=self.operation_id,
                    operation_type=self.operation_type,
                )
            else:
                snapshot = create_snapshot(
                    self.vault,
                    operation_id=self.operation_id,
                    operation_type=self.operation_type,
                )
        except Exception as exc:
            raise StagingPromoteError(
                f"snapshot creation failed: {exc}"
            ) from exc
```

(Имя `create_snapshot_at` импортируется лениво внутри метода, чтобы не плодить циклы.)

- [ ] **Step 5: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_snapshots.py tests/test_staging.py -v
```

Ожидаем: все passed (11 + 3 в test_snapshots = 14, 12 + 3 в test_staging = 15).

- [ ] **Step 6: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное (162 + 1 skipped).

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/core/snapshots.py claude_mnemos/core/staging.py tests/test_snapshots.py tests/test_staging.py
git commit -m "feat(core): pre_promote_snapshot_path locks snapshot path before promote"
```

---

## Task 3: Undo module

**Files:**
- Create: `claude_mnemos/core/undo.py`
- Test: `tests/test_undo.py`

**Why:** Generic `undo()` берёт `pipeline_lock`, читает activity log, проверяет `can_undo`, зовёт `restore_from_snapshot`, потом перезаписывает activity log напрямую (vault уже restored, snapshot+staging излишен).

- [ ] **Step 1: Падающие тесты**

`tests/test_undo.py`:

```python
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from claude_mnemos.core.snapshots import RestoreResult
from claude_mnemos.core.undo import UndoError, UndoResult, can_undo, undo
from claude_mnemos.state.activity import ActivityEntry, ActivityLog


def _populate_vault_with_one_ingest(tmp_path: Path) -> tuple[Path, str, Path]:
    """Set up vault with a fake snapshot and one activity entry; return (vault, op_id, snap_path)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    snap_dir = vault / ".backups" / "pre-op-2026-04-26-14-30-00-ingest-abc"
    snap_dir.mkdir(parents=True)
    (snap_dir / ".meta.json").write_text(
        '{"timestamp":"2026-04-26T14:30:00+00:00","operation_id":"abc",'
        '"operation_type":"ingest","page_count":0,"vault_size_bytes":0}',
        encoding="utf-8",
    )

    op_id = uuid4().hex
    log = ActivityLog()
    log.append(
        ActivityEntry(
            id=op_id,
            timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
            operation_type="ingest_extracted",
            status="success",
            snapshot_path=".backups/pre-op-2026-04-26-14-30-00-ingest-abc",
            can_undo=True,
            affected_pages=["wiki/entities/foo.md"],
            metadata={"session_id": "abc"},
        )
    )
    log.save(vault)
    return vault, op_id, snap_dir


def test_can_undo_true_for_undoable_entry(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    assert entry is not None
    assert can_undo(entry, vault) is True


def test_can_undo_false_when_undone(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    assert entry is not None
    entry.undone = True
    assert can_undo(entry, vault) is False


def test_can_undo_false_when_can_undo_flag_false(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    assert entry is not None
    entry.can_undo = False
    assert can_undo(entry, vault) is False


def test_can_undo_false_when_snapshot_path_none(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    entry = ActivityEntry(
        id="x",
        timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
        operation_type="manual_restore",
        status="success",
        snapshot_path=None,
        can_undo=False,
        affected_pages=[],
        metadata={},
    )
    assert can_undo(entry, vault) is False


def test_can_undo_false_when_snapshot_dir_missing(tmp_path: Path):
    vault, op_id, snap_dir = _populate_vault_with_one_ingest(tmp_path)
    # Remove snapshot dir
    import shutil
    shutil.rmtree(snap_dir)
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    assert entry is not None
    assert can_undo(entry, vault) is False


def test_undo_entry_not_found_raises(tmp_path: Path):
    vault, _, _ = _populate_vault_with_one_ingest(tmp_path)
    with pytest.raises(UndoError, match="not found"):
        undo(vault, "nonexistent-id")


def test_undo_already_undone_raises(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)
    log = ActivityLog.load(vault)
    entry = log.find_by_id(op_id)
    assert entry is not None
    entry.undone = True
    log.save(vault)

    with pytest.raises(UndoError, match="already undone"):
        undo(vault, op_id)


def test_undo_snapshot_missing_raises(tmp_path: Path):
    vault, op_id, snap_dir = _populate_vault_with_one_ingest(tmp_path)
    import shutil
    shutil.rmtree(snap_dir)
    with pytest.raises(UndoError, match="snapshot"):
        undo(vault, op_id)


def test_undo_success_marks_entry_undone(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)

    # Stub restore to claim success without actually swapping the vault dir
    # (we just want to verify post-restore log update logic)
    def fake_restore(vault_arg, snapshot_arg):
        return RestoreResult(success=True, vault_intact=False)

    with patch("claude_mnemos.core.undo.restore_from_snapshot", side_effect=fake_restore):
        result = undo(vault, op_id)

    assert isinstance(result, UndoResult)
    assert result.success is True
    assert result.new_entry_id is not None

    log = ActivityLog.load(vault)
    original = log.find_by_id(op_id)
    assert original is not None
    assert original.undone is True
    assert original.undone_at is not None
    assert original.undone_by_id == result.new_entry_id

    new_entry = log.find_by_id(result.new_entry_id)
    assert new_entry is not None
    assert new_entry.operation_type == "manual_restore"
    assert new_entry.can_undo is False
    assert new_entry.snapshot_path is None
    assert new_entry.metadata["undone_id"] == op_id


def test_undo_restore_failure_raises_with_recovery_hint(tmp_path: Path):
    vault, op_id, _ = _populate_vault_with_one_ingest(tmp_path)

    def fake_failed_restore(vault_arg, snapshot_arg):
        return RestoreResult(
            success=False,
            vault_intact=False,
            vault_possibly_corrupted=True,
            error="rename failed",
            recovery_hint="manual recovery needed at /tmp/old",
        )

    with patch("claude_mnemos.core.undo.restore_from_snapshot", side_effect=fake_failed_restore):
        with pytest.raises(UndoError, match="restore failed"):
            undo(vault, op_id)


def test_undo_manual_restore_entry_not_undoable(tmp_path: Path):
    """A manual_restore entry has can_undo=False, so undo refuses."""
    vault = tmp_path / "vault"
    vault.mkdir()
    log = ActivityLog()
    op_id = uuid4().hex
    log.append(
        ActivityEntry(
            id=op_id,
            timestamp=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
            operation_type="manual_restore",
            status="success",
            snapshot_path=None,
            can_undo=False,
            affected_pages=[],
            metadata={},
        )
    )
    log.save(vault)

    with pytest.raises(UndoError):
        undo(vault, op_id)
```

- [ ] **Step 2: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_undo.py -v
```

Ожидаем: ImportError.

- [ ] **Step 3: Реализовать `claude_mnemos/core/undo.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.snapshots import restore_from_snapshot
from claude_mnemos.state.activity import ActivityEntry, ActivityLog


class UndoError(RuntimeError):
    """Raised when undo cannot proceed (entry missing, not undoable, restore failed)."""


@dataclass(frozen=True)
class UndoResult:
    success: bool
    restored_pages: list[str]
    new_entry_id: str | None
    error: str | None = None
    recovery_hint: str | None = None


def can_undo(entry: ActivityEntry, vault_root: Path) -> bool:
    """Pure check: entry undone? snapshot path set? snapshot dir exists?"""
    if entry.undone:
        return False
    if not entry.can_undo:
        return False
    if entry.snapshot_path is None:
        return False
    return (vault_root / entry.snapshot_path).is_dir()


def undo(
    vault_root: Path,
    op_id: str,
    *,
    lock_timeout: float = 60.0,
) -> UndoResult:
    """Atomically undo the operation identified by op_id.

    Steps:
    1. Acquire pipeline_lock.
    2. Load activity log; find entry by id (raise UndoError if missing).
    3. Verify can_undo (raise UndoError with reason if not).
    4. restore_from_snapshot — on failure, raise UndoError with recovery_hint.
    5. After restore: vault is now in pre-op state. Re-load activity log
       (it was swapped along with vault), append manual_restore entry,
       mark original as undone, save.
    """
    with pipeline_lock(vault_root, timeout=lock_timeout):
        log = ActivityLog.load(vault_root)
        entry = log.find_by_id(op_id)
        if entry is None:
            raise UndoError(f"activity entry not found: {op_id}")
        if entry.undone:
            raise UndoError(f"entry {op_id} already undone at {entry.undone_at}")
        if not entry.can_undo:
            raise UndoError(f"entry {op_id} is not undoable")
        if entry.snapshot_path is None:
            raise UndoError(f"entry {op_id} has no snapshot_path")
        snap_path = vault_root / entry.snapshot_path
        if not snap_path.is_dir():
            raise UndoError(
                f"snapshot at {snap_path} not found (manually deleted?)"
            )

        result = restore_from_snapshot(vault_root, snap_path)
        if not result.success:
            raise UndoError(
                f"restore failed: {result.error}"
                + (
                    f". recovery hint: {result.recovery_hint}"
                    if result.recovery_hint
                    else ""
                )
            )

        # Vault was swapped — re-load activity log from the restored vault.
        # The original entry exists there (it was written during the op being undone? No:
        # the snapshot was taken BEFORE the op, so the snapshot's .activity.json does NOT
        # contain the op's entry. After restore, log lacks the entry — we add it back
        # explicitly with undone=True, then append manual_restore.)
        log = ActivityLog.load(vault_root)

        new_id = uuid4().hex
        now = datetime.now(UTC)

        # Add the original entry (now flagged undone) so the user sees their history.
        original = entry.model_copy(
            update={
                "undone": True,
                "undone_at": now,
                "undone_by_id": new_id,
            }
        )
        # The snapshot may already contain the original entry if the user did:
        #   ingest -> ingest -> undo first.
        # In that case the older snapshot has the FIRST entry but not the SECOND.
        # We want to re-add the SECOND entry (the one we just undid) here.
        # But find_by_id might already have it from a preserved log. Idempotent-safe:
        if log.find_by_id(original.id) is None:
            log.append(original)
        # Else: log already has this entry; mutate in place by reconstruction.
        # (Pydantic frozen=False on ActivityLog allows replacing — entries is a list.)
        else:
            for i, e in enumerate(log.entries):
                if e.id == original.id:
                    log.entries[i] = original
                    break

        manual_restore_entry = ActivityEntry(
            id=new_id,
            timestamp=now,
            operation_type="manual_restore",
            status="success",
            snapshot_path=None,
            can_undo=False,
            affected_pages=list(original.affected_pages),
            metadata={"undone_id": original.id},
        )
        log.append(manual_restore_entry)
        log.save(vault_root)

        return UndoResult(
            success=True,
            restored_pages=list(original.affected_pages),
            new_entry_id=new_id,
        )
```

- [ ] **Step 4: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_undo.py -v
```

Ожидаем: 11 passed.

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное (173 + 1 skipped).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/core/undo.py tests/test_undo.py
git commit -m "feat(core): generic undo via restore_from_snapshot with manual_restore chain entry"
```

---

## Task 4: Pipeline integration — write activity entry through staging

**Files:**
- Modify: `claude_mnemos/ingest/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Why:** Pipeline.ingest должен:
1. Загрузить activity log после lock'а.
2. Внутри `with StagingTransaction`: записать pages+manifest как раньше; затем зафиксировать snapshot_path через `pre_promote_snapshot_path()`; добавить ActivityEntry в log; записать `.activity.json` в staging.
3. На dry_run → reject (entry в staging уедет в .trash, не попадёт в vault).
4. На promote success → IngestResult получает поле `activity_id`.

`already_ingested` ветка НЕ пишет activity entry.

- [ ] **Step 1: Дополнить тесты в `tests/test_pipeline.py`**

В `tests/test_pipeline.py` дописать в конец:

```python
def test_ingest_extracted_writes_activity_entry(tmp_path: Path):
    from claude_mnemos.state.activity import ActivityLog

    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )

    assert res.activity_id is not None

    log = ActivityLog.load(vault)
    assert len(log.entries) == 1
    entry = log.entries[0]
    assert entry.id == res.activity_id
    assert entry.operation_type == "ingest_extracted"
    assert entry.can_undo is True
    # snapshot_path in activity matches the actual snapshot dir
    assert entry.snapshot_path is not None
    assert (vault / entry.snapshot_path).is_dir()
    assert (vault / entry.snapshot_path) == res.snapshot_path
    # affected_pages includes wiki entries (relative posix)
    assert any("wiki/entities/fastapi.md" in p for p in entry.affected_pages)
    # metadata carries session_id
    assert entry.metadata.get("session_id") == "abc-123"


def test_ingest_no_llm_writes_activity_entry(tmp_path: Path):
    from claude_mnemos.state.activity import ActivityLog

    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=None,
        extractor=None,
        extract=False,
        today=FIXED_TODAY,
    )

    assert res.activity_id is not None
    log = ActivityLog.load(vault)
    assert len(log.entries) == 1
    entry = log.entries[0]
    assert entry.operation_type == "ingest_raw_only"
    assert entry.can_undo is True
    assert entry.snapshot_path is not None


def test_ingest_already_ingested_no_activity_entry(tmp_path: Path):
    """Re-ingesting same JSONL must not append a duplicate activity entry."""
    from claude_mnemos.state.activity import ActivityLog

    vault = tmp_path / "vault"
    extractor = MagicMock(side_effect=_stub_extractor())
    ingest(FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor, today=FIXED_TODAY)
    second = ingest(
        FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor, today=FIXED_TODAY
    )

    assert second.status == "already_ingested"
    assert second.activity_id is None

    log = ActivityLog.load(vault)
    assert len(log.entries) == 1  # still only one


def test_ingest_dry_run_no_activity_entry(tmp_path: Path):
    """Dry-run must not append a permanent activity entry (staging gets rejected)."""
    from claude_mnemos.state.activity import ACTIVITY_FILENAME, ActivityLog

    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        dry_run=True,
        today=FIXED_TODAY,
    )

    assert res.activity_id is None
    # No activity file in vault root (only in trash via rejected staging)
    assert not (vault / ACTIVITY_FILENAME).exists()


def test_ingest_promote_failure_no_activity_entry(tmp_path: Path, monkeypatch):
    """Failed promote leaves vault unchanged AND no activity entry."""
    from claude_mnemos.state.activity import ACTIVITY_FILENAME

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "preexisting.md").write_text("survives", encoding="utf-8")

    import shutil as _shutil
    real_move = _shutil.move
    calls = {"n": 0}

    def flaky_move(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("simulated mid-promote failure")
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr("claude_mnemos.core.staging.shutil.move", flaky_move)

    from claude_mnemos.core.staging import StagingPromoteError

    with pytest.raises(StagingPromoteError):
        ingest(
            FIXTURE,
            vault,
            cfg=_cfg(),
            llm_client=MagicMock(),
            extractor=_stub_extractor(),
            today=FIXED_TODAY,
        )

    # Vault: pre-existing file survived
    assert (vault / "preexisting.md").read_text(encoding="utf-8") == "survives"
    # No activity log in vault
    assert not (vault / ACTIVITY_FILENAME).exists()
```

- [ ] **Step 2: Запустить новые тесты — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -v
```

Ожидаем: 5 новых fail (нет поля `activity_id`, нет activity log writing).

- [ ] **Step 3: Изменить `claude_mnemos/ingest/pipeline.py`**

В файле `claude_mnemos/ingest/pipeline.py` сделать следующие правки:

(A) В импорты добавить:
```python
from uuid import uuid4

from claude_mnemos.state.activity import ActivityEntry, ActivityLog, ActivityOperationType
```

(B) В `IngestResult` добавить поле:
```python
@dataclass(frozen=True)
class IngestResult:
    status: IngestStatus
    session_id: str
    raw_path: Path | None
    source_path: Path | None = None
    created_pages: list[Path] = field(default_factory=list)
    skipped_collisions: list[str] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    snapshot_path: Path | None = None
    activity_id: str | None = None  # NEW
```

(C) В функции `ingest`, после загрузки manifest и проверки already_ingested, добавить загрузку activity log:

Найти:
```python
        manifest = Manifest.load(vault_root)
        if sha in manifest.ingested:
            existing = manifest.ingested[sha]
            return IngestResult(
                ...
            )
```

Добавить **после** этого блока (но **перед** `raw_relative = ...`):
```python
        activity = ActivityLog.load(vault_root)
```

(D) В **no-llm path**, после `txn.write(Path(".manifest.json"), manifest.serialize_to_string())`:

```python
                # Build & log activity entry BEFORE promote so it lands in vault atomically.
                snapshot_target = txn.pre_promote_snapshot_path()
                activity_id = uuid4().hex
                activity.append(
                    _build_activity_entry(
                        op_type="ingest_raw_only",
                        snapshot_target=snapshot_target,
                        vault_root=vault_root,
                        affected=[raw_relative.as_posix()],
                        metadata={"session_id": session_id},
                        entry_id=activity_id,
                    )
                )
                txn.write(Path(ACTIVITY_FILENAME), activity.serialize_to_string())

                if dry_run:
                    txn.reject("dry-run (--no-llm)")
                    return IngestResult(
                        status="dry_run",
                        session_id=session_id,
                        raw_path=None,
                        snapshot_path=None,
                        activity_id=None,  # entry rejected with staging
                    )

                promote = txn.promote_to_vault()
                return IngestResult(
                    status="raw_only",
                    session_id=session_id,
                    raw_path=vault_root / raw_relative,
                    snapshot_path=promote.snapshot,
                    activity_id=activity_id,
                )
```

(E) В **LLM-extract path**, после `txn.write(Path(".manifest.json"), manifest.serialize_to_string())`:

```python
            # Build & log activity entry BEFORE promote so it lands in vault atomically.
            snapshot_target = txn.pre_promote_snapshot_path()
            activity_id = uuid4().hex
            affected_paths = [p.relative_path.as_posix() for p in to_write]
            affected_paths.append(raw_relative.as_posix())
            activity.append(
                _build_activity_entry(
                    op_type="ingest_extracted",
                    snapshot_target=snapshot_target,
                    vault_root=vault_root,
                    affected=affected_paths,
                    metadata={
                        "session_id": session_id,
                        "model": cfg.model,
                        "input_tokens": extraction.input_tokens,
                        "output_tokens": extraction.output_tokens,
                        "skipped_collisions": skipped,
                    },
                    entry_id=activity_id,
                )
            )
            txn.write(Path(ACTIVITY_FILENAME), activity.serialize_to_string())

            if dry_run:
                txn.reject("dry-run (--extract)")
                return IngestResult(
                    status="dry_run",
                    session_id=session_id,
                    raw_path=None,
                    source_path=None,
                    created_pages=[vault_root / p.relative_path for p in to_write],
                    skipped_collisions=skipped,
                    input_tokens=extraction.input_tokens,
                    output_tokens=extraction.output_tokens,
                    model=cfg.model,
                    snapshot_path=None,
                    activity_id=None,
                )

            promote = txn.promote_to_vault()

            return IngestResult(
                status="extracted",
                session_id=session_id,
                raw_path=vault_root / raw_relative,
                source_path=vault_root / source_relative,
                created_pages=[vault_root / p.relative_path for p in to_write],
                skipped_collisions=skipped,
                input_tokens=extraction.input_tokens,
                output_tokens=extraction.output_tokens,
                model=cfg.model,
                snapshot_path=promote.snapshot,
                activity_id=activity_id,
            )
```

(F) В импорты добавить:
```python
from claude_mnemos.state.activity import ACTIVITY_FILENAME
```
(если ещё не добавлен в (A)).

(G) В конец файла, после `_to_wikilink`, добавить хелпер:

```python
def _build_activity_entry(
    *,
    op_type: ActivityOperationType,
    snapshot_target: Path,
    vault_root: Path,
    affected: list[str],
    metadata: dict[str, object],
    entry_id: str,
) -> ActivityEntry:
    snapshot_relative = snapshot_target.relative_to(vault_root).as_posix()
    return ActivityEntry(
        id=entry_id,
        timestamp=datetime.now(UTC),
        operation_type=op_type,
        status="success",
        snapshot_path=snapshot_relative,
        can_undo=True,
        affected_pages=affected,
        metadata=metadata,
    )
```

(`datetime` и `UTC` уже импортированы вверху файла.)

(H) В `already_ingested` ветке убедиться что возвращается `activity_id=None`:

Найти `return IngestResult(... status="already_ingested", ...)` и добавить:
```python
                snapshot_path=None,
                activity_id=None,
```

- [ ] **Step 4: Прогнать pipeline тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -v
```

Ожидаем: ~23 passed (18 старых + 5 новых).

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное (~178 + 1 skipped).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/ingest/pipeline.py tests/test_pipeline.py
git commit -m "refactor(ingest): write activity entry through staging atomically with promote"
```

---

## Task 5: CLI subcommands `activity` and `undo`

**Files:**
- Modify: `claude_mnemos/cli.py`
- Modify: `tests/test_cli.py`

**Why:** Точечный CLI для пользователя: `mnemos activity` (история) и `mnemos undo <op_id>` / `mnemos undo --last` (откат). Ловим UndoError → exit 77. ActivityCorruptError → exit 74 (reuse manifest corrupt code).

- [ ] **Step 1: Падающие тесты**

В конец `tests/test_cli.py` дописать:

```python
def test_cli_activity_lists_recent_entries(tmp_path: Path):
    vault = tmp_path / "vault"
    # Seed via no-llm ingest
    res_ingest = _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    assert res_ingest.returncode == 0

    res_activity = _run("activity", "--vault", str(vault))
    assert res_activity.returncode == 0, res_activity.stderr
    assert "ingest_raw_only" in res_activity.stdout


def test_cli_activity_limit(tmp_path: Path):
    vault = tmp_path / "vault"
    _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    res = _run("activity", "--vault", str(vault), "--limit", "0")
    assert res.returncode == 0
    # --limit 0 means show all; with 1 entry stdout still has it
    assert "ingest_raw_only" in res.stdout


def test_cli_activity_empty_vault(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    res = _run("activity", "--vault", str(vault))
    assert res.returncode == 0
    assert "no activity" in res.stdout.lower() or res.stdout.strip() == ""


def test_cli_undo_unknown_id_returns_77(tmp_path: Path):
    vault = tmp_path / "vault"
    _run("ingest", str(FIXTURE), str(vault), "--no-llm")

    res = _run("undo", "fake-id-doesnotexist", "--vault", str(vault))
    assert res.returncode == 77
    assert "not found" in res.stderr.lower()


def test_cli_undo_last_no_undoable_returns_77(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    res = _run("undo", "--last", "--vault", str(vault))
    assert res.returncode == 77
    assert "no undoable" in res.stderr.lower()


def test_cli_undo_last_succeeds_after_ingest(tmp_path: Path):
    vault = tmp_path / "vault"
    res_ingest = _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    assert res_ingest.returncode == 0

    res_undo = _run("undo", "--last", "--vault", str(vault))
    assert res_undo.returncode == 0, res_undo.stderr
    assert "undone" in res_undo.stdout.lower() or "restored" in res_undo.stdout.lower()

    # Verify activity log now has 2 entries: ingest (undone=True) + manual_restore
    import json as _json
    log_text = (vault / ".activity.json").read_text(encoding="utf-8")
    log = _json.loads(log_text)
    assert len(log["entries"]) == 2
    types = [e["operation_type"] for e in log["entries"]]
    assert "ingest_raw_only" in types
    assert "manual_restore" in types
    # Original is undone
    ingest_entry = next(e for e in log["entries"] if e["operation_type"] == "ingest_raw_only")
    assert ingest_entry["undone"] is True


def test_cli_undo_id_prefix_match(tmp_path: Path):
    vault = tmp_path / "vault"
    res_ingest = _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    assert res_ingest.returncode == 0

    # Read full id from activity log
    import json as _json
    log = _json.loads((vault / ".activity.json").read_text(encoding="utf-8"))
    full_id = log["entries"][0]["id"]
    short_prefix = full_id[:8]

    res_undo = _run("undo", short_prefix, "--vault", str(vault))
    assert res_undo.returncode == 0, res_undo.stderr
```

- [ ] **Step 2: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli.py -v
```

Ожидаем: 7 новых fail (no `activity`/`undo` subcommand).

- [ ] **Step 3: Расширить `claude_mnemos/cli.py`**

(A) В импорты добавить:
```python
from claude_mnemos.core.undo import UndoError, undo
from claude_mnemos.state.activity import ActivityCorruptError, ActivityEntry, ActivityLog
```

(B) В `build_parser`, после `ingest` подкоманды, добавить:

```python
    activity_p = sub.add_parser(
        "activity",
        help="Show recent activity entries from the vault's activity log",
    )
    activity_p.add_argument(
        "--vault",
        type=Path,
        default=Path.cwd(),
        help="Path to the vault root (default: current directory)",
    )
    activity_p.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Show last N entries (0 means show all)",
    )

    undo_p = sub.add_parser(
        "undo",
        help="Undo a previous operation by its activity entry id",
    )
    undo_p.add_argument(
        "op_id",
        nargs="?",
        default=None,
        help="Activity entry id (full or short prefix)",
    )
    undo_p.add_argument(
        "--last",
        action="store_true",
        help="Undo the most recent undoable operation",
    )
    undo_p.add_argument(
        "--vault",
        type=Path,
        default=Path.cwd(),
        help="Path to the vault root (default: current directory)",
    )
```

(C) В `main`, добавить ветки для новых команд (можно после блока `ingest`, но до общего `parser.error(...)`):

```python
    if args.command == "activity":
        return _cmd_activity(args)
    if args.command == "undo":
        return _cmd_undo(args)
```

(D) В конец файла добавить функции:

```python
def _cmd_activity(args: argparse.Namespace) -> int:
    try:
        log = ActivityLog.load(args.vault)
    except ActivityCorruptError as exc:
        print(f"error: activity log corrupt: {exc}", file=sys.stderr)
        return 74

    entries = log.entries[::-1]  # newest first
    if args.limit and args.limit > 0:
        entries = entries[: args.limit]

    if not entries:
        print("no activity entries")
        return 0

    for e in entries:
        ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        suffix = _activity_suffix(e)
        sid = e.metadata.get("session_id", "") if isinstance(e.metadata, dict) else ""
        sid_part = f"  ({sid})" if sid else ""
        print(f"{ts}  {e.operation_type}{sid_part}  {suffix}")
    return 0


def _activity_suffix(e: ActivityEntry) -> str:
    if e.operation_type == "manual_restore":
        return "[chain]"
    if e.undone:
        ts = e.undone_at.strftime("%H:%M:%S") if e.undone_at else "?"
        return f"[UNDONE {ts}]"
    if not e.can_undo:
        return ""
    if e.snapshot_path is None:
        return "[snapshot missing]"
    return f"[undo: {e.id[:8]}]"


def _cmd_undo(args: argparse.Namespace) -> int:
    if args.last and args.op_id is not None:
        print("error: --last cannot be combined with positional op_id", file=sys.stderr)
        return 2
    if not args.last and args.op_id is None:
        print("error: provide op_id or --last", file=sys.stderr)
        return 2

    try:
        log = ActivityLog.load(args.vault)
    except ActivityCorruptError as exc:
        print(f"error: activity log corrupt: {exc}", file=sys.stderr)
        return 74

    if args.last:
        candidate = log.last_undoable()
        if candidate is None:
            print("error: no undoable operation in activity log", file=sys.stderr)
            return 77
        op_id = candidate.id
    else:
        # Resolve prefix
        matches = [e for e in log.entries if e.id.startswith(args.op_id)]
        if not matches:
            print(f"error: activity entry not found: {args.op_id}", file=sys.stderr)
            return 77
        if len(matches) > 1:
            ids = ", ".join(m.id[:12] for m in matches)
            print(
                f"error: ambiguous prefix '{args.op_id}' matches {len(matches)} entries: {ids}",
                file=sys.stderr,
            )
            return 77
        op_id = matches[0].id

    try:
        result = undo(args.vault, op_id)
    except UndoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 77
    except LockTimeoutError as exc:
        print(f"error: another ingest is running: {exc}", file=sys.stderr)
        return 73

    print(f"undone: {op_id} restored {len(result.restored_pages)} pages")
    if result.new_entry_id is not None:
        print(f"new activity entry: {result.new_entry_id} (manual_restore)")
    return 0
```

(E) (`ActivityEntry` уже включён в импорт (A) — он нужен для type-аннотации в `_activity_suffix`.)

- [ ] **Step 4: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli.py -v
```

Ожидаем: 18 passed (11 старых + 7 новых).

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное (~185 + 1 skipped).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/cli.py tests/test_cli.py
git commit -m "feat(cli): activity + undo subcommands; exit 77 for UndoError"
```

---

## Task 6: Manual smoke + final verification

**Files:** none (verification only)

**Why:** Прогнать end-to-end на свежем vault'е: ingest → activity → undo → activity. Это не тест — sanity check перед merge.

- [ ] **Step 1: Smoke 1 — ingest --no-llm + activity печатает entry**

```bash
cd /d/code/claude-mnemos && rm -rf tmp/smoke-vault
.venv/Scripts/python.exe -m claude_mnemos ingest tests/fixtures/sample_session.jsonl tmp/smoke-vault --no-llm
.venv/Scripts/python.exe -m claude_mnemos activity --vault tmp/smoke-vault
```

Ожидаем:
- Первая команда печатает `raw_only: ...` + `snapshot: ...` строки.
- Вторая команда печатает одну строку `<ts> ingest_raw_only (abc-123) [undo: <8-hex>]`.
- `tmp/smoke-vault/.activity.json` существует с одной entry.

- [ ] **Step 2: Smoke 2 — undo --last → vault restored**

```bash
.venv/Scripts/python.exe -m claude_mnemos undo --last --vault tmp/smoke-vault
ls tmp/smoke-vault/raw/chats/ 2>&1 || echo "(empty)"
.venv/Scripts/python.exe -m claude_mnemos activity --vault tmp/smoke-vault
```

Ожидаем:
- `undone: <op_id> restored 1 pages` + `new activity entry: ... (manual_restore)`.
- `raw/chats/` либо отсутствует, либо пуст (snapshot был empty pre-op).
- `mnemos activity` теперь показывает 2 строки: `manual_restore [chain]` и `ingest_raw_only ... [UNDONE ...]`.

- [ ] **Step 3: Smoke 3 — undo unknown id → exit 77**

```bash
.venv/Scripts/python.exe -m claude_mnemos undo fake-id-zzzz --vault tmp/smoke-vault
echo "exit code: $?"
```

Ожидаем: exit code 77, stderr содержит "not found".

- [ ] **Step 4: Smoke 4 — undo --last после уже-сделанного undo → exit 77**

```bash
.venv/Scripts/python.exe -m claude_mnemos undo --last --vault tmp/smoke-vault
echo "exit code: $?"
```

Ожидаем: exit code 77, stderr "no undoable operation" (потому что единственная undoable была уже undone, а manual_restore сам не undoable).

- [ ] **Step 5: Финальный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное (~185 passed + 1 skipped).

- [ ] **Step 6: Нет коммита** (verification only). Если smoke выявил баг — отдельный fix-commit.

---

## Definition of Done

- [ ] 5 task-коммитов на ветке `feat/activity-undo` (Tasks 1-5; Task 6 без коммита).
- [ ] `pytest -v` зелёный (~185 passed + 1 skipped).
- [ ] `ruff check claude_mnemos tests` чистый.
- [ ] `mypy claude_mnemos` чистый под strict.
- [ ] Manual smoke в Task 6 прошёл (ingest → activity → undo --last → activity печатает chain).
- [ ] `.activity.json` создаётся в vault root после успешного ingest.
- [ ] `mnemos undo` восстанавливает vault и пишет manual_restore entry.

---

## После плана #4

- **Plan #5+** — daemon (FastAPI :5757), dashboard (React + shadcn), MCP, hooks, scheduler. Activity log + undo сразу полезны: dashboard читает `.activity.json` и рендерит таблицу с кнопкой `[Undo]` которая зовёт REST endpoint, дёргающий `core.undo.undo()`. Никакой новой логики.
- **Plan #5+** — 180-day retention cleanup: scheduler удаляет старые entries из `.activity.json` и старые snapshots из `.backups/`.
- **Plan #6** — ontology operations пишут в тот же activity log с `operation_type="ontology_apply"`. Generic undo работает без изменений.
