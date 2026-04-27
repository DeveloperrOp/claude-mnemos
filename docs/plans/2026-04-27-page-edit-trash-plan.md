# Page Edit + Trash Implementation Plan (Plan #12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** REST + CLI surface for editing/verifying/archiving/deleting wiki pages with snapshot+undo, plus full trash management (list, restore, dismiss, empty).

**Architecture:** All page mutations go through `StagingTransaction` for atomic snapshot/promote and emit activity entries (Plan #4 mechanism). `core/page_apply.py` is the single integration point used by REST routes and CLI. `.trash/<dir>/.metadata.json` stores `original_path` so restore can move content back to its original location. Existing `core/staging.py` `_apply_deletes` is extended to write the metadata file alongside the existing `.reason.txt`.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest. No new third-party deps.

**Design doc:** `docs/plans/2026-04-27-page-edit-trash-design.md`. **Read it before starting.**

---

## Files map

**Create:**

| File | Responsibility |
|---|---|
| `claude_mnemos/core/pages.py` | `PageRefError` + `page_ref_to_path(vault, ref)` |
| `claude_mnemos/core/trash.py` | `TrashMetadata`, `TrashEntry`, `TrashEntryNotFoundError`, `read_metadata`, `list_trash` |
| `claude_mnemos/core/page_apply.py` | `PatchResult`, `DeleteResult`, `RestoreResult`, `PageRestoreCollisionError`, `apply_patch`, `apply_soft_delete`, `apply_restore_from_trash`, `dismiss_trash_entry`, `empty_trash` |
| `claude_mnemos/daemon/routes/pages.py` | PATCH/verify/archive/DELETE `/pages/{page_ref:path}` |
| `claude_mnemos/daemon/routes/trash.py` | GET/POST/DELETE `/trash` + `/trash/{id}` + `/trash/{id}/restore` |
| `tests/core/test_pages.py` | page_ref resolver tests |
| `tests/core/test_trash.py` | trash entry parsing + list_trash |
| `tests/core/test_page_apply.py` | apply_patch / apply_soft_delete / apply_restore_from_trash |
| `tests/daemon/test_app_pages.py` | REST page endpoints |
| `tests/daemon/test_app_trash.py` | REST trash endpoints |
| `tests/test_cli_pages.py` | `mnemos page` subgroup |
| `tests/test_cli_trash.py` | `mnemos trash` subgroup |

**Modify:**

| File | Change |
|---|---|
| `claude_mnemos/state/activity.py` | extend `ActivityOperationType` literal: `manual_edit`, `manual_delete`, `manual_restore_trash`, `trash_dismissed`, `trash_emptied` |
| `claude_mnemos/core/staging.py` | `_apply_deletes` writes `.metadata.json` (TrashMetadata) alongside `.reason.txt` |
| `claude_mnemos/daemon/app.py` | include 2 routers + exception handlers (`PageRefError → 404`, `PageRestoreCollisionError → 409`, `TrashEntryNotFoundError → 404`) |
| `claude_mnemos/cli.py` | add `page` and `trash` subgroups |
| `tests/test_staging_extensions.py` | extend with metadata.json assertion |
| `README.md` | "Pages + Trash" section + status bump |

---

## Task graph

```
Task 1 (activity literal) ── Task 5 (page_apply uses literals) ── Task 6,7,9,10
Task 2 (staging metadata) ─ Task 3 (trash list parses metadata) ── Task 5
Task 3 (core/trash.py) ──── Task 5
Task 4 (core/pages.py) ──── Task 5
Task 5 (core/page_apply.py)
       │
       ├─ Task 6 (REST pages routes)
       ├─ Task 7 (REST trash routes)
       ├─ Task 9 (CLI pages)
       └─ Task 10 (CLI trash)

Task 8 (app.py wiring) — after Tasks 6+7
Task 11 (slow E2E)     — after Tasks 8 + 10
Task 12 (README+merge) — last
```

---

## Task 1: ActivityOperationType extension

**Files:**
- Modify: `claude_mnemos/state/activity.py:15-22`
- Modify: `tests/test_activity.py`

- [ ] **Step 1: Append failing tests**

```python
def test_manual_edit_op_type_accepted():
    e = ActivityEntry(
        id=uuid4().hex,
        timestamp=datetime(2026, 4, 27, 14, 0, 0, tzinfo=UTC),
        operation_type="manual_edit",
        status="success",
        snapshot_path=".backups/pre-op-...",
        can_undo=True,
        affected_pages=["wiki/entities/foo.md"],
        metadata={"fields_changed": ["status"]},
    )
    log = ActivityLog()
    log.append(e)
    assert log.entries[0].operation_type == "manual_edit"


def test_all_new_op_types_accepted():
    for op in ("manual_delete", "manual_restore_trash", "trash_dismissed", "trash_emptied"):
        e = ActivityEntry(
            id=uuid4().hex,
            timestamp=datetime(2026, 4, 27, 14, 0, 0, tzinfo=UTC),
            operation_type=op,
            status="success",
            snapshot_path=None,
            can_undo=False,
            affected_pages=[],
            metadata={},
        )
        log = ActivityLog()
        log.append(e)
        assert log.entries[0].operation_type == op
```

- [ ] **Step 2: Run, confirm fail**

```bash
python -m pytest tests/test_activity.py::test_manual_edit_op_type_accepted -v
```

Expected: ValidationError.

- [ ] **Step 3: Extend literal**

In `claude_mnemos/state/activity.py:15-22`, extend `ActivityOperationType`:

```python
ActivityOperationType = Literal[
    "ingest_extracted",
    "ingest_raw_only",
    "manual_restore",
    "ontology_apply",
    "human_edit_detected",
    "lint_fix",
    "manual_edit",
    "manual_delete",
    "manual_restore_trash",
    "trash_dismissed",
    "trash_emptied",
]
```

- [ ] **Step 4: Run tests + commit**

```bash
python -m pytest tests/test_activity.py -q
python -m ruff check claude_mnemos/state/activity.py tests/test_activity.py
python -m mypy claude_mnemos/state/activity.py

git add claude_mnemos/state/activity.py tests/test_activity.py
git commit -m "$(cat <<'EOF'
feat(state): extend ActivityOperationType for Plan #12

Adds manual_edit, manual_delete, manual_restore_trash, trash_dismissed,
trash_emptied — used by page edit + trash management.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: staging .metadata.json

**Files:**
- Modify: `claude_mnemos/core/staging.py:157-176` (`_apply_deletes`)
- Modify: `tests/test_staging_extensions.py`

`_apply_deletes` writes only `.reason.txt`. Plan #12 adds `.metadata.json` with structured restore info.

- [ ] **Step 1: Append failing test to `tests/test_staging_extensions.py`**

```python
def test_delete_to_trash_writes_metadata_json(tmp_path: Path):
    """Plan #12: trash dirs include .metadata.json with original_path."""
    import json
    vault = tmp_path / "vault"
    _populate(vault)

    with StagingTransaction(vault, "op-meta-1", operation_type="manual_delete") as txn:
        txn.delete("wiki/entities/foo.md")
        txn.promote_to_vault()

    trash_root = vault / ".trash"
    deleted_dirs = [
        p for p in trash_root.iterdir()
        if p.is_dir() and p.name.startswith("deleted-foo-")
    ]
    assert len(deleted_dirs) == 1
    meta_path = deleted_dirs[0] / ".metadata.json"
    assert meta_path.is_file()
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["original_path"] == "wiki/entities/foo.md"
    assert data["operation_id"] == "op-meta-1"
    assert data["operation_type"] == "manual_delete"
    assert data["trash_id"] == deleted_dirs[0].name
    assert "deleted_at" in data
```

- [ ] **Step 2: Run, confirm `meta_path.is_file()` fails**

- [ ] **Step 3: Extend `_apply_deletes`**

In `claude_mnemos/core/staging.py:157-176`, after the existing `.reason.txt` write block, add `.metadata.json` write:

```python
    def _apply_deletes(self) -> None:
        import json
        for rel, to_trash in self._to_remove:
            src = self.vault / rel
            if not src.exists():
                continue
            if not to_trash:
                src.unlink()
                continue
            slug = Path(rel).stem or "page"
            ts = datetime.now(UTC).strftime("%Y-%m-%d-%H-%M-%S")
            trash_dir_name = f"deleted-{slug}-{ts}-{self.operation_id[:8]}"
            trash_dir = self.vault / TRASH_DIRNAME / trash_dir_name
            trash_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(trash_dir / src.name))
            (trash_dir / ".reason.txt").write_text(
                f"deleted via {self.operation_type} operation {self.operation_id}",
                encoding="utf-8",
            )
            metadata = {
                "version": 1,
                "trash_id": trash_dir_name,
                "original_path": rel,
                "deleted_at": datetime.now(UTC).isoformat(),
                "operation_id": self.operation_id,
                "operation_type": self.operation_type,
            }
            (trash_dir / ".metadata.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
```

(Move `import json` to the top of the file if not already there — typical project style.)

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_staging_extensions.py -v
python -m pytest -q
python -m ruff check claude_mnemos/core/staging.py tests/test_staging_extensions.py
python -m mypy claude_mnemos/core/staging.py

git add claude_mnemos/core/staging.py tests/test_staging_extensions.py
git commit -m "feat(core): staging trash dirs include .metadata.json with original_path"
```

---

## Task 3: `core/trash.py` — TrashEntry + list_trash

**Files:**
- Create: `claude_mnemos/core/trash.py`
- Create: `tests/core/test_trash.py`

- [ ] **Step 1: Write failing tests**

Create `tests/core/test_trash.py`:

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.core.trash import (
    TrashEntry,
    TrashEntryNotFoundError,
    TrashMetadata,
    list_trash,
    read_metadata,
)


def _make_trash_dir(
    vault: Path,
    name: str,
    *,
    metadata: dict | None,
    page_basename: str = "foo.md",
    page_content: str = "# foo",
) -> Path:
    d = vault / ".trash" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / page_basename).write_text(page_content, encoding="utf-8")
    (d / ".reason.txt").write_text("test trash entry", encoding="utf-8")
    if metadata is not None:
        (d / ".metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
    return d


def _meta(trash_id: str, original_path: str = "wiki/entities/foo.md") -> dict:
    return {
        "version": 1,
        "trash_id": trash_id,
        "original_path": original_path,
        "deleted_at": "2026-04-27T12:00:00+00:00",
        "operation_id": "op-1",
        "operation_type": "manual_delete",
    }


def test_list_empty(tmp_path: Path):
    assert list_trash(tmp_path) == []


def test_list_returns_entries_with_metadata(tmp_path: Path):
    _make_trash_dir(
        tmp_path, "deleted-foo-2026-04-27-12-00-00-abc12345",
        metadata=_meta("deleted-foo-2026-04-27-12-00-00-abc12345"),
    )
    entries = list_trash(tmp_path)
    assert len(entries) == 1
    assert entries[0].trash_id.startswith("deleted-foo-")
    assert entries[0].original_path == "wiki/entities/foo.md"
    assert entries[0].restorable is True
    assert entries[0].restore_blocked_reason is None


def test_list_marks_missing_metadata_unrestorable(tmp_path: Path):
    _make_trash_dir(tmp_path, "deleted-bar-old-format", metadata=None)
    entries = list_trash(tmp_path)
    assert len(entries) == 1
    assert entries[0].restorable is False
    assert "metadata" in (entries[0].restore_blocked_reason or "").lower()


def test_list_marks_missing_basename_unrestorable(tmp_path: Path):
    d = tmp_path / ".trash" / "deleted-bar-2026-04-27-12-00-00-aaaaaaaa"
    d.mkdir(parents=True)
    # Skip writing the page basename
    (d / ".reason.txt").write_text("r", encoding="utf-8")
    (d / ".metadata.json").write_text(
        json.dumps(_meta("deleted-bar-2026-04-27-12-00-00-aaaaaaaa", "wiki/entities/bar.md")),
        encoding="utf-8",
    )
    entries = list_trash(tmp_path)
    assert len(entries) == 1
    assert entries[0].restorable is False


def test_list_skips_unknown_prefix(tmp_path: Path):
    d = tmp_path / ".trash" / "weird-thing"
    d.mkdir(parents=True)
    (d / "x.md").write_text("x", encoding="utf-8")
    entries = list_trash(tmp_path)
    # 'weird-thing' doesn't start with deleted-/rejected- — list it but mark non-restorable
    # Decision per design §3.10: include all subdirs; restorable=False for unknown prefix
    assert len(entries) == 1
    assert entries[0].restorable is False


def test_list_sorted_desc_by_deleted_at(tmp_path: Path):
    _make_trash_dir(
        tmp_path, "deleted-a-2026-04-27-10-00-00-aaaaaaaa",
        metadata={**_meta("deleted-a-2026-04-27-10-00-00-aaaaaaaa"), "deleted_at": "2026-04-27T10:00:00+00:00"},
    )
    _make_trash_dir(
        tmp_path, "deleted-b-2026-04-27-12-00-00-bbbbbbbb",
        metadata={**_meta("deleted-b-2026-04-27-12-00-00-bbbbbbbb"), "deleted_at": "2026-04-27T12:00:00+00:00"},
    )
    entries = list_trash(tmp_path)
    assert [e.trash_id for e in entries] == [
        "deleted-b-2026-04-27-12-00-00-bbbbbbbb",
        "deleted-a-2026-04-27-10-00-00-aaaaaaaa",
    ]


def test_read_metadata_missing(tmp_path: Path):
    d = tmp_path / ".trash" / "deleted-x-2026-04-27-12-00-00-zzzzzzzz"
    d.mkdir(parents=True)
    assert read_metadata(d) is None


def test_read_metadata_invalid_json(tmp_path: Path):
    d = tmp_path / ".trash" / "deleted-x-2026-04-27-12-00-00-zzzzzzzz"
    d.mkdir(parents=True)
    (d / ".metadata.json").write_text("not json", encoding="utf-8")
    assert read_metadata(d) is None  # tolerate, return None


def test_read_metadata_valid(tmp_path: Path):
    d = tmp_path / ".trash" / "deleted-x-2026-04-27-12-00-00-zzzzzzzz"
    d.mkdir(parents=True)
    (d / ".metadata.json").write_text(
        json.dumps(_meta("deleted-x-2026-04-27-12-00-00-zzzzzzzz")),
        encoding="utf-8",
    )
    meta = read_metadata(d)
    assert meta is not None
    assert isinstance(meta, TrashMetadata)
    assert meta.original_path == "wiki/entities/foo.md"
```

- [ ] **Step 2: Run, confirm ImportError**

- [ ] **Step 3: Implement `core/trash.py`**

```python
"""Trash directory parsing — list manually-deleted (and other) trash entries."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

TRASH_DIRNAME = ".trash"
TRASH_METADATA_FILENAME = ".metadata.json"
TRASH_REASON_FILENAME = ".reason.txt"


class TrashEntryNotFoundError(LookupError):
    """Raised when a trash_id doesn't resolve to a directory inside .trash/."""


class TrashMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    trash_id: str
    original_path: str
    deleted_at: datetime
    operation_id: str
    operation_type: str


class TrashEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trash_id: str
    deleted_at: datetime
    original_path: str | None = None
    operation_type: str | None = None
    page_basename: str | None = None
    restorable: bool = False
    restore_blocked_reason: str | None = None


def read_metadata(trash_dir: Path) -> TrashMetadata | None:
    """Load .metadata.json from a trash subdir. Returns None if missing or invalid."""
    meta_path = trash_dir / TRASH_METADATA_FILENAME
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("trash metadata at %s is invalid JSON", meta_path)
        return None
    try:
        return TrashMetadata.model_validate(data)
    except ValidationError:
        logger.warning("trash metadata at %s fails schema", meta_path)
        return None


def list_trash(vault: Path) -> list[TrashEntry]:
    """Walk <vault>/.trash/, return entries sorted newest-first by deleted_at."""
    trash_root = vault / TRASH_DIRNAME
    if not trash_root.is_dir():
        return []

    entries: list[TrashEntry] = []
    for sub in trash_root.iterdir():
        if not sub.is_dir():
            continue
        meta = read_metadata(sub)
        # Find the page file (first .md not starting with .)
        page_basename: str | None = None
        for f in sub.iterdir():
            if f.is_file() and not f.name.startswith(".") and f.suffix == ".md":
                page_basename = f.name
                break

        if meta is not None:
            restorable = page_basename is not None
            blocked = None if restorable else "page file missing"
            entries.append(
                TrashEntry(
                    trash_id=sub.name,
                    deleted_at=meta.deleted_at,
                    original_path=meta.original_path,
                    operation_type=meta.operation_type,
                    page_basename=page_basename,
                    restorable=restorable,
                    restore_blocked_reason=blocked,
                )
            )
        else:
            # Fallback: dir mtime, marked unrestorable
            try:
                mtime = datetime.fromtimestamp(sub.stat().st_mtime).astimezone()
            except OSError:
                continue
            entries.append(
                TrashEntry(
                    trash_id=sub.name,
                    deleted_at=mtime,
                    original_path=None,
                    operation_type=None,
                    page_basename=page_basename,
                    restorable=False,
                    restore_blocked_reason="missing or invalid metadata",
                )
            )

    entries.sort(key=lambda e: e.deleted_at, reverse=True)
    return entries
```

Note: `TrashEntry.deleted_at` from `mtime` may be naive in some cases; `astimezone()` adds local tz. Pydantic v2 accepts both aware and naive datetimes.

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/core/test_trash.py -v
python -m ruff check claude_mnemos/core/trash.py tests/core/test_trash.py
python -m mypy claude_mnemos/core/trash.py

git add claude_mnemos/core/trash.py tests/core/test_trash.py
git commit -m "feat(core): trash directory listing + TrashMetadata schema"
```

---

## Task 4: `core/pages.py` — page_ref resolver

**Files:**
- Create: `claude_mnemos/core/pages.py`
- Create: `tests/core/test_pages.py`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

import pytest

from claude_mnemos.core.pages import PageRefError, page_ref_to_path


def _seed(vault: Path, rel: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntitle: T\ntype: entity\ncreated: 2026-04-26\nupdated: 2026-04-26\n---\nbody",
        encoding="utf-8",
    )
    return p


def test_resolve_bare_slug_entity(tmp_path: Path):
    p = _seed(tmp_path, "wiki/entities/foo.md")
    assert page_ref_to_path(tmp_path, "foo") == p


def test_resolve_slug_prefers_entity_over_concept(tmp_path: Path):
    _seed(tmp_path, "wiki/concepts/foo.md")
    entity = _seed(tmp_path, "wiki/entities/foo.md")
    assert page_ref_to_path(tmp_path, "foo") == entity


def test_resolve_relative_with_md(tmp_path: Path):
    p = _seed(tmp_path, "wiki/entities/foo.md")
    assert page_ref_to_path(tmp_path, "wiki/entities/foo.md") == p


def test_resolve_relative_without_md(tmp_path: Path):
    p = _seed(tmp_path, "wiki/entities/foo.md")
    assert page_ref_to_path(tmp_path, "wiki/entities/foo") == p


def test_unknown_slug_raises(tmp_path: Path):
    with pytest.raises(PageRefError):
        page_ref_to_path(tmp_path, "nonexistent")


def test_traversal_rejected(tmp_path: Path):
    with pytest.raises(PageRefError):
        page_ref_to_path(tmp_path, "../../etc/passwd")


def test_absolute_path_rejected(tmp_path: Path):
    with pytest.raises(PageRefError):
        page_ref_to_path(tmp_path, "/etc/passwd")
```

- [ ] **Step 2: Implement**

```python
"""Resolve user-supplied page references to absolute paths inside a vault."""

from __future__ import annotations

from pathlib import Path

from claude_mnemos.lint.utils import build_slug_index


class PageRefError(LookupError):
    """Raised when a page reference doesn't resolve to a vault page."""


def page_ref_to_path(vault: Path, ref: str) -> Path:
    """Resolve a page reference to an absolute path inside the vault.

    Accepts:
    - bare slug (`"foo"`) — looks up via slug index, prefers entity > concept > source
    - relative path with .md (`"wiki/entities/foo.md"`)
    - relative path without .md (`"wiki/entities/foo"`)

    Raises PageRefError on unknown slug, missing file, or path outside vault.
    """
    if not ref:
        raise PageRefError("empty page reference")

    if ref.startswith("/") or ref.startswith("\\") or ":" in ref:
        raise PageRefError(f"absolute paths not allowed: {ref!r}")

    vault_resolved = vault.resolve()

    # Detect path-like ref (contains a slash)
    if "/" in ref or "\\" in ref:
        candidate = ref if ref.endswith(".md") else f"{ref}.md"
        path = (vault / candidate).resolve()
        if not path.is_relative_to(vault_resolved):
            raise PageRefError(f"path escapes vault: {ref!r}")
        if not path.is_file():
            raise PageRefError(f"page file not found: {ref!r}")
        return path

    # Bare slug — use slug index
    index = build_slug_index(vault)
    matched = index.get(ref)
    if matched is None:
        raise PageRefError(f"unknown slug: {ref!r}")
    return matched.resolve()
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest tests/core/test_pages.py -v
python -m ruff check claude_mnemos/core/pages.py tests/core/test_pages.py
python -m mypy claude_mnemos/core/pages.py

git add claude_mnemos/core/pages.py tests/core/test_pages.py
git commit -m "feat(core): page_ref_to_path resolver with anti-traversal"
```

---

## Task 5: `core/page_apply.py` — apply_patch / soft_delete / restore_from_trash / dismiss / empty

**Files:**
- Create: `claude_mnemos/core/page_apply.py`
- Create: `tests/core/test_page_apply.py`

This is the single integration module used by REST + CLI. Read design doc §3.3 for full operation semantics.

- [ ] **Step 1: Write failing tests** — include all five operations:

```python
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from claude_mnemos.core.page_apply import (
    PageRestoreCollisionError,
    apply_patch,
    apply_restore_from_trash,
    apply_soft_delete,
    dismiss_trash_entry,
    empty_trash,
)
from claude_mnemos.core.page_io import read_page
from claude_mnemos.state.activity import ActivityLog


def _seed(vault: Path, rel: str = "wiki/entities/foo.md") -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntitle: Foo\ntype: entity\nstatus: draft\nconfidence: 0.7\n"
        "flavor: []\nsources: []\nrelated: []\n"
        "created: 2026-04-26\nupdated: 2026-04-26\n"
        "agent_written: true\n---\noriginal body\n",
        encoding="utf-8",
    )
    return p


