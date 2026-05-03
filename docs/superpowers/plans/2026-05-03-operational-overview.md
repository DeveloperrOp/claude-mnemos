# Operational Overview Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать новую главную страницу дашборда mnemos (KpiBar + RunningJobsLive + ActiveSessionsLive + HealthDot) и backend infrastructure для live-tracking активных сессий + 24h auto-dump страховки.

**Architecture:** Один общий transcript-scanner с TTL-cache (anti-stampede через inflight future). Active-sessions и lost-sessions — две projection'а на один сырой результат. Auto-dump через APScheduler global cron с catch-up после bootstrap. REST aggregator-endpoint `/api/dashboard/snapshot` с per-aggregator try/except fallback. Frontend — React Query polling 10s, локальный setInterval для countdown, переиспользует существующие useHealth/useAlerts.

**Tech Stack:** Python 3.12 + FastAPI + APScheduler + Pydantic v2 + pytest + asyncio. React 19 + TypeScript + Tailwind v4 + shadcn/ui + React Query + Zod + Vitest + i18next.

**Spec:** `docs/superpowers/specs/2026-05-03-operational-overview-design.md`

---

## File Structure

### New backend files
- `claude_mnemos/core/ttl_cache.py` — generic `TTLCache[T]` with asyncio.Lock + inflight future
- `claude_mnemos/core/transcript_scanner.py` — `scan_transcripts()` returns `list[TranscriptEntry]`
- `claude_mnemos/core/active_sessions.py` — `ActiveSession` model, `scan_active_sessions()`
- `claude_mnemos/core/auto_dump.py` — `auto_dump_stale()`
- `claude_mnemos/daemon/routes/dashboard.py` — `/api/dashboard/*` endpoints

### Modified backend files
- `claude_mnemos/core/lost_sessions.py` — refactor `scan_lost_sessions` to use shared scanner (zero behavior change)
- `claude_mnemos/daemon/process.py` — register cron `auto_dump_global` + catch-up after bootstrap
- `claude_mnemos/daemon/app.py` — include `dashboard` router

### New backend tests
- `tests/core/test_ttl_cache.py`
- `tests/core/test_transcript_scanner.py`
- `tests/core/test_active_sessions.py`
- `tests/core/test_auto_dump.py`
- `tests/daemon/test_app_dashboard.py`

### New frontend files
- `frontend/src/types/ActiveSession.ts`
- `frontend/src/api/dashboard.api.ts`
- `frontend/src/hooks/dashboard/useDashboardSnapshot.ts`
- `frontend/src/hooks/dashboard/useDumpNow.ts`
- `frontend/src/hooks/dashboard/useScanActive.ts`
- `frontend/src/components/widgets/dashboard/KpiBar.tsx`
- `frontend/src/components/widgets/dashboard/RunningJobsLive.tsx`
- `frontend/src/components/widgets/dashboard/ActiveSessionsLive.tsx`
- `frontend/src/components/widgets/dashboard/HealthDot.tsx`

### Modified frontend files
- `frontend/src/pages/Overview.tsx` — full rewrite
- `frontend/public/locales/en.json` — new keys (uk/ru deferred to v2)

### New frontend tests
- `frontend/src/__tests__/api-dashboard.test.ts`
- `frontend/src/__tests__/widgets/KpiBar.test.tsx`
- `frontend/src/__tests__/widgets/RunningJobsLive.test.tsx`
- `frontend/src/__tests__/widgets/ActiveSessionsLive.test.tsx`
- `frontend/src/__tests__/widgets/HealthDot.test.tsx`
- `frontend/src/__tests__/Overview.test.tsx`

---

## Phase 1: Backend Foundation (TTL Cache + Common Scanner)

### Task 1: TTLCache generic with asyncio lock + inflight future

**Files:**
- Create: `claude_mnemos/core/ttl_cache.py`
- Test: `tests/core/test_ttl_cache.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_ttl_cache.py
"""Tests for claude_mnemos.core.ttl_cache."""

from __future__ import annotations

import asyncio

import pytest

from claude_mnemos.core.ttl_cache import TTLCache


@pytest.mark.asyncio
async def test_get_or_compute_caches_first_result() -> None:
    cache: TTLCache[int] = TTLCache(ttl_s=60.0)
    calls = 0

    async def compute() -> int:
        nonlocal calls
        calls += 1
        return 42

    assert await cache.get_or_compute(compute) == 42
    assert await cache.get_or_compute(compute) == 42
    assert calls == 1


@pytest.mark.asyncio
async def test_get_or_compute_recomputes_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    cache: TTLCache[int] = TTLCache(ttl_s=10.0)
    now = [0.0]
    monkeypatch.setattr(
        "claude_mnemos.core.ttl_cache.time.monotonic", lambda: now[0]
    )
    calls = 0

    async def compute() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await cache.get_or_compute(compute) == 1
    now[0] = 5.0
    assert await cache.get_or_compute(compute) == 1
    now[0] = 11.0
    assert await cache.get_or_compute(compute) == 2


@pytest.mark.asyncio
async def test_invalidate_forces_recompute() -> None:
    cache: TTLCache[int] = TTLCache(ttl_s=60.0)
    calls = 0

    async def compute() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await cache.get_or_compute(compute) == 1
    cache.invalidate()
    assert await cache.get_or_compute(compute) == 2


@pytest.mark.asyncio
async def test_concurrent_callers_share_inflight_future() -> None:
    """Three concurrent get_or_compute() calls must share ONE compute() invocation."""
    cache: TTLCache[int] = TTLCache(ttl_s=60.0)
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def compute() -> int:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return 7

    task1 = asyncio.create_task(cache.get_or_compute(compute))
    await started.wait()
    task2 = asyncio.create_task(cache.get_or_compute(compute))
    task3 = asyncio.create_task(cache.get_or_compute(compute))
    release.set()
    results = await asyncio.gather(task1, task2, task3)
    assert results == [7, 7, 7]
    assert calls == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_ttl_cache.py -v`
Expected: ImportError — `claude_mnemos.core.ttl_cache` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# claude_mnemos/core/ttl_cache.py
"""Generic TTL cache with anti-stampede inflight-future pattern."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Async TTL cache that shares a single in-flight computation.

    Concurrent get_or_compute() calls during stale state share the same
    asyncio.Future — never spawn N parallel computations.
    """

    def __init__(self, ttl_s: float) -> None:
        self._ttl_s = ttl_s
        self._items: T | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()
        self._inflight: asyncio.Future[T] | None = None

    async def get_or_compute(self, fn: Callable[[], Awaitable[T]]) -> T:
        if self._items is not None and time.monotonic() < self._expires_at:
            return self._items
        async with self._lock:
            if self._items is not None and time.monotonic() < self._expires_at:
                return self._items
            if self._inflight is not None:
                inflight = self._inflight
            else:
                self._inflight = asyncio.get_event_loop().create_future()
                inflight = self._inflight
                will_compute = True
            if "will_compute" not in dir():
                will_compute = False
        if not will_compute:
            return await inflight
        try:
            result = await fn()
        except BaseException as exc:
            self._inflight.set_exception(exc)
            self._inflight = None
            raise
        self._items = result
        self._expires_at = time.monotonic() + self._ttl_s
        self._inflight.set_result(result)
        self._inflight = None
        return result

    def invalidate(self) -> None:
        self._items = None
        self._expires_at = 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_ttl_cache.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/ttl_cache.py tests/core/test_ttl_cache.py
