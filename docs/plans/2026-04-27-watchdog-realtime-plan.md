# Watchdog Real-time Implementation Plan (Plan #9)

> Use TDD at every step. Steps use checkbox (`- [ ]`).

**Goal:** Real-time external file change detection in vault with self-write tracking, `human_edit_detected` activity entries, and in-memory alerts.

**Architecture:** see `docs/plans/2026-04-27-watchdog-realtime-design.md`.

**Tech stack:** Python 3.12, watchdog>=4.0, FastAPI, pytest.

---

## Files map

**Создаём:**

| Файл | Что |
|---|---|
| `claude_mnemos/daemon/our_writes.py` | `OurWritesTracker` (TTL set + paused() context) |
| `claude_mnemos/daemon/alerts.py` | `Alerts` ring buffer + `WatchdogAlert` dataclass |
| `claude_mnemos/daemon/watchdog_observer.py` | `VaultObserver` wrapper над `watchdog.observers.Observer` |
| `claude_mnemos/daemon/watchdog_handler.py` | `VaultChangeHandler` — classifies events, mutates frontmatter, appends activity |
| `claude_mnemos/daemon/routes/alerts.py` | `GET /alerts` + `DELETE /alerts/{id}` |
| `claude_mnemos/core/page_io.py` | `ParsedPage`, `read_page`, `serialize_page`, `PageParseError` |
| `tests/daemon/test_our_writes.py` | tracker unit tests |
| `tests/daemon/test_alerts.py` | alerts unit tests |
| `tests/daemon/test_watchdog_handler.py` | handler classification + mutation |
| `tests/daemon/test_watchdog_integration.py` | in-process observer + tmp dir |
| `tests/daemon/test_watchdog_e2e.py` | slow E2E with subprocess daemon |
| `tests/daemon/test_app_alerts.py` | REST endpoints |
| `tests/core/test_page_io.py` | round-trip with extras |

**Изменяется:**