def test_apply_patch_frontmatter(tmp_path: Path):
    p = _seed(tmp_path)
    result = apply_patch(
        tmp_path, p, frontmatter_patch={"status": "verified"}, body=None,
        today=date(2026, 4, 27),
    )
    assert result.success
    assert result.activity_id
    assert result.snapshot_path is not None
    parsed = read_page(p)
    assert parsed.frontmatter.status == "verified"
    assert parsed.frontmatter.agent_written is False  # auto side-effect
    assert parsed.frontmatter.last_human_edit is not None


def test_apply_patch_body(tmp_path: Path):
    p = _seed(tmp_path)
    apply_patch(tmp_path, p, frontmatter_patch=None, body="new body\n", today=date(2026, 4, 27))
    parsed = read_page(p)
    assert "new body" in parsed.body


def test_apply_patch_invalid_status_raises(tmp_path: Path):
    p = _seed(tmp_path)
    with pytest.raises(Exception):  # ValidationError or wrapper
        apply_patch(
            tmp_path, p, frontmatter_patch={"status": "not_a_status"}, body=None,
            today=date(2026, 4, 27),
        )


def test_apply_patch_empty_is_noop(tmp_path: Path):
    p = _seed(tmp_path)
    result = apply_patch(tmp_path, p, frontmatter_patch=None, body=None, today=date(2026, 4, 27))
    assert result.success
    assert result.snapshot_path is None
    assert result.activity_id is None


