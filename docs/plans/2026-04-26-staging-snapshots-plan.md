# Staging + Snapshots Implementation Plan (Plan #3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрыть partial-write window из Plan #2 через `StagingTransaction` (Layer 2) и snapshots (Layer 4). После Plan #3 ingest pipeline становится транзакционным: либо все pages + manifest появляются в vault'е атомарно, либо ничего — всегда с возможностью откатиться к pre-op snapshot.

**Architecture:** См. design doc `docs/plans/2026-04-26-staging-snapshots-design.md` (commit `ab0f146`). `StagingTransaction(vault, op_id)` — context-менеджер; все pipeline-writes идут в `.staging/<op_id>/`, потом `promote_to_vault()` создаёт snapshot и атомарно перемещает файлы. На любой ошибке во время promote — `restore_from_snapshot` с copy-first/atomic-swap. Если caller вышел из `with` без promote (exception или забыл вызвать) — `__exit__` rejects: staging уезжает в `.trash/rejected-<op_id>/`.

**Tech Stack:** Python 3.12, Pydantic v2, filelock, pytest+ruff+mypy strict.

---

## Что НЕ делаем в этом плане

См. §2.2 design doc'а — daily snapshots (scheduler), 180-day retention cleanup, daemon_pause, pre-promote validation (lint+ontology), restore UI / `--restore` CLI, Activity Center log_promote/log_rejection, incremental snapshots, snapshot compression. Всё это последующие планы (#4, #5+, #6).

---

## Files map

**Создаём:**

| Файл | Ответственность |
|---|---|
| `claude_mnemos/core/snapshots.py` | `SnapshotMeta` Pydantic, `RestoreResult` dataclass, `SnapshotError`, `create_snapshot`, `restore_from_snapshot` |
| `claude_mnemos/core/staging.py` | `PromoteResult` dataclass, `StagingPromoteError`, `StagingTransaction` context manager |
| `tests/test_snapshots.py` | |
| `tests/test_staging.py` | |

**Изменяем:**

