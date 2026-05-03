# Operational Overview Dashboard — Design Spec (MVP v1)

**Date:** 2026-05-03
**Status:** Draft, post-adversarial-review
**Combines:** P0 (operational Overview redesign) + P1 (live-tracking active sessions + 24h auto-dump safety)

## 1. TL;DR

Перерисовка главной mnemos из «3-column grid project cards» в operational dashboard. На одной странице оператор видит KPI cross-project, running jobs, активные сессии (с countdown до auto-dump). Параллельно — backend-инфраструктура live-tracking активных сессий + cron на 24h auto-dump (страховка от потери данных при VSCode `/clear` баге).

После adversarial review scope урезан: убраны новый alerts framework (использует существующую систему), MetricsToday, LostSessionsCompact, CountdownProvider, settings UI для auto_dump_after_hours, AutoDumpResult model. Один общий scanner для lost+active, общий TTL cache, asyncio-lock против stampede.

## 2. Background

Текущий Overview = `ProjectCardsGrid + HookStatusBanner`. Чтобы оператор увидел «что прямо сейчас» нужно 3-4 клика. `.shared` (референс) показывал всё на одной главной с auto-refresh.

Главный риск без этой работы: **VSCode `/clear` баг** убивает сессию без trigger SessionEnd-хука; транскрипт остаётся в `~/.claude/projects/` JSONL, но в vault не попадает. Это причина почему `.shared` сделал свой Fix #8.

## 3. Goals

- **Safety** — auto-dump assigned-сессий с mtime > 24ч (constant).
- **Observability** — оператор видит state с порога без drilling.
- **Reuse existing** — `LostSessionsCache` infra, `JobStore`, `ProjectResolver`, APScheduler, `useHealth`, `Alerts`.

## 4. Non-Goals (v1)

- Auto-ingest (LLM extraction). Auto-dump использует `extract: false`.
- Auto-dump для unassigned (cwd не matches проект). Они остаются в `/lost-sessions`.
- Push-based watchdog для active-sessions (pull раз в 10s достаточно).
- Cancel running jobs (только queued — это всё что поддерживает JobStore).
- **Per-project auto_dump_after_hours** — v2.
- **Новый alerts framework со snooze** — переиспользуем `daemon/alerts.py` + `useAlerts` + dismiss.
- **MetricsToday виджет** — линк на /metrics достаточен.
- **LostSessionsCompact** — плитка в KpiBar + sidebar.
- **Settings UI для auto_dump_after_hours** — захардкожено 24ч.

## 5. Architecture Overview

### 5.1 Backend новые модули

```
claude_mnemos/
├── core/
│   ├── ttl_cache.py            [NEW]  generic TTLCache[T] with asyncio.Lock
│   ├── transcript_scanner.py   [NEW]  единый scan ~/.claude/projects/
│   ├── active_sessions.py      [NEW]  projection: hot/cooling
│   └── auto_dump.py            [NEW]  auto_dump_stale()
└── daemon/
    └── routes/
        └── dashboard.py        [NEW]  один endpoint /api/dashboard/snapshot
```

### 5.2 Backend изменения существующего

- `daemon/process.py` — register cron `auto_dump_global` (hourly) + `asyncio.create_task(catch_up)` ПОСЛЕ `_bootstrap_runtimes` complete (race fix).
- `core/lost_sessions.py` — `scan_lost_sessions` рефакторен, чтобы использовать общий `transcript_scanner.py` (без изменения внешнего API).

### 5.3 Frontend новые модули

```
frontend/src/
├── pages/Overview.tsx                    [REWRITTEN]
├── components/widgets/dashboard/
│   ├── KpiBar.tsx                        [NEW]  4 плитки
│   ├── RunningJobsLive.tsx               [NEW]
│   ├── ActiveSessionsLive.tsx            [NEW]  countdown через локальный setInterval
│   └── HealthDot.tsx                     [NEW]  цветной dot, использует useHealth
├── hooks/dashboard/
│   ├── useDashboardSnapshot.ts           [NEW]  единый горячий
│   └── useDumpNow.ts                     [NEW]  mutation
└── types/ActiveSession.ts                [NEW]
```