def test_apply_patch_writes_activity_manual_edit(tmp_path: Path):
    p = _seed(tmp_path)
    apply_patch(tmp_path, p, frontmatter_patch={"status": "verified"}, body=None, today=date(2026, 4, 27))
    log = ActivityLog.load(tmp_path)
    assert log.entries
    assert log.entries[-1].operation_type == "manual_edit"


def test_apply_soft_delete(tmp_path: Path):
    p = _seed(tmp_path)
    result = apply_soft_delete(tmp_path, p, today=date(2026, 4, 27))
    assert result.success
    assert not p.exists()
    trash_dirs = list((tmp_path / ".trash").iterdir())
    assert any(d.name.startswith("deleted-foo-") for d in trash_dirs)
    log = ActivityLog.load(tmp_path)
    assert log.entries[-1].operation_type == "manual_delete"


def test_apply_restore_from_trash(tmp_path: Path):
    p = _seed(tmp_path)
    delete_result = apply_soft_delete(tmp_path, p, today=date(2026, 4, 27))
    trash_id = delete_result.trash_id
    result = apply_restore_from_trash(tmp_path, trash_id, today=date(2026, 4, 27))
    assert result.success
    assert p.exists()
    # trash dir gone
    assert not (tmp_path / ".trash" / trash_id).exists()
    log = ActivityLog.load(tmp_path)
    assert log.entries[-1].operation_type == "manual_restore_trash"