| Файл | Что |
|---|---|
| `claude_mnemos/state/manifest.py` | Добавить метод `Manifest.serialize_to_string() -> str` — отделить сериализацию от записи на диск (нужен pipeline для записи через staging) |
| `claude_mnemos/ingest/pipeline.py` | Все vault-writes через `StagingTransaction`. `IngestResult` получает поле `snapshot_path: Path \| None`. Source-collision check ВНУТРИ `with`-блока (HARD FAIL → `__exit__` сам reject'нет). Manifest update — теперь `txn.write(".manifest.json", manifest.serialize_to_string())`, не `manifest.save(vault)`. |
| `claude_mnemos/cli.py` | Добавить `StagingPromoteError → exit 76`; печатать `snapshot:` строку в success messages |
| `tests/test_pipeline.py` | Добавить тесты на: snapshot создаётся при extract/no_llm; dry_run rejects staging; promote failure restores vault; staging cleanup после успеха |
| `tests/test_cli.py` | Добавить тест: success вывод содержит `snapshot:` |
| `tests/test_manifest.py` | Добавить тест на `serialize_to_string()` |

---

## Зависимости между задачами

```
Task 1 (snapshots.py)
    ↓
Task 2 (staging.py) ← uses snapshots
    ↓
Task 3 (manifest.serialize_to_string) ← independent, can be parallel
    ↓
Task 4 (pipeline integration) ← uses 1, 2, 3
    ↓
Task 5 (CLI exit code 76)
    ↓
Task 6 (final smoke + manual checks)
```

Каждая задача — отдельный коммит, заканчивается зелёным `pytest -v` + `ruff` + `mypy`.

---

## Task 1: Snapshots module

**Files:**
- Create: `claude_mnemos/core/snapshots.py`
- Test: `tests/test_snapshots.py`

**Why:** `create_snapshot` копирует vault (без `.staging/`/`.backups/`/`.trash/`/`.pipeline.lock`) в `.backups/pre-op-<ts>-<type>-<id>/` плюс `.meta.json`. `restore_from_snapshot` — copy-first/atomic-swap паттерн (копируем snapshot в temp директорию рядом с vault, потом atomic rename'ы). Нужен Task 2 (staging) для rollback при failed promote.

- [ ] **Step 1: Падающие тесты**

`tests/test_snapshots.py`:

```python
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_mnemos.core.snapshots import (
    RestoreResult,
    SnapshotError,
    SnapshotMeta,
    create_snapshot,
    restore_from_snapshot,
)


def _populate_vault(vault: Path) -> None:
    """Create a sample vault with raw, wiki, manifest, and noisy служебные dirs."""
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "raw" / "chats").mkdir(parents=True, exist_ok=True)
    (vault / "raw" / "chats" / "abc.md").write_text("# Transcript\n", encoding="utf-8")
    (vault / "wiki" / "entities").mkdir(parents=True, exist_ok=True)
    (vault / "wiki" / "entities" / "foo.md").write_text("---\ntitle: Foo\n---\nbody\n", encoding="utf-8")
    (vault / ".manifest.json").write_text('{"version":1,"ingested":{}}\n', encoding="utf-8")
    # Noise that MUST be excluded:
    (vault / ".staging").mkdir()
    (vault / ".staging" / "leftover.md").write_text("staged junk", encoding="utf-8")
    (vault / ".backups").mkdir()
    (vault / ".backups" / "old-snapshot").mkdir()
    (vault / ".trash").mkdir()
    (vault / ".trash" / "rejected").mkdir()
    (vault / ".pipeline.lock").write_text("", encoding="utf-8")


def test_create_snapshot_copies_vault_contents(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    assert snap.exists()
    assert snap.is_dir()
    assert (snap / "raw" / "chats" / "abc.md").read_text(encoding="utf-8") == "# Transcript\n"
    assert (snap / "wiki" / "entities" / "foo.md").exists()
    assert (snap / ".manifest.json").exists()


def test_create_snapshot_excludes_internal_dirs(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    assert not (snap / ".staging").exists()
    assert not (snap / ".backups").exists()
    assert not (snap / ".trash").exists()
    assert not (snap / ".pipeline.lock").exists()


def test_create_snapshot_writes_meta_json(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    meta_path = snap / ".meta.json"
    assert meta_path.exists()
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    meta = SnapshotMeta.model_validate(data)
    assert meta.operation_id == "abc-123"
    assert meta.operation_type == "ingest"
    assert meta.page_count >= 1
    assert meta.vault_size_bytes > 0


def test_create_snapshot_path_format(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)

    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    parent = snap.parent
    assert parent == vault / ".backups"
    assert snap.name.startswith("pre-op-")
    assert "-ingest-" in snap.name
    assert snap.name.endswith("-abc-123")


def test_create_snapshot_with_empty_vault(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()

    snap = create_snapshot(vault, operation_id="empty", operation_type="ingest")

    assert snap.exists()
    assert (snap / ".meta.json").exists()
    meta = SnapshotMeta.model_validate(json.loads((snap / ".meta.json").read_text()))
    assert meta.page_count == 0
    assert meta.vault_size_bytes == 0


def test_create_snapshot_collision_raises(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap1 = create_snapshot(vault, operation_id="abc", operation_type="ingest")
    # Trying to create the exact same path again should raise
    # (operation_id duplicate within same second is unrealistic in practice
    # but the function must not silently overwrite)
    with patch("claude_mnemos.core.snapshots._timestamp", return_value=snap1.name.split("pre-op-")[1].rsplit("-ingest-", 1)[0]):
        with pytest.raises(SnapshotError):
            create_snapshot(vault, operation_id="abc", operation_type="ingest")


def test_restore_swaps_vault_atomically(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    # Mutate vault after snapshot
    (vault / "wiki" / "entities" / "foo.md").write_text("CHANGED", encoding="utf-8")
    (vault / "wiki" / "entities" / "new.md").write_text("new content", encoding="utf-8")

    result = restore_from_snapshot(vault, snap)

    assert result.success is True
    assert result.vault_intact is False  # vault was swapped
    # foo.md restored to original
    assert (vault / "wiki" / "entities" / "foo.md").read_text(encoding="utf-8") == "---\ntitle: Foo\n---\nbody\n"
    # new.md gone (didn't exist in snapshot)
    assert not (vault / "wiki" / "entities" / "new.md").exists()


def test_restore_drops_meta_json_from_swap(tmp_path: Path):
    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    restore_from_snapshot(vault, snap)

    # Restored vault must not contain `.meta.json` (that's snapshot bookkeeping, not vault content)
    assert not (vault / ".meta.json").exists()


def test_restore_preserves_old_state_on_stage_failure(tmp_path: Path, monkeypatch):
    vault = tmp_path / "vault"
    _populate_vault(vault)
    snap = create_snapshot(vault, operation_id="abc-123", operation_type="ingest")

    # Sabotage shutil.copytree to fail during restore staging
    real_copytree = shutil.copytree

    def boom(src, dst, **kw):
        if "mnemos-restore" in str(dst):
            raise OSError("disk full")
        return real_copytree(src, dst, **kw)

    monkeypatch.setattr("claude_mnemos.core.snapshots.shutil.copytree", boom)

    result = restore_from_snapshot(vault, snap)

    assert result.success is False
    assert result.vault_intact is True
    # Vault still has the un-restored content
    assert (vault / "wiki" / "entities" / "foo.md").exists()
    # No partial restore directory left around
    leftovers = [p for p in vault.parent.iterdir() if "mnemos-restore" in p.name]
    assert leftovers == []
```

- [ ] **Step 2: Запустить — упадут**

```bash
cd /d/code/claude-mnemos && .venv/Scripts/python.exe -m pytest tests/test_snapshots.py -v
```

Ожидаем: ImportError.

- [ ] **Step 3: Реализовать `claude_mnemos/core/snapshots.py`**

```python
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

SNAPSHOTS_DIRNAME = ".backups"
META_FILENAME = ".meta.json"

_EXCLUDED_DIRS = {".staging", ".backups", ".trash"}
_EXCLUDED_FILES = {".pipeline.lock"}


class SnapshotError(RuntimeError):
    """Raised when snapshot creation fails or target path already exists."""


class SnapshotMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str  # ISO-8601 UTC
    operation_id: str
    operation_type: str
    page_count: int = Field(ge=0)
    vault_size_bytes: int = Field(ge=0)


@dataclass(frozen=True)
class RestoreResult:
    success: bool
    vault_intact: bool
    vault_possibly_corrupted: bool = False
    error: str | None = None
    recovery_hint: str | None = None


def _timestamp() -> str:
    """Filename-safe timestamp (year-month-day-hour-minute-second)."""
    return datetime.now(UTC).strftime("%Y-%m-%d-%H-%M-%S")


def _ignore_internal(directory: str, names: list[str]) -> set[str]:
    return {n for n in names if n in _EXCLUDED_DIRS or n in _EXCLUDED_FILES}


def _count_pages(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for p in root.rglob("*.md") if p.is_file())


def _vault_size(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return total


def create_snapshot(
    vault: Path,
    *,
    operation_id: str,
    operation_type: str,
) -> Path:
    """Copy vault contents (excluding служебные dirs) into .backups/pre-op-<ts>-<type>-<id>/.

    Writes .meta.json with timestamp + operation info + size/page counts.
    Raises SnapshotError if the target snapshot path already exists.
    """
    ts = _timestamp()
    snap_name = f"pre-op-{ts}-{operation_type}-{operation_id}"
    snapshots_root = vault / SNAPSHOTS_DIRNAME
    snapshots_root.mkdir(parents=True, exist_ok=True)
    snap_path = snapshots_root / snap_name

    if snap_path.exists():
        raise SnapshotError(f"snapshot already exists: {snap_path}")

    # Collect vault content (everything except служебные dirs/files at root level).
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

    page_count = sum(
        _count_pages(snap_path / d) for d in ("wiki", "raw")
    )
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


def restore_from_snapshot(vault: Path, snapshot: Path) -> RestoreResult:
    """Atomic restore via copy-first / atomic-swap.

    1. Copy snapshot (minus .meta.json) to temp dir on same filesystem.
    2. Atomic rename: vault → wiki.old.<ts>, temp → vault.
    3. Cleanup wiki.old (best-effort).

    On step 1 failure → vault not touched, success=False, vault_intact=True.
    On step 2 partial failure → vault possibly corrupted, recovery_hint returned.
    NEVER recurses inside except (per spec §7.4 invariant).
    """
    if not snapshot.exists():
        return RestoreResult(
            success=False,
            vault_intact=True,
            error=f"snapshot not found: {snapshot}",
        )

    temp_root = vault.parent / f".mnemos-restore-{int(time.time() * 1000)}"
    try:
        shutil.copytree(
            snapshot,
            temp_root,
            ignore=lambda d, names: {n for n in names if n == META_FILENAME},
        )
    except OSError as exc:
        if temp_root.exists():
            shutil.rmtree(temp_root, ignore_errors=True)
        return RestoreResult(
            success=False,
            vault_intact=True,
            error=f"cannot stage restore: {exc}",
        )

    old_vault: Path | None = None
    if vault.exists():
        old_vault = vault.parent / f".mnemos-old-{int(time.time() * 1000)}"
        try:
            vault.rename(old_vault)
        except OSError as exc:
            shutil.rmtree(temp_root, ignore_errors=True)
            return RestoreResult(
                success=False,
                vault_intact=True,
                error=f"cannot rename vault to old: {exc}",
            )

    try:
        temp_root.rename(vault)
    except OSError as exc:
        # Worst case: vault is gone, temp_root still has the staged copy.
        return RestoreResult(
            success=False,
            vault_intact=False,
            vault_possibly_corrupted=True,
            error=str(exc),
            recovery_hint=(
                f"Manual recovery: pre-restore state at {old_vault}, "
                f"snapshot copy at {temp_root}. Move one of them to {vault}."
            ),
        )

    if old_vault is not None:
        shutil.rmtree(old_vault, ignore_errors=True)

    return RestoreResult(success=True, vault_intact=False)
```

- [ ] **Step 4: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_snapshots.py -v
```

Ожидаем: 9 passed.

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное (112 + 9 + 1 skipped = 121 + 1 skipped). Если ruff жалуется на кириллицу в `_ignore_internal` / `_EXCLUDED_*` — переименовать в latin (`_ignore_internal`, например).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/core/snapshots.py tests/test_snapshots.py
git commit -m "feat(core): vault snapshots — create + atomic-swap restore"
```

---

## Task 2: StagingTransaction module

**Files:**
- Create: `claude_mnemos/core/staging.py`
- Test: `tests/test_staging.py`

**Why:** Контекст-менеджер, оборачивающий все pipeline writes. Принимает их в `.staging/<op_id>/`, на promote — снимок + atomic moves. На любом другом выходе из `with` — reject в `.trash/rejected-<op_id>-<ts>/`.

- [ ] **Step 1: Падающие тесты**

`tests/test_staging.py`:

```python
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_mnemos.core.staging import (
    PromoteResult,
    StagingPromoteError,
    StagingTransaction,
)


def test_init_creates_staging_dir(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        assert (vault / ".staging" / "op-1").exists()
        assert (vault / ".staging" / "op-1").is_dir()
    # After exit (no promote called) — staging должен быть rejected → ушёл в .trash
    assert not (vault / ".staging" / "op-1").exists()


def test_write_creates_file_in_staging(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("wiki/entities/foo.md"), "body")
        # File must be in staging, NOT in vault
        assert (vault / ".staging" / "op-1" / "wiki" / "entities" / "foo.md").exists()
        assert not (vault / "wiki" / "entities" / "foo.md").exists()
        txn.promote_to_vault()


def test_write_creates_intermediate_dirs(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("a/b/c/d.md"), "deep content")
        assert (vault / ".staging" / "op-1" / "a" / "b" / "c" / "d.md").read_text(encoding="utf-8") == "deep content"
        txn.promote_to_vault()


def test_promote_moves_files_to_vault(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("wiki/entities/foo.md"), "foo body")
        txn.write(Path("raw/chats/abc.md"), "raw content")
        result = txn.promote_to_vault()

    assert isinstance(result, PromoteResult)
    assert result.success is True
    assert (vault / "wiki" / "entities" / "foo.md").read_text(encoding="utf-8") == "foo body"
    assert (vault / "raw" / "chats" / "abc.md").read_text(encoding="utf-8") == "raw content"


def test_promote_creates_snapshot(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "preexisting.md").write_text("before", encoding="utf-8")

    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("new.md"), "added")
        result = txn.promote_to_vault()

    assert result.snapshot is not None
    assert result.snapshot.exists()
    # Snapshot has pre-op state (preexisting.md, no new.md)
    assert (result.snapshot / "preexisting.md").read_text(encoding="utf-8") == "before"
    assert not (result.snapshot / "new.md").exists()


def test_promote_cleans_up_staging(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("a.md"), "x")
        txn.promote_to_vault()
    assert not (vault / ".staging" / "op-1").exists()


def test_promote_twice_raises(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("a.md"), "x")
        txn.promote_to_vault()
        with pytest.raises(RuntimeError):
            txn.promote_to_vault()


def test_reject_moves_staging_to_trash(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("a.md"), "x")
        txn.reject("user requested cancel")

    assert not (vault / ".staging" / "op-1").exists()
    rejected = list((vault / ".trash").glob("rejected-op-1-*"))
    assert len(rejected) == 1
    assert (rejected[0] / "a.md").exists()
    reason_file = rejected[0] / ".reason.txt"
    assert "user requested cancel" in reason_file.read_text(encoding="utf-8")


def test_exit_without_promote_rejects(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with StagingTransaction(vault, operation_id="op-1") as txn:
        txn.write(Path("a.md"), "forgotten")
        # caller forgot to call promote_to_vault()

    # On clean exit without promote — staging must be rejected
    assert not (vault / ".staging" / "op-1").exists()
    rejected = list((vault / ".trash").glob("rejected-op-1-*"))
    assert len(rejected) == 1


def test_exit_with_exception_rejects(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    with pytest.raises(RuntimeError, match="caller bug"):
        with StagingTransaction(vault, operation_id="op-1") as txn:
            txn.write(Path("a.md"), "before crash")
            raise RuntimeError("caller bug")

    assert not (vault / ".staging" / "op-1").exists()
    rejected = list((vault / ".trash").glob("rejected-op-1-*"))
    assert len(rejected) == 1


def test_promote_failure_restores_from_snapshot(tmp_path: Path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "preexisting.md").write_text("original", encoding="utf-8")

    # First write succeeds, second raises mid-promote
    real_atomic_write = __import__(
        "claude_mnemos.core.atomic", fromlist=["atomic_write"]
    ).atomic_write
    calls = {"n": 0}

    def flaky_atomic_write(target: Path, content: str) -> None:
        # Only sabotage writes that target the vault root (i.e. promote moves),
        # not the staging area.
        if calls["n"] >= 1 and "staging" not in target.as_posix():
            raise OSError("simulated mid-promote disk error")
        calls["n"] += 1
        return real_atomic_write(target, content)

    monkeypatch.setattr(
        "claude_mnemos.core.staging.atomic_write", flaky_atomic_write
    )

    with pytest.raises(StagingPromoteError):
        with StagingTransaction(vault, operation_id="op-1") as txn:
            txn.write(Path("first.md"), "page one")
            txn.write(Path("second.md"), "page two")
            txn.promote_to_vault()

    # Vault must be restored to pre-op state: preexisting.md present, no first.md / second.md
    assert (vault / "preexisting.md").read_text(encoding="utf-8") == "original"
    assert not (vault / "first.md").exists()
    assert not (vault / "second.md").exists()
    # Staging should also be cleaned up by __exit__ reject path
    assert not (vault / ".staging" / "op-1").exists()


def test_promote_failure_when_snapshot_create_fails(tmp_path: Path, monkeypatch):
    """If snapshot itself can't be created, vault is untouched and StagingPromoteError fires."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "preexisting.md").write_text("intact", encoding="utf-8")

    def boom_snapshot(*args, **kwargs):
        from claude_mnemos.core.snapshots import SnapshotError
        raise SnapshotError("simulated snapshot failure")

    monkeypatch.setattr("claude_mnemos.core.staging.create_snapshot", boom_snapshot)

    with pytest.raises(StagingPromoteError):
        with StagingTransaction(vault, operation_id="op-1") as txn:
            txn.write(Path("a.md"), "would-be content")
            txn.promote_to_vault()

    # Vault never touched
    assert (vault / "preexisting.md").read_text(encoding="utf-8") == "intact"
    assert not (vault / "a.md").exists()
```

- [ ] **Step 2: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_staging.py -v
```

Ожидаем: ImportError.

- [ ] **Step 3: Реализовать `claude_mnemos/core/staging.py`**

```python
from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.core.snapshots import create_snapshot, restore_from_snapshot

STAGING_DIRNAME = ".staging"
TRASH_DIRNAME = ".trash"


class StagingPromoteError(RuntimeError):
    """Raised when promote_to_vault fails (snapshot fail or partial-write rollback)."""


@dataclass(frozen=True)
class PromoteResult:
    success: bool
    snapshot: Path | None
    error: str | None = None
    recovery_hint: str | None = None


class StagingTransaction:
    """Context-managed staging area for atomic vault writes.

    Usage:
        with StagingTransaction(vault, "abc-123") as txn:
            txn.write(Path("wiki/entities/foo.md"), "...")
            txn.write(Path(".manifest.json"), "...")
            txn.promote_to_vault()

    On exit without explicit promote (clean OR exception) — staging is rejected:
    moved to `.trash/rejected-<op_id>-<ts>/` for inspection. Vault is never touched
    until promote_to_vault is called and succeeds.
    """

    def __init__(
        self,
        vault: Path,
        operation_id: str,
        operation_type: str = "ingest",
    ) -> None:
        self.vault = vault
        self.operation_id = operation_id
        self.operation_type = operation_type
        self.staging_dir = vault / STAGING_DIRNAME / operation_id
        self._promoted = False
        self._rejected = False

    def __enter__(self) -> "StagingTransaction":
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if not self._promoted and not self._rejected:
            reason = (
                f"exited with exception {exc_type.__name__}: {exc}"
                if exc_type is not None
                else "exited without promote_to_vault()"
            )
            try:
                self.reject(reason)
            except OSError:
                # Best-effort cleanup; never mask original exception.
                pass
        return False  # never swallow

    def write(self, relative_path: Path, content: str) -> None:
        """Write content to staging area at `relative_path`. NOT to vault."""
        if self._promoted or self._rejected:
            raise RuntimeError("StagingTransaction is finalized; cannot write")
        target = self.staging_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def promote_to_vault(self) -> PromoteResult:
        """Snapshot vault, then atomically move staging files into vault.

        On any failure during the move loop, restore vault from snapshot and raise
        StagingPromoteError. On snapshot creation failure, vault is untouched and
        StagingPromoteError still fires (no restore needed).
        """
        if self._promoted:
            raise RuntimeError("StagingTransaction already promoted")
        if self._rejected:
            raise RuntimeError("StagingTransaction already rejected; cannot promote")

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

        # 2. Move staged files into vault, one at a time, via atomic_write.
        try:
            for staged in self.staging_dir.rglob("*"):
                if not staged.is_file():
                    continue
                relative = staged.relative_to(self.staging_dir)
                target = self.vault / relative
                content = staged.read_text(encoding="utf-8")
                atomic_write(target, content)
        except Exception as exc:
            restore = restore_from_snapshot(self.vault, snapshot)
            self._promoted = True  # mark finalized so __exit__ doesn't reject
            if restore.success:
                raise StagingPromoteError(
                    f"promote failed mid-move; vault restored from snapshot. cause: {exc}"
                ) from exc
            raise StagingPromoteError(
                f"promote failed mid-move; restore ALSO failed: {restore.error}. "
                f"recovery hint: {restore.recovery_hint}. original cause: {exc}"
            ) from exc

        # 3. Cleanup staging.
        shutil.rmtree(self.staging_dir, ignore_errors=True)
        self._promoted = True

        return PromoteResult(success=True, snapshot=snapshot)

    def reject(self, reason: str) -> None:
        """Move staging dir into .trash/rejected-<op_id>-<ts>/ with a .reason.txt."""
        if self._promoted:
            raise RuntimeError("StagingTransaction already promoted; cannot reject")
        if self._rejected:
            return  # idempotent
        ts = int(time.time() * 1000)
        trash_root = self.vault / TRASH_DIRNAME
        trash_root.mkdir(parents=True, exist_ok=True)
        trash_dir = trash_root / f"rejected-{self.operation_id}-{ts}"
        if self.staging_dir.exists():
            shutil.move(str(self.staging_dir), str(trash_dir))
        else:
            trash_dir.mkdir(parents=True, exist_ok=True)
        (trash_dir / ".reason.txt").write_text(reason, encoding="utf-8")
        self._rejected = True
```

- [ ] **Step 4: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_staging.py -v
```

Ожидаем: 12 passed.

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/core/staging.py tests/test_staging.py
git commit -m "feat(core): StagingTransaction context manager with snapshot-backed rollback"
```

---

## Task 3: Manifest.serialize_to_string

**Files:**
- Modify: `claude_mnemos/state/manifest.py`
- Modify: `tests/test_manifest.py`

**Why:** Pipeline нужно записать manifest **через staging** (`txn.write(".manifest.json", content)`), а не через `manifest.save(vault)`. Для этого выделим сериализацию в публичный метод. `Manifest.save()` остаётся (используется напрямую в нескольких местах backwards-compat) и будет переиспользовать новый метод.

- [ ] **Step 1: Падающий тест**

В конец `tests/test_manifest.py` добавить:

```python
def test_serialize_to_string_matches_save_output(tmp_path: Path):
    """serialize_to_string() must produce identical bytes to save() writes to disk."""
    m = Manifest()
    m.add("sha-x", _record("sid-x"))

    serialized = m.serialize_to_string()

    m.save(tmp_path)
    on_disk = (tmp_path / ".manifest.json").read_text(encoding="utf-8")

    assert serialized == on_disk


def test_serialize_to_string_roundtrip_via_model_validate_json():
    import json as _json

    m = Manifest()
    m.add("sha-y", _record("sid-y"))

    out = m.serialize_to_string()
    parsed = _json.loads(out)
    reloaded = Manifest.model_validate(parsed)

    assert "sha-y" in reloaded.ingested
    assert reloaded.ingested["sha-y"].session_id == "sid-y"
```

- [ ] **Step 2: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_manifest.py -v
```

Ожидаем: AttributeError (`serialize_to_string` not found).

- [ ] **Step 3: Добавить метод в `claude_mnemos/state/manifest.py`**

В `class Manifest`:

```python
    def serialize_to_string(self) -> str:
        """Serialize manifest to the exact JSON string we'd write to disk.

        Used by pipeline to put manifest content into the staging area before promote.
        """
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
        path = vault_root / MANIFEST_FILENAME
        atomic_write(path, self.serialize_to_string())
```

(Note: `save` теперь делегирует в `serialize_to_string` — никакого изменения поведения, только дедупликация.)

- [ ] **Step 4: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_manifest.py -v
```

Ожидаем: 10 passed (8 + 2 new).

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/state/manifest.py tests/test_manifest.py
git commit -m "feat(state): expose Manifest.serialize_to_string for staging integration"
```

---

## Task 4: Pipeline integration

**Files:**
- Modify: `claude_mnemos/ingest/pipeline.py` (рефакторинг — все vault writes через StagingTransaction)
- Modify: `tests/test_pipeline.py` (добавить новые сценарии)

**Why:** Это сердце Plan #3. `pipeline.ingest` теперь:
1. Открывает `StagingTransaction(vault, operation_id=session_id)`.
2. Все `atomic_write(...)` заменяются на `txn.write(...)`.
3. Manifest update — `txn.write(".manifest.json", manifest.serialize_to_string())`.
4. На промоте: `txn.promote_to_vault()` → snapshot + atomic moves.
5. На dry-run: `txn.reject("dry-run")`.
6. `IngestResult` получает поле `snapshot_path: Path | None`.
7. Source-collision и slug-collision check ВНУТРИ `with`-блока. Source-collision raises FileExistsError → `__exit__` сам зареджектит.

`already_ingested` ветка ОСТАЁТСЯ без staging — она ничего не пишет, а только читает manifest и возвращает.

- [ ] **Step 1: Дополнить тесты в `tests/test_pipeline.py`**

В `tests/test_pipeline.py` добавить в конец:

```python
def test_ingest_extracted_returns_snapshot_path(tmp_path: Path):
    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    assert res.snapshot_path is not None
    assert res.snapshot_path.exists()
    assert res.snapshot_path.is_dir()
    assert res.snapshot_path.parent == vault / ".backups"


def test_ingest_no_llm_returns_snapshot_path(tmp_path: Path):
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
    assert res.snapshot_path is not None
    assert res.snapshot_path.exists()


def test_ingest_dry_run_no_snapshot(tmp_path: Path):
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
    assert res.snapshot_path is None
    # Dry run rejects staging → goes to .trash
    rejected = list((vault / ".trash").glob("rejected-abc-123-*"))
    assert len(rejected) == 1


def test_ingest_already_ingested_no_snapshot(tmp_path: Path):
    vault = tmp_path / "vault"
    extractor = MagicMock(side_effect=_stub_extractor())
    first = ingest(
        FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor,
        today=FIXED_TODAY,
    )
    assert first.snapshot_path is not None

    second = ingest(
        FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor,
        today=FIXED_TODAY,
    )
    assert second.status == "already_ingested"
    assert second.snapshot_path is None  # no new snapshot for no-op


def test_ingest_cleans_up_staging_on_success(tmp_path: Path):
    vault = tmp_path / "vault"
    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    # .staging/ должен быть либо удалён целиком, либо пуст
    staging = vault / ".staging"
    if staging.exists():
        assert list(staging.iterdir()) == []


def test_ingest_promote_failure_restores_vault(tmp_path: Path, monkeypatch):
    vault = tmp_path / "vault"
    # Pre-populate vault with one extracted page; LLM stub will try to add foo.md
    vault.mkdir()
    (vault / "wiki" / "concepts").mkdir(parents=True)
    (vault / "wiki" / "concepts" / "preserved.md").write_text("survives", encoding="utf-8")

    real_atomic_write = __import__(
        "claude_mnemos.core.atomic", fromlist=["atomic_write"]
    ).atomic_write
    calls = {"n": 0}

    def flaky(target: Path, content: str) -> None:
        # Fail the second vault-root write (the promote stage), succeed in staging.
        if "staging" not in target.as_posix() and "backups" not in target.as_posix():
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("simulated mid-promote failure")
        return real_atomic_write(target, content)

    monkeypatch.setattr("claude_mnemos.core.staging.atomic_write", flaky)

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

    # Pre-existing file must survive
    assert (vault / "wiki" / "concepts" / "preserved.md").read_text(encoding="utf-8") == "survives"
    # No partially-written ingest pages in vault
    assert not (vault / "raw" / "chats" / "abc-123.md").exists()
    assert not (vault / "wiki" / "entities" / "fastapi.md").exists()
    # Manifest must NOT be updated (we rolled back)
    if (vault / ".manifest.json").exists():
        import json as _json
        m = _json.loads((vault / ".manifest.json").read_text(encoding="utf-8"))
        assert m["ingested"] == {}
```

Также **обновить** существующий `test_ingest_dry_run_writes_nothing` — он сейчас проверяет `not (vault / MANIFEST_FILENAME).exists()`. После Plan #3 dry-run уезжает в `.trash`, и нам нужно проверить ещё что vault root **не** содержит manifest:

Существующий тест уже проверяет `not (vault / MANIFEST_FILENAME).exists()` — это останется правдой потому что dry-run rejects staging до promote. Тест **не нужно** менять — просто убедимся что он всё ещё зелёный.

- [ ] **Step 2: Запустить новые тесты — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -v
```

Ожидаем: новые тесты падают (поле `snapshot_path` отсутствует в IngestResult, `StagingTransaction` не используется).

- [ ] **Step 3: Полностью заменить `claude_mnemos/ingest/pipeline.py`**

```python
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from claude_mnemos.config import Config
from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.models import WikiPage, WikiPageFrontmatter
from claude_mnemos.core.staging import StagingTransaction
from claude_mnemos.ingest.extraction import ExtractionResult, extract_wiki_pages
from claude_mnemos.ingest.llm import LLMClient
from claude_mnemos.ingest.transcript import TranscriptMessage, parse_jsonl
from claude_mnemos.state.manifest import IngestRecord, Manifest

IngestStatus = Literal["extracted", "raw_only", "already_ingested", "dry_run"]
Extractor = Callable[..., ExtractionResult]


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


def ingest(
    jsonl_path: Path,
    vault_root: Path,
    *,
    cfg: Config,
    llm_client: LLMClient | None,
    extractor: Extractor | None = extract_wiki_pages,
    extract: bool = True,
    dry_run: bool = False,
    today: date,
) -> IngestResult:
    """Full ingest pipeline. All vault writes go through StagingTransaction.

    On success: snapshot created, files atomically moved into vault, manifest updated.
    On failure mid-promote: vault restored from snapshot via StagingTransaction.
    On dry_run or exception in `with` block: staging moved to .trash/rejected-...
    """
    messages = parse_jsonl(jsonl_path)
    session_id = _resolve_session_id(messages, jsonl_path)
    raw_bytes = jsonl_path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()

    vault_root.mkdir(parents=True, exist_ok=True)

    with pipeline_lock(vault_root, timeout=cfg.lock_timeout):
        manifest = Manifest.load(vault_root)
        if sha in manifest.ingested:
            existing = manifest.ingested[sha]
            return IngestResult(
                status="already_ingested",
                session_id=existing.session_id,
                raw_path=vault_root / existing.raw_path,
                source_path=(
                    vault_root / existing.source_path if existing.source_path else None
                ),
                created_pages=[vault_root / p for p in existing.created_pages],
                skipped_collisions=existing.skipped_collisions,
                model=existing.model,
                input_tokens=existing.input_tokens,
                output_tokens=existing.output_tokens,
                snapshot_path=None,
            )

        raw_relative = Path("raw/chats") / f"{session_id}.md"
        raw_body = _render_raw_transcript(messages)

        with StagingTransaction(vault_root, operation_id=session_id) as txn:
            txn.write(raw_relative, raw_body)

            if not extract:
                # No-LLM path
                manifest.add(
                    sha,
                    IngestRecord(
                        session_id=session_id,
                        ingested_at=datetime.now(UTC),
                        raw_path=raw_relative.as_posix(),
                        source_path=None,
                        created_pages=[raw_relative.as_posix()],
                        skipped_collisions=[],
                        model=None,
                        input_tokens=None,
                        output_tokens=None,
                    ),
                )
                txn.write(Path(".manifest.json"), manifest.serialize_to_string())

                if dry_run:
                    txn.reject("dry-run (--no-llm)")
                    return IngestResult(
                        status="dry_run",
                        session_id=session_id,
                        raw_path=None,
                        snapshot_path=None,
                    )

                promote = txn.promote_to_vault()
                return IngestResult(
                    status="raw_only",
                    session_id=session_id,
                    raw_path=vault_root / raw_relative,
                    snapshot_path=promote.snapshot,
                )

            # LLM-extract path
            if extractor is None:
                raise ValueError("extractor cannot be None when extract=True")
            if llm_client is None:
                raise ValueError("llm_client cannot be None when extract=True")

            extraction = extractor(
                messages=messages, cfg=cfg, llm_client=llm_client, today=today
            )

            source_relative = (
                Path("wiki/sources") / f"{today.isoformat()}-{session_id}.md"
            )
            source_page = _build_source_page(
                session_id=session_id,
                summary=extraction.summary,
                skipped_reason=extraction.skipped_reason,
                extracted_pages=extraction.pages,
                today=today,
                relative_path=source_relative,
            )

            # Source-page collision is HARD FAIL (per Plan #2 design)
            source_target_in_vault = vault_root / source_relative
            if source_target_in_vault.exists():
                raise FileExistsError(
                    f"source page collision at {source_relative.as_posix()}: "
                    "a file already exists. This typically means a stale file from a "
                    "previous manual edit. Move or delete it before re-running."
                )

            # Extracted pages: skip-with-warning on collision
            to_write: list[WikiPage] = []
            skipped: list[str] = []
            for p in extraction.pages:
                if (vault_root / p.relative_path).exists():
                    skipped.append(p.relative_path.as_posix())
                else:
                    to_write.append(p)
            to_write.append(source_page)

            for p in to_write:
                txn.write(p.relative_path, p.serialize())

            manifest.add(
                sha,
                IngestRecord(
                    session_id=session_id,
                    ingested_at=datetime.now(UTC),
                    raw_path=raw_relative.as_posix(),
                    source_path=source_relative.as_posix(),
                    created_pages=[p.relative_path.as_posix() for p in to_write],
                    skipped_collisions=skipped,
                    model=cfg.model,
                    input_tokens=extraction.input_tokens,
                    output_tokens=extraction.output_tokens,
                ),
            )
            txn.write(Path(".manifest.json"), manifest.serialize_to_string())

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
            )


def _resolve_session_id(messages: list[TranscriptMessage], jsonl_path: Path) -> str:
    for m in messages:
        if m.session_id:
            return m.session_id
    return jsonl_path.stem


def _render_raw_transcript(messages: list[TranscriptMessage]) -> str:
    lines = ["# Transcript", ""]
    for m in messages:
        lines.append(f"## {m.role}")
        lines.append("")
        lines.append(m.text)
        lines.append("")
    return "\n".join(lines)


def _build_source_page(
    *,
    session_id: str,
    summary: str,
    skipped_reason: str | None,
    extracted_pages: list[WikiPage],
    today: date,
    relative_path: Path,
) -> WikiPage:
    title = f"Session {session_id} ({today.isoformat()})"
    related = [_to_wikilink(p.relative_path) for p in extracted_pages]
    body_lines = ["## Summary", "", summary, ""]
    if skipped_reason:
        body_lines.extend(["## Skipped", "", skipped_reason, ""])
    if extracted_pages:
        body_lines.append("## Extracted pages")
        body_lines.append("")
        for p in extracted_pages:
            body_lines.append(f"- {_to_wikilink(p.relative_path)}")
        body_lines.append("")
    body_lines.extend(["## Original", "", f"[[{session_id}|Open transcript]]"])
    body = "\n".join(body_lines)

    fm = WikiPageFrontmatter(
        title=title,
        type="source",
        sources=[f"raw/chats/{session_id}.md"],
        related=related,
        created=today,
        updated=today,
        agent_written=True,
    )
    return WikiPage(relative_path=relative_path, frontmatter=fm, body=body)


def _to_wikilink(rel: Path) -> str:
    return f"[[{rel.stem}]]"
```

- [ ] **Step 4: Прогнать pipeline тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -v
```

Ожидаем: ~18 passed (12 старых + 6 новых).

- [ ] **Step 5: Прогнать всё (CLI тесты должны быть всё ещё зелёные — поведение без флагов снапшота не изменилось для CLI)**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное. Если CLI тест на idempotent падает (потому что во второй ingest staging dir уже есть от первой попытки) — должно работать корректно (txn создаёт новую `.staging/<sid>/` каждый раз, очищается на успехе). Перепроверь.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/ingest/pipeline.py tests/test_pipeline.py
git commit -m "refactor(ingest): pipeline writes through StagingTransaction with snapshot rollback"
```

---

## Task 5: CLI exit code 76

**Files:**
- Modify: `claude_mnemos/cli.py`
- Modify: `tests/test_cli.py`

**Why:** `StagingPromoteError` нужен mapping на специфический exit code (76 — никем ещё не занят). Также CLI печатает `snapshot:` строку в success messages.

- [ ] **Step 1: Падающий тест**

В конец `tests/test_cli.py` добавить:

```python
def test_cli_no_llm_prints_snapshot_line(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    assert res.returncode == 0, res.stderr
    assert "snapshot:" in res.stdout.lower()
    # Snapshot path should reference .backups directory
    assert ".backups" in res.stdout
```

- [ ] **Step 2: Запустить — упадёт**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli.py::test_cli_no_llm_prints_snapshot_line -v
```

Ожидаем: AssertionError (CLI ещё не печатает snapshot:).

- [ ] **Step 3: Расширить `claude_mnemos/cli.py`**

Найти блок `from claude_mnemos.ingest.llm import (...)` и сразу после добавить импорт:

```python
from claude_mnemos.core.staging import StagingPromoteError
```

В блоке `except` добавить (анywhere до общего fallthrough, рекомендуется после `FileExistsError`):

```python
    except StagingPromoteError as exc:
        print(f"error: staging promote failed: {exc}", file=sys.stderr)
        return 76
```

В success-выводах (`raw_only` и `extracted` блоки) дополнить строки `snapshot:`. Заменить:

```python
    if result.status == "raw_only":
        print(f"raw_only: wrote {result.raw_path}")
        return 0
```

на:

```python
    if result.status == "raw_only":
        print(f"raw_only: wrote {result.raw_path}")
        if result.snapshot_path is not None:
            print(f"snapshot: {result.snapshot_path}")
        return 0
```

И заменить:

```python
    print(
        f"extracted: session_id={result.session_id} "
        f"pages={len(result.created_pages)} skipped={len(result.skipped_collisions)} "
        f"tokens_in={result.input_tokens} tokens_out={result.output_tokens}"
    )
    return 0
```

на:

```python
    print(
        f"extracted: session_id={result.session_id} "
        f"pages={len(result.created_pages)} skipped={len(result.skipped_collisions)} "
        f"tokens_in={result.input_tokens} tokens_out={result.output_tokens}"
    )
    if result.snapshot_path is not None:
        print(f"snapshot: {result.snapshot_path}")
    return 0
```

- [ ] **Step 4: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli.py -v
```

Ожидаем: 11 passed (10 старых + 1 новый).

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/cli.py tests/test_cli.py
git commit -m "feat(cli): exit 76 for StagingPromoteError; print snapshot path on success"
```

---

## Task 6: Final smoke + docs touchpoints

**Files:**
- (no code changes, just verification)

**Why:** Прогнать ручной end-to-end smoke на свежем vault'е, убедиться что `.staging/`, `.backups/`, manifest всё работает в живую. Это не тест — это sanity check перед merge'ом.

- [ ] **Step 1: Manual smoke `--no-llm`**

```bash
cd /d/code/claude-mnemos && rm -rf tmp/smoke-vault
.venv/Scripts/python.exe -m claude_mnemos ingest tests/fixtures/sample_session.jsonl tmp/smoke-vault --no-llm
ls tmp/smoke-vault/
ls tmp/smoke-vault/.backups/
cat tmp/smoke-vault/.manifest.json
cat tmp/smoke-vault/raw/chats/abc-123.md | head -10
```

Ожидаем:
- В stdout видна строка `raw_only: wrote ...` и строка `snapshot: ...`.
- `.backups/pre-op-...-ingest-abc-123/` существует.
- Snapshot содержит `.meta.json`.
- `.manifest.json` есть в vault, ingested запись присутствует.
- `.staging/` либо отсутствует, либо пуст.

- [ ] **Step 2: Manual smoke `--no-llm` идемпотентный**

```bash
.venv/Scripts/python.exe -m claude_mnemos ingest tests/fixtures/sample_session.jsonl tmp/smoke-vault --no-llm
```

Ожидаем: `already_ingested: session_id=abc-123` в stdout. Никакого нового snapshot'а. `.staging/` чистый.

- [ ] **Step 3: Manual smoke `--no-llm --dry-run`**

```bash
rm -rf tmp/smoke-vault
.venv/Scripts/python.exe -m claude_mnemos ingest tests/fixtures/sample_session.jsonl tmp/smoke-vault --no-llm --dry-run
ls tmp/smoke-vault/ 2>/dev/null
ls tmp/smoke-vault/.trash/ 2>/dev/null
```

Ожидаем:
- В stdout: `dry_run: ...`.
- vault либо не существует, либо пуст в smoke-выводе. `.trash/rejected-abc-123-*` существует с `.reason.txt = "dry-run (--no-llm)"`.
- `.manifest.json` НЕ в vault root (только в `.trash/.../...`).
- `.backups/` пусто или отсутствует (snapshot не создавался).

- [ ] **Step 4: Прогнать ВСЕ тесты ещё раз**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Ожидаем: все passed (полный счёт зависит от Tasks 1-5; примерно 112 + 9 (snapshots) + 12 (staging) + 2 (manifest) + 6 (pipeline) + 1 (cli) = 142 passed + 1 skipped).

- [ ] **Step 5: ruff + mypy финал**

```bash
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: чистые.

- [ ] **Step 6: Нет коммита** (Task 6 — verification only). Если smoke выявил баг — заведи отдельный fix-commit и запиши его сюда явно.

---

## Definition of Done

- [ ] 5 task-коммитов на ветке `feat/staging-snapshots` (Tasks 1-5 + Task 6 без коммита).
- [ ] `pytest -v` зелёный (~142 passed + 1 skipped).
- [ ] `ruff check claude_mnemos tests` чистый.
- [ ] `mypy claude_mnemos` чистый под strict.
- [ ] Manual smoke в Task 6 прошёл (no-llm, idempotent, dry-run).
- [ ] `.staging/` либо пуст, либо отсутствует после успешного ingest.
- [ ] `.backups/<...>/` создаётся на каждый non-no-op ingest.
- [ ] Mid-promote crash-сценарий тестом покрыт и vault восстанавливается.

---

## После плана #3

- **Plan #4** (Activity Center / Layer 5): `.activity.json` с `op_id`, `snapshot_path`, `restore_command`. Undo через "найти запись → `restore_from_snapshot(vault, snapshot_path)`".
- **Plan #5+** (daemon/dashboard/MCP/hooks): daily snapshots, retention cleanup, `daemon_pause()` для restore, `--restore <snapshot>` CLI команда.
- **Plan #6** (Ontology): merge через `StagingTransaction(operation_type="ontology")` для preview перед apply.
