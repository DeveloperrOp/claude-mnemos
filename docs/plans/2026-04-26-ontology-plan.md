# Ontology Implementation Plan (Plan #8)

> Use TDD at every step. Steps use checkbox (`- [ ]`).

**Goal:** HITL ontology suggestions infrastructure: Pydantic suggestion file format, CRUD store, wikilinks helper, StagingTransaction `move`/`delete` extensions, apply pipeline for `merge_entities`/`rename_entity`/`delete_page`, daemon REST endpoints, MCP tools, CLI subcommands.

**Architecture:** see `docs/plans/2026-04-26-ontology-design.md`.

**Tech stack:** Python 3.12, Pydantic v2, FastAPI, MCP SDK, pytest.

---

## Files map

**Создаём:**

| Файл | Что |
|---|---|
| `claude_mnemos/state/ontology.py` | `SuggestionFrontmatter`, `Suggestion`, `SuggestionStore`, `SuggestionStatus`, `SuggestionOperation`, `OntologyCorruptError`, lifecycle |
| `claude_mnemos/core/wikilinks.py` | `Wikilink`, `extract_wikilinks`, `rewrite_wikilinks`, `find_files_referencing` |
| `claude_mnemos/core/ontology_apply.py` | `OntologyError`, `ApplyResult`, `apply_merge_entities`, `apply_rename_entity`, `apply_delete_page`, `apply_suggestion` (dispatcher) |
| `claude_mnemos/daemon/routes/ontology.py` | `/suggestions` GET/POST + `/suggestions/{id}` GET + `/suggestions/{id}/{approve\|reject\|defer}` POST |
| `claude_mnemos/mcp/read_tools/ontology.py` | `list_suggestions(vault, status?)` |
| `claude_mnemos/mcp/write_tools/ontology.py` | `apply_ontology_suggestion`, `propose_ontology_change` |
| `tests/state/__init__.py` | empty if not exists |
| `tests/state/test_ontology.py` | Suggestion CRUD |
| `tests/test_wikilinks.py` | extract/rewrite |
| `tests/test_ontology_apply.py` | merge/rename/delete |
| `tests/test_staging_extensions.py` | `txn.move()`, `txn.delete()` |
| `tests/daemon/test_app_ontology.py` | endpoints |
| `tests/mcp/test_ontology_tools.py` | MCP tools |
| `tests/test_cli_ontology.py` | CLI |

**Изменяется:**

| Файл | Что |
|---|---|
| `claude_mnemos/state/activity.py` | `ActivityOperationType` literal: добавить `"ontology_apply"` |
| `claude_mnemos/core/staging.py` | `move()`, `delete()` методы + promote учитывает `_to_remove`/`_to_move` |
| `claude_mnemos/cli.py` | Subgroup `ontology {list,approve,reject,defer,propose}` + exit code 81 |
| `claude_mnemos/daemon/app.py` | Include ontology router |
| `claude_mnemos/mcp/server.py` | Register 3 ontology tools (12 → 12 with new dispatchers; точное число — через TOOL_DEFS append) |

---

## Зависимости задач

```
Task 1: state/ontology.py — models + SuggestionStore
    ↓
Task 2: state/activity.py — extend literal с "ontology_apply"
    ↓
Task 3: core/wikilinks.py — extract/rewrite/find_files_referencing
    ↓
Task 4: core/staging.py — txn.move() + txn.delete() + promote integration
    ↓
Task 5: core/ontology_apply.py — apply_merge/rename/delete + apply_suggestion
    ↓
Task 6: daemon/routes/ontology.py + app.py wiring
    ↓
Task 7: mcp/{read,write}_tools/ontology.py + server registration
    ↓
Task 8: cli.py — ontology subgroup + exit 81
    ↓
Task 9: smoke + README + memory + merge
```

---

## Task 1: state/ontology.py — models + SuggestionStore

**Files create:** `claude_mnemos/state/ontology.py`, `tests/state/__init__.py`, `tests/state/test_ontology.py`

- [ ] Tests первыми — все основные кейсы:
   - SuggestionFrontmatter validation: id pattern (`ont-YYYY-MM-DD-6hex`), status enum, confidence 0-1, operation enum
   - SuggestionFrontmatter rejects extra fields
   - Suggestion serialize → starts with `---\n`, parseable back via parse
   - Suggestion.parse roundtrip
   - SuggestionStore.list empty / 3 pending / status filter / include_archive
   - SuggestionStore.create writes file with id-derived name
   - SuggestionStore.create with existing id raises ValueError
   - SuggestionStore.get returns None for missing
   - SuggestionStore.get returns Suggestion for known
   - SuggestionStore.archive moves file from root to archive/
   - SuggestionStore.update_status updates frontmatter (and persists)
   - Corrupt YAML in suggestion file → OntologyCorruptError
   - SuggestionStore.list skips files which fail to parse (logs warning, continues)