def test_apply_restore_collision_raises(tmp_path: Path):
    p = _seed(tmp_path)
    delete_result = apply_soft_delete(tmp_path, p, today=date(2026, 4, 27))
    # Recreate at original path
    _seed(tmp_path)
    with pytest.raises(PageRestoreCollisionError):
        apply_restore_from_trash(tmp_path, delete_result.trash_id, today=date(2026, 4, 27))


def test_dismiss_trash_entry(tmp_path: Path):
    p = _seed(tmp_path)
    delete_result = apply_soft_delete(tmp_path, p, today=date(2026, 4, 27))
    dismiss_trash_entry(tmp_path, delete_result.trash_id, today=date(2026, 4, 27))
    assert not (tmp_path / ".trash" / delete_result.trash_id).exists()
    log = ActivityLog.load(tmp_path)
    assert log.entries[-1].operation_type == "trash_dismissed"


def test_empty_trash_removes_all(tmp_path: Path):
    p1 = _seed(tmp_path, "wiki/entities/foo.md")
    p2 = _seed(tmp_path, "wiki/entities/bar.md")
    apply_soft_delete(tmp_path, p1, today=date(2026, 4, 27))
    apply_soft_delete(tmp_path, p2, today=date(2026, 4, 27))
    result = empty_trash(tmp_path, today=date(2026, 4, 27))
    assert result.removed_count == 2
    trash_root = tmp_path / ".trash"
    assert not any(d.is_dir() for d in trash_root.iterdir() if d.name.startswith("deleted-"))
    log = ActivityLog.load(tmp_path)
    assert log.entries[-1].operation_type == "trash_emptied"
