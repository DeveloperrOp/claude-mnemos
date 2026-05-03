# Three Essentials — Design Spec

**Date:** 2026-05-03 (evening)
**Status:** Draft, approved via dialogue
**Scope:** 3 production-safety features — pre-compact hook, health-monitor with persistence, inject context visualization

## TL;DR

Three independent features. After today's redesign + Operational Overview + auto-dump, these three close the remaining production-safety gaps:

1. **Pre-compact hook** — capture transcript snapshot before Claude `/compact` truncates context (data-loss prevention).
2. **Health-monitor** — 7 semantic detectors running on a 5-min cron, with persistence + silence/snooze. Alert banner on Overview.
3. **Inject context visualization** — per-project widget showing tokens, limit, pages list, and inject-preview text.

After these mnemos passes the bar of "you'll know if something is broken" — the main gap vs `.shared`.

## Goals

- **Data safety** — pre-compact closes a data-loss vector when SessionEnd hook misses.
- **Observability** — operator sees system health with one glance at Overview.
- **Confidence in inject** — operator verifies system is doing its job (memory across sessions).

## Non-Goals

- HITL staging UI / diff view (deferred — depends on whether ingest_mode=hybrid is wanted).
- Memory tools (archive log, split index, Claude optimize) — deferred, premature for current vault size.
- Vault initialization helper — deferred, no public release yet.

---

## Feature A — Pre-compact hook

### Problem
Claude Code emits a `PreCompact` event before truncating context. mnemos currently subscribes only to `SessionStart` + `SessionEnd`. If a long session is `/compact`-ed and the user does not exit cleanly, the pre-compact transcript content is lost.

### Solution
Add a `PreCompact` hook that mirrors `SessionEnd` flow with a `-precompact` suffix on the dumped raw chat file.

### Files
- Create: `hooks/pre_compact.py`
- Modify: `hooks/hooks.json` — add PreCompact entry
- Test: `tests/plugin/test_pre_compact_hook.py`

### Behaviour
- On `PreCompact` event, hook receives `{transcript_path, session_id, project, ...}`.
- POST to `/api/jobs` (kind=ingest) with payload `{transcript_path, extract: false, raw_filename_suffix: "-precompact"}`.
- Worker writes to `<vault>/raw/chats/<session_id>-precompact.md`.
- Manifest gets entry with `kind=ingest_raw_only` for the precompact snapshot.
- Idempotency: SHA-based manifest filter prevents duplicates if the same transcript bytes seen twice.

### Risk
**Low.** Additive — no existing hook behaviour changes. Worker already supports `extract: false`. Race with SessionEnd is handled by manifest filter (idempotent).

---

## Feature B — Health-monitor with persistence

### Problem
Daemon currently only has watchdog-level alerts (file-system events, parse errors). No business-level detectors. Operator does not know when:
- Hooks have stopped firing (pre-existing bug we found 2026-05-01).
- Auto-dump cron has not run for hours.
- Ingest is failing in a streak (Claude-cli rate-limit, broken transcripts).
- Disk is filling up.
- A job is stuck in `running` for 30+ minutes.
- `project-map.json` is corrupted.
- Daemon connectivity (handled implicitly by frontend already, but worth confirming on health page).

Old alerts are also in-memory only — restart = forget.

### Solution
- New `core/health_checks.py` with 7 check functions.
- New `state/alerts_store.py` for persistent alerts (file: `~/.claude-mnemos/alerts.json`) with silence support.
- Scheduler task `health_checks_task` runs every 5 min from `daemon/process.py`.
- New REST endpoints: `GET /api/health-alerts`, `POST /api/health-alerts/{id}/silence`, `POST /api/health-alerts/{id}/dismiss`.
- Frontend widget `HealthAlertsBar` on Overview (collapsible if > 3).

### Files
- Create: `claude_mnemos/core/health_checks.py`
- Create: `claude_mnemos/state/alerts_store.py`
- Create: `claude_mnemos/daemon/routes/health_alerts.py`
- Create: `frontend/src/components/widgets/dashboard/HealthAlertsBar.tsx`
- Create: `frontend/src/hooks/dashboard/useHealthAlerts.ts`, `useSilenceAlert.ts`, `useDismissAlert.ts` (rename existing if needed)
- Modify: `claude_mnemos/daemon/process.py` — register `health_checks_global` cron
- Modify: `claude_mnemos/daemon/app.py` — include `health_alerts` router
- Modify: `frontend/src/pages/Overview.tsx` — render `<HealthAlertsBar />` after `<HookStatusBanner />`
- Modify: `frontend/public/locales/en.json` — i18n keys
- Tests: `tests/core/test_health_checks.py`, `tests/state/test_alerts_store.py`, `tests/daemon/test_app_health_alerts.py`

### Detector list (the actual 7 — final)

| Id | Trigger | Severity | Suggested message |
|---|---|---|---|
| `auto_dump_overdue` | last `auto_dump_global` cron run > 2h ago | warning | "Auto-dump cron last ran HH ago. Safety net may be broken." |
| `ingest_failure_streak` | 3 most-recent `ingest` jobs in last 24h all `failed_permanent` | critical | "3 ingest jobs failed in a row. Check dead-letter for traceback." |
| `runaway_job` | any job with `status=running` and `started_at` > 30 min ago | warning | "Job {id} running for {minutes} min. May be stuck." |
| `hook_silence` | no successful hook-log entries (SessionEnd/PreCompact) in last 6h despite recent active sessions in `~/.claude/projects/` | warning | "Hooks may have stopped firing. Check `mnemos hooks status`." |
| `disk_low` | free space on vault disk < 5% | critical | "Disk {drive} only {pct}% free. Vault writes may fail." |
| `project_map_broken` | `project-map.json` failed Pydantic load on last attempt | critical | "project-map.json is corrupted. Restore from .backups/." |
| `daemon_uptime_warning` | daemon uptime < 60s (just restarted) | info | "Daemon recently restarted at HH:MM." (auto-dismisses after 10 min) |

