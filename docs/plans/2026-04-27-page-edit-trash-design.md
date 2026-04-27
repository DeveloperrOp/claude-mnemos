# Design: Page edit + Trash management (Plan #12 — NEW)

**Status:** drafted; scope per Plan #11 follow-up roadmap.
**Date:** 2026-04-27
**Author:** Claude (autonomous per Yarik's "следовать плану" directive).
**Predecessor:** `2026-04-27-jobs-queue-design.md` (Plan #11, merged in `4b9b4e4` + 4 hotfixes).
**Successor planned:** Plan #13 (Sessions+Settings+Metrics+Multi-vault+adaptive context) → Plan #14 (Dashboard).

---

## 1. Goal

Дать пользователю **прямое управление страницами и корзиной** через REST + CLI, без необходимости лезть в файловую систему vault'а напрямую. После Plan #12:

```bash
# Edit a page
mnemos page edit wiki/entities/foo --vault <path>      # opens $EDITOR with current content
mnemos page verify wiki/entities/foo --vault <path>    # status=verified
mnemos page archive wiki/entities/foo --vault <path>   # status=archived
mnemos page delete wiki/entities/foo --vault <path>    # soft-delete to .trash/
                                                        # → activity entry, undo via mnemos undo

# Trash management
mnemos trash list --vault <path>                       # list trashed pages with original paths
mnemos trash restore <trash-id> --vault <path>         # back to original location
mnemos trash dismiss <trash-id> --vault <path>         # hard delete (no undo)
mnemos trash empty --vault <path>                      # hard delete all trash entries
```

REST surface для будущего dashboard (Plan #14):

```
PATCH  /pages/{page_ref}                — full edit (frontmatter dict + optional body)
POST   /pages/{page_ref}/verify         — convenience: status=verified
POST   /pages/{page_ref}/archive        — convenience: status=archived
DELETE /pages/{page_ref}                — soft-delete to .trash/

GET    /trash                           — list trashed entries with metadata
GET    /trash/{trash_id}                — single entry detail
POST   /trash/{trash_id}/restore        — move back to original path
DELETE /trash/{trash_id}                — hard delete one entry
DELETE /trash                           — empty trash (hard delete all entries)
```

### Что НЕ даёт (явно отложено)

- **Backlinks endpoint** (`GET /pages/{id}/backlinks`) — Plan #13.
- **3-tier confirmation UI semantics** (`Tier 1: single`, `Tier 2: typed 'delete'`, `Tier 3: project name + 30s cooldown`) — Plan #14 (UI concern). Backend в Plan #12 просто принимает DELETE и выполняет.
- **MCP tools** (`update_page`, `verify_page`, `archive_page`, `delete_page`, `restore_from_trash`, `list_trash`) — Plan #14 (вместе с dashboard, чтобы LLM имел symmetric capabilities). В Plan #12 — только REST + CLI.
- **Bulk operations** (`POST /pages/batch-archive`, `DELETE /pages/batch`) — Plan #14.
- **Pin trash entry** (preserve from auto-cleanup) — Plan #14+. В Plan #12 нет auto-cleanup для manually-deleted; только spec §7.5 180-day pruning, который применится одинаково.

---

## 2. Scope

### 2.1 In scope

| Component | Where |
|---|---|
| `ActivityOperationType += "manual_edit", "manual_delete", "manual_restore_trash", "trash_dismissed", "trash_emptied"` | edit `state/activity.py` |
| `core/staging.py` — extend `StagingTransaction.delete(to_trash=True)` to write `.metadata.json` (operation_id, original_path, page_type, deleted_at) alongside `.reason.txt` | edit |
| `core/trash.py` — `TrashEntry`, `parse_trash_entry`, `list_trash`, `read_metadata`, `compute_manual_deleted_path` | new |
| `core/pages.py` — `page_ref_to_path(vault, ref)` resolver: bare slug ('foo'), relative POSIX ('wiki/entities/foo.md'), or absolute path. Returns resolved `Path`. Includes anti-traversal | new |
| `core/page_apply.py` — `apply_patch(vault, page_path, *, frontmatter_patch, body, tracker, today)` — load via `read_page`, apply patch, validate via Pydantic, write via `StagingTransaction(operation_type="manual_edit")` with snapshot + activity. `apply_soft_delete(vault, page_path, tracker, today)` — wraps `txn.delete(to_trash=True)` + activity. `apply_restore_from_trash(vault, trash_id, tracker, today)` — read metadata, verify original_path free, move back via `txn.move()` + activity, then rmtree empty trash dir | new |
| Daemon REST: `daemon/routes/pages.py` (PATCH/verify/archive/DELETE), `daemon/routes/trash.py` (GET list/get/restore/dismiss/empty) | new |
| Exception handlers in `app.py`: `PageRefError → 404`, `PageInvalidStateError → 409`, `TrashEntryNotFoundError → 404` | edit |
| CLI: `mnemos page {edit, verify, archive, delete}` + `mnemos trash {list, restore, dismiss, empty}` | edit `cli.py` |
| Tests: `core/test_pages.py`, `core/test_trash.py`, `core/test_page_apply.py`, `daemon/test_app_pages.py`, `daemon/test_app_trash.py`, `test_cli_pages.py`, `test_cli_trash.py`, `test_staging_extensions.py` (extend metadata.json) | new+extend |

### 2.2 Out of scope

| Component | План | Reason |
|---|---|---|
| Backlinks endpoint | Plan #13 | Уже есть `find_files_referencing` (Plan #8 wikilinks); REST/CLI обёртка отделится от Plan #12 |
| MCP tools для pages/trash | Plan #14 | LLM получит вместе с UI |
| 3-tier confirmation flow | Plan #14 (UI) | Backend без cooldown/typed-name — это UX |
| Auto-prune trash > 180 дней | Plan #13+ | spec §7.5 retention; нужен `scheduler/trash_cleanup.py` |
| Page versioning / history view | Plan #14+ | Spec §11.1 mentions but not in current scope |
| Bulk operations | Plan #14 | YAGNI now |
| Edit conflict detection (server-side If-Match ETag) | Plan #14 | Single-user MVP |
| Trash pin (защита от auto-cleanup) | Plan #14+ | YAGNI |

---

## 3. Architecture

### 3.1 Trash directory layout (extension of Plan #8 ontology trash format)

Existing format from `core/staging.py:_apply_deletes`:

```
<vault>/.trash/deleted-<slug>-<utc-ts>-<op-id-short>/
    <basename>.md                # the actual page file
    .reason.txt                  # human-readable reason
```

Plan #12 **adds** `.metadata.json` next to `.reason.txt`:

```
<vault>/.trash/deleted-<slug>-<utc-ts>-<op-id-short>/
    <basename>.md
    .reason.txt
    .metadata.json               # NEW
```

`.metadata.json` schema:

```python
class TrashMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    trash_id: str                       # the dir name, e.g. "deleted-foo-2026-04-27-12-34-56-abcd1234"
    original_path: str                  # vault-relative POSIX, e.g. "wiki/entities/foo.md"
    deleted_at: datetime                # UTC
    operation_id: str
    operation_type: str                 # "manual_delete" | "ontology_apply" | etc
```

**Backward compat:** old trash dirs from Plan #8 (no `.metadata.json`) appear in listing as `restorable=False` with `restore_blocked_reason="missing metadata"`. They can still be `dismissed`/empty'ed normally.

**Other trash directory kinds** (`rejected-*` from staging exit cleanups, `manual-deleted-*` from past versions if any) — listed but `restorable=False` (no original_path).

### 3.2 `core/pages.py:page_ref_to_path`

```python
def page_ref_to_path(vault: Path, ref: str) -> Path:
    """Resolve a user-supplied page reference to an absolute path inside vault.

    Accepts:
    - Bare slug: "foo" → searches wiki/{entities,concepts,sources}/foo.md, prefers entity > concept > source.
    - Relative POSIX path: "wiki/entities/foo.md" → vault / "wiki/entities/foo.md".
    - Relative without .md: "wiki/entities/foo" → +".md".

    Raises:
    - PageRefError if no matching page exists or path escapes vault.
    """
```

Uses `lint.utils.build_slug_index` (already exists from Plan #10) for slug→path resolution.

Anti-traversal: `path.resolve().is_relative_to(vault.resolve())`.

### 3.3 `core/page_apply.py`

Three operations, all under `pipeline_lock` + `StagingTransaction`:

```python
@dataclass(frozen=True)
class PatchResult:
    success: bool
    snapshot_path: Path | None
    activity_id: str | None
    new_frontmatter: WikiPageFrontmatter | None  # for echo-back to API caller


def apply_patch(
    vault: Path,
    page_path: Path,
    *,
    frontmatter_patch: dict[str, Any] | None = None,
    body: str | None = None,
    tracker: OurWritesTracker | None = None,
    today: date | None = None,
    cfg: Config | None = None,
) -> PatchResult:
    """Load page via core/page_io.read_page, apply patch (frontmatter dict updates
    via model_copy(update=...), body replaces if not None), validate Pydantic,
    write via StagingTransaction(operation_type="manual_edit"), append activity
    "manual_edit" with can_undo=True, promote.

    `frontmatter_patch` is a dict applied via Pydantic model_copy(update=...);
    raises ValidationError if patch produces invalid frontmatter (e.g.,
    status='not_a_status').

    Empty patch (None + None) → no-op success without snapshot/activity.
    """


def apply_soft_delete(
    vault: Path,
    page_path: Path,
    *,
    tracker: OurWritesTracker | None = None,
    today: date | None = None,
    cfg: Config | None = None,
) -> DeleteResult:
    """Wrap StagingTransaction with txn.delete(rel_path, to_trash=True), append
    activity "manual_delete" with can_undo=True (snapshot lets undo restore the
    deleted file from .trash via restore_from_snapshot)."""


def apply_restore_from_trash(
    vault: Path,
    trash_id: str,
    *,
    tracker: OurWritesTracker | None = None,
    today: date | None = None,
    cfg: Config | None = None,
) -> RestoreResult:
    """Load .metadata.json, verify original_path doesn't already exist (else
    PageRestoreCollisionError → 409), move via txn.move(trash/<id>/<basename>,
    original_path), append activity "manual_restore_trash" with can_undo=True,
    after promote shutil.rmtree the now-empty trash dir.

    Note: txn.move source/dest are both vault-relative; .trash/<id>/<basename>
    is inside vault, so this works."""
```

### 3.4 Activity entries

| Operation | op_type | can_undo | snapshot_path | metadata |
|---|---|---|---|---|
| PATCH /pages | `manual_edit` | True | yes | `{"page_path": "...", "fields_changed": ["status", "body?"]}` |
| POST /verify | `manual_edit` | True | yes | `{"page_path": "...", "fields_changed": ["status"], "convenience": "verify"}` |
| POST /archive | `manual_edit` | True | yes | `{"page_path": "...", "fields_changed": ["status"], "convenience": "archive"}` |
| DELETE /pages | `manual_delete` | True | yes | `{"page_path": "...", "trash_id": "deleted-..."}` |
| POST /trash/{id}/restore | `manual_restore_trash` | True | yes | `{"trash_id": "...", "restored_path": "..."}` |
| DELETE /trash/{id} | `trash_dismissed` | False | None | `{"trash_id": "...", "had_metadata": bool}` |
| DELETE /trash (empty) | `trash_emptied` | False | None | `{"removed_count": N, "trash_ids": [...]}` |

`trash_dismissed`/`trash_emptied` non-undoable but logged for audit trail.

### 3.5 REST API

```python
# pages
PATCH  /pages/{page_ref:path}
       body: {"frontmatter": {dict}, "body": str | null}
       → 200 with PatchResult dict
       → 404 if page_ref doesn't resolve
       → 422 on Pydantic validation error
       → 409 on lock timeout

POST   /pages/{page_ref:path}/verify
       → 200 with PatchResult — equivalent to PATCH frontmatter={"status": "verified"}

POST   /pages/{page_ref:path}/archive
       → 200 — equivalent to PATCH frontmatter={"status": "archived"}

DELETE /pages/{page_ref:path}
       → 200 with DeleteResult (trash_id, snapshot_path, activity_id)
       → 404 if not found

# trash
GET    /trash
       → 200 with {"entries": [TrashEntryDict], "total": N}
GET    /trash/{trash_id}
       → 200 with TrashEntryDict, 404 if not found

POST   /trash/{trash_id}/restore
       → 200 with RestoreResult, 404, 409 on collision

DELETE /trash/{trash_id}
       → 204, 404 if not found

DELETE /trash
       → 200 with {"removed_count": N, "removed_ids": [...]}
       (acceptable to use 200+body instead of 204+empty since we return summary)
```

`page_ref` uses FastAPI `:path` converter to allow slashes in slug.

### 3.6 CLI

```bash
mnemos page edit <page_ref> [--vault PATH] [--frontmatter '{json}'] [--body-file PATH]
mnemos page verify <page_ref> [--vault PATH]
mnemos page archive <page_ref> [--vault PATH]
mnemos page delete <page_ref> [--vault PATH]

mnemos trash list [--vault PATH]
mnemos trash restore <trash_id> [--vault PATH]
mnemos trash dismiss <trash_id> [--vault PATH]
mnemos trash empty [--vault PATH] [--yes]      # --yes skips Tier 2 typed confirm
```

`mnemos page edit` без `--frontmatter`/`--body-file` пытается открыть `$EDITOR` с current content (frontmatter+body in markdown form) и парсить результат. Сложно для tests; в Plan #12 поддержим только explicit `--frontmatter` JSON и `--body-file`. `$EDITOR` — Plan #14+.

`mnemos trash empty` без `--yes` запрашивает typed `delete` confirmation на stdin. Tier 1 single — без confirmation. Tier 2 batch (multi) — вне scope, нет batch CLI. Tier 3 project-level — Plan #14.

Read commands (`trash list`) — direct filesystem scan через `core/trash.py`. Write commands (`page edit/verify/archive/delete`, `trash restore/dismiss/empty`) — через REST к daemon (требует `mnemos daemon start`). Exit codes:

- 0 success
- 1 missing vault
- 87 daemon offline
- 88 PageRefError / TrashEntryNotFoundError
- 89 PageRestoreCollisionError / invalid state
- 90 ValidationError (bad PATCH payload)

### 3.7 Daemon wiring

`MnemosDaemon` без новых attributes — все REST routes используют `app.state.vault_root` + `app.state.daemon.tracker`. Concurrent ingest serialization — через `pipeline_lock` (already used by `apply_patch`/`apply_soft_delete`/`apply_restore_from_trash`).

### 3.8 Snapshot interaction

Все patch/delete/restore операции создают pre-op snapshot через `StagingTransaction`. `mnemos undo <activity_id>` восстанавливает.

`trash_dismissed` и `trash_emptied` — НЕ создают snapshot (no undo path). Но они **писали бы** в `.trash/` и `.activity.json`, которые watchdog handler skip'ает (dotfile rule). Также `_EXCLUDED_FILES` уже включает `.pipeline.lock`, `.jobs.db*`. Snapshots уже исключают `.trash/` через `_EXCLUDED_DIRS` (Plan #5).

### 3.9 Watchdog interaction

`apply_patch` mutates `wiki/{type}/{slug}.md` — это watched path. Чтобы handler не пометил own write как `human_edit_detected`, операция идёт через `StagingTransaction.promote_to_vault(tracker=tracker)` — tracker регистрирует target paths до shutil.move (Plan #9 mechanism). Уже работает.

### 3.10 Trash listing

```python
class TrashEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trash_id: str                       # dir name
    deleted_at: datetime                # from metadata.json or fs mtime fallback
    original_path: str | None           # None if no metadata.json
    operation_type: str | None
    page_basename: str | None           # e.g. "foo.md"; None if dir empty
    restorable: bool                    # True iff original_path != None and basename exists
    restore_blocked_reason: str | None  # e.g. "missing metadata", "page already exists"


def list_trash(vault: Path) -> list[TrashEntry]:
    """Walk <vault>/.trash/, parse each subdir, return sorted by deleted_at desc."""
```

Subdirectories matching prefixes `deleted-*`, `rejected-*` (legacy from staging __exit__ rejection) are listed. `staging-*` or `manual-*` — also listed for completeness but typically restorable=False.

### 3.11 PATCH semantics

- `frontmatter_patch` must be a JSON object. Allowed keys = subset of `WikiPageFrontmatter` fields. Pydantic validates result.
- Forbidden keys (immutable): `created` (cannot change creation date). `agent_written` (manual edit always sets agent_written=False — that's a free side-effect, document it).
- `last_human_edit` is **automatically set** by patch logic to current UTC datetime — мирror watchdog handler behavior.
- `body` replaces full body. No append/insert mode.
- Empty PATCH (frontmatter={} or null AND body=None) → 200 no-op without snapshot/activity. Avoid noise.
- Multiple field PATCH: `frontmatter={"status": "verified", "tags": ["important"]}` — both applied atomically.

---

## 4. Test strategy

### 4.1 Unit

- `tests/core/test_pages.py`: page_ref_to_path with bare slug, full path, no .md suffix, ambiguous slug (multiple types) — entity wins, missing ref raises PageRefError, anti-traversal `../etc/passwd` raises.
- `tests/core/test_trash.py`: list_trash empty vault → []; with mixed metadata-having and metadata-missing dirs → correct restorable flags; sorted desc.
- `tests/core/test_page_apply.py`: apply_patch frontmatter-only / body-only / both; auto-set last_human_edit + agent_written=False; ValidationError on bad status; empty patch → no-op; apply_soft_delete writes metadata.json; apply_restore_from_trash collision → error.
- `tests/test_staging_extensions.py` extend: txn.delete(to_trash=True) writes .metadata.json with original_path.

### 4.2 Integration / REST

- `tests/daemon/test_app_pages.py`: PATCH success (frontmatter), PATCH 422 on bad value, verify/archive shortcuts, DELETE soft-delete + activity entry, 404 on missing.
- `tests/daemon/test_app_trash.py`: GET list (empty + populated), GET by id, POST restore (success + collision 409), DELETE single, DELETE bulk.

### 4.3 CLI

- `tests/test_cli_pages.py`: parse + main dispatch for edit/verify/archive/delete.
- `tests/test_cli_trash.py`: parse + main + `--yes` skip confirmation; empty without --yes → typed prompt (mock stdin).

### 4.4 Slow E2E (optional)

- `tests/daemon/test_pages_e2e.py`: subprocess daemon, seed page, PATCH via REST, verify content; DELETE → check `.trash/`; restore → page back; full round trip.

---

## 5. Open questions

| # | Q | Решение |
|---|---|---|
| Q1 | PATCH `frontmatter`: full replace or partial merge? | Partial merge via Pydantic `model_copy(update=...)`. Full replace = footgun. |
| Q2 | Body — replace or append? | Replace. Plan #14+ может добавить append/insert. |
| Q3 | `last_human_edit` auto-set on PATCH? | Yes — manual edit IS a human edit. `agent_written=False` тоже. |
| Q4 | Что если PATCH дает empty diff (новые значения = старым)? | Pydantic-validate, write через staging anyway, snapshot+activity created. Идempotent. Если хочется skip — тяжелее реализовать (deep diff), отложил. |
| Q5 | Trash empty CLI — Tier 2 typed-delete confirmation? | Backend без, CLI делает typed prompt unless `--yes`. REST endpoint без — frontend implements. |
| Q6 | Что если trash dir пуст (page basename удалён вручную)? | `restorable=False`, `restore_blocked_reason="page file missing"`. |
| Q7 | TrashEntry sort order? | `deleted_at` desc (newest first), как Activity. |
| Q8 | `:path` URL converter pages_ref может содержать `..` — anti-traversal? | `page_ref_to_path` валидирует через `resolve().is_relative_to(vault)`. |
| Q9 | Восстановленная страница — какой `last_human_edit`? | Не трогаем — restore returns to its original state pre-delete. Если нужен timestamp — можно metadata.restored_at в activity, не во frontmatter. |
| Q10 | Concurrent PATCH + watchdog edit (race) | pipeline_lock сериализует. Watchdog blocked while patch in progress. After patch promote, watchdog sees own writes via tracker → skip. |

---

## 6. Migration / compatibility

- `ActivityOperationType` literal расширяется (5 new values). Old activity logs парсятся.
- `core/staging.py:_apply_deletes` теперь пишет `.metadata.json`. Existing trash dirs без metadata — работают через `restorable=False` fallback.
- No new pyproject deps.
- Watchdog handler не изменяется — dotfile rule покрывает `.trash/` и `.metadata.json`.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| User PATCH'ит invalid frontmatter via direct REST call | Pydantic `extra="forbid"` + 422 response with detail |
| Restore из trash → original_path уже занят | Pre-check `(vault / original_path).exists()` → PageRestoreCollisionError → 409 |
| Trash empty rmtree fails partway | Per-dir try/except, accumulate errors, return partial summary |
| `mnemos page delete` для `wiki/sources/*` (raw chat reference) | Allowed, but breaks ingest manifest if source page missing. Document; same as ontology delete. |
| Patch removes required field | Pydantic catches; 422 |
| Body-file CLI very large file | Acceptable; pages are small по design |
| URL `:path` converter accepts `wiki/entities/../../etc` | page_ref_to_path resolves and validates inside vault |
| Trash dir name collision (same slug + same second + same op_id_short) | Existing format includes second + 8-char op_id — collision negligible |

---

## 8. Estimated diff

- New files: 3 prod (`core/pages.py`, `core/trash.py`, `core/page_apply.py`) + 2 daemon routes (`pages.py`, `trash.py`) + 8 test files
- Modified: `core/staging.py`, `state/activity.py`, `daemon/app.py`, `cli.py`, optionally `daemon/schemas.py`
- LOC estimate: ~2200 prod + ~1900 tests = ~4100 total
- Branch: `feat/page-edit-trash` (created)
- Expected commits: ~12

---

## 9. Spec self-review

1. **Placeholder scan:** все sections concrete, нет TBD. ✓
2. **Internal consistency:** activity types match table in §3.4 ↔ §3.6 CLI exit codes ↔ scope §2.1. ✓
3. **Scope check:** single subsystem (page edit + trash management). ✓
4. **Ambiguity check:** PATCH semantics (Q1-Q4) специфицированы. ✓