```

- [ ] **Step 2: Implement** `claude_mnemos/core/page_apply.py`:

```python
"""Page mutation operations: edit, soft-delete, restore-from-trash, dismiss, empty."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from claude_mnemos.config import Config
from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.page_io import ParsedPage, read_page, serialize_page
from claude_mnemos.core.staging import StagingTransaction
from claude_mnemos.core.trash import (
    TRASH_DIRNAME,
    TrashEntryNotFoundError,
    list_trash,
    read_metadata,
)
from claude_mnemos.state.activity import (
    ACTIVITY_FILENAME,
    ActivityEntry,
    ActivityLog,
    ActivityOperationType,
)

if TYPE_CHECKING:
    from claude_mnemos.daemon.our_writes import OurWritesTracker


class PageRestoreCollisionError(RuntimeError):
    """Raised when restore_from_trash would overwrite an existing file."""


@dataclass(frozen=True)
class PatchResult:
    success: bool
    snapshot_path: Path | None = None
    activity_id: str | None = None


@dataclass(frozen=True)
class DeleteResult:
    success: bool
    snapshot_path: Path | None = None
    activity_id: str | None = None
    trash_id: str | None = None


@dataclass(frozen=True)
class RestoreResult:
    success: bool
    snapshot_path: Path | None = None
    activity_id: str | None = None
    restored_path: str | None = None


@dataclass(frozen=True)
class EmptyTrashResult:
    removed_count: int = 0
    removed_ids: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    activity_id: str | None = None


_FORBIDDEN_FRONTMATTER_KEYS = frozenset({"created", "type"})  # type also locked: changing type would move file


def apply_patch(
    vault: Path,
    page_path: Path,
    *,
    frontmatter_patch: Mapping[str, Any] | None = None,
    body: str | None = None,
    tracker: "OurWritesTracker | None" = None,
    today: date | None = None,
    cfg: Config | None = None,
) -> PatchResult:
    cfg = cfg or Config.from_env()
    today = today or date.today()
    rel = page_path.relative_to(vault).as_posix()

    if not frontmatter_patch and body is None:
        return PatchResult(success=True, snapshot_path=None, activity_id=None)

    parsed = read_page(page_path)
    new_fm = parsed.frontmatter
    fields_changed: list[str] = []

    if frontmatter_patch:
        forbidden = set(frontmatter_patch.keys()) & _FORBIDDEN_FRONTMATTER_KEYS
        if forbidden:
            raise ValueError(f"forbidden frontmatter keys: {forbidden}")
        update = dict(frontmatter_patch)
        # auto side-effects of manual edit
        update.setdefault("agent_written", False)
        update.setdefault("last_human_edit", datetime.now(UTC))
        update.setdefault("updated", today)
        new_fm = parsed.frontmatter.model_copy(update=update)
        fields_changed = sorted(set(frontmatter_patch.keys()))

    new_body = body if body is not None else parsed.body
    if body is not None:
        fields_changed.append("body")

    new_parsed = ParsedPage(frontmatter=new_fm, extra_fm=parsed.extra_fm, body=new_body)
    op_id = uuid4().hex

    with pipeline_lock(vault, timeout=cfg.lock_timeout):
        with StagingTransaction(vault, op_id, operation_type="manual_edit") as txn:
            txn.write(Path(rel), serialize_page(new_parsed))
            snap = txn.pre_promote_snapshot_path()
            log = ActivityLog.load(vault)
            log.append(
                ActivityEntry(
                    id=op_id,
                    timestamp=datetime.now(UTC),
                    operation_type="manual_edit",
                    status="success",
                    snapshot_path=snap.relative_to(vault).as_posix(),
                    can_undo=True,
                    affected_pages=[rel],
                    metadata={"page_path": rel, "fields_changed": fields_changed},
                )
            )
            txn.write(Path(ACTIVITY_FILENAME), log.serialize_to_string())
            promote = txn.promote_to_vault(tracker=tracker)

    return PatchResult(success=True, snapshot_path=promote.snapshot, activity_id=op_id)


def apply_soft_delete(
    vault: Path,
    page_path: Path,
    *,
    tracker: "OurWritesTracker | None" = None,
    today: date | None = None,
    cfg: Config | None = None,
) -> DeleteResult:
    cfg = cfg or Config.from_env()
    rel = page_path.relative_to(vault).as_posix()
    op_id = uuid4().hex

    with pipeline_lock(vault, timeout=cfg.lock_timeout):
        with StagingTransaction(vault, op_id, operation_type="manual_delete") as txn:
            txn.delete(rel, to_trash=True)
            snap = txn.pre_promote_snapshot_path()
            # We don't know trash_id until after promote (computed in _apply_deletes
            # using utc-now). Pre-write activity entry with placeholder, fix after.
            slug = Path(rel).stem or "page"
            ts = datetime.now(UTC).strftime("%Y-%m-%d-%H-%M-%S")
            trash_id = f"deleted-{slug}-{ts}-{op_id[:8]}"
            log = ActivityLog.load(vault)
            log.append(
                ActivityEntry(
                    id=op_id,
                    timestamp=datetime.now(UTC),
                    operation_type="manual_delete",
                    status="success",
                    snapshot_path=snap.relative_to(vault).as_posix(),
                    can_undo=True,
                    affected_pages=[rel],
                    metadata={"page_path": rel, "trash_id": trash_id},
                )
            )
            txn.write(Path(ACTIVITY_FILENAME), log.serialize_to_string())
            promote = txn.promote_to_vault(tracker=tracker)

    return DeleteResult(
        success=True, snapshot_path=promote.snapshot, activity_id=op_id, trash_id=trash_id,
    )


def apply_restore_from_trash(
    vault: Path,
    trash_id: str,
    *,
    tracker: "OurWritesTracker | None" = None,
    today: date | None = None,
    cfg: Config | None = None,
) -> RestoreResult:
    cfg = cfg or Config.from_env()
    trash_dir = vault / TRASH_DIRNAME / trash_id
    if not trash_dir.is_dir():
        raise TrashEntryNotFoundError(trash_id)
    meta = read_metadata(trash_dir)
    if meta is None:
        raise PageRestoreCollisionError(f"no metadata for trash entry {trash_id}")

    target = vault / meta.original_path
    if target.exists():
        raise PageRestoreCollisionError(
            f"original path {meta.original_path} already exists"
        )

    # Locate the page basename
    page_basename: str | None = None
    for f in trash_dir.iterdir():
        if f.is_file() and not f.name.startswith(".") and f.suffix == ".md":
            page_basename = f.name
            break
    if page_basename is None:
        raise PageRestoreCollisionError(f"trash entry {trash_id} has no page file")

    op_id = uuid4().hex
    src_rel = (Path(TRASH_DIRNAME) / trash_id / page_basename).as_posix()
    dst_rel = meta.original_path

    with pipeline_lock(vault, timeout=cfg.lock_timeout):
        with StagingTransaction(vault, op_id, operation_type="manual_restore_trash") as txn:
            txn.move(src_rel, dst_rel)
            snap = txn.pre_promote_snapshot_path()
            log = ActivityLog.load(vault)
            log.append(
                ActivityEntry(
                    id=op_id,
                    timestamp=datetime.now(UTC),
                    operation_type="manual_restore_trash",
                    status="success",
                    snapshot_path=snap.relative_to(vault).as_posix(),
                    can_undo=True,
                    affected_pages=[dst_rel],
                    metadata={"trash_id": trash_id, "restored_path": dst_rel},
                )
            )
            txn.write(Path(ACTIVITY_FILENAME), log.serialize_to_string())
            promote = txn.promote_to_vault(tracker=tracker)

        # Clean up empty trash dir (orchestration outside transaction)
        shutil.rmtree(trash_dir, ignore_errors=True)

    return RestoreResult(
        success=True, snapshot_path=promote.snapshot, activity_id=op_id, restored_path=dst_rel,
    )


def dismiss_trash_entry(
    vault: Path,
    trash_id: str,
    *,
    today: date | None = None,
    cfg: Config | None = None,
) -> None:
    cfg = cfg or Config.from_env()
    trash_dir = vault / TRASH_DIRNAME / trash_id
    if not trash_dir.is_dir():
        raise TrashEntryNotFoundError(trash_id)
    op_id = uuid4().hex
    had_metadata = (trash_dir / ".metadata.json").is_file()

    with pipeline_lock(vault, timeout=cfg.lock_timeout):
        shutil.rmtree(trash_dir, ignore_errors=False)
        log = ActivityLog.load(vault)
        log.append(
            ActivityEntry(
                id=op_id,
                timestamp=datetime.now(UTC),
                operation_type="trash_dismissed",
                status="success",
                snapshot_path=None,
                can_undo=False,
                affected_pages=[],
                metadata={"trash_id": trash_id, "had_metadata": had_metadata},
            )
        )
        log.save(vault)


def empty_trash(
    vault: Path,
    *,
    today: date | None = None,
    cfg: Config | None = None,
) -> EmptyTrashResult:
    cfg = cfg or Config.from_env()
    op_id = uuid4().hex
    entries = list_trash(vault)
    removed: list[str] = []
    errors: list[tuple[str, str]] = []

    with pipeline_lock(vault, timeout=cfg.lock_timeout):
        for entry in entries:
            d = vault / TRASH_DIRNAME / entry.trash_id
            try:
                shutil.rmtree(d, ignore_errors=False)
                removed.append(entry.trash_id)
            except OSError as exc:
                errors.append((entry.trash_id, str(exc)))

        log = ActivityLog.load(vault)
        log.append(
            ActivityEntry(
                id=op_id,
                timestamp=datetime.now(UTC),
                operation_type="trash_emptied",
                status="success",
                snapshot_path=None,
                can_undo=False,
                affected_pages=[],
                metadata={"removed_count": len(removed), "removed_ids": removed, "errors": errors},
            )
        )
        log.save(vault)

    return EmptyTrashResult(
        removed_count=len(removed), removed_ids=removed, errors=errors, activity_id=op_id,
    )
```

- [ ] **Step 3: Run + commit**

```bash
python -m pytest tests/core/test_page_apply.py -v
python -m pytest -q
python -m ruff check claude_mnemos/core/page_apply.py tests/core/test_page_apply.py
python -m mypy claude_mnemos/core/page_apply.py

git add claude_mnemos/core/page_apply.py tests/core/test_page_apply.py
git commit -m "feat(core): page_apply — patch / soft_delete / restore / dismiss / empty"
```

---

## Tasks 6-12 — Routes, App wiring, CLI, E2E, Docs

Tasks 6-12 follow the same TDD pattern as Plans #10/#11. **Read design doc §3.5 for REST shapes, §3.6 for CLI surface.** Implementer subagents will be told to follow design doc verbatim where this plan abbreviates.

### Task 6: REST `/pages/*` routes

Files: `claude_mnemos/daemon/routes/pages.py`, `tests/daemon/test_app_pages.py`. Endpoints per design §3.5: PATCH/verify/archive/DELETE on `/pages/{page_ref:path}`. Each route resolves `page_ref` via `core/pages.page_ref_to_path` (404 on PageRefError), then calls `apply_patch` / `apply_soft_delete`. Body: `{"frontmatter": {dict|null}, "body": str|null}` for PATCH. Verify/archive are convenience wrappers.

Tests: PATCH success, PATCH 422 on invalid status, verify shortcut, archive shortcut, DELETE creates trash dir, 404 on missing ref. ~6 tests.

Commit: `feat(daemon): /pages/{ref}/{verify,archive,DELETE,PATCH} routes`.

### Task 7: REST `/trash/*` routes

Files: `claude_mnemos/daemon/routes/trash.py`, `tests/daemon/test_app_trash.py`. Endpoints: GET list, GET by id, POST restore, DELETE one, DELETE all (empty). Read paths use `core/trash.list_trash`. Write paths call `apply_restore_from_trash` / `dismiss_trash_entry` / `empty_trash`. Exception handlers: `TrashEntryNotFoundError → 404`, `PageRestoreCollisionError → 409`.

Tests: list empty + populated, get by id, restore success + collision (409), dismiss + 404, empty (returns count). ~6 tests.

Commit: `feat(daemon): /trash/* routes for list/get/restore/dismiss/empty`.

### Task 8: app.py wiring

Files: `claude_mnemos/daemon/app.py`. Include 2 new routers. Add 3 exception handlers (PageRefError → 404, PageRestoreCollisionError → 409, TrashEntryNotFoundError → 404).

Tests: implicit via Tasks 6-7.

Commit: `feat(daemon): wire pages + trash routers and exception handlers`.

### Task 9: CLI `mnemos page` subgroup

Files: `claude_mnemos/cli.py`, `tests/test_cli_pages.py`. Subcommands: `edit` (with `--frontmatter '{json}'` and `--body-file PATH`), `verify`, `archive`, `delete`. All POST/PATCH/DELETE via daemon REST. Read commands not present (`page show` is reading — already covered by `read_page` MCP tool / can use HTTP; skip for Plan #12).

Exit codes: 0/1/87 (daemon offline)/88 (PageRefError)/89 (collision)/90 (validation).

Tests: parse for each subcommand, main dispatch with mocked httpx (or live daemon optional). ~8 tests.

Commit: `feat(cli): mnemos page {edit,verify,archive,delete} subgroup`.

### Task 10: CLI `mnemos trash` subgroup

Files: `claude_mnemos/cli.py`, `tests/test_cli_trash.py`. Subcommands: `list` (direct DB read via `core/trash.list_trash`), `restore`, `dismiss`, `empty` (with `--yes` flag and stdin typed-`delete` confirm without it).

Tests: parse, list output formatting, restore via daemon, dismiss, empty without --yes (mock stdin "delete"), empty with --yes (no prompt). ~8 tests.

Commit: `feat(cli): mnemos trash {list,restore,dismiss,empty} subgroup`.

### Task 11: slow E2E (optional but recommended)

Files: `tests/daemon/test_pages_e2e.py`. Subprocess daemon. Seed page → PATCH → verify content → DELETE → check trash → POST /trash/{id}/restore → page back. Validates round-trip.

Commit: `test(daemon): slow E2E for pages + trash round trip`.

### Task 12: README + memory + merge

Files: `README.md`, memory file. Status `Plans #1-#12`. New "Pages + Trash" section. Memory entry for Plan #12 with files and design choices. Verify suite green. Merge non-FF to main. Cleanup `feat/page-edit-trash` after merge.

Commit: `docs: README — Plans #1-#12 status + Pages + Trash section`.

Merge: `Merge branch 'feat/page-edit-trash' — Plan #12: Page edit + Trash`.

---

## Definition of Done

- [ ] All 12 tasks committed on `feat/page-edit-trash`
- [ ] `pytest -q` green (~810 fast tests)
- [ ] `pytest -q -m slow` green (~11 slow tests)
- [ ] `ruff check .` clean
- [ ] `mypy claude_mnemos` clean
- [ ] Manual smoke (optional): edit a page, verify it, delete it, list trash, restore it, undo via `mnemos undo <activity_id>`
- [ ] README + memory updated
- [ ] Merged to `main` via non-FF commit
- [ ] feat/page-edit-trash branch deleted after merge

---

## Spec coverage check

- PATCH /pages — `apply_patch` + Task 6 ✓
- POST /pages/.../verify — convenience shortcut ✓
- POST /pages/.../archive — convenience shortcut ✓
- DELETE /pages — `apply_soft_delete` + Task 6 ✓
- GET /trash, GET /trash/{id} — Task 7 ✓
- POST /trash/{id}/restore — Task 7 ✓
- DELETE /trash/{id} — Task 7 ✓
- DELETE /trash — Task 7 ✓
- 3-tier confirmation — backend doesn't enforce, CLI does for `empty`, frontend does in Plan #14 ✓ (documented OOS)
- Backlinks — Plan #13 ✓ (documented OOS)
- MCP tools — Plan #14 ✓ (documented OOS)
