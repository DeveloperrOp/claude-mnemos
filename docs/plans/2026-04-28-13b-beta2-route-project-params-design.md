# Plan #13b-β2: Per-route project params + cross-vault aggregation — design

**Status:** DRAFT
**Date:** 2026-04-28
**Branch:** `feat/13b-beta2-route-project-params`
**Predecessor:** Plan #13b-β1 (`c17fdc5`, 2026-04-28)
**Successor:** Plan #13c (SessionStart adaptive context) → Plan #14 (Dashboard)

---

## 1. Background and goals

### 1.1 Where we are

After Plan #13b-β1, `MnemosDaemon` is multi-vault (`runtimes: dict[str, VaultRuntime]` under `_runtimes_lock: asyncio.Lock`), hot mount/unmount via `/projects` CRUD works, `/jobs` POST routes by `payload["project_name"]`. **However, every route except `/jobs` POST, `/projects/*`, `/settings/*`, `/health`, `/version` still operates on a single "primary" vault** selected by `GlobalSettings.primary_project` (or alphabetical first). That primary concept was a deliberate stopgap — β1's foundation was structural, β2's job is the API surface.

Concretely, after β1:
- `app.state.vault_root: Path | None` is set to `primary_runtime.vault_root` at boot/CRUD changes.
- 11 route modules read `app.state.vault_root` via `_vault(request)` helper (or directly): `activity`, `snapshots`, `pages`, `trash`, `lint`, `ontology`, `dead_letter`, `lost_sessions`, `sessions`, `metrics`, `vault`, `health`.
- 7 route modules read per-vault state from `daemon.primary_runtime` (`tracker`, `lost_sessions_cache`, `job_store`, `job_worker`, `observer`).
- `/metrics/usage/by-project` returns `[{"project": "default", ...}]` stub instead of real aggregation.
- 6 e2e tests are skip-marked with `TODO(β2)` because they hit endpoints that need per-project params.

### 1.2 Goal of β2

Migrate every route to take an explicit project parameter per spec §10.3 contract, drop the "primary vault" concept entirely, implement real cross-vault aggregation in metrics, and re-enable all e2e tests.

After β2:
- Every per-project endpoint has `{project}` as the first path segment after the resource (e.g. `/snapshots/{project}`, `/sessions/{project}/{sid}`, `/pages/{project}/{page_id}`).
- Every global endpoint that used to single-vault becomes either:
  - Truly global (aggregates across all vaults — `/lost-sessions`, `/jobs` GET, `/dead-letter` GET).
  - Per-project but accepts optional `?project=NAME` filter (`/jobs` GET).
- `app.state.vault_root` is **gone**. Routes resolve VaultRuntime via a new `_runtime(request, project_name)` helper that returns the runtime or raises 404 if not found.
- `daemon.primary_runtime`, `_recompute_primary`, and `GlobalSettings.primary_project` are **removed**. No more "primary" anywhere.
- `/metrics/usage/by-project` iterates `daemon.runtimes` and reads each manifest, returns real per-project breakdown.
- `/lost-sessions` scans every mounted vault, results carry `project_name` for attribution.
- CLI / MCP consumers updated where they call routes that gained a `{project}` segment (mostly already correct via `--project NAME` arg passing through).
- 6 e2e tests re-enabled and passing.

### 1.3 Non-goals