## 6. Backend Detailed Design

### 6.1 `core/ttl_cache.py` (NEW)

```python
from typing import Generic, TypeVar, Callable, Awaitable
import asyncio, time

T = TypeVar("T")

class TTLCache(Generic[T]):
    """Async TTL cache with anti-stampede inflight-future pattern.
    
    Concurrent get_or_compute() calls during stale state share a single
    in-flight future — never spawn N parallel computations.
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
                return await self._inflight
            self._inflight = asyncio.get_event_loop().create_future()
        try:
            result = await fn()
            self._items = result
            self._expires_at = time.monotonic() + self._ttl_s
            self._inflight.set_result(result)
            return result
        finally:
            self._inflight = None
    
    def invalidate(self) -> None:
        self._items = None
        self._expires_at = 0.0
```

### 6.2 `core/transcript_scanner.py` (NEW)

```python
@dataclass
class TranscriptEntry:
    """Сырая запись о jsonl-файле — общий результат скана."""
    session_id: str          # = path.stem
    transcript_path: str
    sha: str                 # SHA-256 файла
    size_bytes: int
    mtime: datetime          # UTC
    cwd: str | None
    preview: str | None

async def scan_transcripts(
    transcripts_root: Path | None = None,
) -> list[TranscriptEntry]:
    """Pull-based scan ~/.claude/projects/. 
    Возвращает все .jsonl без фильтрации — projection делается в caller.
    
    Каждый файл — один stat + один sha256_file + одно extract_cwd_and_preview.
    """
```

`lost_sessions.py` и `active_sessions.py` оба фильтруют результат `scan_transcripts()` — без дубль-IO.

Cache: `_TRANSCRIPTS_CACHE = TTLCache[list[TranscriptEntry]](ttl_s=10)`. `lost_sessions.py` (TTL=60s) внутри использует тот же cache, но обёртку с локальным TTL — приемлемо потому что lost-данные не критичны к 10s свежести (cache из active-flow всегда до 10s свежий).

### 6.3 `core/active_sessions.py` (NEW)

```python
class ActiveSession(BaseModel):
    session_id: str
    transcript_path: str
    sha: str
    project_name: str          # "__unassigned__" если cwd не matches
    cwd: str | None
    preview: str | None
    mtime: datetime
    size_bytes: int
    status: Literal["hot", "cooling"]   # hot=<30мин, cooling=<24ч
    auto_dump_at: datetime | None       # mtime + 24h для assigned

HOT_THRESHOLD_MIN = 30
COOLING_THRESHOLD_HOURS = 24

async def scan_active_sessions(
    runtimes_snapshot: list[VaultRuntime],
) -> list[ActiveSession]:
    """1. await scan_transcripts() (через общий cache).
    2. Filter: mtime > now - 24h.
    3. Filter: sha not in union(manifest.ingested for runtime in runtimes).
    4. Resolve cwd → project_name (or __unassigned__).
    5. Status = hot/cooling.
    6. auto_dump_at = mtime+24h для assigned, None для unassigned.
    """
```

### 6.4 `core/auto_dump.py` (NEW)

```python
COOLING_THRESHOLD_HOURS = 24
MAX_PER_RUN = 50

async def auto_dump_stale(runtimes: dict[str, VaultRuntime]) -> int:
    """Для assigned-сессий с mtime > COOLING_THRESHOLD_HOURS не ingested:
    enqueue ingest job extract=False в правильный VaultRuntime.job_store.
    
    Cap at MAX_PER_RUN. Skip __unassigned__.
    Idempotency: manifest filter уже исключает ingested. Если cron сдвоится
    или dump-now пересечётся, worker сделает no-op на дубль (manifest hit).
    
    Returns: int количество enqueued. Для логирования.
    """
    log.info("auto_dump: queued=%d", queued)
    return queued
```