- [ ] Implementation:
   - Pydantic v2 models per design §3.3
   - `Suggestion.serialize()` — YAML frontmatter via `yaml.safe_dump` + `\n---\n` + body
   - `Suggestion.parse(text)` — split frontmatter and body, validate
   - `SuggestionStore`: store inside `<vault>/.ontology-suggestions/` (root for pending, `archive/` for completed)
   - file naming: `<id>.md`
   - `update_status` reads → mutates frontmatter → atomic_write back
   - `archive(suggestion_id)` — `shutil.move` to archive subdir, returns new path
   - `OntologyCorruptError(ValueError)` like `ManifestCorruptError`

- [ ] Run tests + ruff + mypy
- [ ] Commit `feat(state): ontology suggestion file format + SuggestionStore`

---

## Task 2: state/activity.py — extend literal

**Files modify:** `claude_mnemos/state/activity.py`, `tests/test_activity.py`

- [ ] Add `"ontology_apply"` to `ActivityOperationType` literal
- [ ] Test: создать ActivityEntry с `operation_type="ontology_apply"` без ошибок
- [ ] Run tests + lint
- [ ] Commit `feat(state): extend ActivityOperationType with ontology_apply`

---

## Task 3: core/wikilinks.py

**Files create:** `claude_mnemos/core/wikilinks.py`, `tests/test_wikilinks.py`