- **Backwards compat for old route URLs.** β1 routes used unprefixed paths because the daemon was effectively single-vault. β2 hard-cuts: existing CLI/MCP/hook callers that still hit `/snapshots`, `/sessions/{sid}`, `/pages/{id}` etc. must be updated. There is no graceful redirection.
- Plan #13c (SessionStart adaptive context) and Plan #14 (Dashboard) — these consume the β2 API but don't ship in this plan.
- `/api/` prefix on routes — β1/α convention was paths without the `/api/` prefix (matched real codebase pragmatic style); β2 keeps that. Spec §10.3 writes URLs with `/api/` but this is a documentation choice, not a code requirement (per #13b-α decision in commit `1ce46ba`).

### 1.4 Spec alignment

| Spec section | β2 alignment |
|---|---|
| §10.3 endpoint list | Direct implementation of every `/{project}` path-prefix endpoint. |
| §15 token metrics | `/metrics/usage` (global aggregate across vaults), `/metrics/usage/by-project` (real per-project breakdown), `/metrics/usage/timeline` (cross-vault), `/metrics/usage/top-sessions` (cross-vault). |
| §13.2 onboarding step 4 (dashboard preview) | Dashboard (Plan #14) needs every route to take explicit project param — β2 unblocks it. |
| §1.4 Принцип 5 (always UI path to fix) | Empty project-map at boot still serves `/projects/*`, `/settings/*`, `/health`, `/version`, `/alerts` — same semantics as β1. Per-project routes return 404 with `unknown_project` instead of 503 when project doesn't exist. |

---

## 2. Architecture overview

### 2.1 Routing model: path-prefix per spec §10.3

Spec §10.3 picks **path-prefix `{project}`** for every per-project endpoint and `/api` prefix in the doc (we drop `/api/` per existing convention). This is the most RESTful and dashboard-friendly choice (URLs are self-documenting; no query-string juggling).

Path-prefix examples:

```
GET    /sessions/{project}                     — list sessions in project
GET    /sessions/{project}/{sid}               — session details
POST   /sessions/{project}/{sid}/ingest        — manual ingest

GET    /snapshots/{project}                    — list project snapshots
POST   /snapshots/{project}/{id}/restore       — restore from snapshot

GET    /pages/{project}                        — list project pages
PATCH  /pages/{project}/{page_id}              — manual edit
DELETE /pages/{project}/{page_id}              — soft-delete

GET    /trash/{project}                        — list trashed pages
POST   /trash/{project}/{id}/restore           — restore from trash

GET    /lint/{project}/results                 — lint reports
POST   /lint/{project}/run                     — run lint (was POST /lint)
POST   /lint/{project}/autofix                 — apply autofix

GET    /ontology/{project}/suggestions         — pending suggestions
POST   /ontology/{project}/run                 — run check
POST   /ontology/{project}/suggestions/{id}/approve

GET    /activity/{project}                     — recent activity (paginated)
POST   /activity/{project}/{id}/undo           — undo

GET    /vault/{project}                        — vault summary (was GET /vault)
```

### 2.2 Global routes (no project param)

These remain global and aggregate across all vaults:

```
GET    /health                                 — daemon-level health (cross-vault summary)
GET    /version                                — daemon version
GET    /alerts                                 — all alerts (already global)
POST   /alerts/{id}/silence                    — silence alert
POST   /alerts/{id}/resolve                    — resolve alert

GET    /lost-sessions                          — cross-vault scan with project attribution
POST   /lost-sessions/scan                     — rescan all vaults
POST   /lost-sessions/{sid}/import             — import to specific project (project_name in body)
POST   /lost-sessions/{sid}/ignore             — mark ignored

GET    /jobs                                   — cross-vault job listing (optional ?project= filter)
GET    /jobs/{job_id}                          — global by job_id (search runtimes)
DELETE /jobs/{job_id}                          — cancel job

GET    /dead-letter                            — cross-vault dead-letter listing
GET    /dead-letter/{id}                       — global by id (search runtimes)
POST   /dead-letter/{id}/retry                 — retry
DELETE /dead-letter/{id}                       — dismiss

POST   /jobs (already exists)                  — kept; routes by payload.project_name

GET    /projects                               — list (already exists)
GET    /projects/{name}                        — get details (already exists)
POST   /projects                               — create (already exists)
PATCH  /projects/{name}                        — update (already exists)
DELETE /projects/{name}                        — delete (already exists)

GET    /settings/global                        — global settings (already exists)
PATCH  /settings/global                        — update global (already exists)
GET    /settings/{name}                        — per-project (already exists, name=project)
PATCH  /settings/{name}                        — update per-project (already exists)

GET    /metrics/usage                          — cross-vault aggregate
GET    /metrics/usage/by-project               — real per-project breakdown
GET    /metrics/usage/timeline                 — cross-vault by day
GET    /metrics/usage/top-sessions             — cross-vault top N
```

`/jobs/{job_id}` and `/dead-letter/{id}` are interesting: job IDs are unique across all `<vault>/.jobs.db` (UUIDv4), so the daemon can look up "any runtime whose store contains this id" by iterating runtimes. Test will verify this works.

### 2.3 Helper: `_runtime(request, project_name)` replaces `_vault(request)`

```python
# claude_mnemos/daemon/routes/_helpers.py (new)
from __future__ import annotations

from fastapi import HTTPException, Request

from claude_mnemos.daemon.vault_runtime import VaultRuntime


def get_runtime(request: Request, project_name: str) -> VaultRuntime:
    """Resolve a project's VaultRuntime or raise HTTP 404.

    Replaces the β1 `_vault(request)` helper. Every per-project route now
    uses this to look up its target vault directly.
    """
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "daemon_unavailable"},
        )
    runtime = daemon.runtimes.get(project_name)
    if runtime is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "unknown_project",
                "project_name": project_name,
                "hint": "GET /projects to list registered projects",
            },
        )
    return runtime
```

Per-project routes call `get_runtime(request, project)` and use `.vault_root`, `.job_store`, `.tracker`, `.lost_sessions_cache`, `.job_worker`, `.observer`, `.settings` from the returned runtime.

### 2.4 Cross-vault aggregation pattern

```python
# claude_mnemos/daemon/routes/_helpers.py
def all_runtimes(request: Request) -> list[VaultRuntime]:
    """Iterate every mounted runtime, sorted by name. Empty list if no runtimes."""
    daemon = request.app.state.daemon
    if daemon is None:
        return []
    return [daemon.runtimes[name] for name in sorted(daemon.runtimes)]
```

Endpoints that need to aggregate (e.g. `/jobs` GET, `/lost-sessions`, `/metrics/usage`) iterate this list, accumulate results, attach `project_name` to each item, return.

### 2.5 What changes in `MnemosDaemon`

Removed:
- `primary_runtime` property
- `_primary_runtime` field
- `_recompute_primary` method
- `app.state.vault_root` initialization (already None-by-default after β2)

Kept:
- `runtimes: dict[str, VaultRuntime]`
- `_runtimes_lock: asyncio.Lock`
- Lifecycle methods: `mount_vault`, `unmount_vault`, `remount_vault`, `_bootstrap_runtimes`, `reload_*_settings`, `_shutdown_runtimes`, `run`

`reload_global_settings` no longer re-picks primary; it just stores the new global. (`primary_project` field is also removed from `GlobalSettings`.)

### 2.6 What changes in `app.py`

`create_app(daemon: MnemosDaemon | None = None)` signature drops the `vault_root: Path | None` parameter. `app.state.vault_root` no longer exists — every route resolves vault from `app.state.daemon.runtimes`.

---

## 3. Per-route changes — detail by route module

### 3.1 `routes/sessions.py`

**Before:**
- `GET /sessions` (uses primary)
- `GET /sessions/{session_id}` (uses primary; ambiguous with project)
- `POST /sessions/{session_id}/ingest` (uses primary)

**After:**
```
GET    /sessions/{project}                    — list sessions
GET    /sessions/{project}/{sid}              — session details
POST   /sessions/{project}/{sid}/ingest       — manual ingest enqueue
```

`{sid}` second position avoids ambiguity with `{project}`.

### 3.2 `routes/snapshots.py`

**Before:** `GET /snapshots`, `POST /snapshots/{id}/restore`, etc. — all primary.

**After:**
```
GET    /snapshots/{project}                   — list
POST   /snapshots/{project}                   — create manual snapshot
DELETE /snapshots/{project}/{id}              — delete
POST   /snapshots/{project}/{id}/restore      — restore
POST   /snapshots/{project}/{id}/pin          — pin
```

### 3.3 `routes/pages.py`

**Before:** `GET /pages`, `PATCH /pages/{page_id}`, etc. — primary.

**After:**
```
GET    /pages/{project}                       — list
GET    /pages/{project}/{page_id}             — get
PATCH  /pages/{project}/{page_id}             — manual edit
DELETE /pages/{project}/{page_id}             — soft-delete
POST   /pages/{project}/{page_id}/verify      — mark verified
POST   /pages/{project}/{page_id}/archive     — archive
GET    /pages/{project}/{page_id}/backlinks   — incoming wikilinks
```

### 3.4 `routes/trash.py`

**Before:** `GET /trash`, `POST /trash/{id}/restore`, etc. — primary.

**After:**
```
GET    /trash/{project}                       — list
POST   /trash/{project}/{id}/restore          — restore
DELETE /trash/{project}/{id}                  — permanent delete
DELETE /trash/{project}                       — empty trash (Tier 2)
```

### 3.5 `routes/lint.py`

**Before:** `POST /lint`, `GET /lint/results`, etc. — primary.

**After:**
```
POST   /lint/{project}/run                    — run lint
GET    /lint/{project}/results                — lint reports
POST   /lint/{project}/autofix                — apply autofix
```

### 3.6 `routes/ontology.py`

**Before:** `POST /ontology/run`, `GET /ontology/suggestions`, etc. — primary.

**After:**
```
POST   /ontology/{project}/run                — run check
GET    /ontology/{project}/suggestions        — list
POST   /ontology/{project}/suggestions/{id}/approve
POST   /ontology/{project}/suggestions/{id}/reject
POST   /ontology/{project}/suggestions/{id}/defer
PATCH  /ontology/{project}/suggestions/{id}   — edit before apply
```

### 3.7 `routes/activity.py`

**Before:** `GET /activity`, `POST /activity/{id}/undo` — primary.

**After:**
```
GET    /activity/{project}                    — recent activity (paginated)
GET    /activity/{project}/{id}               — get specific entry
POST   /activity/{project}/{id}/undo          — undo
```

### 3.8 `routes/vault.py`

**Before:** `GET /vault` — vault summary for primary.

**After:**
```
GET    /vault/{project}                       — vault summary
```

### 3.9 `routes/lost_sessions.py`

**Before:** `GET /lost-sessions` reads only primary's vault. `POST /lost-sessions/{sid}/import` imports to primary.

**After:** truly cross-vault.

```
GET    /lost-sessions                         — scan all mounted vaults; each result has project_name
POST   /lost-sessions/scan                    — rescan all mounted vaults
POST   /lost-sessions/{sid}/import            — body: {"project_name": "...", ...}; resolves runtime → enqueue ingest there
POST   /lost-sessions/{sid}/ignore            — record ignore in all vaults' caches
```

The cache is per-vault (in `runtime.lost_sessions_cache`); when `/scan` runs we ask each runtime to refresh its cache, then merge results.

### 3.10 `routes/jobs.py`

**Before:** `POST /jobs` already routes by `payload.project_name`. GET/DELETE use primary.

**After:**

```
POST   /jobs                                  — unchanged (routes by payload.project_name)
GET    /jobs[?project=NAME]                   — cross-vault listing; optional filter
GET    /jobs/{job_id}                         — search across runtimes by id
DELETE /jobs/{job_id}                         — find runtime owning the id, cancel
```

`/jobs?project=NAME&status=queued&limit=50&offset=0` — filter is composable. Without `?project=`, results from all runtimes merge (sorted by `created_at desc`), each item carries `project_name`.

### 3.11 `routes/dead_letter.py`

**Before:** primary's DLQ only.

**After:**
```
GET    /dead-letter                           — cross-vault listing
GET    /dead-letter/{id}                      — search across runtimes
POST   /dead-letter/{id}/retry                — retry (creates new ingest job in same runtime)
DELETE /dead-letter/{id}                      — dismiss
```

### 3.12 `routes/metrics.py`

**Before:** all primary or single-vault stub.

**After:** real cross-vault aggregation.

```python
# Pseudocode
def usage_aggregate(daemon, period_days):
    total = UsageSummary.zero()
    for runtime in daemon.runtimes.values():
        per_vault = core_metrics.usage_summary(runtime.vault_root, period_days)
        total = total + per_vault   # sum tokens_injected, sessions_covered, weighted compression ratio
    return total

def usage_by_project(daemon, period_days):
    return [
        {"project": name, **core_metrics.usage_summary(rt.vault_root, period_days).model_dump(mode="json")}
        for name, rt in sorted(daemon.runtimes.items())
    ]

def usage_timeline(daemon, period_days):
    """For each day in period, sum tokens_injected across all vaults."""
    timelines = [
        core_metrics.timeline(rt.vault_root, period_days) for rt in daemon.runtimes.values()
    ]
    return _merge_timelines(timelines)  # group by date, sum

def usage_top_sessions(daemon, limit):
    """All sessions across all vaults, sorted by tokens_injected desc, top N."""
    all_sessions = []
    for name, rt in daemon.runtimes.items():
        for s in core_metrics.top_sessions(rt.vault_root, limit=limit):
            d = s.model_dump(mode="json")
            d["project"] = name
            all_sessions.append(d)
    all_sessions.sort(key=lambda x: x["tokens_injected"], reverse=True)
    return all_sessions[:limit]
```

`UsageSummary` arithmetic: `tokens_full + tokens_full`, `tokens_actual + tokens_actual`, `sessions_covered + sessions_covered`. `avg_compression_ratio` recomputed as `total_tokens_full / total_tokens_actual`.

### 3.13 `routes/health.py`

**Before:** reads `daemon.observer` (None → 503) + `daemon.alerts` + primary's job_store counts.

**After:** aggregate across all runtimes.

```
GET    /health
{
  "status": "healthy" | "degraded",
  "uptime_seconds": ...,
  "version": "...",
  "vaults": {
    "alpha": {"watchdog_running": true, "jobs": {"queued": 3, "running": 1}},
    "beta":  {"watchdog_running": true, "jobs": {"queued": 0, "running": 0}}
  },
  "alerts_count": 5
}
```

If no vaults mounted, `vaults: {}` and `status: "healthy"` (daemon itself is fine, just no projects).

---

## 4. State that gets removed

### 4.1 `MnemosDaemon`
- `_primary_runtime: VaultRuntime | None`
- `primary_runtime` property
- `_recompute_primary()`

### 4.2 `app.py`
- `create_app(vault_root: Path | None = None, ...)` → `create_app(daemon: ... | None = None)`
- `app.state.vault_root` (no longer set)

### 4.3 `state/settings.py`
- `GlobalSettings.primary_project: str | None`

### 4.4 `routes/*` (every per-project route)
- `_vault(request)` helper — replaced by `get_runtime(request, project)`

### 4.5 `reload_global_settings`
- The "re-pick primary" branch goes away.

---

## 5. Hooks, CLI, MCP — consumer updates

### 5.1 SessionEnd hook (`hooks/session_end.py`)

Already POSTs to `/jobs` with `payload["project_name"]`. **No change needed** for β2 — that endpoint is unchanged.

### 5.2 CLI (`claude_mnemos/cli.py`, `claude_mnemos/cli_project.py`, `claude_mnemos/cli_settings.py`)

Most CLI commands already accept `--project NAME`. The internal HTTP calls need URL updates:

- `mnemos sessions list` (or similar) — calls `GET /sessions/{project}` instead of `/sessions`.
- `mnemos snapshots list` — `GET /snapshots/{project}`.
- `mnemos lint run` — `POST /lint/{project}/run`.
- `mnemos pages list` — `GET /pages/{project}`.
- etc.

If `mnemos <subcommand>` doesn't already require `--project`, β2 must add it (with auto-resolve from cwd as fallback, mirroring α's `--project` resolution).

Audit: every CLI subcommand that hits a daemon URL containing a previously-implicit primary vault must now construct the URL with `{project}`.

### 5.3 MCP server (`claude_mnemos/mcp/`)

MCP tools are mostly local-vault-bound (the MCP server is bound to one vault at startup via `--auto-resolve` / `--project`). Tools that hit daemon REST need updated URLs. Check `claude_mnemos/mcp/tools/*.py` and `claude_mnemos/mcp/server.py`.

### 5.4 Plugin / hooks beyond SessionEnd

`hooks/session_start.py` (if it exists / Plan #13c) reads project context — uses local vault (filesystem reads, not daemon REST). Not affected.

---

## 6. Testing strategy

### 6.1 Unit tests (per route module)

For each route module touched (12 modules), add or update tests:
- New project param resolves correctly.
- Unknown project returns 404 with `unknown_project` error.
- Existing per-project behaviour preserved (e.g. snapshots list shows snapshots from the right vault).

Most existing α/β1 unit tests use `_FakeDaemon` shims — they need `runtimes: dict` populated explicitly with at least one runtime. Pattern from `tests/daemon/test_routes_real_daemon.py`.

### 6.2 Cross-vault aggregation tests

- `tests/daemon/test_routes_metrics_aggregation.py` — two mounted vaults with different events, `/metrics/usage` totals correctly, `/metrics/usage/by-project` lists both, `/metrics/usage/timeline` merges correctly.
- `tests/daemon/test_routes_lost_sessions_cross_vault.py` — two vaults each with lost sessions, `GET /lost-sessions` returns merged list with project names.
- `tests/daemon/test_routes_jobs_cross_vault.py` — two vaults each with jobs, `GET /jobs` aggregates, `GET /jobs?project=alpha` filters.

### 6.3 Re-enable e2e tests

The 6 skip-marked e2e tests from β1:
- `tests/daemon/test_jobs_e2e.py` — adapt to new `/jobs` GET cross-vault response.
- `tests/daemon/test_watchdog_e2e.py` — adapt `/health` aggregate response.
- `tests/e2e/test_project_settings_e2e.py` (3 tests) — these were about `/settings/{name}` PATCH, which already works in β1. The skip reason was about `daemon.config.vault_root` (removed in β1) — re-check why they're still failing and fix.

### 6.4 Backward-compat regression tests

α/β1 callers that hit unprefixed routes (e.g. `GET /snapshots`) now return 404. Ensure error message is helpful (`hint: route requires {project} segment, see GET /projects`).

### 6.5 Empty project-map test

Already exists for β1 (`test_empty_project_map.py`). Update to verify per-project endpoints return 404 (not 503) when called with an unknown project name on an empty map.

### 6.6 Test counts

Target: ~50–80 new tests + ~30 updated tests. Total `pytest` count should stay under 1300 fast.

---

## 7. File-level change summary

### 7.1 Modified files

**Daemon orchestration:**
- `claude_mnemos/daemon/process.py` — drop `_primary_runtime`, `_recompute_primary`, `primary_runtime` property; `reload_global_settings` simplified.
- `claude_mnemos/daemon/app.py` — drop `vault_root` arg from `create_app`.
- `claude_mnemos/state/settings.py` — drop `GlobalSettings.primary_project`.

**New helper:**
- `claude_mnemos/daemon/routes/_helpers.py` — `get_runtime(request, project_name)`, `all_runtimes(request)`.

**Routes (per-project, path prefix migration):**
- `claude_mnemos/daemon/routes/sessions.py`
- `claude_mnemos/daemon/routes/snapshots.py`
- `claude_mnemos/daemon/routes/pages.py`
- `claude_mnemos/daemon/routes/trash.py`
- `claude_mnemos/daemon/routes/lint.py`
- `claude_mnemos/daemon/routes/ontology.py`
- `claude_mnemos/daemon/routes/activity.py`
- `claude_mnemos/daemon/routes/vault.py`

**Routes (cross-vault aggregation):**
- `claude_mnemos/daemon/routes/lost_sessions.py`
- `claude_mnemos/daemon/routes/jobs.py` (GET/DELETE only; POST unchanged)
- `claude_mnemos/daemon/routes/dead_letter.py`
- `claude_mnemos/daemon/routes/metrics.py`
- `claude_mnemos/daemon/routes/health.py`

**Consumers:**
- `claude_mnemos/cli.py` — update CLI subcommands that hit daemon URLs.
- `claude_mnemos/cli_project.py` — already correct (uses `/projects/*`).
- `claude_mnemos/cli_settings.py` — already correct (uses `/settings/*`).
- `claude_mnemos/mcp/tools/*.py` — audit for daemon REST calls.

**Tests:** ~12 updated, ~6–8 new.

### 7.2 Removed code

- `MnemosDaemon._primary_runtime`, `_recompute_primary`, `primary_runtime`.
- `app.state.vault_root` references.
- `_vault(request)` helpers in 11 route files.
- `GlobalSettings.primary_project`.
- `tests/daemon/test_routes_no_primary.py` — replaced by per-route 404 tests + an `unknown_project` test.

### 7.3 New code

- `claude_mnemos/daemon/routes/_helpers.py` — `get_runtime`, `all_runtimes`.
- Cross-vault aggregation helpers in `core/metrics.py` (or `core/cross_vault_metrics.py` if needed).
- Tests listed in §6.

---

## 8. Risks and rollback

### 8.1 Top risks

| Risk | Mitigation |
|---|---|
| Many tests break because they rely on `app.state.vault_root` or unprefixed URLs. | Migrate them in the same task as the route. Plan tasks accordingly. |
| Cross-vault aggregation introduces N+1 IO patterns (manifest read per vault per request). | For typical N≤10 it's fine; if scale grows, cache layer in `core/metrics.py`. β2 doesn't optimise — measure first. |
| Job ID lookup for `/jobs/{id}` requires iterating runtimes. | Bounded by N (number of vaults). Each lookup is one indexed sqlite query. Acceptable. |
| Empty `runtimes` dict on cross-vault GET → empty response (not error). | Documented behaviour. `/health` shows `vaults: {}`. UI handles gracefully. |
| Old CLI invocations break (e.g. `mnemos sessions list` without `--project`). | All CLI subcommands take `--project NAME` or auto-resolve from cwd (α pattern). |
| Removing `primary_project` field from `GlobalSettings` is a breaking schema change for users who set it. | `extra="ignore"` on read absorbs the field silently. (β1 set it via `set_global` so files exist.) |

### 8.2 Rollback

β2 ships as one branch + one merge to main. If integration breaks:
1. `git revert -m 1 <merge-sha>` on main → restore β1 state.
2. Existing on-disk state (`~/.claude-mnemos/`, vaults' `.jobs.db`, etc.) unchanged.
3. The only forward-incompatible change is `GlobalSettings.primary_project` removal — rollback restores the field, β1's `_recompute_primary` works again.

---

## 9. Acceptance criteria

β2 is done when:

1. ✅ Every per-project route accepts `{project}` as the first path segment after the resource.
2. ✅ Every per-project route returns 404 `unknown_project` for unknown names.
3. ✅ `app.state.vault_root` is gone (grep returns 0 matches).
4. ✅ `daemon.primary_runtime`, `_primary_runtime`, `_recompute_primary` are gone (grep returns 0 matches).
5. ✅ `GlobalSettings.primary_project` is gone.
6. ✅ `/lost-sessions` GET aggregates across all mounted vaults.
7. ✅ `/jobs` GET aggregates across all mounted vaults; `?project=NAME` filters.
8. ✅ `/dead-letter` GET aggregates across all mounted vaults.
9. ✅ `/metrics/usage`, `/metrics/usage/by-project`, `/metrics/usage/timeline`, `/metrics/usage/top-sessions` all real cross-vault aggregation.
10. ✅ `/health` reports per-vault status.
11. ✅ All 6 e2e tests skip-marked in β1 are re-enabled and passing.
12. ✅ Test suite green: ~1180+ fast pytest, ~10+ slow.
13. ✅ ruff + mypy --strict clean.
14. ✅ CLI subcommands that hit daemon REST work end-to-end with the new URLs.

---

## 10. Open questions resolved by this design

| Question | Decision | Rationale |
|---|---|---|
| Path prefix vs query param for project? | Path prefix `{project}` everywhere per spec §10.3 | Spec is explicit; RESTful; dashboard-friendly URLs. |
| Cross-vault aggregation in daemon vs separate service? | In daemon, in-process | N≤10 vaults, no caching needed at this scale. |
| Keep `primary_project` for "default vault for CLI" semantics? | No, remove | β2's CLI requires explicit `--project` or cwd-resolves; primary was an artefact of β1's stopgap. |
| Backward compat for old route URLs? | No, hard-cut | β1 was always a stopgap; no production users. |
| `/api/` prefix? | No (preserve α/β1 convention) | Existing codebase doesn't use it; spec is documentation only. |
| `/jobs/{id}` global resolution? | Iterate runtimes, find owner | UUIDv4 unique; bounded by N vaults; one indexed sqlite query each. |
| `/health` shape? | Per-vault dict + global summary | Dashboard wants per-project health; aggregating gives both. |

---

## 11. Out of scope

- **Plan #13c** (SessionStart adaptive context inject) — needs cross-project context resolution; β2 unblocks but doesn't ship.
- **Plan #14** (React dashboard) — consumes β2 API; β2 unblocks but doesn't ship.
- **`/suggestions/{project}` endpoint** (spec §10.3) — Ontology suggestions panel composite endpoint; defer (Ontology already has its own endpoints).
- **`/system-status` endpoint** (spec §10.3) — global diagnostic; defer (`/health` covers most of it).
- **`/guide`, `/locales`, `/onboarding/complete`** (spec §10.3 misc) — Plan #14 (Dashboard) territory.
- **Caching layer for cross-vault metrics** — measure first; YAGNI.