**Без AutoDumpResult Pydantic — `int` достаточно.**
**Без LIKE-проверки pending — manifest filter в worker защищает от вреда.**

### 6.5 Scheduler регистрация (`daemon/process.py`)

```python
# В run() ПОСЛЕ await self._bootstrap_runtimes() вернётся:
self.scheduler.add_job(
    auto_dump_task,
    "cron",
    minute=0,
    args=[self.runtimes],     # передаём live dict, не snapshot
    id="auto_dump_global",
    replace_existing=True,
)
self.scheduler.start()

# Catch-up после полного bootstrap, не во время:
asyncio.create_task(auto_dump_stale(self.runtimes))
```

`auto_dump_task` итерирует `runtimes.values()` внутри — берёт текущее состояние при каждом запуске cron'а (видит hot-mounted vaults).

### 6.6 REST endpoint (`daemon/routes/dashboard.py`)

```
GET  /api/dashboard/snapshot
     → {
         kpi: {
           queue: {queued, running, failed},
           active: {hot, cooling},
           today: {ingest_count, pages_count},   # из state/activity.py count за UTC-day
           tokens_today: int,
           lost_total: int,
         },
         active_sessions: ActiveSession[],
         running_jobs: RunningJob[],
       }

POST /api/dashboard/active-sessions/{session_id}/dump-now
     body: {project_name: str}
     → enqueue ingest job extract=False, returns Job

POST /api/dashboard/scan-active                    # invalidates active cache
     → {scanned: int}
```

**Per-aggregator try/except в snapshot endpoint** — если scan_active падает, возвращаем `active_sessions: []` + `errors: ["active_sessions: ..."]` поле, остальные данные доходят до UI. Frontend рендерит deg-state per-widget.

**Health/Alerts/Metrics endpoints НЕ создаются** — Frontend использует существующие `useHealth()`, `useAlerts()`, `/metrics` page.

### 6.7 Settings

`auto_dump_after_hours` — **константа 24** в `core/auto_dump.py`. **Без Config поля, без Settings UI.** v2 если понадобится.

## 7. Frontend Detailed Design

### 7.1 `pages/Overview.tsx` структура

```tsx
<Overview>
  <header>
    <h1>...</h1>
    <HealthDot />              {/* использует useHealth, ссылка на /health */}
  </header>
  <KpiBar />                   {/* 4 плитки + lost-count тоже здесь */}
  <RunningJobsLive />          {/* список или empty */}
  <ActiveSessionsLive />       {/* группа по проекту, локальный countdown */}
  <ProjectCardsGrid />         {/* существующий */}
</Overview>
```

### 7.2 `KpiBar.tsx`

5 плиток (изначально 4 + 1 для lost):
- 📋 Очередь: `queued · running · failed`
- 🔥 Активные: `🟢 N · 🟡 M`
- ⏱ Сегодня: `5 ingest · 12 pages`
- 💉 Tokens: `862K`
- 📦 Lost: `1304 → Розібрати` (link to /lost-sessions)

Conditional accent: red если failed > 0, amber если cooling > 0.

### 7.3 `RunningJobsLive.tsx`

Per-row: kind badge, project_name, elapsed time. **Без cancel button** (JobStore не поддерживает cancel running). Empty state: "😴 Ничего не запущено".

### 7.4 `ActiveSessionsLive.tsx`

Группа по `project_name`. Per-row: ProjectBadge, session_id (8 chars), mtime relative, status badge 🟢/🟡, countdown (только cooling), кнопки `📥 Затащить сейчас`, `📖 Читать`.

**Countdown:** локальный `useState(Date.now())` + `useEffect(setInterval(1s))` прямо в компоненте. Один tick на компонент, не глобальный context. При unmount — clearInterval. Если виджет не виден (другая страница) — не тикает.

```tsx
function CountdownLabel({ at }: { at: Date }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const remaining_ms = at.getTime() - now;
  // ... format
}
```

