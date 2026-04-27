# Design: Watchdog real-time (Plan #9 — NEW)

**Status:** drafted, awaiting Yarik approval before implementation-plan generation.
**Date:** 2026-04-27
**Author:** Claude (with Yarik approval).
**Predecessor:** `2026-04-26-ontology-design.md` (Plan #8, merged in `bf5c9e9`).
**Successor planned:** Plan #10 (Lint) → Plan #11 (Jobs+Dead-letter) → Plan #12 (Page edit + Trash) → Plan #13 (Sessions+Settings+Metrics+Multi-vault+adaptive context) → Plan #14 (Dashboard).

---

## 1. Goal

Дать daemon'у глаза: **видеть external file changes в vault'е**, отличать «наши writes» от «human edits в Obsidian/IDE/etc.», и помечать вручную отредактированные страницы (`agent_written=False`, `last_human_edit=<ts>`).

Базис для всего, что зависит от знания «эта страница тронута человеком»:
- **Plan #10 (Lint):** `human_edited_overwritten` rule — предупреждать когда auto-fix перепишет ручную правку.
- **Plan #14 (Dashboard):** `human-edited` badge в Pages Browser, suggestions panel для revert/keep/merge.
- **Plan #11+ (HITL `force_overwrite`):** ingest pipeline спрашивает разрешение прежде чем перезаписать `agent_written=False` страницу.

После Plan #9:

```bash
# В одном терминале — daemon работает
mnemos daemon start --vault /path/to/vault

# В другом — открыли page в Obsidian, отредактировали, сохранили
echo "manual edit" >> /path/to/vault/wiki/entities/foo.md

# Через ~1s в activity log появляется новая запись
mnemos activity --limit 5
# Output:
# - human_edit_detected | wiki/entities/foo | <ts>
# - ingest_extracted    | ...
# ...

# В frontmatter foo.md:
# agent_written: false
# last_human_edit: 2026-04-27T14:23:11Z
```

### Что НЕ даёт (явно отложено)

- **Suggestions panel для conflicts** (Strict/Merge/Open mode UX) → Plan #14 (Dashboard) — backend помечает страницу, UX над этим — отдельная задача.
- **Ingest pipeline блокировка `agent_written=False` страниц** (`force_overwrite` HITL) → Plan #11+. В Plan #9 pipeline по-прежнему скипает по slug-collision; знание `agent_written=False` ещё нигде не reads'ится в pipeline.
- **Multi-vault watching** — Plan #13. В Plan #9 daemon наблюдает один vault (тот что в `DaemonConfig.vault_root`).
- **Persistent alerts log** — Plan #11+ (нужен dead-letter / persistent jobs). В Plan #9 alerts in-memory, теряются при restart daemon'а.
- **Alert silence/resolve UI** — Plan #11+. В Plan #9 только `GET /alerts` (read-only) и `DELETE /alerts/{id}` (clear из памяти).
- **Watchdog для Obsidian metadata files (`.obsidian/`, `.trash/`)** — skip'аются по dotfile-rule, как и наши internal directories.
- **Debouncing batch external changes** (один пользователь сохранил 50 файлов через replace-all) — пока handler обрабатывает каждый event by event. Реальный pain — Plan #11+.

---

## 2. Scope

### 2.1 In scope

| Компонент | Где |
|---|---|
| Расширение `WikiPageFrontmatter`: `last_human_edit: datetime \| None = None` | edit `core/models.py` |
| Расширение `ActivityOperationType` literal: `"human_edit_detected"` | edit `state/activity.py` |
| `OurWritesTracker` — thread-safe path set с TTL и pause-режимом | новый `daemon/our_writes.py` |
| `StagingTransaction.promote_to_vault` — register vault target paths в tracker до shutil.move | edit `core/staging.py` |
| `restore_from_snapshot` — pause tracker на время swap'а | edit `core/snapshots.py` (узкая интеграция) |
| `Alerts` — in-memory list of `WatchdogAlert(id, kind, path, message, detected_at)` | новый `daemon/alerts.py` |
| `VaultObserver` — wrapper над `watchdog.observers.Observer`, наблюдает vault root | новый `daemon/watchdog_observer.py` |
| `VaultChangeHandler` — `FileSystemEventHandler` подкласс, классифицирует events и пишет `human_edit_detected` activity | новый `daemon/watchdog_handler.py` |
| `MnemosDaemon` — держит `tracker`/`alerts`/`observer`, start/stop hooks | edit `daemon/process.py` |
| Daemon endpoints: `GET /alerts`, `DELETE /alerts/{id}` | новый `daemon/routes/alerts.py` + wiring в `app.py` |
| `core/page_io.py` — read+roundtrip page (frontmatter parse + body), preserving extra fields gracefully (Obsidian может добавить свои) | новый |
| `pyproject.toml` — `watchdog>=4.0` dependency | edit |
| Tests: tracker (thread-safety, TTL, pause), handler classification, page_io roundtrip, activity append, integration daemon+real-fs, slow E2E | новые в `tests/daemon/`, `tests/core/` |

### 2.2 Out of scope

| Component | План |
|---|---|
| Multi-vault: один daemon — несколько watcher'ов | Plan #13 |
| Persistent alerts (поверх state-файла) | Plan #11+ |
| Alerts silence/resolve / annotations | Plan #11+ |
| Suggestions panel (revert/keep/merge UX) | Plan #14 (Dashboard) |
| `force_overwrite` HITL: ingest спрашивает разрешение для `agent_written=False` | Plan #11+ |
| `human_edited_overwritten` lint rule | Plan #10 (Lint) |
| Debouncing batch changes (replace-all из IDE) | Plan #11+ |
| Watchdog conflict suggestions (создавать `.ontology-suggestions/` от watchdog handler'а) | Plan #11+ — пока только activity entry |
| Frontend `human-edited` badge | Plan #14 |
| Backfill `agent_written=False` для существующих manually-edited страниц | не делаем — поезд ушёл, marked будут только новые правки after Plan #9 |

---

## 3. Architecture

### 3.1 Data flow

```
                            ┌──────────────────────┐
                            │  Filesystem event    │
                            │  (modified, created, │
                            │   moved, deleted)    │
                            └──────────┬───────────┘
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │  watchdog Observer   │
                            │  (background thread) │
                            └──────────┬───────────┘
                                       │ dispatch
                                       ▼
                            ┌──────────────────────┐
                            │ VaultChangeHandler   │
                            │  on_modified/created │
                            └──────────┬───────────┘
                                       │
                       ┌───────────────┼─────────────────┐
                       ▼               ▼                 ▼
              skip if dotfile   skip if path in    skip if observer
              (.staging/, etc.) tracker.our_writes paused (snapshot
                                                   restore in flight)
                       │               │                 │
                       └───────────────┼─────────────────┘
                                       │ external change
                                       ▼
                            ┌──────────────────────┐
                            │ _mark_human_edited   │
                            │ ─ acquire pipeline   │
                            │   lock (timeout 5s)  │
                            │ ─ load page          │
                            │ ─ mutate frontmatter │
                            │ ─ tracker.add(path)  │
                            │ ─ atomic_write back  │
                            │ ─ tracker.remove     │
                            │ ─ append activity    │
                            └──────────────────────┘
                                       │
                                       │ on any exception
                                       ▼
                            ┌──────────────────────┐
                            │ alerts.add(          │
                            │   WatchdogAlert(...))│
                            │ logger.exception(...)│
                            └──────────────────────┘
```

### 3.2 Self-write tracking — `OurWritesTracker`

```python
# daemon/our_writes.py

@dataclass(frozen=True)
class _Entry:
    path: Path  # absolute, resolved
    expires_at: float  # monotonic deadline


class OurWritesTracker:
    """Thread-safe set of paths the daemon is currently writing.

    Why TTL: watchdog events can arrive with delay (OS buffering). After we add
    a path before shutil.move and remove after fsync, the corresponding event
    may still be in-flight. TTL gives the event a window to be matched against
    the set.

    Why pause: bulk operations like restore_from_snapshot create dozens of CREATE
    events that we cannot enumerate path-by-path beforehand. Pause flag tells the
    handler to ignore everything until the bulk op finishes.
    """

    DEFAULT_TTL_S = 5.0

    def __init__(self, ttl_s: float = DEFAULT_TTL_S) -> None:
        self._entries: dict[Path, float] = {}
        self._lock = threading.Lock()
        self._paused = False
        self._ttl_s = ttl_s

    def add(self, path: Path, *, ttl_s: float | None = None) -> None:
        ttl = ttl_s if ttl_s is not None else self._ttl_s
        with self._lock:
            self._entries[path.resolve()] = time.monotonic() + ttl
            self._gc_locked()

    def remove(self, path: Path) -> None:
        with self._lock:
            self._entries.pop(path.resolve(), None)

    def contains(self, path: Path) -> bool:
        with self._lock:
            self._gc_locked()
            return path.resolve() in self._entries

    @contextmanager
    def writing(self, paths: Iterable[Path]):
        """Add paths on enter, remove on exit. Use around shutil.move loops."""
        normalized = [p.resolve() for p in paths]
        for p in normalized:
            self.add(p)
        try:
            yield
        finally:
            for p in normalized:
                self.remove(p)

    @contextmanager
    def paused(self):
        """Skip all events while inside. Use around restore_from_snapshot."""
        with self._lock:
            self._paused = True
        try:
            yield
        finally:
            with self._lock:
                self._paused = False

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def _gc_locked(self) -> None:
        now = time.monotonic()
        expired = [p for p, exp in self._entries.items() if exp < now]
        for p in expired:
            del self._entries[p]
```

**Integration with `StagingTransaction`:**

```python
# core/staging.py — extension
def promote_to_vault(self, *, tracker: OurWritesTracker | None = None) -> PromoteResult:
    ...
    # 2. Move staged files into vault — register paths with tracker first
    targets: list[Path] = [
        self.vault / staged.relative_to(self.staging_dir)
        for staged in self.staging_dir.rglob("*") if staged.is_file()
    ]
    # ontology moves and deletes target additional paths
    targets.extend(self.vault / dst for _, dst in self._to_move)
    # we need to track *destination* paths; sources of moves and deletes
    # are inside vault already and don't trigger CREATE — but we still want
    # to suppress the synthetic 'deleted' event watchdog might emit
    targets.extend(self.vault / src for src, _ in self._to_move)
    targets.extend(self.vault / rel for rel, _ in self._to_remove)

    cm = tracker.writing(targets) if tracker is not None else nullcontext()
    with cm:
        try:
            for staged in ...:
                shutil.move(...)
            self._apply_moves()
            self._apply_deletes()
        except Exception as exc:
            ...
```

**Integration with `restore_from_snapshot`:**

```python
# core/snapshots.py — узкая правка
def restore_from_snapshot(
    vault: Path,
    snapshot: Path,
    *,
    tracker: OurWritesTracker | None = None,
) -> RestoreResult:
    cm = tracker.paused() if tracker is not None else nullcontext()
    with cm:
        # ... existing restore logic ...
```

**Where tracker lives:** на `MnemosDaemon` instance. Pipeline (CLI `mnemos ingest`) **не знает** про daemon — но если daemon работает рядом, его watcher увидит CREATE events от ingest'а. Решение:

- В Plan #9 daemon-side: tracker — атрибут `MnemosDaemon`. CLI ingest пишет vault напрямую через staging без knowledge о tracker'е.
- **Ingest CLI и watcher'у нужно общаться о self-writes.** Sharing-mechanism: filelock-coordinated **on-disk hint file** `.our-writes.json` или **in-process только** (нужен pipeline через daemon).
- **Решение Plan #9:** **in-process only.** Если daemon видит external CREATE от concurrent CLI ingest — handler детектирует это как human edit и помечает страницу. **Это false positive.** Чтобы избежать — pipeline_lock уже сериализует ingest, но daemon его не держит.
  - **Mitigation:** handler перед обработкой делает `pipeline_lock(timeout=10s)` — если ingest именно сейчас идёт, handler ждёт окончания. После окончания страница уже в vault (CREATE event прилетел в очередь handler'а), handler читает её и видит valid frontmatter с `agent_written=True` → mutates на False ❌ — false positive.
  - **Compromise:** handler **проверяет `agent_written` в frontmatter после load**. Если уже `True` и `last_human_edit is None` и timestamp создания файла свежий (< 10s) — это вероятно ingest write, **skip**. Это эвристика, не идеальная, но безопасная (false negative > false positive).
  - **Чище решение:** все ingest writes идут через daemon (Plan #11+, daemon-as-orchestrator). Тогда tracker в process'е daemon'а покрывает всё.
  - **В Plan #9 принимаем:** если CLI ingest запущен параллельно с daemon, possible false positive `human_edit_detected` на свежесозданных pages. Документируем как known limitation. Yarik в обычном flow всё равно auto-ingest → SessionEnd hook spawns CLI → не concurrent с user editing.

### 3.3 `VaultObserver` и `VaultChangeHandler`

```python
# daemon/watchdog_observer.py

class VaultObserver:
    def __init__(
        self,
        vault: Path,
        handler: VaultChangeHandler,
    ) -> None:
        self.vault = vault
        self.handler = handler
        self._observer = watchdog.observers.Observer()

    def start(self) -> None:
        self._observer.schedule(self.handler, str(self.vault), recursive=True)
        self._observer.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        self._observer.stop()
        self._observer.join(timeout=timeout)
```

```python
# daemon/watchdog_handler.py

class VaultChangeHandler(FileSystemEventHandler):
    def __init__(
        self,
        vault: Path,
        tracker: OurWritesTracker,
        alerts: Alerts,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.vault = vault.resolve()
        self.tracker = tracker
        self.alerts = alerts
        self.clock = clock

    def on_created(self, event: FileSystemEvent) -> None:
        # Newly-created page from external editor (Obsidian "new note") —
        # we don't have prior frontmatter to mutate. Log alert with hint to
        # ingest manually. No activity entry (it would imply we changed
        # something, but we did nothing).
        self._handle(event, is_new=True)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event, is_new=False)

    def on_moved(self, event: FileSystemMovedEvent) -> None:
        # External rename — log alert, don't try to follow.
        if event.is_directory:
            return
        try:
            self._maybe_alert_external_move(event)
        except Exception as exc:
            self._record_handler_failure(event.dest_path, exc)

    def _handle(self, event: FileSystemEvent, *, is_new: bool) -> None:
        try:
            if event.is_directory:
                return
            if self.tracker.is_paused:
                return
            path = Path(event.src_path).resolve()
            if not self._is_watched(path):
                return
            if self.tracker.contains(path):
                return
            if is_new:
                self.alerts.add(WatchdogAlert(
                    kind="external_create",
                    path=str(path),
                    message="External create detected — ingest manually if needed",
                    detected_at=self.clock(),
                ))
                return
            self._mark_human_edited(path)
        except Exception as exc:
            self._record_handler_failure(event.src_path, exc)

    def _is_watched(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.vault)
        except ValueError:
            return False
        # Skip dotfile branches — .staging/, .backups/, .trash/, .ontology-suggestions/, .obsidian/, .git/, etc.
        if any(p.startswith(".") for p in rel.parts):
            return False
        # Only mark .md files under wiki/ — raw/ is recordings, not editable.
        if rel.parts[:1] != ("wiki",):
            return False
        if path.suffix != ".md":
            return False
        return True

    def _mark_human_edited(self, path: Path) -> None:
        # Acquire pipeline_lock so we don't race ingest. If busy, just alert.
        # NOTE 2026-04-27: the mtime-based ingest-freshness heuristic that was
        # originally documented here was REMOVED in commit 7641e2d. write_text
        # on a real human edit also bumps mtime, so the heuristic blocked
        # legitimate edits — it was a false-friend, not a true filter for ingest
        # writes. Concurrent CLI ingest false-positive remains a documented
        # known limitation, closed in Plan #11+ (daemon-as-orchestrator).
        try:
            with pipeline_lock(self.vault, timeout=5.0):
                page = read_page(path)
                new_fm = page.frontmatter.model_copy(update={
                    "agent_written": False,
                    "last_human_edit": self.clock(),
                })
                new_page = replace_frontmatter(page, new_fm)
                self.tracker.add(path)
                try:
                    atomic_write(path, new_page.serialize())
                finally:
                    self.tracker.remove(path)
                self._append_activity(path)
        except LockTimeoutError:
            self.alerts.add(WatchdogAlert(
                kind="lock_timeout",
                path=str(path),
                message="Could not acquire pipeline_lock to mark human edit; skipped",
                detected_at=self.clock(),
            ))
        except (PageParseError, FrontmatterValidationError) as exc:
            self.alerts.add(WatchdogAlert(
                kind="parse_failed",
                path=str(path),
                message=f"Frontmatter invalid after edit: {exc}",
                detected_at=self.clock(),
            ))

    def _append_activity(self, path: Path) -> None:
        rel = path.relative_to(self.vault).as_posix()
        log = ActivityLog.load(self.vault)
        entry = ActivityEntry(
            id=uuid4().hex,
            timestamp=self.clock(),
            operation_type="human_edit_detected",
            status="success",
            snapshot_path=None,
            can_undo=False,
            affected_pages=[rel],
            metadata={"detected_at": self.clock().isoformat()},
        )
        log.append(entry)
        self.tracker.add(self.vault / ".activity.json")
        try:
            log.save(self.vault)
        finally:
            self.tracker.remove(self.vault / ".activity.json")

    def _record_handler_failure(self, raw_path: str | None, exc: Exception) -> None:
        logger.exception("watchdog handler failed for %s", raw_path)
        self.alerts.add(WatchdogAlert(
            kind="handler_error",
            path=str(raw_path) if raw_path else "",
            message=str(exc),
            detected_at=self.clock(),
        ))
```

### 3.4 `Alerts`

```python
# daemon/alerts.py

@dataclass(frozen=True)
class WatchdogAlert:
    id: str
    kind: Literal[
        "external_create", "external_rename", "lock_timeout",
        "parse_failed", "handler_error",
    ]
    path: str
    message: str
    detected_at: datetime

class Alerts:
    """In-memory ring buffer (keep last N=200)."""

    MAX = 200

    def __init__(self) -> None:
        self._items: deque[WatchdogAlert] = deque(maxlen=self.MAX)
        self._lock = threading.Lock()

    def add(self, kind, path, message, detected_at) -> WatchdogAlert:
        alert = WatchdogAlert(uuid4().hex, kind, path, message, detected_at)
        with self._lock:
            self._items.appendleft(alert)
        return alert

    def list(self) -> list[WatchdogAlert]:
        with self._lock:
            return list(self._items)

    def clear(self, alert_id: str) -> bool:
        with self._lock:
            for i, a in enumerate(self._items):
                if a.id == alert_id:
                    del self._items[i]
                    return True
        return False
```

### 3.5 `core/page_io.py`

Существующий `WikiPage.serialize()` мы используем для **agent writes**. Для round-trip (read → mutate → write) нужно:
- читать существующий markdown из vault
- парсить frontmatter (YAML)
- получить `WikiPageFrontmatter` (Pydantic) — с `extra="forbid"`
- если YAML содержит поля **за пределами** schema (Obsidian мог добавить `cssclass`, `obsidianUIMode` и т.п.) — **не падать**, но **сохранять** unknown keys для round-trip.

Two options:
**A. Strict:** schema reject extras → handler выкидывает alert, не трогает страницу. **Плюс:** safe. **Минус:** реалистичный Obsidian add'ит extras → каждое сохранение в Obsidian = alert, никогда не помечается.

**B. Round-trip preserving extras:** parse frontmatter в **two slots** — known fields в Pydantic, unknown в `extra_fm: dict`. На write — merge back.

**Решение Plan #9: B.** Делаем параллельную читалку (отдельно от existing `WikiPage`) с round-trip extras:

```python
# core/page_io.py

class PageParseError(ValueError):
    pass

@dataclass(frozen=True)
class ParsedPage:
    """Round-trippable page. `extra_fm` carries unknown YAML keys verbatim."""

    frontmatter: WikiPageFrontmatter
    extra_fm: dict[str, Any]
    body: str

def read_page(path: Path) -> ParsedPage:
    text = path.read_text(encoding="utf-8")
    fm_dict, body = _split_frontmatter(text)
    known_keys = set(WikiPageFrontmatter.model_fields)
    known = {k: v for k, v in fm_dict.items() if k in known_keys}
    extras = {k: v for k, v in fm_dict.items() if k not in known_keys}
    try:
        fm = WikiPageFrontmatter.model_validate(known)
    except ValidationError as exc:
        raise PageParseError(f"frontmatter invalid: {exc}") from exc
    return ParsedPage(frontmatter=fm, extra_fm=extras, body=body)

def serialize_page(parsed: ParsedPage) -> str:
    fm_dict = {
        **parsed.frontmatter.model_dump(mode="json", exclude_defaults=False),
        **parsed.extra_fm,  # unknown keys preserved at the end
    }
    yaml_block = yaml.safe_dump(fm_dict, sort_keys=False, allow_unicode=True)
    return f"---\n{yaml_block}---\n{parsed.body.rstrip(chr(10))}\n"
```

Существующий `WikiPage.serialize()` остаётся as-is для ingest (он не имеет extras, всегда новая страница). `core/page_io.read_page` — for daemon round-trip.

Open question: Pydantic `extra="forbid"` для `WikiPageFrontmatter` остаётся — это контракт с ingest (LLM никогда не пишет extras). Парсилка `read_page` обходит контракт через manual filter known/unknown — это явный compromise, документируем в docstring.

### 3.6 Wiring в `MnemosDaemon`

```python
class MnemosDaemon:
    def __init__(self, config: DaemonConfig) -> None:
        self.config = config
        self.tracker = OurWritesTracker()
        self.alerts = Alerts()
        self.scheduler = build_scheduler(...)
        self.app = create_app(config.vault_root, daemon=self)
        self.observer: VaultObserver | None = None
        ...

    async def run(self) -> None:
        write_pid_file(...)
        try:
            self._start_observer()
            self.scheduler.start()
            ...
        finally:
            self._stop_observer()
            self.scheduler.shutdown(wait=False)
            cleanup_pid_file(...)

    def _start_observer(self) -> None:
        handler = VaultChangeHandler(self.config.vault_root, self.tracker, self.alerts)
        self.observer = VaultObserver(self.config.vault_root, handler)
        self.observer.start()

    def _stop_observer(self) -> None:
        if self.observer is not None:
            try:
                self.observer.stop()
            except Exception:
                logger.exception("observer stop failed")
```

### 3.7 REST API

```
GET    /alerts                      → list of WatchdogAlert (newest first, max 200)
DELETE /alerts/{id}                 → clear single alert; 404 if not found
```

`HealthResponse` добавляет `alerts_count: int` и `watchdog_running: bool` — frontend сможет показать red dot.

### 3.8 Activity entry

```python
ActivityEntry(
    id=uuid4().hex,
    timestamp=now,
    operation_type="human_edit_detected",
    status="success",
    snapshot_path=None,
    can_undo=False,                          # we don't snapshot; can't undo a human edit
    affected_pages=["wiki/entities/foo.md"],
    metadata={"detected_at": ts.isoformat()},
)
```

`ActivityLog.append` уже валидирует chronological order и unique id — handler пишет под `pipeline_lock`, который сериализует с ingest'ом, поэтому order гарантирован.

### 3.9 CLI exit codes

Plan #9 не добавляет новые CLI exit codes — handler работает только в daemon'е. Из CLI нет новых subcommands.

---

## 4. Test strategy

### 4.1 Unit

- `tests/daemon/test_our_writes.py`:
  - add/contains/remove
  - TTL expiration
  - thread-safety smoke (10 threads × 1000 add/contains)
  - paused() context — все contains() return False внутри

- `tests/daemon/test_alerts.py`:
  - add → list newest-first
  - ring buffer cap 200
  - clear by id; 404 path

- `tests/core/test_page_io.py`:
  - round-trip plain page
  - round-trip page with Obsidian extras (`cssclass: foo`) — extras preserved
  - PageParseError on invalid YAML
  - PageParseError on missing required frontmatter fields

- `tests/daemon/test_watchdog_handler.py`:
  - skip dotfiles (`.staging/foo.md`, `.backups/...`)
  - skip non-md (raw/chats/foo.txt)
  - skip raw/ even if .md
  - skip if tracker.contains
  - skip if tracker.is_paused
  - on_modified valid markdown → frontmatter.agent_written=False, last_human_edit set
  - on_modified extras preserved
  - on_modified ingest-recent file → skip (heuristic)
  - on_modified parse-fail → alert, file unchanged
  - on_created → alert (no mutation)
  - on_moved → alert (no follow)
  - handler exception → alert, observer thread alive (no propagation)

### 4.2 Integration (in-process)

- `tests/daemon/test_watchdog_integration.py`:
  - Spin up VaultObserver на временной директории
  - Write `wiki/entities/foo.md` через external open() → событие, через `wait_for(condition, timeout=2s)` проверить что страница помечена
  - Write `.staging/foo.md` → no mutation, no activity
  - Write через `tracker.writing([path])` context — no mutation, no activity
  - Run `restore_from_snapshot` через `tracker.paused()` — на десятки CREATE events handler не реагирует

### 4.3 E2E (slow, marker `@pytest.mark.slow`)

- `tests/daemon/test_watchdog_e2e.py`:
  - Subprocess `mnemos daemon foreground --vault <tmpdir>` (как существующий daemon e2e)
  - Wait /health
  - Write external `wiki/entities/foo.md` через regular Python open()
  - Polling /activity until human_edit_detected entry; timeout 5s
  - GET /alerts — empty (нормальный path)
  - SIGINT; assert clean shutdown

---

## 5. Open questions

| # | Q | Решение |
|---|---|---|
| Q1 | Tracker — process-local или filelock-coordinated с CLI ingest'ом? | Process-local в Plan #9. False positives документируем; daemon-as-orchestrator закроет в Plan #11+. |
| Q2 | Heuristic «ingest-recent» (mtime < 10s) — magic number? | Да, magic. Альтернатива — manifest lookup (если path в `.manifest.json` с `ingested_at < 10s` — skip). Дороже на каждом event. Магию принимаем, документируем константу `INGEST_FRESHNESS_S = 10.0`. |
| Q3 | Что делать на parse_failed (Obsidian rendered страницу с broken YAML)? | Alert, **не** mutating file. Юзер фиксит вручную. |
| Q4 | watchdog Observer на Windows работает через ReadDirectoryChangesW — может пропускать events при overflow buffer'а. Reliable? | Принимаем. Plan #11+ может добавить периодический rescan для compensation. |
| Q5 | Может ли pipeline_lock из handler thread'а deadlock с asyncio loop'ом? | filelock — process-level, не thread-level. Handler в worker thread держит lock на short window (parse + write), asyncio loop ничего не ждёт. OK. |
| Q6 | extra_fm в `core/page_io.py` дублирует контракт `WikiPageFrontmatter`. Не лучше ли поменять model_config = "allow"? | Нет: ingest pipeline должен оставаться strict (LLM не имеет права писать extras). Round-trip — отдельный use case. |
| Q7 | Нужен ли `alerts_count` в /health сразу? | Да — fronted в Plan #14 будет polling /health, дешевле чем GET /alerts каждые N секунд. |

---

## 6. Migration / compatibility

- Plan #9 добавляет два nullable поля во frontmatter (`last_human_edit`) — old pages без поля парсятся (default None).
- `ActivityOperationType` literal расширяется — старые activity logs не ломаются (JSON literal — open enum при парсинге).
- watchdog dependency добавляется — `pip install -e ".[dev]"` reinstall'ит. Wheel rebuild.
- Daemon без watchdog (если import упал) → `_start_observer` ловит exception, alerts.add(handler_error), daemon продолжает (scheduler+REST живы).

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| watchdog буферный overflow (тысячи writes за секунду) | beyond Plan #9; не ожидаем такого load'а |
| Obsidian rapid save (modified → modified → modified) → 3 activity entries | Acceptable (каждый mark подтверждает). Debouncing — Plan #11+. |
| concurrent CLI ingest триггерит false positive | heuristic INGEST_FRESHNESS_S; документированная limitation |
| handler thread помрёт из-за uncaught exception | top-level try/except в `_handle` ловит всё; logger + alert |
| `.activity.json` race между handler и ingest pipeline | `pipeline_lock` сериализует |
| paused tracker stuck if exception inside paused() | contextmanager finally restores |
| Windows `os.replace` race с watchdog event'ами | TTL дает window 5s, достаточно для antivirus delays |

---

## 8. Estimated diff

- New files: 7 (`daemon/our_writes.py`, `daemon/alerts.py`, `daemon/watchdog_observer.py`, `daemon/watchdog_handler.py`, `daemon/routes/alerts.py`, `core/page_io.py`, plus 5 tests files)
- Modified files: 6 (`core/models.py`, `state/activity.py`, `core/staging.py`, `core/snapshots.py`, `daemon/process.py`, `daemon/app.py`, `daemon/schemas.py`, `pyproject.toml`)
- LOC estimate: ~1100 prod + ~900 tests
- Branch: `feat/watchdog-realtime`
- Expected commits: ~10 (deps → models/activity literal → page_io → tracker+alerts → handler+observer → staging integration → snapshot integration → daemon wiring → routes → smoke+README+memory)