- [ ] Tests:
   - extract: `"Hello [[foo]]"` → `[Wikilink(target="foo")]`
   - extract with alias: `"[[foo|Foo]]"` → `[Wikilink(target="foo", alias="Foo")]`
   - extract multiple: `"[[a]] and [[b]]"` → 2 entries
   - extract empty: `""` → `[]`
   - extract nested brackets: `"[[a]] [text]"` → 1 wikilink
   - rewrite: `"[[old]]"` with `{"old": "new"}` → `"[[new]]"`
   - rewrite preserves alias: `"[[old|alias]]"` with `{"old": "new"}` → `"[[new|alias]]"`
   - rewrite no-op: `"[[other]]"` with `{"old": "new"}` → unchanged
   - rewrite multiple: `"[[a]] [[b]]"` with `{"a": "x"}` → `"[[x]] [[b]]"`
   - find_files_referencing: empty vault → []
   - find_files_referencing: 2 files reference target → both returned
   - find_files_referencing: ignores file with same name (don't return self-link)

- [ ] Implementation:
   - `WIKILINK_RE = re.compile(r"\[\[([^\[\]\|]+)(?:\|([^\]]+))?\]\]")`
   - `Wikilink` dataclass с `target: str`, `alias: str | None`
   - `extract_wikilinks(text)` — re.findall
   - `rewrite_wikilinks(text, mapping)` — re.sub с callback
   - `find_files_referencing(vault, target_slug)` — rglob `wiki/**/*.md`, для каждого извлекаем wikilinks, фильтруем by target

- [ ] Run + lint + commit `feat(core): wikilinks regex helper for extract+rewrite`

---

## Task 4: core/staging.py — move + delete

**Files modify:** `claude_mnemos/core/staging.py`, `tests/test_staging.py`, `tests/test_staging_extensions.py`

- [ ] Tests:
   - `txn.move(src, dst)` happy path: после promote файл src отсутствует, dst есть с тем же содержимым
   - `txn.move` с src missing → ValueError при move call
   - `txn.move` с dst пересекающим существующий staged write → конфликт?
   - `txn.delete(path, to_trash=True)` happy: после promote path в `.trash/deleted-<slug>-<ts>/`
   - `txn.delete` с .reason.txt: проверить что файл создан с reason
   - `txn.delete(path, to_trash=False)` happy: файл просто исчезает
   - Snapshot перед promote captures pre-move state — restore_from_snapshot восстанавливает
   - `txn.move` после reject (within with-block raise) — vault не тронут
   - `txn.delete` после reject — vault не тронут

- [ ] Implementation:
   - `_to_move: list[tuple[str, str]]` field в `StagingTransaction`
   - `_to_remove: list[tuple[str, bool]]` field — (relpath, to_trash)
   - `move(src_relpath, dst_relpath)`: append to `_to_move`, validate src_relpath != dst_relpath
   - `delete(relpath, *, to_trash=True)`: append to `_to_remove`
   - `_apply_moves_and_deletes(self)` — helper called inside `promote_to_vault` AFTER staging files written
   - For move: `shutil.move(vault/src, vault/dst)` — но нужно атомарно с staged write на dst (если dst был staged, наш staged write побеждает; если staged_dst отсутствует — это плохо, raise)
   - For delete with to_trash: создаёт `<vault>/.trash/deleted-<slug>-<utc-ts>/<basename>` + `.reason.txt`
   - For delete to_trash=False: `(vault/relpath).unlink(missing_ok=False)`
   - Промт-документация в docstring каждого метода

- [ ] Run all staging tests (existing + new) + lint
- [ ] Commit `feat(core): StagingTransaction.move/delete extensions for ontology operations`

---

## Task 5: core/ontology_apply.py

**Files create:** `claude_mnemos/core/ontology_apply.py`, `tests/test_ontology_apply.py`

- [ ] Tests:
   - apply_merge_entities happy: 2 sources → target создан, sources в trash, wikilinks переписаны в 3-м файле
   - apply_merge_entities target уже существует → OntologyError
   - apply_merge_entities source missing → OntologyError
   - apply_merge_entities frontmatter merge: title из target, type из первого, flavor union, sources/related union
   - apply_rename_entity happy: source moved, wikilinks rewritten
   - apply_rename_entity target exists → OntologyError
   - apply_delete_page happy: source в trash, wikilinks НЕ переписаны
   - apply_delete_page source missing → OntologyError
   - На любой apply error: vault unchanged (snapshot restore), suggestion stays pending
   - Activity entry written: operation_type="ontology_apply", metadata.suggestion_id, metadata.operation, metadata.wikilinks_rewritten
   - apply_suggestion (dispatcher) routes по operation
   - apply_suggestion с already-applied → OntologyError("already applied")

- [ ] Implementation:
   - `OntologyError(RuntimeError)`
   - `ApplyResult` dataclass: success, target_path?, affected_pages, activity_id, wikilinks_rewritten
   - `apply_merge_entities(vault, suggestion, *, today)`:
     ```
     pre-validate: sources exist, target doesn't exist
     pipeline_lock
     load activity
     with StagingTransaction(vault, op_id=suggestion.id, op_type="ontology"):
        read sources, merge content into target_content
        compose target frontmatter
        txn.write(target_path, serialized)
        for src in sources: txn.delete(src) (to_trash)
        # wikilinks rewrite
        affected_files = find_files_referencing(vault, src_slug for each src)
        mapping = {src_slug: target_slug for each src}
        for f in affected_files:
            new_text = rewrite_wikilinks(f.read_text(), mapping)
            txn.write(rel(f), new_text)
        snapshot_path = txn.pre_promote_snapshot_path()
        activity entry append через txn.write(.activity.json)
        promote_to_vault
     return ApplyResult
     ```
   - `apply_rename_entity`: txn.move(old, new), wikilinks rewrite mapping={old_slug: new_slug}, activity
   - `apply_delete_page`: txn.delete(path, to_trash=True), no wikilinks rewrite, activity
   - `apply_suggestion(vault, suggestion_id)` — dispatcher:
     - load suggestion via SuggestionStore
     - if already applied/rejected/deferred → OntologyError
     - call appropriate apply_X
     - on success: SuggestionStore.update_status(approved, applied_at, applied_op_id) + archive
     - return ApplyResult

- [ ] Run + lint + commit `feat(core): ontology_apply for merge/rename/delete via StagingTransaction`

---

## Task 6: daemon/routes/ontology.py

**Files create:** `claude_mnemos/daemon/routes/ontology.py`, `tests/daemon/test_app_ontology.py`
**Files modify:** `claude_mnemos/daemon/app.py` (include router + exception handler)

- [ ] Tests:
   - GET /suggestions empty → `{suggestions: [], total: 0}`
   - GET /suggestions с 3 pending + 1 archived → 3 (default), `?status=all` → 4
   - GET /suggestions/{id} known → 200 + body
   - GET /suggestions/{id} missing → 404
   - POST /suggestions body={operation: merge_entities, sources: [...], target: ..., reason: ...} → 201 + suggestion
   - POST /suggestions с invalid operation → 422
   - POST /suggestions с missing sources → 422
   - POST /suggestions/{id}/approve happy → applies, returns ApplyResult, status=approved, file moved to archive
   - POST /suggestions/{id}/approve already approved → 409
   - POST /suggestions/{id}/reject → status=rejected, archive
   - POST /suggestions/{id}/defer → status=deferred (stays in root in Plan #8)

- [ ] Implementation:
   - `CreateSuggestionRequest` Pydantic в роутере (operation, sources, target?, reason?, confidence?)
   - GET handlers — sync def (file IO)
   - POST approve/reject/defer — sync def под threadpool
   - Exception handler `OntologyError` → 409 в `app.py`
   - Exception handler `OntologyCorruptError` → 503 с `error="ontology_corrupt"`

- [ ] Run + lint + commit `feat(daemon): /suggestions REST endpoints`

---

## Task 7: MCP ontology tools

**Files create:** `claude_mnemos/mcp/read_tools/ontology.py`, `claude_mnemos/mcp/write_tools/ontology.py`, `tests/mcp/test_ontology_tools.py`
**Files modify:** `claude_mnemos/mcp/server.py` (register 3 new tools), `claude_mnemos/mcp/schemas.py` (3 new schemas)

- [ ] Tests:
   - `list_suggestions(vault)` reads `.ontology-suggestions/` directly, returns list of dicts
   - `apply_ontology_suggestion` через mocked httpx → POST `/suggestions/{id}/approve`, returns response
   - `propose_ontology_change` через mocked httpx → POST `/suggestions`, returns created suggestion
   - server.py registered 12 tools (9 existing + 3 new), `list_tools` request returns all 12
   - call_tool `list_suggestions` → TextContent with JSON array
   - call_tool `apply_ontology_suggestion` daemon offline → "daemon not reachable" message

- [ ] Implementation:
   - `mcp/read_tools/ontology.py` `list_suggestions(vault, *, status=None)` — uses SuggestionStore directly
   - `mcp/write_tools/ontology.py`:
     - `apply_ontology_suggestion(client, daemon_url, suggestion_id)` → POST `/suggestions/{id}/approve`
     - `propose_ontology_change(client, daemon_url, operation, sources, target=None, reason="", confidence=0.7)` → POST `/suggestions`
   - `mcp/schemas.py`:
     - `LIST_SUGGESTIONS` — properties: status (enum optional)
     - `APPLY_ONTOLOGY_SUGGESTION` — required suggestion_id
     - `PROPOSE_ONTOLOGY_CHANGE` — required operation+sources, optional target+reason+confidence
   - `mcp/server.py`:
     - 3 tools в `TOOL_DEFS` с descriptions
     - `READ_TOOL_NAMES` += {"list_suggestions"}
     - `WRITE_TOOL_NAMES` += {"apply_ontology_suggestion", "propose_ontology_change"}
     - dispatcher cases в `_dispatch_read` и `_dispatch_write`

- [ ] Run + lint + commit `feat(mcp): 3 ontology tools (list_suggestions + apply + propose)`

---

## Task 8: CLI ontology subgroup

**Files modify:** `claude_mnemos/cli.py`, `tests/test_cli_ontology.py`

- [ ] Tests via build_parser:
   - `ontology list --vault PATH` parses
   - `ontology list --vault PATH --all` flag
   - `ontology approve <id> --vault PATH` parses
   - `ontology reject <id> --vault PATH`
   - `ontology defer <id> --vault PATH`
   - `ontology propose merge --source A --source B --target C --vault PATH` requires 2+ sources
   - `ontology propose rename --source old --target new --vault PATH`
   - `ontology propose delete --source path --vault PATH`
   - missing required flags → SystemExit
   - apply unknown id → exit 81

- [ ] Implementation:
   - `daemon` subparsers pattern (как Plan #5)
   - `_cmd_ontology_list` — печатает таблицу через SuggestionStore.list
   - `_cmd_ontology_approve` — calls apply_suggestion, prints summary, exit 0/81
   - `_cmd_ontology_reject` — SuggestionStore.update_status + archive
   - `_cmd_ontology_defer` — update status only (file stays)
   - `_cmd_ontology_propose` — argparse подкоманды merge/rename/delete:
     - validates inputs (sources exist, target doesn't for merge/rename)
     - generates id `ont-<today>-<6hex>`
     - SuggestionStore.create
     - prints created suggestion id
   - exit code 81 для OntologyError (catch на уровне `main`)

- [ ] Run all CLI tests + lint
- [ ] Commit `feat(cli): mnemos ontology {list,approve,reject,defer,propose} subgroup; exit 81`

---

## Task 9: smoke + README + memory + merge

- [ ] Manual smoke: создать fixture vault с 3 страницами, propose merge через CLI, approve, проверить:
   - target page существует
   - sources в `.trash/deleted-...`
   - wikilinks в 3-м файле переписаны
   - `.activity.json` содержит ontology_apply entry
   - undo через `mnemos undo <id>` восстанавливает
- [ ] README раздел `## Ontology` — короткое описание + ссылки на CLI/MCP/REST
- [ ] Update `claude_mnemos_project.md` memory с Plan #8 (Ontology) — что нового, что отложено
- [ ] Final pytest + ruff + mypy strict — clean
- [ ] `git checkout main && git merge --no-ff feat/ontology -m "Merge branch 'feat/ontology' — Plan #8: ontology HITL suggestions + apply"`

---

## Risks / known limitations

- StagingTransaction extension может выявить race conditions с pre-existing tests — следить.
- Wikilinks regex может не покрыть некоторые edge cases — best effort, warnings.
- `apply_merge_entities` frontmatter merge — emergent rules, могут потребоваться правки после dogfooding.