| Файл | Что |
|---|---|
| `pyproject.toml` | `watchdog>=4.0` dependency + mypy override |
| `claude_mnemos/core/models.py` | `WikiPageFrontmatter.last_human_edit: datetime \| None = None` |
| `claude_mnemos/state/activity.py` | `ActivityOperationType` literal: добавить `"human_edit_detected"` |
| `claude_mnemos/core/staging.py` | `promote_to_vault(*, tracker=None)` — register paths through `tracker.writing()` |
| `claude_mnemos/core/snapshots.py` | `restore_from_snapshot(*, tracker=None)` — wrap in `tracker.paused()` |
| `claude_mnemos/daemon/process.py` | wire tracker/alerts/observer; start/stop hooks |
| `claude_mnemos/daemon/app.py` | include alerts router |
| `claude_mnemos/daemon/schemas.py` | extend `HealthResponse` with `alerts_count: int`, `watchdog_running: bool`; new `WatchdogAlertResponse` |
| `claude_mnemos/daemon/routes/health.py` | populate new HealthResponse fields |
| `claude_mnemos/core/undo.py` | pass `tracker` to `restore_from_snapshot` if daemon present (но undo runs in CLI process — daemon-side undo через REST уже инжектит) |
| `claude_mnemos/ingest/pipeline.py` | передать tracker (Plan #9: pipeline tracker остаётся None — CLI-only ingest) |
| `README.md` | watchdog section |

---

## Зависимости задач

```
Task 1: pyproject.toml — add watchdog dep
    ↓
Task 2: core/models.py — extend WikiPageFrontmatter
Task 3: state/activity.py — extend literal
    ↓
Task 4: core/page_io.py — read/serialize with extras
    ↓
Task 5: daemon/our_writes.py — OurWritesTracker
Task 6: daemon/alerts.py — Alerts + WatchdogAlert
    ↓
Task 7: core/staging.py — promote_to_vault(*, tracker=None)
Task 8: core/snapshots.py — restore_from_snapshot(*, tracker=None)
    ↓
Task 9: daemon/watchdog_handler.py — VaultChangeHandler
Task 10: daemon/watchdog_observer.py — VaultObserver
    ↓
Task 11: daemon/process.py — wire tracker/alerts/observer
Task 12: daemon/schemas.py + routes/health.py — extend health
Task 13: daemon/routes/alerts.py + app.py — REST endpoints
    ↓
Task 14: integration tests (in-process)
Task 15: slow E2E (subprocess daemon)
    ↓
Task 16: README + memory + merge
```

---

## Task 1: pyproject.toml — add watchdog dep

**Files modify:** `pyproject.toml`

- [ ] Add `"watchdog>=4.0"` to `dependencies`.
- [ ] Add `[[tool.mypy.overrides]] module = "watchdog.*" ignore_missing_imports = true`.
- [ ] `pip install -e ".[dev]"` (verify install OK).
- [ ] Run `pytest -q` — confirm baseline still green.
- [ ] Commit `chore(deps): add watchdog>=4.0 for Plan #9`

---

## Task 2: core/models.py — extend WikiPageFrontmatter

**Files modify:** `claude_mnemos/core/models.py`, `tests/test_models.py` (if exists)

- [ ] Add `last_human_edit: datetime | None = None` field after `agent_written`.
- [ ] Update tests: validate default None; validate with explicit datetime; serialize roundtrip preserves field.
- [ ] Verify existing 19 model tests still pass (no breaks — field is additive nullable).
- [ ] Run pytest + ruff + mypy.
- [ ] Commit `feat(core): WikiPageFrontmatter.last_human_edit field`

---

## Task 3: state/activity.py — extend ActivityOperationType

**Files modify:** `claude_mnemos/state/activity.py`, `tests/state/test_activity.py` (if exists, else create)

- [ ] Add `"human_edit_detected"` to literal.
- [ ] Test: ActivityEntry can be constructed with this op_type, can_undo=False, snapshot_path=None.
- [ ] Test: ActivityLog.append accepts the new entry.
- [ ] Run tests + ruff + mypy.
- [ ] Commit `feat(state): extend ActivityOperationType with human_edit_detected`

---

## Task 4: core/page_io.py — read+serialize with extras

**Files create:** `claude_mnemos/core/page_io.py`, `tests/core/test_page_io.py`

- [ ] Tests first:
  - `read_page` plain page (no extras) → frontmatter validates, body matches
  - `read_page` page with extras (`cssclass: foo`) → frontmatter validates, extras dict populated
  - `read_page` invalid YAML → PageParseError
  - `read_page` missing required field (e.g. no `title`) → PageParseError
  - `read_page` unknown field with same name as future field — preserved (no shadowing)
  - `serialize_page(read_page(p))` round-trips bytes-equal for known input (modulo YAML formatting normalization)
  - `serialize_page` after frontmatter mutation (`agent_written=False`) — extras preserved at end
- [ ] Implementation:
  - `_split_frontmatter(text)` — find leading `---\n...---\n`, parse YAML, return `(dict, body_str)`
  - `read_page(path)` — read text, split, partition by known schema keys, validate Pydantic (with `extra="forbid"`)
  - `serialize_page(parsed)` — serialize known fields first, append extras at end (preserving order from input via `extra_fm` dict)
  - `PageParseError(ValueError)` — wrap ValidationError + YAML errors
- [ ] Run tests + ruff + mypy.
- [ ] Commit `feat(core): page_io with extras-preserving round-trip`

---

## Task 5: daemon/our_writes.py — OurWritesTracker

**Files create:** `claude_mnemos/daemon/our_writes.py`, `tests/daemon/test_our_writes.py`

- [ ] Tests first:
  - `add` then `contains` returns True
  - `remove` makes `contains` return False
  - TTL: after `time.monotonic` advance > TTL, `contains` returns False (use monkeypatch)
  - `writing()` context manager adds on enter, removes on exit, removes even on exception
  - `paused()` makes `is_paused` True inside, False after; restores on exception
  - thread-safety smoke: 8 threads × 500 add/contains/remove for the same path — no exceptions, final state empty
- [ ] Implementation per design §3.2.
- [ ] Run tests + ruff + mypy.
- [ ] Commit `feat(daemon): OurWritesTracker with TTL+pause`

---

## Task 6: daemon/alerts.py — Alerts ring buffer

**Files create:** `claude_mnemos/daemon/alerts.py`, `tests/daemon/test_alerts.py`

- [ ] Tests first:
  - `add` returns alert with non-empty id
  - `list()` returns newest-first
  - 250 added → `list()` returns 200 (cap)
  - `clear(id)` returns True on hit, False on miss
  - thread-safety: 8 threads × 100 add — no exceptions, total <= 200
- [ ] Implementation per design §3.4.
- [ ] Run tests + ruff + mypy.
- [ ] Commit `feat(daemon): Alerts ring buffer with WatchdogAlert`

---

## Task 7: core/staging.py — promote_to_vault(*, tracker=None)

**Files modify:** `claude_mnemos/core/staging.py`, `tests/test_staging_extensions.py` (extend)

- [ ] Tests first:
  - `promote_to_vault(tracker=tracker)` — every staged target path is `contains` in tracker DURING the move (use a fake tracker that records add/remove order)
  - paths are removed from tracker after promote (or after exception)
  - `_to_move` source and dest both registered (suppress source DELETE event)
  - `_to_remove` paths registered
  - `tracker=None` → existing behavior unchanged (regression)
- [ ] Implementation per design §3.2 ("Integration with `StagingTransaction`").
- [ ] Run tests + ruff + mypy.
- [ ] Commit `feat(core): staging promote with optional our-writes tracker`

---

## Task 8: core/snapshots.py — restore_from_snapshot(*, tracker=None)

**Files modify:** `claude_mnemos/core/snapshots.py`, `tests/test_snapshots.py` (extend)

- [ ] Tests first:
  - `restore_from_snapshot(tracker=tracker)` — `tracker.is_paused` True during call (use a tracker spy that records timing)
  - paused state restored after success, after exception
  - `tracker=None` → existing behavior unchanged
- [ ] Implementation: wrap restore body in `tracker.paused() if tracker else nullcontext()`.
- [ ] Run tests + ruff + mypy.
- [ ] Commit `feat(core): snapshots restore with optional pause hook`

---

## Task 9: daemon/watchdog_handler.py — VaultChangeHandler

**Files create:** `claude_mnemos/daemon/watchdog_handler.py`, `tests/daemon/test_watchdog_handler.py`

- [ ] Tests first (use synthesized `FileModifiedEvent`/`FileCreatedEvent`/`FileMovedEvent` and tmp paths; no real Observer):
  - skip if event.is_directory
  - skip if path is dotfile-prefixed (`.staging/foo.md`, `wiki/.draft.md`)
  - skip if path is outside vault root
  - skip if path not under `wiki/`
  - skip if path is not `.md`
  - skip if `tracker.contains(path)` is True
  - skip if `tracker.is_paused`
  - on_modified valid markdown → frontmatter `agent_written=False`, `last_human_edit` set; activity entry appended
  - on_modified preserves Obsidian extras (`cssclass`)
  - on_modified ingest-recent (mtime < INGEST_FRESHNESS_S) → skip, no mutation
  - on_modified parse-fail → alert `parse_failed`, file unchanged
  - on_modified pipeline_lock timeout → alert `lock_timeout`
  - on_created → alert `external_create`, no mutation, no activity
  - on_moved → alert `external_rename`, no mutation, no activity
  - handler exception inside `_mark_human_edited` → alert `handler_error`, observer thread alive (no propagation)
  - tracker.add+remove called around the file write to prevent self-loop
- [ ] Implementation per design §3.3 ("`VaultChangeHandler`").
- [ ] Run tests + ruff + mypy.
- [ ] Commit `feat(daemon): VaultChangeHandler with self-write tracking`

---

## Task 10: daemon/watchdog_observer.py — VaultObserver

**Files create:** `claude_mnemos/daemon/watchdog_observer.py`

- [ ] No new test file — VaultObserver is a thin Observer wrapper, covered in integration tests (Task 14).
- [ ] Implementation per design §3.3 ("`VaultObserver`").
- [ ] Verify `mypy` passes (Observer is `Any` per stub).
- [ ] Commit `feat(daemon): VaultObserver wrapper`

---

## Task 11: daemon/process.py — wire tracker/alerts/observer

**Files modify:** `claude_mnemos/daemon/process.py`, `tests/daemon/test_process.py` (if exists)

- [ ] Add `tracker: OurWritesTracker` and `alerts: Alerts` to `MnemosDaemon.__init__`.
- [ ] Add `observer: VaultObserver | None = None` attribute.
- [ ] In `run()`: call `_start_observer()` after `write_pid_file`, before `scheduler.start()`. Wrap in try/except — if observer fails to start, log + alert, daemon continues without watchdog.
- [ ] In `run()` finally: call `_stop_observer()` before `scheduler.shutdown(wait=False)`.
- [ ] `_start_observer()` and `_stop_observer()` private methods.
- [ ] Tests:
  - daemon constructed → tracker and alerts non-None, observer None until run
  - observer start failure (mock VaultObserver.start to raise) → daemon still runs, alert added with kind="handler_error"
- [ ] Run tests + ruff + mypy.
- [ ] Commit `feat(daemon): wire watchdog observer with safe-start fallback`

---

## Task 12: daemon/schemas.py + routes/health.py — extend HealthResponse

**Files modify:** `claude_mnemos/daemon/schemas.py`, `claude_mnemos/daemon/routes/health.py`, `tests/daemon/test_app_health.py` (extend)

- [ ] `HealthResponse`: add `alerts_count: int = 0`, `watchdog_running: bool = False`.
- [ ] `routes/health.py`: read `daemon.alerts.list()` length and `daemon.observer is not None and observer._observer.is_alive()` (encapsulate `is_running` on VaultObserver).
- [ ] Add `VaultObserver.is_running` property to keep encapsulation.
- [ ] Tests:
  - daemon=None → both fields default
  - daemon with observer not started → watchdog_running=False
  - daemon with running observer → watchdog_running=True
  - alerts_count reflects current alerts list size
- [ ] Run tests + ruff + mypy.
- [ ] Commit `feat(daemon): /health exposes alerts_count + watchdog_running`

---

## Task 13: daemon/routes/alerts.py + app.py — REST endpoints

**Files create:** `claude_mnemos/daemon/routes/alerts.py`, `tests/daemon/test_app_alerts.py`
**Files modify:** `claude_mnemos/daemon/app.py`, `claude_mnemos/daemon/schemas.py`

- [ ] `WatchdogAlertResponse` schema in `daemon/schemas.py`: id, kind, path, message, detected_at.
- [ ] `routes/alerts.py`:
  - `GET /alerts` → list[WatchdogAlertResponse]
  - `DELETE /alerts/{id}` → 204 on success, 404 if not found
- [ ] Wire in `app.py`: include router.
- [ ] Tests:
  - GET empty → []
  - daemon.alerts.add(...) × 3 → GET returns 3 newest-first
  - DELETE existing → 204, GET returns 2
  - DELETE missing → 404
- [ ] Run tests + ruff + mypy.
- [ ] Commit `feat(daemon): /alerts REST endpoints`

---

## Task 14: integration tests (in-process)

**Files create:** `tests/daemon/test_watchdog_integration.py`

Real Observer on tmp dir, real handler, no subprocess.

- [ ] Test: external write to `wiki/entities/foo.md` → within 2s page is marked human_edited, activity entry appended.
- [ ] Test: write through `tracker.writing([path])` context — no mutation, no activity.
- [ ] Test: write to `.staging/foo.md` — no events that trigger handler (path skipped).
- [ ] Test: paused tracker — write `wiki/entities/bar.md` while paused, no mutation; resume, write again, mutation happens.
- [ ] Helper: `wait_for(predicate, timeout=2s, interval=0.05s)` for event polling.
- [ ] Run tests + ruff + mypy. Mark with `@pytest.mark.slow` if real watchdog Observer is slow on CI.
- [ ] Commit `test(daemon): watchdog integration with in-process Observer`

---

## Task 15: slow E2E (subprocess daemon)

**Files create:** `tests/daemon/test_watchdog_e2e.py`

Mirror existing `test_daemon_e2e.py` style.

- [ ] `@pytest.mark.slow`.
- [ ] Spin `mnemos daemon foreground --vault <tmpdir>` subprocess.
- [ ] Wait `/health` → 200, `watchdog_running=True`.
- [ ] Seed `wiki/entities/foo.md` with valid frontmatter (agent_written=True).
- [ ] Wait > INGEST_FRESHNESS_S to clear heuristic.
- [ ] External Python `Path.write_text(...)` modify foo.md (preserve frontmatter, change body).
- [ ] Poll `/activity?limit=5` until `human_edit_detected` for foo appears (timeout 5s).
- [ ] GET `/alerts` — expect empty (clean path).
- [ ] SIGINT, assert clean shutdown, runtime config cleaned up.
- [ ] Commit `test(daemon): slow E2E for watchdog real-time`

---

## Task 16: README + memory + merge

- [ ] README — new section "Watchdog real-time" describing detection rules, how to inspect `/alerts`, known limitations (concurrent CLI ingest false positives, no debouncing).
- [ ] Update memory: `claude_mnemos_project.md` — add "Что нового после Plan #9" section.
- [ ] PR commit message + non-FF merge to main per existing convention.
- [ ] Confirm full test suite passes (`pytest -q` + `pytest -q -m slow`).
- [ ] Commit `docs: README — Plans #1-#9 status + watchdog section`
- [ ] Merge: `git checkout main && git merge --no-ff feat/watchdog-realtime`

---

## Risks & rollback

- All commits sit on `feat/watchdog-realtime` branch. If integration breaks, branch is discardable; main untouched until merge.
- watchdog dep can be removed from `pyproject.toml` cleanly if needed.
- Activity literal extension is additive — old logs parse fine.
- `WikiPageFrontmatter.last_human_edit` is nullable — old pages without it parse fine (Pydantic default).
- Tracker pause is process-local — if daemon crashes mid-pause, no leftover state on disk.

---

## Definition of Done

- [ ] All 16 tasks committed on `feat/watchdog-realtime`.
- [ ] `pytest -q` green (~570 tests after additions).
- [ ] `pytest -q -m slow` green (4 slow tests after addition).
- [ ] `ruff check .` clean.
- [ ] `mypy claude_mnemos` clean.
- [ ] Manual smoke: start daemon, edit `wiki/entities/foo.md` in editor, verify activity entry + frontmatter mutation in <2s.
- [ ] README updated.
- [ ] Memory updated.
- [ ] Merged to `main` via non-FF commit.