### `AlertsStore` model
```python
class StoredAlert(BaseModel):
    id: str           # stable id like "auto_dump_overdue" — overwrites on update
    detector: str     # detector function name
    severity: Literal["info", "warning", "critical"]
    message: str
    context: dict[str, Any]    # detector-specific data
    first_seen: datetime
    last_seen: datetime
    silenced_until: datetime | None
    dismissed: bool

class AlertsStore(BaseModel):
    version: Literal[1] = 1
    alerts: list[StoredAlert]

    @classmethod
    def load(cls) -> AlertsStore: ...
    def save(self) -> None: ...    # atomic write
    def upsert(self, alert: StoredAlert) -> None: ...
    def silence(self, alert_id: str, duration: timedelta) -> None: ...
    def dismiss(self, alert_id: str) -> None: ...
    def active_alerts(self, *, now: datetime) -> list[StoredAlert]: ...
```

### REST shape
```
GET /api/health-alerts
  → {alerts: StoredAlert[], silenced: StoredAlert[]}

POST /api/health-alerts/{id}/silence
  body: {duration_hours: int}    # 1, 24, or huge for "forever"
  → 200 {ok: true}

POST /api/health-alerts/{id}/dismiss
  → 200 {ok: true}
```

### Risk
**Low-Medium.**
- Additive scheduler task. No existing behaviour changes.
- `AlertsStore` writes one JSON file, atomic via `core/atomic.py`.
- New router prefix doesn't collide with existing `/api/alerts` (in-memory daemon alerts) — kept separate intentionally; later release can merge.
- Each detector wrapped in try/except — one bad detector won't crash the cron.

---

## Feature C — Inject context visualization

### Problem
mnemos's central value is "memory across sessions" via inject. Operator currently has no UI to verify it works:
- How many tokens go into next session inject?
- Which pages are included?
- Is the inject being truncated against limit?
- What does Claude actually see at session start?

`core/session_start.py::build_adaptive_context_with_stats` already computes everything. Just not exposed.

### Solution
- New REST endpoint exposing inject preview per project.
- Frontend widget `InjectPreview` shown on `ProjectView` page (and read-only summary in Overview KpiBar).
- TTL cache 30s on backend so widget polling doesn't re-compute.

### Files
- Create: `claude_mnemos/daemon/routes/inject_preview.py`
- Create: `frontend/src/components/widgets/InjectPreview.tsx`
- Create: `frontend/src/hooks/useInjectPreview.ts`
- Modify: `frontend/src/pages/ProjectView.tsx` — render `<InjectPreview project={...} />`
- Modify: `claude_mnemos/daemon/app.py` — include router
- Modify: `frontend/public/locales/en.json` — i18n keys
- Tests: `tests/daemon/test_app_inject_preview.py`, `frontend/src/__tests__/widgets/InjectPreview.test.tsx`

### REST shape
```
GET /api/projects/{name}/inject-preview
  → {
      tokens_estimate: int,
      limit: int,
      ratio: float,         // 0.0–1.5  (>1.0 means truncated)
      pages: [
        {path: str, slug: str, score: float, included: bool}
      ],
      preview_text: str,    // the actual inject text, truncated to first ~5000 chars
      computed_at: ISO datetime
    }
```

### Widget UX
- Eyebrow label "INJECT CONTEXT"
- Big mono number `12.5K / 50K` (tokens / limit) using `hero-num`
- Three-zone progress bar:
  - 0–75%: green
  - 75–100%: amber
  - >100%: red (with "TRUNCATED" badge)
- Collapsible "Pages included (12)" — expandable list with scores
- Collapsible "Preview" — `<pre>` block with first ~5000 chars of inject text + "show full" link

### Risk
**Low.** Read-only endpoint. TTL cache prevents recompute storm. Frontend widget is additive.

---

## Cross-feature integration

### Order of implementation
A → C → B (A is smallest and most independent; C uses existing data; B is largest and best done last so health-monitor can include detectors that observe outputs of A+C if needed).

Actually — these three are file-disjoint. They can be implemented in parallel by separate subagents. We'll dispatch 3 subagents.

### Tests target after merge
- Backend pytest: was 1620, target ~1660 (40 new tests).
- Frontend Vitest: was 325, target ~340 (15 new tests).
- TypeScript: 0 errors.
- Lint: 0 new errors (warnings count unchanged).
- Build: ✓.

### Live walk verification
After merge:
1. Restart daemon to pick up new routes + scheduler.
2. Trigger pre-compact via `/compact` in a test Claude session, verify file created in `<vault>/raw/chats/<sid>-precompact.md`.
3. Visit Overview — confirm `HealthAlertsBar` visible (or absent if no alerts; force-trigger one detector for visual check).
4. Click Silence on alert → verify reappears as silenced + does not show in main bar; verify reappears after silence expires.
5. Visit ProjectView — confirm `InjectPreview` widget renders with data.

### Performance budget
- `/api/health-alerts` should respond < 50ms (read JSON file).
- `/api/projects/{name}/inject-preview` should respond < 200ms cached, < 1s uncached (depends on vault size).
- Health checks cron < 2s wall clock total (7 detectors).

### Rollback
Each feature ships in its own commit. Revert is per-feature.

---

## Non-issues

- `core/staging.py` exists as backend-stub — leave for now. Decision deferred (HITL).
- `tokens_today = 0` in dashboard KPI — deferred. Cosmetic. Will close in followup.
- Side-by-side diff viewer — deferred (depends on staging being kept).