### 7.5 `HealthDot.tsx`

Простая компактная версия `Health.tsx` — цветной dot + label. Использует **существующий `useHealth()`**. Без отдельного API endpoint.

### 7.6 Hooks

```typescript
useDashboardSnapshot()  // refetchInterval: 10_000
useDumpNow()            // mutation, invalidates ["dashboard-snapshot"]
useScanActive()         // mutation для force-rescan
```

`useHealth()`, `useAlerts()` — существующие, переиспользуем.

## 8. Data Flow

```
~/.claude/projects/*.jsonl   (live transcripts)
        |
        | scan_transcripts() [shared cache 10s, asyncio.Lock]
        v
TranscriptEntry[]
        |
        +─── filter mtime > now-24h ──▶ scan_active_sessions ──▶ /snapshot ──▶ Overview
        |
        +─── filter mtime older     ──▶ scan_lost_sessions   ──▶ /lost-sessions

dump-now (manual or cron):
        |
        | JobStore.create(extract=false)  [no LIKE pending-check; manifest filter защищает]
        v
        ingest worker ──▶ raw/chats/X.md ──▶ manifest.ingested[sha]
                                                |
                                                v (next scan)
                                         not lost / not active anymore
```

## 9. Error Handling

**Backend:**
- `scan_transcripts` per-file try/except: skip + log warning. Не crash.
- `auto_dump_stale` per-session try/except: skip + log warning. Counter goes up.
- `/dashboard/snapshot` per-aggregator try/except: вернёт partial response + `errors: [...]`.

**Frontend:**
- React Query default retry behaviour.
- Empty states на каждом виджете.
- Если `errors` в response — показать неаккуратный warning toast «частичная загрузка».

## 10. Edge Cases (явно)

1. **VSCode /clear** — partial JSONL. Auto-dump возьмёт sha от current bytes. Если позже Claude дописывает в тот же файл — sha поменяется, scan вернёт повторно, второй ingest. **Принимается как known limitation в v1.** Workaround: caller может ручной dump-now на ранней стадии.
2. **Daemon рестарт во время auto-dump** — partial state. Manifest filter в worker делает дубль-job no-op'ом.
3. **Project удалён, sessia ещё пишется** — после удаления → cwd не resolves → status `__unassigned__` → пропадает из ActiveSessionsLive (показываются только assigned). В lost-compact цифра растёт.
4. **Mtime drift / DST** — pull-based устойчиво.
5. **Snapshot endpoint partial failure** — degraded UI (errors: [...] field).

## 11. Testing

### 11.1 Backend (pytest)

- `tests/core/test_ttl_cache.py` — concurrent get_or_compute (no stampede), TTL behavior, invalidate
- `tests/core/test_transcript_scanner.py` — fixture jsonls, mtime, cwd extraction, sha
- `tests/core/test_active_sessions.py` — status classification, attribution, manifest filter
- `tests/core/test_auto_dump.py` — assigned-only, cap, idempotent under double-cron
- `tests/daemon/test_app_dashboard.py` — endpoints, partial-failure errors[]

### 11.2 Frontend (vitest)

- `__tests__/Overview.test.tsx` — render с mock snapshot
- `__tests__/widgets/ActiveSessionsLive.test.tsx` — countdown rendering, group по проекту
- `__tests__/widgets/KpiBar.test.tsx` — accent colors, lost link
- `__tests__/widgets/RunningJobsLive.test.tsx` — empty state, list rendering
- `__tests__/api-dashboard.test.ts` — Zod validation

### 11.3 Live walk

Manual scenario при готовом коде:
1. Touch jsonl с recent mtime + cwd matching project → status=hot.
2. Mock mtime в 1ч назад → status=cooling, countdown появляется.
3. Mock mtime в 25ч → ручной cron run → enqueue ingest extract=false → manifest entry → пропадает из active.
4. Catch-up: stop daemon → mock 5 stale jsonl → start daemon → проверить что catch-up схватил.

## 12. Phasing (high-level, для writing-plans)