git commit -m "feat(core): generic TTLCache with asyncio anti-stampede inflight future"
```

---

### Task 2: TranscriptEntry model + scan_transcripts()

**Files:**
- Create: `claude_mnemos/core/transcript_scanner.py`
- Test: `tests/core/test_transcript_scanner.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_transcript_scanner.py
"""Tests for claude_mnemos.core.transcript_scanner."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.core.transcript_scanner import (
    TranscriptEntry,
    scan_transcripts,
)


def _write_jsonl(
    root: Path, name: str, payload: dict[str, object] | None = None
) -> tuple[Path, str]:
    content = json.dumps(payload or {"sid": name}).encode("utf-8")
    p = root / f"{name}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p, hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_scan_empty_root_returns_empty(tmp_path: Path) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    out = await scan_transcripts(transcripts_root=root)
    assert out == []


@pytest.mark.asyncio
async def test_scan_returns_one_entry_per_jsonl(tmp_path: Path) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    _write_jsonl(root, "a")
    _write_jsonl(root, "b")
    out = await scan_transcripts(transcripts_root=root)
    assert {e.session_id for e in out} == {"a", "b"}
    for e in out:
        assert isinstance(e, TranscriptEntry)
        assert isinstance(e.mtime, datetime)
        assert e.mtime.tzinfo == UTC
        assert e.size_bytes > 0


@pytest.mark.asyncio
async def test_scan_extracts_cwd_from_first_event(tmp_path: Path) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    _write_jsonl(root, "with-cwd", {"cwd": "D:\\code\\foo", "type": "user"})
    out = await scan_transcripts(transcripts_root=root)
    assert len(out) == 1
    assert out[0].cwd == "D:\\code\\foo"


@pytest.mark.asyncio
async def test_scan_skips_non_jsonl_files(tmp_path: Path) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    (root / "ignore.txt").write_text("hi", encoding="utf-8")
    _write_jsonl(root, "real")
    out = await scan_transcripts(transcripts_root=root)
    assert {e.session_id for e in out} == {"real"}


@pytest.mark.asyncio
async def test_scan_recursive(tmp_path: Path) -> None:
    root = tmp_path / "transcripts"
    nested = root / "project-1"
    nested.mkdir(parents=True)
    _write_jsonl(nested, "nested-sess")
    out = await scan_transcripts(transcripts_root=root)
    assert {e.session_id for e in out} == {"nested-sess"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_transcript_scanner.py -v`
Expected: ImportError.

- [ ] **Step 3: Write implementation**

```python
# claude_mnemos/core/transcript_scanner.py
"""Single source-of-truth scanner for ~/.claude/projects/*.jsonl.

Both core.lost_sessions and core.active_sessions consume the result of
scan_transcripts(); this avoids duplicate disk IO and SHA-256 of the
same files.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from claude_mnemos.core.lost_sessions import (
    _extract_cwd_and_preview,
    _resolve_transcripts_root,
)


class TranscriptEntry(BaseModel):
    session_id: str
    transcript_path: str
    sha: str
    size_bytes: int
    mtime: datetime
    cwd: str | None = None
    preview: str | None = None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan_sync(transcripts_root: Path | None) -> list[TranscriptEntry]:
    root = _resolve_transcripts_root(transcripts_root)
    if not root.is_dir():
        return []
    out: list[TranscriptEntry] = []
    for path in root.rglob("*.jsonl"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            sha = _sha256_file(path)
        except OSError:
            continue
        cwd, preview = _extract_cwd_and_preview(path)
        out.append(
            TranscriptEntry(
                session_id=path.stem,
                transcript_path=str(path.resolve()),
                sha=sha,
                size_bytes=stat.st_size,
                mtime=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                cwd=cwd,
                preview=preview,
            )
        )
    out.sort(key=lambda e: e.mtime, reverse=True)
    return out


async def scan_transcripts(
    *, transcripts_root: Path | None = None
) -> list[TranscriptEntry]:
    """Async wrapper — runs blocking scan in default executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _scan_sync, transcripts_root)
```

- [ ] **Step 4: Run tests**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_transcript_scanner.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/transcript_scanner.py tests/core/test_transcript_scanner.py
git commit -m "feat(core): single transcript scanner shared by lost+active flows"
```

---

### Task 3: Refactor scan_lost_sessions to use transcript_scanner (no behavior change)

**Files:**
- Modify: `claude_mnemos/core/lost_sessions.py:243` (function `scan_lost_sessions`)
- Existing tests must still pass: `tests/core/test_lost_sessions.py`

- [ ] **Step 1: Run existing tests to capture current passing state**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_lost_sessions.py -v`
Expected: all pass. Note count.

- [ ] **Step 2: Modify scan_lost_sessions to delegate to scanner**

Replace function body in `claude_mnemos/core/lost_sessions.py` (around line 243):

```python
def scan_lost_sessions(
    vault: Path,
    *,
    transcripts_root: Path | None = None,
) -> list[LostSession]:
    """Return all transcripts under ``transcripts_root`` that are neither
    ingested (per manifest) nor explicitly ignored.

    Internal: delegates to async scan_transcripts via asyncio.run when called
    from sync context. The TTLCache wrapper above (LostSessionsCache) keeps
    callers unchanged.
    """
    import asyncio

    from claude_mnemos.core.transcript_scanner import scan_transcripts

    manifest = Manifest.load(vault)
    known_shas: set[str] = set(manifest.ingested.keys())
    ignored_shas: set[str] = LostSessionsIgnore.load(vault).ignored_shas

    try:
        entries = asyncio.run(scan_transcripts(transcripts_root=transcripts_root))
    except RuntimeError:
        # Already in event loop (e.g. called from FastAPI handler).
        # Fall back to direct sync helper.
        from claude_mnemos.core.transcript_scanner import _scan_sync
        entries = _scan_sync(transcripts_root)

    results: list[LostSession] = []
    for e in entries:
        if e.sha in known_shas or e.sha in ignored_shas:
            continue
        results.append(
            LostSession(
                session_id=e.session_id,
                transcript_path=e.transcript_path,
                sha=e.sha,
                size_bytes=e.size_bytes,
                mtime=e.mtime,
                cwd=e.cwd,
                preview=e.preview,
            )
        )
    results.sort(key=lambda i: i.mtime, reverse=True)
    return results
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_lost_sessions.py tests/daemon/test_app_lost_sessions.py tests/daemon/test_routes_lost_sessions_cross_vault.py -v`
Expected: all pass — same count as Step 1.

- [ ] **Step 4: Commit**

```bash
git add claude_mnemos/core/lost_sessions.py
git commit -m "refactor(lost-sessions): delegate file scan to shared transcript_scanner"
```

---

## Phase 2: Active Sessions + Auto-Dump

### Task 4: ActiveSession model + scan_active_sessions

**Files:**
- Create: `claude_mnemos/core/active_sessions.py`
- Test: `tests/core/test_active_sessions.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_active_sessions.py
"""Tests for claude_mnemos.core.active_sessions."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.core.active_sessions import (
    ActiveSession,
    scan_active_sessions,
)
from claude_mnemos.state.manifest import IngestRecord, Manifest


def _write_jsonl_with_mtime(root: Path, name: str, mtime_ago: timedelta, cwd: str | None = None) -> Path:
    """Write a jsonl and set its mtime to `now - mtime_ago`."""
    payload: dict[str, object] = {"sid": name}
    if cwd is not None:
        payload["cwd"] = cwd
    content = json.dumps(payload).encode("utf-8")
    p = root / f"{name}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    target = datetime.now(tz=UTC) - mtime_ago
    import os
    ts = target.timestamp()
    os.utime(p, (ts, ts))
    return p


class _FakeRuntime:
    """Minimal VaultRuntime stand-in for active_sessions tests."""

    def __init__(self, name: str, vault: Path) -> None:
        self.name = name
        self.vault_root = vault


def _ingest(sid: str, sha: str, vault: Path) -> None:
    manifest = Manifest.load(vault)
    manifest.ingested[sha] = IngestRecord(
        session_id=sid,
        ingested_at=datetime.now(tz=UTC),
        raw_path=f"raw/chats/{sid}.md",
        source_path=None,
        model=None,
        input_tokens=None,
        output_tokens=None,
    )
    manifest.save(vault)


@pytest.mark.asyncio
async def test_scan_returns_empty_for_no_jsonls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    out = await scan_active_sessions([])
    assert out == []


@pytest.mark.asyncio
async def test_scan_filters_by_24h_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    _write_jsonl_with_mtime(root, "fresh", timedelta(minutes=15))
    _write_jsonl_with_mtime(root, "old", timedelta(hours=30))
    out = await scan_active_sessions([])
    assert {s.session_id for s in out} == {"fresh"}


@pytest.mark.asyncio
async def test_scan_classifies_hot_vs_cooling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    _write_jsonl_with_mtime(root, "hot", timedelta(minutes=10))
    _write_jsonl_with_mtime(root, "cool", timedelta(hours=3))
    out = await scan_active_sessions([])
    by_id = {s.session_id: s for s in out}
    assert by_id["hot"].status == "hot"
    assert by_id["cool"].status == "cooling"


@pytest.mark.asyncio
async def test_scan_excludes_globally_ingested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    p = _write_jsonl_with_mtime(root, "ingested", timedelta(minutes=10))
    import hashlib
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    vault = tmp_path / "vault"
    vault.mkdir()
    _ingest("ingested", sha, vault)
    runtime = _FakeRuntime("alpha", vault)
    out = await scan_active_sessions([runtime])
    assert out == []


@pytest.mark.asyncio
async def test_scan_attributes_via_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a project's cwd_patterns matches the cwd, project_name attaches.

    Without registered project — sessions are __unassigned__.
    """
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    _write_jsonl_with_mtime(root, "no-cwd", timedelta(minutes=10))
    out = await scan_active_sessions([])
    assert all(s.project_name == "__unassigned__" for s in out)


@pytest.mark.asyncio
async def test_auto_dump_at_set_for_assigned_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """auto_dump_at = mtime+24h for assigned, None for unassigned."""
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    _write_jsonl_with_mtime(root, "u", timedelta(hours=2))
    out = await scan_active_sessions([])
    assert len(out) == 1
    assert out[0].project_name == "__unassigned__"
    assert out[0].auto_dump_at is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_active_sessions.py -v`
Expected: ImportError.

- [ ] **Step 3: Implementation**

```python
# claude_mnemos/core/active_sessions.py
"""Active-sessions scanner — projection of transcript_scanner restricted
to recent jsonls (mtime > now - cooling_threshold) that are not yet
ingested in any vault. Status hot vs cooling for UI bins.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from claude_mnemos.core.transcript_scanner import scan_transcripts
from claude_mnemos.mapping.resolver import (
    ProjectResolver,
    ResolverAmbiguityError,
)
from claude_mnemos.state.manifest import Manifest

if TYPE_CHECKING:
    from claude_mnemos.daemon.vault_runtime import VaultRuntime

UNASSIGNED_PROJECT = "__unassigned__"
HOT_THRESHOLD_MIN = 30
COOLING_THRESHOLD_HOURS = 24


class ActiveSession(BaseModel):
    session_id: str
    transcript_path: str
    sha: str
    project_name: str
    cwd: str | None
    preview: str | None
    mtime: datetime
    size_bytes: int
    status: Literal["hot", "cooling"]
    auto_dump_at: datetime | None


def _global_ingested_shas(runtimes: list["VaultRuntime"]) -> set[str]:
    out: set[str] = set()
    for rt in runtimes:
        try:
            manifest = Manifest.load(rt.vault_root)
        except Exception:
            continue
        out.update(manifest.ingested.keys())
    return out


async def scan_active_sessions(
    runtimes: list["VaultRuntime"],
    *,
    cooling_threshold_hours: int = COOLING_THRESHOLD_HOURS,
    transcripts_root: Path | None = None,
) -> list[ActiveSession]:
    entries = await scan_transcripts(transcripts_root=transcripts_root)
    if not entries:
        return []

    now = datetime.now(tz=UTC)
    cutoff = now - timedelta(hours=cooling_threshold_hours)
    hot_cutoff = now - timedelta(minutes=HOT_THRESHOLD_MIN)
    ingested = _global_ingested_shas(runtimes)
    resolver = ProjectResolver()

    out: list[ActiveSession] = []
    for e in entries:
        if e.mtime < cutoff:
            continue
        if e.sha in ingested:
            continue
        project_name = UNASSIGNED_PROJECT
        if e.cwd:
            try:
                entry = resolver.resolve_by_cwd(Path(e.cwd))
                if entry is not None:
                    project_name = entry.name
            except (ResolverAmbiguityError, OSError):
                pass
        status: Literal["hot", "cooling"] = (
            "hot" if e.mtime >= hot_cutoff else "cooling"
        )
        auto_dump_at = (
            e.mtime + timedelta(hours=cooling_threshold_hours)
            if project_name != UNASSIGNED_PROJECT
            else None
        )
        out.append(
            ActiveSession(
                session_id=e.session_id,
                transcript_path=e.transcript_path,
                sha=e.sha,
                project_name=project_name,
                cwd=e.cwd,
                preview=e.preview,
                mtime=e.mtime,
                size_bytes=e.size_bytes,
                status=status,
                auto_dump_at=auto_dump_at,
            )
        )
    out.sort(key=lambda s: s.mtime, reverse=True)
    return out
```

- [ ] **Step 4: Run tests**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_active_sessions.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/active_sessions.py tests/core/test_active_sessions.py
git commit -m "feat(core): scan_active_sessions with hot/cooling classification"
```

---

### Task 5: auto_dump_stale function

**Files:**
- Create: `claude_mnemos/core/auto_dump.py`
- Test: `tests/core/test_auto_dump.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_auto_dump.py
"""Tests for claude_mnemos.core.auto_dump."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.core.auto_dump import auto_dump_stale
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore
from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore


class _FakeRuntime:
    def __init__(self, name: str, vault: Path) -> None:
        self.name = name
        self.vault_root = vault
        self.job_store = JobStore(vault / JOBS_DB_FILENAME)
        self.job_worker = None


def _stale_jsonl(root: Path, name: str, cwd: str, hours_ago: float) -> Path:
    p = root / f"{name}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(json.dumps({"cwd": cwd, "sid": name}).encode("utf-8"))
    ts = (datetime.now(tz=UTC) - timedelta(hours=hours_ago)).timestamp()
    os.utime(p, (ts, ts))
    return p


@pytest.fixture
def projects_with_alpha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """Register project 'alpha' with cwd_patterns matching tmp_path/work."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    work = tmp_path / "work"
    work.mkdir()
    vault = tmp_path / "vault-alpha"
    vault.mkdir()
    store = ProjectStore()
    store.add(ProjectMapEntry(
        name="alpha",
        vault_root=str(vault),
        cwd_patterns=[str(work)],
    ))
    return vault, str(work)


@pytest.mark.asyncio
async def test_auto_dump_stale_assigned_session_enqueues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "sess-stale", cwd, hours_ago=25)

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale({"alpha": runtime})

    assert queued == 1
    counts = runtime.job_store.count_by_status()
    assert sum(counts.values()) == 1
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_skips_unassigned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    vault, _cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "orphan", "D:\\nowhere", hours_ago=25)

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale({"alpha": runtime})

    assert queued == 0
    counts = runtime.job_store.count_by_status()
    assert sum(counts.values()) == 0
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_skips_recent_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "fresh", cwd, hours_ago=2)

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale({"alpha": runtime})

    assert queued == 0
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_caps_at_max_per_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    for i in range(5):
        _stale_jsonl(transcripts, f"s{i}", cwd, hours_ago=25 + i)

    runtime = _FakeRuntime("alpha", vault)
    queued = await auto_dump_stale({"alpha": runtime}, max_per_run=2)

    assert queued == 2
    runtime.job_store.close()


@pytest.mark.asyncio
async def test_auto_dump_payload_extract_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects_with_alpha: tuple[Path, str]
) -> None:
    """Auto-dump must always enqueue with extract=False (no LLM stage)."""
    vault, cwd = projects_with_alpha
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts))
    _stale_jsonl(transcripts, "auto", cwd, hours_ago=25)

    runtime = _FakeRuntime("alpha", vault)
    await auto_dump_stale({"alpha": runtime})

    rows = runtime.job_store.list_by_status("queued")
    assert len(rows) == 1
    assert rows[0].payload["extract"] is False
    assert rows[0].payload["transcript_path"].endswith("auto.jsonl")
    runtime.job_store.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_auto_dump.py -v`
Expected: ImportError.

- [ ] **Step 3: Implementation**

```python
# claude_mnemos/core/auto_dump.py
"""24h auto-dump scheduler task — safety net against missed SessionEnd hook.

For every assigned (cwd resolves to a project) transcript whose mtime is
older than COOLING_THRESHOLD_HOURS and is not yet ingested in any vault,
enqueue an ingest job with extract=False (raw dump, no LLM stage).

Idempotency: relies on the worker's manifest filter to make duplicate
jobs a no-op. We do NOT pre-check pending jobs; the cap+manifest combo
is simpler and correct.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from claude_mnemos.core.active_sessions import (
    COOLING_THRESHOLD_HOURS,
    UNASSIGNED_PROJECT,
    scan_active_sessions,
)

if TYPE_CHECKING:
    from claude_mnemos.daemon.vault_runtime import VaultRuntime

log = logging.getLogger(__name__)

MAX_PER_RUN = 50


async def auto_dump_stale(
    runtimes: dict[str, "VaultRuntime"],
    *,
    threshold_hours: int = COOLING_THRESHOLD_HOURS,
    max_per_run: int = MAX_PER_RUN,
) -> int:
    """Enqueue ingest jobs for assigned, stale, non-ingested sessions.

    Returns the number of jobs queued. Safe to call repeatedly (idempotent
    via manifest filter in the worker).
    """
    if not runtimes:
        return 0

    runtimes_list = list(runtimes.values())
    sessions = await scan_active_sessions(
        runtimes_list, cooling_threshold_hours=threshold_hours
    )

    queued = 0
    for s in sessions:
        if queued >= max_per_run:
            break
        if s.project_name == UNASSIGNED_PROJECT:
            continue
        if s.status != "cooling":
            continue
        runtime = runtimes.get(s.project_name)
        if runtime is None or runtime.job_store is None:
            continue
        try:
            runtime.job_store.create(
                kind="ingest",
                payload={"transcript_path": s.transcript_path, "extract": False},
            )
        except Exception as exc:
            log.warning("auto_dump: failed to enqueue %s: %s", s.session_id, exc)
            continue
        queued += 1
        if runtime.job_worker is not None:
            runtime.job_worker.signal_wakeup()

    log.info("auto_dump: queued=%d (cap=%d)", queued, max_per_run)
    return queued
```

- [ ] **Step 4: Run tests**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_auto_dump.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/auto_dump.py tests/core/test_auto_dump.py
git commit -m "feat(core): auto_dump_stale — 24h safety net for assigned non-ingested sessions"
```

---

## Phase 3: Daemon Integration

### Task 6: Register auto_dump cron + catch-up after bootstrap

**Files:**
- Modify: `claude_mnemos/daemon/process.py` — add scheduler registration + catch-up call

- [ ] **Step 1: Read existing daemon/process.py to find post-bootstrap location**

Run: `grep -n "_bootstrap_runtimes\|scheduler.start" /d/code/claude-mnemos/claude_mnemos/daemon/process.py`

Find the line numbers of `await self._bootstrap_runtimes()` and `self.scheduler.start()` calls.

- [ ] **Step 2: Write the failing test**

```python
# tests/daemon/test_auto_dump_integration.py
"""Integration test: daemon registers auto_dump cron after bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.mark.asyncio
async def test_daemon_registers_auto_dump_cron(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    try:
        from fastapi.testclient import TestClient

        with TestClient(daemon.app):
            job_ids = {j.id for j in daemon.scheduler.get_jobs()}
            assert "auto_dump_global" in job_ids
    finally:
        import asyncio
        await daemon._shutdown_runtimes()
        if daemon.scheduler.running:
            daemon.scheduler.shutdown(wait=False)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/daemon/test_auto_dump_integration.py -v`
Expected: FAIL — `auto_dump_global` not in scheduler jobs.

- [ ] **Step 4: Modify `claude_mnemos/daemon/process.py`**

Add at the top of file (with other imports):

```python
from claude_mnemos.core.auto_dump import auto_dump_stale
```

In the run/lifespan code, immediately after `await self._bootstrap_runtimes()` (and before `self.scheduler.start()` if it comes later), add:

```python
        # Operational dashboard — auto-dump safety net (P0+P1 spec).
        async def _auto_dump_task() -> None:
            await auto_dump_stale(self.runtimes)

        self.scheduler.add_job(
            _auto_dump_task,
            "cron",
            minute=0,
            id="auto_dump_global",
            replace_existing=True,
        )
        # Catch-up immediately after bootstrap (only AFTER all runtimes mounted)
        import asyncio as _asyncio
        _asyncio.create_task(_auto_dump_task())
```

NOTE: locate the exact insert point by reading `daemon/process.py` near `_bootstrap_runtimes` call. The cron must be added BEFORE `scheduler.start()`.

- [ ] **Step 5: Run integration test + existing daemon tests**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/daemon/test_auto_dump_integration.py tests/daemon/test_process_multivault.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/process.py tests/daemon/test_auto_dump_integration.py
git commit -m "feat(daemon): register auto_dump_global cron + catch-up after bootstrap"
```

---

### Task 7: GET /api/dashboard/snapshot endpoint

**Files:**
- Create: `claude_mnemos/daemon/routes/dashboard.py`
- Modify: `claude_mnemos/daemon/app.py` — register router
- Test: `tests/daemon/test_app_dashboard.py`

- [ ] **Step 1: Find app.py router-registration pattern**

Run: `grep -n "include_router\|from claude_mnemos.daemon.routes" /d/code/claude-mnemos/claude_mnemos/daemon/app.py`

- [ ] **Step 2: Write the failing tests**

```python
# tests/daemon/test_app_dashboard.py
"""REST tests for /api/dashboard/* endpoints."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobStore


_PROJECT = "alpha"


class _FakeRuntime:
    def __init__(self, vault: Path) -> None:
        self.name = _PROJECT
        self.vault_root = vault
        self.tracker = OurWritesTracker(ttl_s=60.0)
        self.job_store = JobStore(vault / JOBS_DB_FILENAME)
        self.job_worker = None
        self.lost_sessions_cache = None


class _FakeDaemon:
    def __init__(self, vault: Path) -> None:
        self.started_at_monotonic = 0.0
        self._runtime = _FakeRuntime(vault)
        self.runtimes: dict[str, _FakeRuntime] = {_PROJECT: self._runtime}

    def scheduler_jobs_info(self) -> list[Any]:
        return []


@pytest.fixture
def daemon(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    d = _FakeDaemon(vault)
    yield d
    d._runtime.job_store.close()


@pytest.fixture
def app(daemon: _FakeDaemon):
    return create_app(daemon=daemon)


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def transcripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "transcripts"
    root.mkdir()
    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
    return root


def _stale_jsonl(root: Path, name: str, cwd: str | None, hours_ago: float) -> Path:
    payload: dict[str, object] = {"sid": name}
    if cwd:
        payload["cwd"] = cwd
    p = root / f"{name}.jsonl"
    p.write_bytes(json.dumps(payload).encode("utf-8"))
    ts = (datetime.now(tz=UTC) - timedelta(hours=hours_ago)).timestamp()
    os.utime(p, (ts, ts))
    return p


async def test_snapshot_empty_returns_zeros(client, transcripts: Path) -> None:
    r = await client.get("/api/dashboard/snapshot")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kpi"]["queue"]["queued"] == 0
    assert body["active_sessions"] == []
    assert body["running_jobs"] == []


async def test_snapshot_includes_active_sessions(client, transcripts: Path) -> None:
    _stale_jsonl(transcripts, "active-1", cwd=None, hours_ago=0.5)
    r = await client.get("/api/dashboard/snapshot")
    assert r.status_code == 200
    body = r.json()
    sids = {s["session_id"] for s in body["active_sessions"]}
    assert "active-1" in sids


async def test_snapshot_kpi_active_counts(client, transcripts: Path) -> None:
    _stale_jsonl(transcripts, "hot-1", cwd=None, hours_ago=0.2)
    _stale_jsonl(transcripts, "cool-1", cwd=None, hours_ago=2)
    r = await client.get("/api/dashboard/snapshot")
    body = r.json()
    assert body["kpi"]["active"]["hot"] >= 1
    assert body["kpi"]["active"]["cooling"] >= 1


async def test_snapshot_returns_errors_field_when_aggregator_fails(
    client, transcripts: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If one aggregator raises, snapshot returns partial data with errors[]."""
    async def boom(*a: object, **kw: object) -> Any:
        raise RuntimeError("simulated")

    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.dashboard.scan_active_sessions", boom
    )
    r = await client.get("/api/dashboard/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["active_sessions"] == []
    assert any("active_sessions" in e for e in body["errors"])
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/daemon/test_app_dashboard.py -v`
Expected: 404 or ImportError.

- [ ] **Step 4: Create router**

```python
# claude_mnemos/daemon/routes/dashboard.py
"""REST aggregator endpoints for the operational Overview dashboard.

Single endpoint /api/dashboard/snapshot wraps the four hot data sources
(KPI, active sessions, running jobs) in per-aggregator try/except so a
single failure does not nuke the whole response.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core.active_sessions import scan_active_sessions
from claude_mnemos.daemon.routes._helpers import all_runtimes, get_runtime

router = APIRouter()
log = logging.getLogger(__name__)


def _kpi_for(runtimes: list[Any]) -> dict[str, Any]:
    queue = {"queued": 0, "running": 0, "failed": 0}
    today_ingest = 0
    today_pages = 0
    tokens_today = 0
    lost_total = 0  # placeholder; reuse useLostSessions on FE if needed

    today_start = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    for rt in runtimes:
        if rt.job_store is None:
            continue
        counts = rt.job_store.count_by_status()
        queue["queued"] += counts.get("queued", 0)
        queue["running"] += counts.get("running", 0)
        queue["failed"] += counts.get("failed_permanent", 0)

        # Today's activity (best-effort, no crash on missing tables).
        try:
            from claude_mnemos.state.activity import ActivityLog
            log_entries = ActivityLog.load(rt.vault_root).entries
            for entry in log_entries:
                if entry.created_at >= today_start:
                    if entry.kind in ("ingest", "page_create"):
                        today_ingest += 1
                    if entry.kind == "page_create":
                        today_pages += 1
        except Exception as exc:
            log.debug("kpi today-activity failed for %s: %s", rt.name, exc)

    return {
        "queue": queue,
        "today": {"ingest_count": today_ingest, "pages_count": today_pages},
        "tokens_today": tokens_today,
        "lost_total": lost_total,
    }


def _running_jobs_for(runtimes: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rt in runtimes:
        if rt.job_store is None:
            continue
        try:
            for job in rt.job_store.list_by_status("running"):
                d = job.model_dump(mode="json")
                d["project_name"] = rt.name
                out.append(d)
        except Exception as exc:
            log.warning("running_jobs read failed for %s: %s", rt.name, exc)
    return out


@router.get("/dashboard/snapshot")
async def dashboard_snapshot(request: Request) -> dict[str, Any]:
    """Single-call aggregator for the Overview dashboard.

    Per-aggregator try/except → partial data + errors[] on failure.
    """
    runtimes = list(all_runtimes(request))
    errors: list[str] = []
    kpi: dict[str, Any] = {
        "queue": {"queued": 0, "running": 0, "failed": 0},
        "active": {"hot": 0, "cooling": 0},
        "today": {"ingest_count": 0, "pages_count": 0},
        "tokens_today": 0,
        "lost_total": 0,
    }
    active_sessions: list[dict[str, Any]] = []
    running_jobs: list[dict[str, Any]] = []

    try:
        kpi.update(_kpi_for(runtimes))
    except Exception as exc:
        log.warning("kpi aggregator failed: %s", exc)
        errors.append(f"kpi: {exc}")

    try:
        sessions = await scan_active_sessions(runtimes)
        active_sessions = [s.model_dump(mode="json") for s in sessions]
        kpi["active"]["hot"] = sum(1 for s in sessions if s.status == "hot")
        kpi["active"]["cooling"] = sum(1 for s in sessions if s.status == "cooling")
    except Exception as exc:
        log.warning("active_sessions aggregator failed: %s", exc)
        errors.append(f"active_sessions: {exc}")

    try:
        running_jobs = _running_jobs_for(runtimes)
    except Exception as exc:
        log.warning("running_jobs aggregator failed: %s", exc)
        errors.append(f"running_jobs: {exc}")

    return {
        "kpi": kpi,
        "active_sessions": active_sessions,
        "running_jobs": running_jobs,
        "errors": errors,
    }


@router.post("/dashboard/active-sessions/{session_id}/dump-now", status_code=201)
async def dump_now_route(
    session_id: str, request: Request, body: dict[str, Any]
) -> dict[str, Any]:
    project_name = body.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(status_code=422, detail={"error": "missing_project_name"})
    runtime = get_runtime(request, project_name)
    if runtime.job_store is None:
        raise HTTPException(
            status_code=503, detail={"error": "vault_unavailable"}
        )
    sessions = await scan_active_sessions([runtime])
    match = next((s for s in sessions if s.session_id == session_id), None)
    if match is None:
        raise HTTPException(
            status_code=404, detail={"error": "active_session_not_found"}
        )
    job = runtime.job_store.create(
        kind="ingest",
        payload={"transcript_path": match.transcript_path, "extract": False},
    )
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    return job.model_dump(mode="json")


@router.post("/dashboard/scan-active")
async def scan_active_route(request: Request) -> dict[str, Any]:
    runtimes = list(all_runtimes(request))
    sessions = await scan_active_sessions(runtimes)
    return {"scanned": len(sessions)}
```

- [ ] **Step 5: Register router in `claude_mnemos/daemon/app.py`**

Find the section with `app.include_router(...)` calls and add:

```python
from claude_mnemos.daemon.routes import dashboard as dashboard_routes

app.include_router(dashboard_routes.router, prefix="/api")
```

- [ ] **Step 6: Run dashboard tests + existing routes tests for regressions**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/daemon/test_app_dashboard.py tests/daemon/test_app_routes.py -v`
Expected: 4 dashboard tests pass + no regressions.

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/daemon/routes/dashboard.py claude_mnemos/daemon/app.py tests/daemon/test_app_dashboard.py
git commit -m "feat(daemon): /api/dashboard/snapshot + dump-now + scan-active endpoints"
```

---

## Phase 4: Frontend Foundation

### Task 8: ActiveSession Zod schema

**Files:**
- Create: `frontend/src/types/ActiveSession.ts`

- [ ] **Step 1: Create the schema**

```typescript
// frontend/src/types/ActiveSession.ts
import { z } from "zod";

export const ActiveSessionStatusSchema = z.enum(["hot", "cooling"]);
export type ActiveSessionStatus = z.infer<typeof ActiveSessionStatusSchema>;

export const ActiveSessionSchema = z.object({
  session_id: z.string(),
  transcript_path: z.string(),
  sha: z.string(),
  project_name: z.string(),
  cwd: z.string().nullable(),
  preview: z.string().nullable(),
  mtime: z.string(), // ISO datetime
  size_bytes: z.number().int().nonnegative(),
  status: ActiveSessionStatusSchema,
  auto_dump_at: z.string().nullable(),
});
export type ActiveSession = z.infer<typeof ActiveSessionSchema>;

export const RunningJobSchema = z.object({
  id: z.string(),
  kind: z.string(),
  status: z.string(),
  payload: z.record(z.string(), z.unknown()).optional(),
  project_name: z.string(),
  started_at: z.string().nullable().optional(),
});
export type RunningJob = z.infer<typeof RunningJobSchema>;

export const KpiSchema = z.object({
  queue: z.object({
    queued: z.number().int(),
    running: z.number().int(),
    failed: z.number().int(),
  }),
  active: z.object({
    hot: z.number().int(),
    cooling: z.number().int(),
  }),
  today: z.object({
    ingest_count: z.number().int(),
    pages_count: z.number().int(),
  }),
  tokens_today: z.number().int(),
  lost_total: z.number().int(),
});
export type Kpi = z.infer<typeof KpiSchema>;

export const DashboardSnapshotSchema = z.object({
  kpi: KpiSchema,
  active_sessions: z.array(ActiveSessionSchema),
  running_jobs: z.array(RunningJobSchema),
  errors: z.array(z.string()),
});
export type DashboardSnapshot = z.infer<typeof DashboardSnapshotSchema>;
```

- [ ] **Step 2: Type-check**

Run: `cd /d/code/claude-mnemos/frontend && pnpm tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/ActiveSession.ts
git commit -m "feat(types): ActiveSession + DashboardSnapshot Zod schemas"
```

---

### Task 9: dashboard.api.ts

**Files:**
- Create: `frontend/src/api/dashboard.api.ts`
- Test: `frontend/src/__tests__/api-dashboard.test.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/__tests__/api-dashboard.test.ts
import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "../api/client";
import {
  getDashboardSnapshot,
  postDumpNow,
  postScanActive,
} from "../api/dashboard.api";

const SNAPSHOT_FIXTURE = {
  kpi: {
    queue: { queued: 1, running: 0, failed: 0 },
    active: { hot: 1, cooling: 0 },
    today: { ingest_count: 0, pages_count: 0 },
    tokens_today: 0,
    lost_total: 1304,
  },
  active_sessions: [
    {
      session_id: "abc",
      transcript_path: "C:/x/abc.jsonl",
      sha: "deadbeef",
      project_name: "alpha",
      cwd: "D:/code/alpha",
      preview: "hi",
      mtime: "2026-05-03T10:00:00Z",
      size_bytes: 1024,
      status: "hot",
      auto_dump_at: "2026-05-04T10:00:00Z",
    },
  ],
  running_jobs: [],
  errors: [],
};

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe("dashboard api", () => {
  afterEach(() => vi.resetAllMocks());

  it("getDashboardSnapshot parses payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: SNAPSHOT_FIXTURE });
    const r = await getDashboardSnapshot();
    expect(r.kpi.active.hot).toBe(1);
    expect(r.active_sessions[0].session_id).toBe("abc");
  });

  it("postDumpNow sends project_name in body", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { id: "j1", kind: "ingest", status: "queued" },
    });
    await postDumpNow("abc", { project_name: "alpha" });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/dashboard/active-sessions/abc/dump-now",
      { project_name: "alpha" },
    );
  });

  it("postScanActive returns scanned count", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { scanned: 3 } });
    const r = await postScanActive();
    expect(r.scanned).toBe(3);
  });

  it("getDashboardSnapshot rejects malformed payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { kpi: { queue: { queued: "not-a-number" } } },
    });
    await expect(getDashboardSnapshot()).rejects.toThrow();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run __tests__/api-dashboard.test.ts`
Expected: import error.

- [ ] **Step 3: Implementation**

```typescript
// frontend/src/api/dashboard.api.ts
import { apiClient } from "./client";
import {
  DashboardSnapshotSchema,
  type DashboardSnapshot,
} from "@/types/ActiveSession";

export async function getDashboardSnapshot(): Promise<DashboardSnapshot> {
  const r = await apiClient.get("/dashboard/snapshot");
  return DashboardSnapshotSchema.parse(r.data);
}

export interface DumpNowBody {
  project_name: string;
}

export async function postDumpNow(
  sessionId: string,
  body: DumpNowBody,
): Promise<unknown> {
  const r = await apiClient.post(
    `/dashboard/active-sessions/${encodeURIComponent(sessionId)}/dump-now`,
    body,
  );
  return r.data;
}

export async function postScanActive(): Promise<{ scanned: number }> {
  const r = await apiClient.post("/dashboard/scan-active");
  return r.data as { scanned: number };
}
```

- [ ] **Step 4: Run tests**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run __tests__/api-dashboard.test.ts`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/dashboard.api.ts frontend/src/__tests__/api-dashboard.test.ts
git commit -m "feat(api): dashboard.api with snapshot + dump-now + scan-active"
```

---

### Task 10: Hooks (useDashboardSnapshot, useDumpNow, useScanActive)

**Files:**
- Create: `frontend/src/hooks/dashboard/useDashboardSnapshot.ts`
- Create: `frontend/src/hooks/dashboard/useDumpNow.ts`
- Create: `frontend/src/hooks/dashboard/useScanActive.ts`

- [ ] **Step 1: Implementation**

```typescript
// frontend/src/hooks/dashboard/useDashboardSnapshot.ts
import { useQuery } from "@tanstack/react-query";
import { getDashboardSnapshot } from "@/api/dashboard.api";

export function useDashboardSnapshot() {
  return useQuery({
    queryKey: ["dashboard-snapshot"],
    queryFn: getDashboardSnapshot,
    refetchInterval: 10_000,
  });
}
```

```typescript
// frontend/src/hooks/dashboard/useDumpNow.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { postDumpNow, type DumpNowBody } from "@/api/dashboard.api";
import { extractApiError } from "@/lib/error";

interface Args {
  sessionId: string;
  body: DumpNowBody;
}

export function useDumpNow() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ sessionId, body }: Args) => postDumpNow(sessionId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dashboard-snapshot"] });
      void qc.invalidateQueries({ queryKey: ["sessions"] });
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      toast.success(t("overview.dump_now.toast_success"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

```typescript
// frontend/src/hooks/dashboard/useScanActive.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postScanActive } from "@/api/dashboard.api";

export function useScanActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postScanActive,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dashboard-snapshot"] });
    },
  });
}
```

- [ ] **Step 2: Type-check**

Run: `cd /d/code/claude-mnemos/frontend && pnpm tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/dashboard/
git commit -m "feat(hooks): dashboard query/mutation hooks (snapshot 10s, dump-now, scan-active)"
```

---

### Task 11: i18n keys (en only — uk/ru deferred)

**Files:**
- Modify: `frontend/public/locales/en.json`

- [ ] **Step 1: Add keys**

Find existing `"overview"` section in en.json (or create one if absent). Add inside:

```json
"overview": {
  "kpi": {
    "queue_label": "Queue",
    "queue_format": "{{queued}} queued · {{running}} running · {{failed}} failed",
    "active_label": "Active",
    "active_format": "🟢 {{hot}} · 🟡 {{cooling}}",
    "today_label": "Today",
    "today_format": "{{ingest}} ingest · {{pages}} pages",
    "tokens_label": "Tokens",
    "lost_label": "Lost",
    "lost_link": "→ Sort"
  },
  "running": {
    "title": "Running now",
    "elapsed": "{{seconds}}s elapsed",
    "empty": "😴 Nothing running"
  },
  "active": {
    "title": "Active sessions",
    "empty": "No active sessions",
    "dump_now_button": "Dump now",
    "read_button": "Read",
    "auto_dump_in": "auto-dump in {{remaining}}",
    "auto_dump_overdue": "auto-dump pending"
  },
  "health_dot": {
    "ok": "Healthy",
    "warning": "Warnings",
    "critical": "Critical",
    "details_link": "→ Details"
  },
  "dump_now": {
    "toast_success": "Queued for dump"
  }
}
```

- [ ] **Step 2: Validate JSON**

Run: `~/pipx/venvs/claude-mnemos/Scripts/python.exe -c "import json; json.load(open('D:/code/claude-mnemos/frontend/public/locales/en.json', encoding='utf-8')); print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add frontend/public/locales/en.json
git commit -m "feat(i18n): en keys for operational overview (uk/ru deferred to v2)"
```

---

## Phase 5: Frontend Widgets

### Task 12: KpiBar widget

**Files:**
- Create: `frontend/src/components/widgets/dashboard/KpiBar.tsx`
- Test: `frontend/src/__tests__/widgets/KpiBar.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/widgets/KpiBar.test.tsx
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "../../i18n";
import { KpiBar } from "../../components/widgets/dashboard/KpiBar";
import type { Kpi } from "../../types/ActiveSession";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    overview: {
      kpi: {
        queue_label: "Queue",
        queue_format: "{{queued}} queued · {{running}} running · {{failed}} failed",
        active_label: "Active",
        active_format: "🟢 {{hot}} · 🟡 {{cooling}}",
        today_label: "Today",
        today_format: "{{ingest}} ingest · {{pages}} pages",
        tokens_label: "Tokens",
        lost_label: "Lost",
        lost_link: "→ Sort",
      },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

const KPI: Kpi = {
  queue: { queued: 3, running: 1, failed: 0 },
  active: { hot: 2, cooling: 1 },
  today: { ingest_count: 5, pages_count: 12 },
  tokens_today: 862_000,
  lost_total: 1304,
};

function wrap(ui: React.ReactNode) {
  return <MemoryRouter>{ui}</MemoryRouter>;
}

describe("KpiBar", () => {
  it("renders all five tiles with values", () => {
    render(wrap(<KpiBar data={KPI} />));
    expect(screen.getByText(/Queue/i)).toBeDefined();
    expect(screen.getByText(/3 queued/)).toBeDefined();
    expect(screen.getByText(/Active/i)).toBeDefined();
    expect(screen.getByText(/Today/i)).toBeDefined();
    expect(screen.getByText(/Tokens/i)).toBeDefined();
    expect(screen.getByText(/Lost/i)).toBeDefined();
    expect(screen.getByText(/1304/)).toBeDefined();
  });

  it("highlights queue tile in red when failed > 0", () => {
    const failedKpi = { ...KPI, queue: { ...KPI.queue, failed: 2 } };
    const { container } = render(wrap(<KpiBar data={failedKpi} />));
    const tile = container.querySelector('[data-testid="kpi-queue"]');
    expect(tile?.className).toMatch(/destructive|red/);
  });
});
```

- [ ] **Step 2: Run test to fail**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run __tests__/widgets/KpiBar.test.tsx`
Expected: import error.

- [ ] **Step 3: Implementation**

```tsx
// frontend/src/components/widgets/dashboard/KpiBar.tsx
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import type { Kpi } from "@/types/ActiveSession";

interface KpiTileProps {
  label: string;
  value: string;
  accent?: "default" | "destructive" | "warning";
  href?: string;
  testId?: string;
}

function KpiTile({ label, value, accent = "default", href, testId }: KpiTileProps) {
  const accentClass =
    accent === "destructive"
      ? "border-destructive/50 bg-destructive/5"
      : accent === "warning"
      ? "border-amber-500/50 bg-amber-500/5"
      : "border-border";

  const content = (
    <div
      data-testid={testId}
      className={`rounded-md border ${accentClass} p-3 text-sm`}
    >
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono">{value}</div>
    </div>
  );

  return href ? <Link to={href}>{content}</Link> : content;
}

export function KpiBar({ data }: { data: Kpi }) {
  const { t } = useTranslation();
  const queueAccent = data.queue.failed > 0 ? "destructive" : "default";
  const activeAccent = data.active.cooling > 0 ? "warning" : "default";

  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
      <KpiTile
        label={t("overview.kpi.queue_label")}
        value={t("overview.kpi.queue_format", {
          queued: data.queue.queued,
          running: data.queue.running,
          failed: data.queue.failed,
        })}
        accent={queueAccent}
        testId="kpi-queue"
      />
      <KpiTile
        label={t("overview.kpi.active_label")}
        value={t("overview.kpi.active_format", {
          hot: data.active.hot,
          cooling: data.active.cooling,
        })}
        accent={activeAccent}
        testId="kpi-active"
      />
      <KpiTile
        label={t("overview.kpi.today_label")}
        value={t("overview.kpi.today_format", {
          ingest: data.today.ingest_count,
          pages: data.today.pages_count,
        })}
        testId="kpi-today"
      />
      <KpiTile
        label={t("overview.kpi.tokens_label")}
        value={`${(data.tokens_today / 1000).toFixed(1)}K`}
        testId="kpi-tokens"
      />
      <KpiTile
        label={t("overview.kpi.lost_label")}
        value={`${data.lost_total} ${t("overview.kpi.lost_link")}`}
        href="/lost-sessions"
        testId="kpi-lost"
      />
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run __tests__/widgets/KpiBar.test.tsx`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/dashboard/KpiBar.tsx frontend/src/__tests__/widgets/KpiBar.test.tsx
git commit -m "feat(widget): KpiBar with 5 tiles + accent colors + lost-link"
```

---

### Task 13: RunningJobsLive widget

**Files:**
- Create: `frontend/src/components/widgets/dashboard/RunningJobsLive.tsx`
- Test: `frontend/src/__tests__/widgets/RunningJobsLive.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/widgets/RunningJobsLive.test.tsx
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import i18n from "../../i18n";
import { RunningJobsLive } from "../../components/widgets/dashboard/RunningJobsLive";
import type { RunningJob } from "../../types/ActiveSession";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    overview: {
      running: {
        title: "Running now",
        elapsed: "{{seconds}}s elapsed",
        empty: "😴 Nothing running",
      },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

describe("RunningJobsLive", () => {
  it("shows empty state when no jobs", () => {
    render(<RunningJobsLive jobs={[]} />);
    expect(screen.getByText(/Nothing running/)).toBeDefined();
  });

  it("renders each running job with project + elapsed", () => {
    const now = Date.now();
    const jobs: RunningJob[] = [
      {
        id: "j1",
        kind: "ingest",
        status: "running",
        project_name: "alpha",
        started_at: new Date(now - 12_000).toISOString(),
      },
    ];
    render(<RunningJobsLive jobs={jobs} />);
    expect(screen.getByText(/ingest/)).toBeDefined();
    expect(screen.getByText(/alpha/)).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to fail**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run __tests__/widgets/RunningJobsLive.test.tsx`
Expected: import error.

- [ ] **Step 3: Implementation**

```tsx
// frontend/src/components/widgets/dashboard/RunningJobsLive.tsx
import { useTranslation } from "react-i18next";
import { ProjectBadge } from "@/components/widgets/ProjectBadge";
import type { RunningJob } from "@/types/ActiveSession";

function elapsedSeconds(startIso: string | null | undefined): number {
  if (!startIso) return 0;
  return Math.max(0, Math.floor((Date.now() - new Date(startIso).getTime()) / 1000));
}

export function RunningJobsLive({ jobs }: { jobs: RunningJob[] }) {
  const { t } = useTranslation();
  if (jobs.length === 0) {
    return (
      <section className="rounded-md border bg-background p-3">
        <h2 className="text-sm font-semibold mb-2">{t("overview.running.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("overview.running.empty")}</p>
      </section>
    );
  }
  return (
    <section className="rounded-md border bg-background p-3">
      <h2 className="text-sm font-semibold mb-2">{t("overview.running.title")}</h2>
      <ul className="space-y-1.5">
        {jobs.map((j) => (
          <li
            key={j.id}
            className="flex items-center gap-3 rounded border px-2 py-1.5 text-sm"
          >
            <span className="font-mono text-xs uppercase tracking-wide rounded bg-muted px-1.5 py-0.5">
              {j.kind}
            </span>
            <ProjectBadge name={j.project_name} />
            <span className="ml-auto text-xs text-muted-foreground">
              {t("overview.running.elapsed", { seconds: elapsedSeconds(j.started_at) })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run __tests__/widgets/RunningJobsLive.test.tsx`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/dashboard/RunningJobsLive.tsx frontend/src/__tests__/widgets/RunningJobsLive.test.tsx
git commit -m "feat(widget): RunningJobsLive with empty state + per-job project badge"
```

---

### Task 14: ActiveSessionsLive widget (with countdown)

**Files:**
- Create: `frontend/src/components/widgets/dashboard/ActiveSessionsLive.tsx`
- Test: `frontend/src/__tests__/widgets/ActiveSessionsLive.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/widgets/ActiveSessionsLive.test.tsx
import { describe, it, expect, beforeAll, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import i18n from "../../i18n";
import { ActiveSessionsLive } from "../../components/widgets/dashboard/ActiveSessionsLive";
import type { ActiveSession } from "../../types/ActiveSession";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    overview: {
      active: {
        title: "Active sessions",
        empty: "No active sessions",
        dump_now_button: "Dump now",
        read_button: "Read",
        auto_dump_in: "auto-dump in {{remaining}}",
        auto_dump_overdue: "auto-dump pending",
      },
    },
    lost_sessions: {
      selection: { unassigned_label: "unassigned" },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

vi.mock("../../api/client", () => ({
  apiClient: { post: vi.fn() },
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  );
}

const HOT: ActiveSession = {
  session_id: "abcd1234efgh",
  transcript_path: "C:/x.jsonl",
  sha: "deadbeef",
  project_name: "alpha",
  cwd: "D:/code/alpha",
  preview: "hello",
  mtime: new Date(Date.now() - 5 * 60_000).toISOString(),
  size_bytes: 1024,
  status: "hot",
  auto_dump_at: null,
};

const COOLING: ActiveSession = {
  ...HOT,
  session_id: "cool0001",
  status: "cooling",
  mtime: new Date(Date.now() - 2 * 60 * 60_000).toISOString(),
  auto_dump_at: new Date(Date.now() + 22 * 60 * 60_000).toISOString(),
};

describe("ActiveSessionsLive", () => {
  it("shows empty state when no sessions", () => {
    render(wrap(<ActiveSessionsLive sessions={[]} />));
    expect(screen.getByText(/No active sessions/)).toBeDefined();
  });

  it("groups by project and renders rows", () => {
    render(wrap(<ActiveSessionsLive sessions={[HOT, COOLING]} />));
    expect(screen.getAllByText(/alpha/).length).toBeGreaterThan(0);
    expect(screen.getByText(/abcd1234/)).toBeDefined();
  });

  it("renders countdown for cooling sessions only", () => {
    render(wrap(<ActiveSessionsLive sessions={[HOT, COOLING]} />));
    expect(screen.getByText(/auto-dump in/)).toBeDefined();
  });

  it("Dump now button is present for assigned sessions", () => {
    render(wrap(<ActiveSessionsLive sessions={[HOT]} />));
    expect(screen.getByRole("button", { name: /Dump now/i })).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to fail**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run __tests__/widgets/ActiveSessionsLive.test.tsx`
Expected: import error.

- [ ] **Step 3: Implementation**

```tsx
// frontend/src/components/widgets/dashboard/ActiveSessionsLive.tsx
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectBadge } from "@/components/widgets/ProjectBadge";
import { LostSessionTranscriptViewer } from "@/components/widgets/LostSessionTranscriptViewer";
import { useDumpNow } from "@/hooks/dashboard/useDumpNow";
import { isUnassigned } from "@/lib/lostSessionsConst";
import type { ActiveSession } from "@/types/ActiveSession";

function formatRemaining(targetIso: string, now: number): string {
  const remaining = new Date(targetIso).getTime() - now;
  if (remaining <= 0) return "0";
  const hours = Math.floor(remaining / 3_600_000);
  const minutes = Math.floor((remaining % 3_600_000) / 60_000);
  if (hours > 0) return `${hours}h ${minutes}m`;
  const seconds = Math.floor((remaining % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

function CountdownLabel({ at }: { at: string }) {
  const { t } = useTranslation();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const remainingMs = new Date(at).getTime() - now;
  if (remainingMs <= 0) {
    return (
      <span className="text-xs text-amber-600">
        {t("overview.active.auto_dump_overdue")}
      </span>
    );
  }
  return (
    <span className="text-xs text-muted-foreground">
      {t("overview.active.auto_dump_in", { remaining: formatRemaining(at, now) })}
    </span>
  );
}

interface RowProps {
  session: ActiveSession;
  expanded: boolean;
  onToggleExpand: () => void;
}

function Row({ session: s, expanded, onToggleExpand }: RowProps) {
  const { t } = useTranslation();
  const dumpMut = useDumpNow();
  const unassigned = isUnassigned(s.project_name);
  const statusEmoji = s.status === "hot" ? "🟢" : "🟡";
  return (
    <div className="rounded-md border bg-background">
      <div className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
        <span>{statusEmoji}</span>
        <ProjectBadge name={s.project_name} />
        <span className="font-mono text-xs">{s.session_id.slice(0, 8)}…</span>
        {s.cwd && (
          <span className="truncate text-xs text-muted-foreground" title={s.cwd}>
            {s.cwd}
          </span>
        )}
        {s.auto_dump_at && <CountdownLabel at={s.auto_dump_at} />}
        <div className="ml-auto flex gap-2">
          <Button
            size="sm"
            variant={expanded ? "default" : "outline"}
            onClick={onToggleExpand}
          >
            <BookOpen className="mr-1 h-3 w-3" />
            {t("overview.active.read_button")}
          </Button>
          {!unassigned && (
            <Button
              size="sm"
              disabled={dumpMut.isPending}
              onClick={() =>
                dumpMut.mutate({
                  sessionId: s.session_id,
                  body: { project_name: s.project_name },
                })
              }
            >
              <Download className="mr-1 h-3 w-3" />
              {t("overview.active.dump_now_button")}
            </Button>
          )}
        </div>
      </div>
      {expanded && (
        <div className="px-3 pb-3">
          <LostSessionTranscriptViewer sessionId={s.session_id} enabled={expanded} />
        </div>
      )}
    </div>
  );
}

export function ActiveSessionsLive({ sessions }: { sessions: ActiveSession[] }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const groups = useMemo(() => {
    const m = new Map<string, ActiveSession[]>();
    for (const s of sessions) {
      const arr = m.get(s.project_name) ?? [];
      arr.push(s);
      m.set(s.project_name, arr);
    }
    return Array.from(m.entries());
  }, [sessions]);

  if (sessions.length === 0) {
    return (
      <section className="rounded-md border bg-background p-3">
        <h2 className="text-sm font-semibold mb-2">{t("overview.active.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("overview.active.empty")}</p>
      </section>
    );
  }

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <section className="rounded-md border bg-background p-3">
      <h2 className="text-sm font-semibold mb-2">{t("overview.active.title")}</h2>
      <div className="space-y-3">
        {groups.map(([project, items]) => (
          <div key={project} className="space-y-2">
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {project}
            </div>
            {items.map((s) => (
              <Row
                key={s.session_id}
                session={s}
                expanded={expanded.has(s.session_id)}
                onToggleExpand={() => toggle(s.session_id)}
              />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run __tests__/widgets/ActiveSessionsLive.test.tsx`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/dashboard/ActiveSessionsLive.tsx frontend/src/__tests__/widgets/ActiveSessionsLive.test.tsx
git commit -m "feat(widget): ActiveSessionsLive with countdown + dump-now + transcript reader"
```

---

### Task 15: HealthDot widget (uses existing useHealth)

**Files:**
- Create: `frontend/src/components/widgets/dashboard/HealthDot.tsx`
- Test: `frontend/src/__tests__/widgets/HealthDot.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/widgets/HealthDot.test.tsx
import { describe, it, expect, beforeAll, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import i18n from "../../i18n";
import { HealthDot } from "../../components/widgets/dashboard/HealthDot";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    overview: {
      health_dot: { ok: "Healthy", warning: "Warnings", critical: "Critical", details_link: "→ Details" },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

vi.mock("../../hooks/useHealth", () => ({
  useHealth: () => ({
    data: { status: "ok", alerts_count: 0 },
    isLoading: false,
  }),
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient();
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("HealthDot", () => {
  it("renders Healthy state", () => {
    render(wrap(<HealthDot />));
    expect(screen.getByText(/Healthy/)).toBeDefined();
  });
});
```

- [ ] **Step 2: Run test to fail**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run __tests__/widgets/HealthDot.test.tsx`
Expected: import error.

- [ ] **Step 3: Implementation**

```tsx
// frontend/src/components/widgets/dashboard/HealthDot.tsx
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { useHealth } from "@/hooks/useHealth";

export function HealthDot() {
  const { t } = useTranslation();
  const q = useHealth();
  const status = q.data?.status ?? "ok";
  const alertsCount = q.data?.alerts_count ?? 0;

  const isOk = status === "ok" && alertsCount === 0;
  const dotColor = isOk
    ? "bg-emerald-500"
    : status === "degraded" || alertsCount > 0
    ? "bg-amber-500"
    : "bg-rose-500";
  const label = isOk
    ? t("overview.health_dot.ok")
    : alertsCount > 0
    ? t("overview.health_dot.warning")
    : t("overview.health_dot.critical");

  return (
    <Link to="/health" className="flex items-center gap-2 text-xs hover:underline">
      <span className={`inline-block h-2 w-2 rounded-full ${dotColor}`} />
      <span>{label}</span>
      <span className="text-muted-foreground">{t("overview.health_dot.details_link")}</span>
    </Link>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run __tests__/widgets/HealthDot.test.tsx`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/dashboard/HealthDot.tsx frontend/src/__tests__/widgets/HealthDot.test.tsx
git commit -m "feat(widget): HealthDot reusing existing useHealth"
```

---

## Phase 6: Frontend Integration

### Task 16: Overview.tsx full rewrite

**Files:**
- Modify (rewrite): `frontend/src/pages/Overview.tsx`
- Test: `frontend/src/__tests__/Overview.test.tsx`

- [ ] **Step 1: Read current Overview.tsx for context**

Run: `cat /d/code/claude-mnemos/frontend/src/pages/Overview.tsx`
Note current imports — keep ProjectCardsGrid + HookStatusBanner usage. Replace 3-column grid with new operational layout.

- [ ] **Step 2: Write the failing test**

```tsx
// frontend/src/__tests__/Overview.test.tsx
import { describe, it, expect, beforeAll, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Overview } from "../pages/Overview";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    overview: {
      kpi: {
        queue_label: "Queue", queue_format: "{{queued}} queued · {{running}} running · {{failed}} failed",
        active_label: "Active", active_format: "🟢 {{hot}} · 🟡 {{cooling}}",
        today_label: "Today", today_format: "{{ingest}} ingest · {{pages}} pages",
        tokens_label: "Tokens", lost_label: "Lost", lost_link: "→ Sort",
      },
      running: { title: "Running now", elapsed: "{{seconds}}s elapsed", empty: "Nothing" },
      active: { title: "Active sessions", empty: "No active", dump_now_button: "Dump", read_button: "Read",
                auto_dump_in: "in {{remaining}}", auto_dump_overdue: "now" },
      health_dot: { ok: "OK", warning: "warn", critical: "crit", details_link: "→" },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

vi.mock("../hooks/useProjects", () => ({
  useProjects: () => ({ data: [], isLoading: false }),
}));

vi.mock("../hooks/useHealth", () => ({
  useHealth: () => ({ data: { status: "ok", alerts_count: 0 }, isLoading: false }),
}));

const SNAPSHOT = {
  kpi: {
    queue: { queued: 0, running: 0, failed: 0 },
    active: { hot: 0, cooling: 0 },
    today: { ingest_count: 0, pages_count: 0 },
    tokens_today: 0,
    lost_total: 0,
  },
  active_sessions: [],
  running_jobs: [],
  errors: [],
};

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Overview", () => {
  it("renders KpiBar + RunningJobsLive + ActiveSessionsLive sections", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: SNAPSHOT });
    render(wrap(<Overview />));
    await waitFor(() => expect(screen.getByText(/Queue/)).toBeDefined());
    expect(screen.getByText(/Running now/)).toBeDefined();
    expect(screen.getByText(/Active sessions/)).toBeDefined();
  });
});
```

- [ ] **Step 3: Run test to fail (or pass with stale Overview)**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run __tests__/Overview.test.tsx`
Expected: FAIL — текущий Overview не рендерит новые секции.

- [ ] **Step 4: Rewrite Overview.tsx**

```tsx
// frontend/src/pages/Overview.tsx
import { useTranslation } from "react-i18next";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardSnapshot } from "@/hooks/dashboard/useDashboardSnapshot";
import { useProjects } from "@/hooks/useProjects";
import { KpiBar } from "@/components/widgets/dashboard/KpiBar";
import { RunningJobsLive } from "@/components/widgets/dashboard/RunningJobsLive";
import { ActiveSessionsLive } from "@/components/widgets/dashboard/ActiveSessionsLive";
import { HealthDot } from "@/components/widgets/dashboard/HealthDot";
import { ProjectCard } from "@/components/widgets/ProjectCard";
import { HookStatusBanner } from "@/components/widgets/HookStatusBanner";
import { NoProjectsCallout } from "@/components/widgets/NoProjectsCallout";

export function Overview() {
  const { t } = useTranslation();
  const snapshot = useDashboardSnapshot();
  const projects = useProjects();

  if (projects.isLoading || snapshot.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-12" />
        <Skeleton className="h-32" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if ((projects.data?.length ?? 0) === 0) {
    return <NoProjectsCallout />;
  }

  const data = snapshot.data;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("overview.title", "Overview")}</h1>
        <HealthDot />
      </div>
      <HookStatusBanner />
      {data && (
        <>
          {data.errors.length > 0 && (
            <div className="rounded border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs">
              {data.errors.join(" · ")}
            </div>
          )}
          <KpiBar data={data.kpi} />
          <RunningJobsLive jobs={data.running_jobs} />
          <ActiveSessionsLive sessions={data.active_sessions} />
        </>
      )}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold">{t("overview.projects_heading", "Projects")}</h2>
        <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {(projects.data ?? []).map((p) => (
            <ProjectCard key={p.name} project={p} />
          ))}
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 5: Run all frontend tests**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run`
Expected: all pass (309 + new ones).

- [ ] **Step 6: Type-check + lint + build**

Run sequentially:
```bash
cd /d/code/claude-mnemos/frontend && pnpm tsc --noEmit
cd /d/code/claude-mnemos/frontend && pnpm lint 2>&1 | tail -5
cd /d/code/claude-mnemos/frontend && pnpm build 2>&1 | tail -3
```

Expected: tsc 0 errors, lint 0 errors (warnings ok), build success.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Overview.tsx frontend/src/__tests__/Overview.test.tsx
git commit -m "feat(overview): operational dashboard rewrite (KPI + running + active + health)"
```

---

## Phase 7: Visual Polish (frontend-design skill)

### Task 17: Production-grade visual polish via frontend-design skill

**Files:**
- Iterates on: all `frontend/src/components/widgets/dashboard/*.tsx` + `frontend/src/pages/Overview.tsx`

- [ ] **Step 1: Invoke frontend-design skill**

Use the Skill tool with name `frontend-design`. Provide the skill with:
- Spec: `docs/superpowers/specs/2026-05-03-operational-overview-design.md`
- Currently implemented files list (from File Structure section)
- Existing design tokens: shadcn/ui + Tailwind v4 + OKLCH + Geist Sans/Mono
- Icons: lucide-react

- [ ] **Step 2: Apply skill output to widgets**

Update each widget's CSS classes / layout based on skill recommendations. Common areas to refine:
- Visual hierarchy of KpiBar tiles (sizing, accent color usage)
- Spacing in Active sessions rows (multi-line layout for cwd preview)
- Countdown styling (monospace, warn-red when < 1h)
- Empty states (illustration / better tone)

- [ ] **Step 3: Re-run all FE tests after styling changes**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run && pnpm tsc --noEmit && pnpm build 2>&1 | tail -3`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/widgets/dashboard/ frontend/src/pages/Overview.tsx
git commit -m "polish(overview): production-grade visual refinement via frontend-design skill"
```

---

## Phase 8: Live Walk Verification

### Task 18: Restart daemon, hard-refresh, manual test scenarios

**Files:** none new — verification only.

- [ ] **Step 1: Stop daemon and start fresh**

```bash
~/pipx/venvs/claude-mnemos/Scripts/mnemos.exe daemon stop
~/pipx/venvs/claude-mnemos/Scripts/mnemos.exe daemon start
```

Wait 3 seconds, verify `daemon status` returns running.

- [ ] **Step 2: Verify cron job registered**

```bash
curl -sS http://127.0.0.1:5757/api/health | python -c "import json,sys; d=json.load(sys.stdin); print([j for j in d.get('scheduler_jobs',[]) if 'auto_dump' in j.get('id','')])"
```

Expected: list contains `auto_dump_global`.

- [ ] **Step 3: Verify snapshot endpoint**

```bash
curl -sS http://127.0.0.1:5757/api/dashboard/snapshot | python -m json.tool | head -30
```

Expected: JSON with `kpi`, `active_sessions`, `running_jobs`, `errors` keys.

- [ ] **Step 4: Open dashboard with hard refresh**

In browser: navigate to http://localhost:5757/, press Ctrl+Shift+R.

Verify visually:
- KpiBar with 5 tiles renders.
- RunningJobsLive shows "Nothing running" (or actual jobs if some are running).
- ActiveSessionsLive shows "No active sessions" (or your live JSONLs).
- ProjectCardsGrid below.
- HealthDot top right.

- [ ] **Step 5: (Optional) Force an active session**

```bash
# Touch a recent jsonl in ~/.claude/projects/<some-project>/<sid>.jsonl
# OR start a new Claude Code session in any project; it should appear within 10s.
```

Wait 10 seconds, refresh dashboard. Sessia должна появиться в ActiveSessionsLive со статусом 🟢.

- [ ] **Step 6: Smoke test "Dump now"**

Click "Dump now" button on an active assigned session. Expected:
- Toast «Queued for dump».
- Sessia пропадает из ActiveSessionsLive в течение 10-30 сек (после ingest worker).
- В Sessions странице соответствующего проекта появляется новый chat.

- [ ] **Step 7: No commit** — this is just verification.

---

## Phase 9: Memory Snapshot

### Task 19: Update memory and create session snapshot

**Files:**
- Create: memory file (`session_2026-XX-XX_operational_overview_complete.md` in user's memory dir)
- Update: `MEMORY.md` index

- [ ] **Step 1: Create memory snapshot**

Write a session-snapshot file describing:
- What shipped in this iteration
- Verify status (test counts before/after)
- Open follow-ups (uk/ru i18n, per-project override, MetricsToday, etc — copy from spec §13)
- File-anchor map (production files)

- [ ] **Step 2: Update MEMORY.md index** with one-line entry pointing to the new snapshot.

---

## Notes for executor

- **Always run from `~/pipx/venvs/claude-mnemos/Scripts/python.exe`** (not system Python). Same for pytest.
- **Frontend always under `cd /d/code/claude-mnemos/frontend`** before pnpm commands.
- **Per-task commit cadence:** every task ends with a commit. If a task seems to take more than ~10 minutes between commits, that's a sign to re-decompose.
- **JSON locale validity:** after every i18n edit, run the python json.load check.
- **When stuck on regression:** run the smallest existing test that exercised the touched module BEFORE you debug — `pytest tests/path/to/test.py -v`.
- **No new endpoints in v1 beyond the three listed** (`/dashboard/snapshot`, `/dashboard/active-sessions/{id}/dump-now`, `/dashboard/scan-active`). Anything else is v2.
- **No new i18n languages in v1**. Only `en.json` keys. uk/ru/en parity is a separate v2 task.