1. **Backend foundation**
   - `core/ttl_cache.py` + tests
   - `core/transcript_scanner.py` + tests
   - Refactor `core/lost_sessions.py` чтобы использовать общий scanner (zero behavior change, only internal)
2. **Backend feature**
   - `core/active_sessions.py` + tests
   - `core/auto_dump.py` + tests
3. **Backend integration**
   - Scheduler registration в `daemon/process.py`
   - Catch-up после bootstrap
   - `daemon/routes/dashboard.py` snapshot + dump-now + scan-active
   - Tests
4. **Frontend foundation**
   - `types/ActiveSession.ts` + Zod
   - `api/dashboard.api.ts`
   - `hooks/dashboard/useDashboardSnapshot.ts` + `useDumpNow.ts` + `useScanActive.ts`
   - i18n keys (en только)
5. **Frontend widgets** — `KpiBar`, `RunningJobsLive`, `ActiveSessionsLive`, `HealthDot`
6. **Frontend integration** — `pages/Overview.tsx` rewrite
7. **`frontend-design` skill pass** — production-grade visual mockup до final CSS polish
8. **Live walk verification** + uk/ru локализация (если время есть в фазе)

## 13. Deferred to v2

- Per-project `auto_dump_after_hours` override.
- Snooze persistence для alerts (когда реальные источники появятся).
- MetricsToday виджет.
- Phase progress в running jobs (требует JobStore refactor).
- /clear-aware sha handling (по `(session_id, size_bytes)` ключу).
- uk/ru i18n (после стабильности).

## Appendix A — File-anchor map

| Concept | New file | Existing |
|---------|----------|----------|
| TTL cache abstraction | core/ttl_cache.py | — |
| Common scanner | core/transcript_scanner.py | — |
| Active session model | core/active_sessions.py | — |
| Auto-dump | core/auto_dump.py | — |
| Dashboard routes | daemon/routes/dashboard.py | — |
| Scheduler hookup | — | daemon/process.py |
| Reused: ProjectResolver | — | mapping/resolver.py:29 |
| Reused: scan_lost_sessions (refactored internally) | — | core/lost_sessions.py |
| Reused: JobStore.create | — | state/jobs.py:175 |
| Reused: useHealth | — | frontend/src/hooks/useHealth.ts |
| Reused: useAlerts | — | frontend/src/hooks/useAlerts.ts |

## Appendix B — Adversarial review summary

Spec прошёл через 3 параллельных reviewers (Skeptic, Architect, Minimalist). Применённые findings inline:

- **Skeptic HIGH**: cache stampede → TTLCache с inflight future + asyncio.Lock.
- **Skeptic HIGH**: payload_json LIKE → dropped pending check, manifest filter защищает.
- **Skeptic HIGH**: snoozed_alerts concurrent write → весь modul удалён.
- **Skeptic MEDIUM**: catch-up race с bootstrap → catch-up после bootstrap.
- **Skeptic MEDIUM**: snapshot partial failure → per-aggregator try/except + errors[] field.
- **Architect HIGH**: health schema mismatch → используем существующий /health + useHealth.
- **Architect HIGH**: два сканера одного каталога → общий transcript_scanner.py.
- **Architect HIGH**: snoozed_alerts namespace → модуль удалён.
- **Architect MEDIUM**: TTL cache copy-paste → общий core/ttl_cache.py.
- **Architect MEDIUM**: scheduler не подписан на mount → передача live runtimes dict + iterate в task.
- **Minimalist HIGH** (×4): AlertsBar / dashboard health endpoint / auto_dump_after_hours settings / CountdownProvider — все вырезаны.
- **Minimalist MEDIUM** (×4): AutoDumpResult / LostSessionsCompact / phase progress / MetricsToday — вырезаны.
- **Minimalist LOW**: i18n тройная локализация → en-only в v1.

Deferred to v2: per-project override, snooze persistence, MetricsToday, phase progress, /clear sha edge case, uk/ru.
