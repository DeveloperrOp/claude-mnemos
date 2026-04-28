# Per-route project params + cross-vault aggregation Implementation Plan (Plan #13b-β2)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** Migrate every per-project daemon route from the β1 "primary vault" stopgap onto explicit `{project}` path-prefix per spec §10.3, implement real cross-vault aggregation in `/metrics`, `/lost-sessions`, `/jobs` GET, `/dead-letter`, `/health`, drop `app.state.vault_root` + `primary_runtime` + `GlobalSettings.primary_project` entirely, and re-enable the 6 e2e tests skip-marked in β1.

**Architecture:** New helper `claude_mnemos/daemon/routes/_helpers.py` with `get_runtime(request, project_name) → VaultRuntime | 404` and `all_runtimes(request) → list[VaultRuntime]`. Per-project routes use `get_runtime`. Cross-vault routes iterate `all_runtimes` and merge with `project_name` attribution. After every route is migrated, `app.py` drops the `vault_root` arg, `process.py` drops `_primary_runtime`/`_recompute_primary`/`primary_runtime`, and `state/settings.py` drops `GlobalSettings.primary_project`.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, APScheduler, sqlite, pytest, pytest-asyncio. No new third-party deps.

**Design doc:** `docs/plans/2026-04-28-13b-beta2-route-project-params-design.md` — read before each task.

---

## Files map

**Create:**
- `claude_mnemos/daemon/routes/_helpers.py` — `get_runtime`, `all_runtimes`
- `tests/daemon/test_routes_helpers.py`
- `tests/daemon/test_routes_metrics_aggregation.py`
- `tests/daemon/test_routes_lost_sessions_cross_vault.py`
- `tests/daemon/test_routes_jobs_cross_vault.py`
- `tests/daemon/test_routes_dead_letter_cross_vault.py`
- `tests/daemon/test_routes_health_aggregate.py`

**Modify (per-project routes — path prefix migration):**
- `claude_mnemos/daemon/routes/sessions.py`
- `claude_mnemos/daemon/routes/snapshots.py`
- `claude_mnemos/daemon/routes/pages.py`
- `claude_mnemos/daemon/routes/trash.py`
- `claude_mnemos/daemon/routes/lint.py`
- `claude_mnemos/daemon/routes/ontology.py`
- `claude_mnemos/daemon/routes/activity.py`
- `claude_mnemos/daemon/routes/vault.py`

**Modify (cross-vault aggregation routes):**
- `claude_mnemos/daemon/routes/lost_sessions.py`
- `claude_mnemos/daemon/routes/jobs.py` (GET/`{id}` only; POST unchanged)
- `claude_mnemos/daemon/routes/dead_letter.py`
- `claude_mnemos/daemon/routes/metrics.py`
- `claude_mnemos/daemon/routes/health.py`

**Modify (cleanup after all routes migrated):**
- `claude_mnemos/daemon/process.py` — drop `_primary_runtime`/`_recompute_primary`/`primary_runtime`/`reload_global_settings` re-pick
- `claude_mnemos/daemon/app.py` — `create_app(daemon=...)` only (drop `vault_root` arg)
- `claude_mnemos/state/settings.py` — drop `GlobalSettings.primary_project`
- `claude_mnemos/daemon/schemas.py` — `HealthResponse` shape change (per-vault dict)

**Modify (consumer updates):**
- `claude_mnemos/mcp/write_tools/snapshots.py` — `/snapshots/{project}/...`
- `claude_mnemos/mcp/write_tools/lint.py` — `/lint/{project}/run`
- `claude_mnemos/mcp/write_tools/ontology.py` — `/ontology/{project}/...`
- `claude_mnemos/mcp/write_tools/activity.py` — `/activity/{project}/{id}/undo`
- `claude_mnemos/mcp/server.py` — pass project name to write tools (already known via `--project`/`--auto-resolve`)
- `claude_mnemos/mcp/read_tools/status.py` — `/health` shape change handling
- `claude_mnemos/cli.py`, `claude_mnemos/cli_*.py` — any subcommand hitting changed routes

**Modify (e2e tests re-enable):**
- `tests/daemon/test_jobs_e2e.py` — adapt to cross-vault response
- `tests/daemon/test_watchdog_e2e.py` — adapt to new `/health` shape
- `tests/e2e/test_project_settings_e2e.py` (3 tests) — re-enable

**Update existing tests** (extensive — every route's existing α/β1 test needs URL update).

---

## Task 1: New `_helpers.py` module

**Files:**
- Create: `claude_mnemos/daemon/routes/_helpers.py`
- Create: `tests/daemon/test_routes_helpers.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/daemon/test_routes_helpers.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from claude_mnemos.daemon.routes._helpers import all_runtimes, get_runtime


def _request(daemon: object | None) -> object:
    """Build a fake request with .app.state.daemon."""
    req = MagicMock()
    req.app.state.daemon = daemon
    return req


def test_get_runtime_returns_runtime():
    rt = MagicMock()
    daemon = MagicMock()
    daemon.runtimes = {"alpha": rt}
    assert get_runtime(_request(daemon), "alpha") is rt


def test_get_runtime_unknown_project_returns_404():
    daemon = MagicMock()
    daemon.runtimes = {}
    with pytest.raises(HTTPException) as exc_info:
        get_runtime(_request(daemon), "ghost")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "unknown_project"
    assert exc_info.value.detail["project_name"] == "ghost"


def test_get_runtime_no_daemon_returns_503():
    with pytest.raises(HTTPException) as exc_info:
        get_runtime(_request(None), "alpha")
    assert exc_info.value.status_code == 503


def test_all_runtimes_sorted_by_name():
    rt_a = MagicMock(); rt_a.name = "alpha"
    rt_b = MagicMock(); rt_b.name = "beta"
    rt_c = MagicMock(); rt_c.name = "charlie"
    daemon = MagicMock()
    daemon.runtimes = {"charlie": rt_c, "alpha": rt_a, "beta": rt_b}
    result = all_runtimes(_request(daemon))
    assert [r.name for r in result] == ["alpha", "beta", "charlie"]


def test_all_runtimes_empty_when_no_daemon():
    assert all_runtimes(_request(None)) == []


def test_all_runtimes_empty_when_no_runtimes():
    daemon = MagicMock()
    daemon.runtimes = {}
    assert all_runtimes(_request(daemon)) == []
```

- [ ] **Step 2: Run** → FAIL.

```
pytest tests/daemon/test_routes_helpers.py -v
```

- [ ] **Step 3: Implement helper**

```python
# claude_mnemos/daemon/routes/_helpers.py
"""Route helpers shared across per-project and cross-vault endpoints (β2).

After β2 every per-project route resolves its target VaultRuntime via
``get_runtime(request, project_name)`` (404 on unknown), and every
cross-vault aggregation route iterates the full set via
``all_runtimes(request)`` (sorted by project name; empty list when no
mounted vaults).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from claude_mnemos.daemon.vault_runtime import VaultRuntime


def get_runtime(request: Request, project_name: str) -> VaultRuntime:
    """Resolve a project's VaultRuntime or raise HTTP 404 / 503."""
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
    rt: VaultRuntime = runtime
    return rt


def all_runtimes(request: Request) -> list[VaultRuntime]:
    """Iterate every mounted runtime, sorted alphabetically by name.

    Returns empty list when daemon is None or no runtimes are mounted.
    """
    daemon = request.app.state.daemon
    if daemon is None:
        return []
    runtimes: dict[str, VaultRuntime] = daemon.runtimes
    return [runtimes[name] for name in sorted(runtimes)]
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/_helpers.py tests/daemon/test_routes_helpers.py
git commit -m "feat(daemon): _helpers.get_runtime/all_runtimes for β2 routing"
```

---

## Task 2: Migrate `routes/sessions.py` to `/sessions/{project}/...`

**Files:**
- Modify: `claude_mnemos/daemon/routes/sessions.py`
- Modify: existing tests in `tests/daemon/test_app_sessions.py` (and any other callers)

- [ ] **Step 1: Write failing tests**

Append to `tests/daemon/test_app_sessions.py` (or update existing):

```python
def test_get_sessions_requires_project(client_with_runtime):
    """GET /sessions/{project} returns project's sessions."""
    client, vault = client_with_runtime  # fixture mounts "alpha"
    r = client.get("/sessions/alpha")
    assert r.status_code == 200


def test_get_sessions_unknown_project_returns_404(client_with_runtime):
    client, _ = client_with_runtime
    r = client.get("/sessions/ghost")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_project"


def test_get_session_detail(client_with_runtime, tmp_path):
    client, vault = client_with_runtime
    # ... create a session, then:
    r = client.get(f"/sessions/alpha/{some_sid}")
    assert r.status_code == 200


def test_post_ingest_session_routes_to_correct_vault(client_with_runtime, tmp_path):
    client, vault = client_with_runtime
    transcript = vault / "t.jsonl"
    transcript.write_text("{}\n")
    r = client.post(
        f"/sessions/alpha/some-sid/ingest",
        json={"transcript_path": str(transcript)},
    )
    assert r.status_code == 201
```

The `client_with_runtime` fixture is the standard β1 pattern from `tests/daemon/test_routes_real_daemon.py`: real `MnemosDaemon` + `TestClient` + one project mounted. Reuse / extract to conftest if needed.

Old tests asserting `GET /sessions` (no project) must update — they now hit `GET /sessions/alpha`. If a test asserted 503 for missing primary, replace with 404 for unknown project on a populated daemon.

- [ ] **Step 2: Run** → FAIL.

```
pytest tests/daemon/test_app_sessions.py -v
```

- [ ] **Step 3: Rewrite `routes/sessions.py`**

```python
# claude_mnemos/daemon/routes/sessions.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core import sessions as core_sessions
from claude_mnemos.daemon.routes._helpers import get_runtime
from claude_mnemos.state.jobs import JobStore

router = APIRouter()


@router.get("/sessions/{project}")
async def list_sessions_route(
    project: str,
    request: Request,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    items = core_sessions.list_sessions(runtime.vault_root)
    if status:
        items = [s for s in items if s.status.value == status]
    return {
        "sessions": [s.model_dump(mode="json") for s in items[:limit]],
        "total": len(items),
    }


@router.get("/sessions/{project}/{session_id}")
async def get_session_route(
    project: str, session_id: str, request: Request
) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    try:
        session = core_sessions.get_session(runtime.vault_root, session_id)
    except core_sessions.SessionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "session_id": session_id},
        ) from exc
    return session.model_dump(mode="json")


@router.post("/sessions/{project}/{session_id}/ingest", status_code=201)
async def ingest_session_route(
    project: str,
    session_id: str,
    request: Request,
    body: dict[str, Any],
) -> dict[str, Any]:
    del session_id  # informational only; payload carries the path
    runtime = get_runtime(request, project)
    transcript_path = body.get("transcript_path")
    if (
        not isinstance(transcript_path, str)
        or not transcript_path
        or not Path(transcript_path).is_file()
    ):
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_or_invalid_transcript_path"},
        )
    if runtime.job_store is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "vault_unavailable", "project": project},
        )
    store: JobStore = runtime.job_store
    job = store.create(kind="ingest", payload={"transcript_path": transcript_path})
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    dumped: dict[str, Any] = job.model_dump(mode="json")
    return dumped
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/sessions.py tests/daemon/test_app_sessions.py
git commit -m "feat(daemon): /sessions/{project}/[{sid}/ingest] path prefix"
```

---

## Task 3: Migrate `routes/snapshots.py` to `/snapshots/{project}/...`

**Files:**
- Modify: `claude_mnemos/daemon/routes/snapshots.py`
- Modify: `tests/daemon/test_app_snapshots.py`

- [ ] **Step 1: Write failing tests**

Update existing tests + add a 404 test:

```python
def test_list_snapshots_under_project(client_with_runtime):
    client, _ = client_with_runtime
    r = client.get("/snapshots/alpha")
    assert r.status_code == 200
    assert "snapshots" in r.json()


def test_create_snapshot_under_project(client_with_runtime):
    client, _ = client_with_runtime
    r = client.post("/snapshots/alpha", json={})
    assert r.status_code == 201


def test_unknown_project_returns_404(client_with_runtime):
    client, _ = client_with_runtime
    r = client.get("/snapshots/ghost")
    assert r.status_code == 404


def test_restore_snapshot(client_with_runtime):
    client, _ = client_with_runtime
    # create snapshot first
    create = client.post("/snapshots/alpha", json={}).json()
    name = create["name"]
    r = client.post(f"/snapshots/alpha/{name}/restore")
    assert r.status_code == 200
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Rewrite `routes/snapshots.py`**

Replace `_vault(request)` calls with `runtime = get_runtime(request, project)` then `runtime.vault_root`. Move `{name}` path param to second position after `{project}`. Endpoints become:

```
GET    /snapshots/{project}
POST   /snapshots/{project}                       (body: CreateSnapshotRequest)
DELETE /snapshots/{project}/{name}
POST   /snapshots/{project}/{name}/restore
```

Each handler signature gains `project: str` first path param. Resolve via `get_runtime` and use `runtime.vault_root` for snapshot ops.

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/snapshots.py tests/daemon/test_app_snapshots.py
git commit -m "feat(daemon): /snapshots/{project}/[{name}/restore] path prefix"
```

---

## Task 4: Migrate `routes/pages.py` to `/pages/{project}/...`

**Files:**
- Modify: `claude_mnemos/daemon/routes/pages.py`
- Modify: `tests/daemon/test_app_pages.py`

Endpoints become:

```
GET    /pages/{project}
GET    /pages/{project}/{page_id}
PATCH  /pages/{project}/{page_id}
DELETE /pages/{project}/{page_id}
POST   /pages/{project}/{page_id}/verify
POST   /pages/{project}/{page_id}/archive
GET    /pages/{project}/{page_id}/backlinks
```

- [ ] **Step 1: Write failing tests** — append project param to all existing `/pages/...` tests; add 404 test for unknown project.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Rewrite handlers** — every signature gains `project: str` first path param; each calls `runtime = get_runtime(request, project)` and uses `runtime.vault_root` + `runtime.tracker` (tracker for our-writes registration on PATCH/DELETE).

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/pages.py tests/daemon/test_app_pages.py
git commit -m "feat(daemon): /pages/{project}/[{id}/{action}] path prefix"
```

---

## Task 5: Migrate `routes/trash.py` to `/trash/{project}/...`

Endpoints:

```
GET    /trash/{project}
POST   /trash/{project}/{id}/restore
DELETE /trash/{project}/{id}
DELETE /trash/{project}                        — empty trash (Tier 2)
```

- [ ] **Step 1: Write failing tests** — append project param + 404 test.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Rewrite handlers** — `project: str` first; `runtime = get_runtime(request, project)`; use `runtime.vault_root` + `runtime.tracker`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/trash.py tests/daemon/test_app_trash.py
git commit -m "feat(daemon): /trash/{project}/[{id}] path prefix"
```

---

## Task 6: Migrate `routes/lint.py` to `/lint/{project}/...`

Endpoints:

```
POST   /lint/{project}/run
GET    /lint/{project}/results
POST   /lint/{project}/autofix
```

(Existing routes: `POST /lint/run`, `GET /lint/results`, `POST /lint/autofix` — they'll all gain `{project}` segment between `/lint` and the action.)

- [ ] **Step 1: Write failing tests** — update + add 404.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Rewrite handlers** — `project: str` first; `runtime = get_runtime(request, project)`; use `runtime.vault_root` + `runtime.tracker`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/lint.py tests/daemon/test_app_lint.py
git commit -m "feat(daemon): /lint/{project}/{run,results,autofix} path prefix"
```

---

## Task 7: Migrate `routes/ontology.py` to `/ontology/{project}/...`

Endpoints:

```
POST   /ontology/{project}/run
GET    /ontology/{project}/suggestions
POST   /ontology/{project}/suggestions/{id}/approve
POST   /ontology/{project}/suggestions/{id}/reject
POST   /ontology/{project}/suggestions/{id}/defer
PATCH  /ontology/{project}/suggestions/{id}
```

- [ ] **Step 1: Write failing tests** — update + add 404.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Rewrite handlers** — `project: str` first; `runtime = get_runtime(request, project)`; use `runtime.vault_root` + `runtime.tracker`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/ontology.py tests/daemon/test_app_ontology.py
git commit -m "feat(daemon): /ontology/{project}/... path prefix"
```

---

## Task 8: Migrate `routes/activity.py` to `/activity/{project}/...`

Endpoints:

```
GET    /activity/{project}
GET    /activity/{project}/{id}
POST   /activity/{project}/{id}/undo
```

- [ ] **Step 1: Write failing tests** — update + add 404.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Rewrite handlers** — `project: str` first; use `runtime.vault_root` + `runtime.tracker` (undo writes to vault).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/activity.py tests/daemon/test_app_activity.py
git commit -m "feat(daemon): /activity/{project}/[{id}/undo] path prefix"
```

---

## Task 9: Migrate `routes/vault.py` to `/vault/{project}`

Endpoint: `GET /vault/{project}` returns vault summary.

- [ ] **Step 1: Write failing tests** — update + add 404.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Rewrite handler** — `project: str` first; `runtime = get_runtime(request, project)`; use `runtime.vault_root`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/vault.py tests/daemon/test_app_vault.py 2>/dev/null || true
git commit -m "feat(daemon): /vault/{project} path prefix"
```

---

## Task 10: Migrate `routes/lost_sessions.py` to cross-vault aggregation

**Files:**
- Modify: `claude_mnemos/daemon/routes/lost_sessions.py`
- Create: `tests/daemon/test_routes_lost_sessions_cross_vault.py`
- Update: `tests/daemon/test_app_lost_sessions.py`

Endpoints (unchanged URL shapes, new behaviour):

```
GET    /lost-sessions                          — scan all mounted vaults
POST   /lost-sessions/scan                     — invalidate + rescan all caches
POST   /lost-sessions/{sid}/import             — body must include "project_name"
POST   /lost-sessions/{sid}/ignore             — body must include "project_name"
```

- [ ] **Step 1: Write failing tests**

```python
# tests/daemon/test_routes_lost_sessions_cross_vault.py
@pytest.fixture
def daemon_with_two_vaults(...):
    """Mount alpha and beta; create lost sessions in each."""
    ...


def test_list_lost_sessions_cross_vault(daemon_with_two_vaults):
    daemon, client = daemon_with_two_vaults
    r = client.get("/lost-sessions")
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    project_names = {s["project_name"] for s in sessions}
    assert project_names == {"alpha", "beta"}


def test_scan_invalidates_all_caches(daemon_with_two_vaults):
    daemon, client = daemon_with_two_vaults
    r = client.post("/lost-sessions/scan")
    assert r.status_code == 200


def test_import_routes_to_specified_project(daemon_with_two_vaults, tmp_path):
    daemon, client = daemon_with_two_vaults
    # ... fetch a lost session for alpha:
    sessions = client.get("/lost-sessions").json()["sessions"]
    alpha_sess = next(s for s in sessions if s["project_name"] == "alpha")
    r = client.post(
        f"/lost-sessions/{alpha_sess['session_id']}/import",
        json={"project_name": "alpha"},
    )
    assert r.status_code == 201
    # Job should be in alpha's job_store, not beta's:
    assert sum(daemon.runtimes["alpha"].job_store.count_by_status().values()) == 1
    assert sum(daemon.runtimes["beta"].job_store.count_by_status().values()) == 0


def test_import_missing_project_name_returns_400(daemon_with_two_vaults):
    daemon, client = daemon_with_two_vaults
    r = client.post("/lost-sessions/some-sid/import", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "missing_project_name"


def test_import_unknown_project_returns_404(daemon_with_two_vaults):
    daemon, client = daemon_with_two_vaults
    sessions = client.get("/lost-sessions").json()["sessions"]
    sid = sessions[0]["session_id"]
    r = client.post(
        f"/lost-sessions/{sid}/import",
        json={"project_name": "ghost"},
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Rewrite `routes/lost_sessions.py`**

```python
# claude_mnemos/daemon/routes/lost_sessions.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core import lost_sessions as core_lost_sessions
from claude_mnemos.daemon.routes._helpers import all_runtimes, get_runtime
from claude_mnemos.state.jobs import JobStore

router = APIRouter()


def _scan_all_vaults(request: Request) -> list[dict[str, Any]]:
    """Cross-vault scan with project attribution."""
    out: list[dict[str, Any]] = []
    for runtime in all_runtimes(request):
        cache = runtime.lost_sessions_cache
        items = (
            cache.get_or_scan(runtime.vault_root)
            if cache is not None
            else core_lost_sessions.scan_lost_sessions(runtime.vault_root)
        )
        for item in items:
            d = item.model_dump(mode="json")
            d["project_name"] = runtime.name
            out.append(d)
    return out


@router.get("/lost-sessions")
async def list_lost_route(request: Request) -> dict[str, Any]:
    sessions = _scan_all_vaults(request)
    return {"sessions": sessions, "total": len(sessions)}


@router.post("/lost-sessions/scan")
async def rescan_route(request: Request) -> dict[str, Any]:
    """Invalidate caches in every mounted vault, then rescan."""
    for runtime in all_runtimes(request):
        cache = runtime.lost_sessions_cache
        if cache is not None:
            cache.invalidate()
    sessions = _scan_all_vaults(request)
    return {"sessions": sessions, "total": len(sessions)}


@router.post("/lost-sessions/{session_id}/import", status_code=201)
async def import_route(
    session_id: str,
    request: Request,
    body: dict[str, Any],
) -> dict[str, Any]:
    project_name = body.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(
            status_code=400, detail={"error": "missing_project_name"}
        )
    runtime = get_runtime(request, project_name)

    transcript_path = body.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        # Resolve from this vault's scan.
        cache = runtime.lost_sessions_cache
        items = (
            cache.get_or_scan(runtime.vault_root)
            if cache is not None
            else core_lost_sessions.scan_lost_sessions(runtime.vault_root)
        )
        match = next((i for i in items if i.session_id == session_id), None)
        if match is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "lost_session_not_found",
                    "session_id": session_id,
                    "project_name": project_name,
                },
            )
        transcript_path = match.transcript_path
    elif not Path(transcript_path).is_file():
        raise HTTPException(
            status_code=400,
            detail={"error": "transcript_not_found", "transcript_path": transcript_path},
        )

    if runtime.job_store is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "vault_unavailable", "project_name": project_name},
        )
    store: JobStore = runtime.job_store
    job = store.create(kind="ingest", payload={"transcript_path": transcript_path})
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    dumped: dict[str, Any] = job.model_dump(mode="json")
    return dumped


@router.post("/lost-sessions/{session_id}/ignore", status_code=200)
async def ignore_route(
    session_id: str,
    request: Request,
    body: dict[str, Any],
) -> dict[str, Any]:
    project_name = body.get("project_name")
    if not isinstance(project_name, str) or not project_name:
        raise HTTPException(
            status_code=400, detail={"error": "missing_project_name"}
        )
    runtime = get_runtime(request, project_name)

    sha = body.get("sha")
    if not isinstance(sha, str) or not sha:
        cache = runtime.lost_sessions_cache
        items = (
            cache.get_or_scan(runtime.vault_root)
            if cache is not None
            else core_lost_sessions.scan_lost_sessions(runtime.vault_root)
        )
        match = next((i for i in items if i.session_id == session_id), None)
        if match is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "lost_session_not_found",
                    "session_id": session_id,
                    "project_name": project_name,
                },
            )
        sha = match.sha

    ignore = core_lost_sessions.add_to_ignore(
        runtime.vault_root, sha, tracker=runtime.tracker
    )
    cache = runtime.lost_sessions_cache
    if cache is not None:
        cache.invalidate()
    return {"ignored_count": len(ignore.ignored_shas)}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/lost_sessions.py tests/daemon/test_routes_lost_sessions_cross_vault.py tests/daemon/test_app_lost_sessions.py
git commit -m "feat(daemon): /lost-sessions cross-vault scan + project_name routing"
```

---

## Task 11: Migrate `routes/jobs.py` GET/`{id}` to cross-vault

**Files:**
- Modify: `claude_mnemos/daemon/routes/jobs.py`
- Create: `tests/daemon/test_routes_jobs_cross_vault.py`
- Update: existing jobs tests

Endpoints (POST unchanged):

```
GET    /jobs[?project=NAME&status=...&limit=...&offset=...]
GET    /jobs/{job_id}                          — search across runtimes
DELETE /jobs/{job_id}                          — find owning runtime, cancel
POST   /jobs                                   — unchanged (routes by payload.project_name)
```

- [ ] **Step 1: Write failing tests**

```python
# tests/daemon/test_routes_jobs_cross_vault.py
def test_list_jobs_cross_vault(daemon_with_two_vaults_jobs):
    daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/jobs")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    project_names = {j["project_name"] for j in jobs}
    assert project_names == {"alpha", "beta"}


def test_list_jobs_filtered_by_project(daemon_with_two_vaults_jobs):
    daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/jobs?project=alpha")
    jobs = r.json()["jobs"]
    assert all(j["project_name"] == "alpha" for j in jobs)


def test_list_jobs_status_filter(daemon_with_two_vaults_jobs):
    daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/jobs?status=queued")
    assert r.status_code == 200


def test_get_job_searches_across_runtimes(daemon_with_two_vaults_jobs):
    daemon, client = daemon_with_two_vaults_jobs
    # Pick a known job from beta:
    list_r = client.get("/jobs?project=beta")
    job_id = list_r.json()["jobs"][0]["id"]
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["project_name"] == "beta"


def test_get_job_unknown_returns_404(daemon_with_two_vaults_jobs):
    daemon, client = daemon_with_two_vaults_jobs
    r = client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_cancel_job_finds_correct_runtime(daemon_with_two_vaults_jobs):
    daemon, client = daemon_with_two_vaults_jobs
    job_id = client.get("/jobs?project=alpha&status=queued").json()["jobs"][0]["id"]
    r = client.delete(f"/jobs/{job_id}")
    assert r.status_code == 204
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Rewrite GET / `{id}` / DELETE handlers**

```python
@router.get("/jobs")
async def list_jobs(
    request: Request,
    project: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    daemon = request.app.state.daemon
    if daemon is None:
        return {"jobs": [], "counts": {}}
    if project is not None:
        runtime = get_runtime(request, project)
        store = runtime.job_store
        if store is None:
            return {"jobs": [], "counts": {}}
        jobs = store.list_by_status(status, limit=limit, offset=offset)
        counts = store.count_by_status()
        return {
            "jobs": [
                {**j.model_dump(mode="json"), "project_name": project}
                for j in jobs
            ],
            "counts": counts,
        }
    # Cross-vault aggregation.
    aggregated_jobs: list[dict[str, Any]] = []
    aggregated_counts: dict[str, int] = {}
    for runtime in all_runtimes(request):
        store = runtime.job_store
        if store is None:
            continue
        jobs = store.list_by_status(status, limit=limit, offset=offset)
        for j in jobs:
            d = j.model_dump(mode="json")
            d["project_name"] = runtime.name
            aggregated_jobs.append(d)
        for k, v in store.count_by_status().items():
            aggregated_counts[k] = aggregated_counts.get(k, 0) + v
    aggregated_jobs.sort(key=lambda x: x["created_at"], reverse=True)
    return {
        "jobs": aggregated_jobs[:limit],
        "counts": aggregated_counts,
    }


def _find_job_owner(request: Request, job_id: str) -> tuple[VaultRuntime, Job]:
    """Iterate runtimes, return the one whose store has the job. 404 if none."""
    for runtime in all_runtimes(request):
        store = runtime.job_store
        if store is None:
            continue
        job = store.get_by_id(job_id)
        if job is not None:
            return runtime, job
    raise HTTPException(status_code=404, detail={"error": "not_found", "job_id": job_id})


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    runtime, job = _find_job_owner(request, job_id)
    d = job.model_dump(mode="json")
    d["project_name"] = runtime.name
    return d


@router.delete("/jobs/{job_id}", status_code=204)
async def cancel_job(job_id: str, request: Request) -> Response:
    runtime, job = _find_job_owner(request, job_id)
    if job.status != "queued":
        raise HTTPException(
            status_code=409,
            detail={"error": "not_queued", "current_status": job.status},
        )
    if not runtime.job_store.cancel_queued(job_id):
        raise HTTPException(status_code=409, detail={"error": "race_lost"})
    return Response(status_code=204)
```

(POST `/jobs` already validates `payload.project_name` — keep it as-is.)

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/jobs.py tests/daemon/test_routes_jobs_cross_vault.py tests/daemon/test_app_jobs.py
git commit -m "feat(daemon): /jobs GET cross-vault [+filter]; /jobs/{id} owner search"
```

---

## Task 12: Migrate `routes/dead_letter.py` to cross-vault

**Files:**
- Modify: `claude_mnemos/daemon/routes/dead_letter.py`
- Create: `tests/daemon/test_routes_dead_letter_cross_vault.py`
- Update: `tests/daemon/test_app_dead_letter.py`

Endpoints:

```
GET    /dead-letter                            — cross-vault list
GET    /dead-letter/{id}                       — search across runtimes
POST   /dead-letter/{id}/retry                 — find owning runtime, restore
DELETE /dead-letter/{id}                       — find owning runtime, dismiss
```

- [ ] **Step 1: Write failing tests** — mirror Task 11 pattern but for dead_letter status.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Rewrite handlers**

```python
@router.get("/dead-letter")
async def list_dead_letter(
    request: Request, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    aggregated: list[dict[str, Any]] = []
    for runtime in all_runtimes(request):
        store = runtime.job_store
        if store is None:
            continue
        for j in store.list_by_status("dead_letter", limit=limit, offset=offset):
            d = j.model_dump(mode="json")
            d["project_name"] = runtime.name
            aggregated.append(d)
    aggregated.sort(key=lambda x: x.get("finished_at") or 0, reverse=True)
    return {"jobs": aggregated[:limit]}


def _find_dead_letter_owner(request: Request, job_id: str) -> tuple[VaultRuntime, Job]:
    for runtime in all_runtimes(request):
        store = runtime.job_store
        if store is None:
            continue
        job = store.get_by_id(job_id)
        if job is not None and job.status == "dead_letter":
            return runtime, job
    raise HTTPException(status_code=404, detail={"error": "not_found", "id": job_id})


@router.get("/dead-letter/{job_id}")
async def get_dead_letter(job_id: str, request: Request) -> dict[str, Any]:
    runtime, job = _find_dead_letter_owner(request, job_id)
    d = job.model_dump(mode="json")
    d["project_name"] = runtime.name
    return d


@router.post("/dead-letter/{job_id}/retry")
async def retry_dead_letter(job_id: str, request: Request) -> dict[str, Any]:
    runtime, _ = _find_dead_letter_owner(request, job_id)
    restored = runtime.job_store.restore_from_dead_letter(job_id)
    if runtime.job_worker is not None:
        runtime.job_worker.signal_wakeup()
    d = restored.model_dump(mode="json")
    d["project_name"] = runtime.name
    return d


@router.delete("/dead-letter/{job_id}", status_code=204)
async def dismiss_dead_letter(job_id: str, request: Request) -> Response:
    runtime, _ = _find_dead_letter_owner(request, job_id)
    if not runtime.job_store.dismiss_dead_letter(job_id):
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return Response(status_code=204)
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/dead_letter.py tests/daemon/test_routes_dead_letter_cross_vault.py tests/daemon/test_app_dead_letter.py
git commit -m "feat(daemon): /dead-letter cross-vault + owner search"
```

---

## Task 13: Migrate `routes/metrics.py` to real cross-vault aggregation

**Files:**
- Modify: `claude_mnemos/daemon/routes/metrics.py`
- Create: `tests/daemon/test_routes_metrics_aggregation.py`

- [ ] **Step 1: Write failing tests**

```python
def test_usage_summary_sums_across_vaults(daemon_with_two_vaults_metrics):
    daemon, client = daemon_with_two_vaults_metrics  # pre-seeded inject events
    r = client.get("/metrics/usage")
    body = r.json()
    assert body["total_tokens_injected"] == ALPHA_TOKENS + BETA_TOKENS
    assert body["sessions_covered"] == ALPHA_SESSIONS + BETA_SESSIONS


def test_usage_by_project_real_breakdown(daemon_with_two_vaults_metrics):
    daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/metrics/usage/by-project")
    projects = {p["project"]: p for p in r.json()["projects"]}
    assert projects["alpha"]["tokens_injected"] == ALPHA_TOKENS
    assert projects["beta"]["tokens_injected"] == BETA_TOKENS


def test_usage_by_project_empty_when_no_runtimes(empty_daemon):
    daemon, client = empty_daemon
    r = client.get("/metrics/usage/by-project")
    assert r.json()["projects"] == []


def test_usage_timeline_merges_days(daemon_with_two_vaults_metrics):
    daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/metrics/usage/timeline?period=30d")
    points = r.json()["points"]
    # Per-date totals across both vaults
    by_date = {p["date"]: p for p in points}
    assert by_date.get("2026-04-25", {}).get("tokens_injected") == ALPHA_25 + BETA_25


def test_top_sessions_cross_vault_sorted(daemon_with_two_vaults_metrics):
    daemon, client = daemon_with_two_vaults_metrics
    r = client.get("/metrics/usage/top-sessions?limit=5")
    sessions = r.json()["sessions"]
    assert all(s["project"] in ("alpha", "beta") for s in sessions)
    tokens = [s["tokens_injected"] for s in sessions]
    assert tokens == sorted(tokens, reverse=True)
```

The `daemon_with_two_vaults_metrics` fixture pre-seeds `<vault>/state/inject-metrics.json` with known events for predictable assertions.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Rewrite handlers + add aggregation helpers in `core/metrics.py` if needed**

```python
# claude_mnemos/daemon/routes/metrics.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.core import metrics as core_metrics
from claude_mnemos.daemon.routes._helpers import all_runtimes

router = APIRouter()


def _parse_period(period: str) -> int:
    if period.endswith("d"):
        try:
            value = int(period[:-1])
        except ValueError:
            value = -1
        if value > 0:
            return value
    raise HTTPException(
        status_code=400,
        detail={"error": "invalid_period_format", "expected": "Nd", "got": period},
    )


@router.get("/metrics/usage")
async def usage_route(request: Request, period: str = "30d") -> dict[str, Any]:
    days = _parse_period(period)
    total_full = 0
    total_actual = 0
    sessions_covered = 0
    events_count = 0
    for runtime in all_runtimes(request):
        s = core_metrics.usage_summary(runtime.vault_root, period_days=days)
        total_full += s.tokens_full
        total_actual += s.tokens_actual
        sessions_covered += s.sessions_covered
        events_count += s.events_count
    avg_ratio = (total_full / total_actual) if total_actual else 0.0
    return {
        "period": period,
        "total_tokens_injected": total_actual,
        "tokens_full": total_full,
        "sessions_covered": sessions_covered,
        "avg_compression_ratio": avg_ratio,
        "events_count": events_count,
    }


@router.get("/metrics/usage/by-project")
async def by_project_route(request: Request, period: str = "30d") -> dict[str, Any]:
    days = _parse_period(period)
    projects = []
    for runtime in all_runtimes(request):
        s = core_metrics.usage_summary(runtime.vault_root, period_days=days)
        projects.append({"project": runtime.name, **s.model_dump(mode="json")})
    return {"projects": projects}


@router.get("/metrics/usage/top-sessions")
async def top_sessions_route(request: Request, limit: int = 10) -> dict[str, Any]:
    aggregated: list[dict[str, Any]] = []
    for runtime in all_runtimes(request):
        for m in core_metrics.top_sessions(runtime.vault_root, limit=limit):
            d = m.model_dump(mode="json")
            d["project"] = runtime.name
            aggregated.append(d)
    aggregated.sort(key=lambda x: x["tokens_injected"], reverse=True)
    return {"sessions": aggregated[:limit]}


@router.get("/metrics/usage/timeline")
async def timeline_route(request: Request, period: str = "30d") -> dict[str, Any]:
    days = _parse_period(period)
    by_date: dict[str, dict[str, int]] = {}
    for runtime in all_runtimes(request):
        for p in core_metrics.timeline(runtime.vault_root, period_days=days):
            d = p.model_dump(mode="json")
            entry = by_date.setdefault(
                d["date"],
                {"date": d["date"], "tokens_injected": 0, "sessions": 0},
            )
            entry["tokens_injected"] += d.get("tokens_injected", 0)
            entry["sessions"] += d.get("sessions", 0)
    points = sorted(by_date.values(), key=lambda p: p["date"])
    return {"points": points}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/metrics.py tests/daemon/test_routes_metrics_aggregation.py
git commit -m "feat(daemon): /metrics/* real cross-vault aggregation"
```

---

## Task 14: Migrate `routes/health.py` to per-vault summary

**Files:**
- Modify: `claude_mnemos/daemon/routes/health.py`
- Modify: `claude_mnemos/daemon/schemas.py` — `HealthResponse` shape change
- Create: `tests/daemon/test_routes_health_aggregate.py`
- Update: existing `tests/daemon/test_app_health.py`

New shape:

```json
{
  "status": "ok",
  "version": "...",
  "uptime_s": 12.3,
  "scheduler_jobs": [...],
  "alerts_count": 5,
  "vaults": {
    "alpha": {
      "watchdog_running": true,
      "jobs_queued": 3,
      "jobs_running": 1,
      "jobs_dead_letter": 0
    },
    "beta": {...}
  }
}
```

`vault: str` field is **removed** from `HealthResponse`. `jobs_queued` / `jobs_running` / `jobs_dead_letter` / `watchdog_running` move under `vaults[name]`.

- [ ] **Step 1: Update `HealthResponse` schema**

```python
# claude_mnemos/daemon/schemas.py — modify HealthResponse
class VaultHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    watchdog_running: bool
    jobs_queued: int
    jobs_running: int
    jobs_dead_letter: int


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    version: str
    uptime_s: float
    scheduler_jobs: list[SchedulerJobInfo]
    alerts_count: int
    vaults: dict[str, VaultHealth]
    jobs_alert: bool
```

- [ ] **Step 2: Write failing tests**

```python
# tests/daemon/test_routes_health_aggregate.py
def test_health_lists_per_vault(daemon_with_two_vaults):
    daemon, client = daemon_with_two_vaults
    r = client.get("/health")
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["vaults"].keys()) == {"alpha", "beta"}
    assert body["vaults"]["alpha"]["watchdog_running"] in (True, False)
    assert "jobs_queued" in body["vaults"]["alpha"]


def test_health_empty_runtimes(empty_daemon):
    daemon, client = empty_daemon
    r = client.get("/health")
    body = r.json()
    assert body["vaults"] == {}
    assert body["status"] == "ok"
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Rewrite handler**

```python
@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    daemon = request.app.state.daemon
    uptime_s = 0.0
    jobs: list[SchedulerJobInfo] = []
    alerts_count = 0
    vaults: dict[str, VaultHealth] = {}
    total_dead_letter = 0
    if daemon is not None:
        if getattr(daemon, "started_at_monotonic", 0.0) > 0.0:
            uptime_s = max(0.0, time.monotonic() - daemon.started_at_monotonic)
        if hasattr(daemon, "scheduler_jobs_info"):
            jobs = daemon.scheduler_jobs_info()
        alerts = getattr(daemon, "alerts", None)
        if alerts is not None:
            alerts_count = len(alerts.list())
        runtimes = getattr(daemon, "runtimes", {}) or {}
        for name, runtime in sorted(runtimes.items()):
            observer = runtime.observer
            store = runtime.job_store
            counts: dict[str, int] = {}
            if store is not None:
                try:
                    counts = store.count_by_status()
                except Exception:
                    counts = {}
            vh_dead = int(counts.get("dead_letter", 0))
            total_dead_letter += vh_dead
            vaults[name] = VaultHealth(
                watchdog_running=bool(observer is not None and observer.is_running),
                jobs_queued=int(counts.get("queued", 0)),
                jobs_running=int(counts.get("running", 0)),
                jobs_dead_letter=vh_dead,
            )
    return HealthResponse(
        status="ok",
        version=__version__,
        uptime_s=uptime_s,
        scheduler_jobs=jobs,
        alerts_count=alerts_count,
        vaults=vaults,
        jobs_alert=total_dead_letter > 10,
    )
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/health.py claude_mnemos/daemon/schemas.py tests/daemon/test_routes_health_aggregate.py tests/daemon/test_app_health.py
git commit -m "feat(daemon): /health per-vault dict + drop top-level 'vault' field"
```

---

## Task 15: Drop `app.state.vault_root`, `primary_runtime`, `_recompute_primary`, `GlobalSettings.primary_project`

**Files:**
- Modify: `claude_mnemos/daemon/process.py`
- Modify: `claude_mnemos/daemon/app.py`
- Modify: `claude_mnemos/state/settings.py`
- Modify: existing tests that use these (verify list)

After Tasks 2-14, no production code reads any of these. This task removes them.

- [ ] **Step 1: Identify call sites**

```bash
grep -rn "primary_runtime\|_primary_runtime\|_recompute_primary\|primary_project" claude_mnemos
grep -rn "app.state.vault_root\|vault_root: Path | None" claude_mnemos
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/daemon/test_process_no_primary.py
def test_daemon_has_no_primary_runtime_property(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from claude_mnemos.daemon.process import MnemosDaemon
    from claude_mnemos.daemon.config import DaemonConfig
    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    assert not hasattr(daemon, "primary_runtime")
    assert not hasattr(daemon, "_primary_runtime")
    assert not hasattr(daemon, "_recompute_primary")
    assert not hasattr(daemon.app.state, "vault_root")


def test_global_settings_no_primary_project_field():
    from claude_mnemos.state.settings import GlobalSettings
    g = GlobalSettings()
    assert not hasattr(g, "primary_project")
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Modifications**

`claude_mnemos/daemon/process.py`:
- Remove `_primary_runtime: VaultRuntime | None`, `primary_runtime` property, `_recompute_primary()` method.
- In `__init__`, replace `self.app: FastAPI = create_app(vault_root=None, daemon=self)` with `self.app: FastAPI = create_app(daemon=self)`.
- Remove every `self._recompute_primary()` call (`mount_vault`, `unmount_vault`, `remount_vault`, `_shutdown_runtimes`).
- Simplify `reload_global_settings`:

```python
async def reload_global_settings(self, new: GlobalSettings) -> None:
    async with self._runtimes_lock:
        self.global_settings = new
```

- In `_shutdown_runtimes`, remove `self.app.state.vault_root = None`.

`claude_mnemos/daemon/app.py`:

```python
def create_app(daemon: Any | None = None) -> FastAPI:
    app = FastAPI(title="claude-mnemos daemon", version=__version__)
    app.state.daemon = daemon
    # ... rest unchanged
```

`claude_mnemos/state/settings.py`:

```python
class GlobalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")  # forbid still — primary_project simply gone
    version: Literal[1] = 1
    locale: Literal["uk", "ru", "en"] = "uk"
    daemon_port: int = Field(default=5757, ge=1, le=65535)
    default_model: str = "claude-sonnet-4-6"
    default_language_hint: Literal["auto", "uk", "ru", "en"] = "auto"
    default_max_input_tokens: int = Field(default=150_000, ge=1024)
    default_retention_days: int = Field(default=180, ge=1)
    # primary_project removed.
```

If users had a `primary_project` value persisted via β1, the strict `extra="forbid"` will cause `SettingsCorruptError` on next read. Migrate by switching this single field to `extra="ignore"` (one-shot tolerance for β1→β2 migration). Document the choice in commit message.

Actually: the cleaner fix is to keep `extra="forbid"` (β1 was never released to other users, only the developer) and write a migration that strips `primary_project` from existing files at daemon start. Since this is a single-user project, the simpler path is to switch `extra="ignore"` permanently — settings models accept unknown fields silently, simplifying future schema additions.

**Decision: switch `GlobalSettings` to `extra="ignore"`.** Documented as schema flexibility going forward.

```python
class GlobalSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")  # forward-compat for schema changes
    ...
```

- [ ] **Step 5: Update consumer/test references**

```bash
grep -rn "primary_runtime\|_primary_runtime\|_recompute_primary\|primary_project" tests
```

For each test that asserts existence/behaviour of these — delete or rewrite.

`tests/daemon/test_process_multivault.py`:
- `test_recompute_primary_*` tests — DELETE all 4 (alphabetical_first, pinned, pinned_missing_falls_back, empty_runtimes).
- Remove `daemon._recompute_primary()` calls from other tests.
- `test_init_empty_runtimes`: drop `assert daemon.primary_runtime is None` and `assert daemon.app.state.vault_root is None`.
- `test_reload_global_settings_repicks_primary` — DELETE (β1-specific).

`tests/state/test_settings.py`:
- Remove `test_global_settings_primary_project_*` tests.

`tests/daemon/test_routes_no_primary.py` (β1) — keep but tests now assert per-route 404 (`unknown_project`) when calling with unknown project on populated daemon. Or DELETE if the new per-route 404 tests cover it.

- [ ] **Step 6: Run full daemon suite**

```
pytest tests/daemon/ tests/state/ -v 2>&1 | tail -30
```

Expected: green (with adjusted tests).

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/daemon/process.py claude_mnemos/daemon/app.py claude_mnemos/state/settings.py
git add tests/daemon/test_process_multivault.py tests/state/test_settings.py
git add tests/daemon/test_process_no_primary.py
# ... other touched files
git commit -m "refactor: drop app.state.vault_root + primary_runtime + GlobalSettings.primary_project"
```

---

## Task 16: Update MCP write tools

**Files:**
- Modify: `claude_mnemos/mcp/write_tools/snapshots.py` — `/snapshots/{project}/...`
- Modify: `claude_mnemos/mcp/write_tools/lint.py` — `/lint/{project}/run`
- Modify: `claude_mnemos/mcp/write_tools/ontology.py` — `/ontology/{project}/...`
- Modify: `claude_mnemos/mcp/write_tools/activity.py` — `/activity/{project}/{id}/undo`
- Modify: `claude_mnemos/mcp/server.py` — pass project name to write tool calls
- Update: relevant tests in `tests/mcp/`

The MCP server already knows its project name (`mcp_config.project_name` after `--auto-resolve` or `--project NAME`). Each write tool gets a `project: str` parameter (or pulls it from config).

- [ ] **Step 1: Read current MCP write tools** (4 files) to see their signatures and how they're called from `server.py`.

- [ ] **Step 2: Write failing tests**

For each MCP write tool, update its test to assert the URL contains `/{project}/`:

```python
# tests/mcp/test_write_tools_snapshots.py — example
def test_create_snapshot_url_includes_project(monkeypatch):
    captured = {}
    async def fake_call_daemon(client, method, url, *, json_body=None):
        captured["url"] = url
        captured["method"] = method
        return {"name": "snap"}
    monkeypatch.setattr(
        "claude_mnemos.mcp.write_tools.snapshots.call_daemon", fake_call_daemon
    )
    from claude_mnemos.mcp.write_tools.snapshots import create_snapshot
    asyncio.run(create_snapshot(daemon_url="http://x", project="alpha", label=None))
    assert captured["url"] == "http://x/snapshots/alpha"
    assert captured["method"] == "POST"
```

(Repeat for each write tool, asserting `/lint/alpha/run`, `/ontology/alpha/run`, `/activity/alpha/{id}/undo`, etc.)

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Update each write tool**

Add `project: str` parameter to the function signature, embed it in the URL:

```python
# claude_mnemos/mcp/write_tools/snapshots.py
async def create_snapshot(
    daemon_url: str, *, project: str, label: str | None
) -> dict[str, Any]:
    return await call_daemon(
        client,
        "POST",
        f"{daemon_url.rstrip('/')}/snapshots/{project}",
        json_body={"label": label},
    )

async def restore_snapshot(
    daemon_url: str, *, project: str, name: str
) -> dict[str, Any]:
    return await call_daemon(
        client, "POST",
        f"{daemon_url.rstrip('/')}/snapshots/{project}/{name}/restore",
    )

async def delete_snapshot(
    daemon_url: str, *, project: str, name: str
) -> dict[str, Any]:
    return await call_daemon(
        client, "DELETE",
        f"{daemon_url.rstrip('/')}/snapshots/{project}/{name}",
    )
```

Apply analogous changes to lint.py, ontology.py, activity.py.

- [ ] **Step 5: Update `claude_mnemos/mcp/server.py`**

Wherever the server invokes a write tool, pass `project=mcp_config.project_name` (or wherever the project is stored). Read the file, find the call sites, update them.

- [ ] **Step 6: Run MCP suite**

```
pytest tests/mcp/ -v 2>&1 | tail -20
```

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/mcp tests/mcp
git commit -m "feat(mcp): write tools embed {project} segment per β2 routing"
```

---

## Task 17: Update CLI subcommands

**Files:**
- Identify CLI commands that hit changed routes.

```bash
grep -rn "f\"\{daemon_base_url" claude_mnemos/cli*.py
grep -rn "\"/snapshots\\|/sessions\\|/pages\\|/trash\\|/lint\\|/ontology\\|/activity\\|/vault\"" claude_mnemos/cli*.py
```

For β1, most CLI flows already passed through `--project NAME` and used `/projects/*` or `/settings/*` (both unchanged). β2 adds new URL patterns. Audit:
- `claude_mnemos/cli.py` — daemon health/status calls `/health` (shape change: now `vaults: {...}` dict).
- Any other subcommand directly hitting daemon REST.

- [ ] **Step 1: Audit + write failing tests for affected commands**

If `mnemos daemon status` parses `/health` response and was looking for `vault` field — now it looks for `vaults` dict, lists per-project. Update CLI output formatting.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Update CLI parsers/formatters** — adapt to new `/health` shape, pass `--project NAME` through to URL building where applicable.

- [ ] **Step 4: Run CLI tests**

```
pytest tests/test_cli*.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/cli*.py tests/test_cli*.py
git commit -m "feat(cli): adapt daemon status output to /health per-vault shape"
```

---

## Task 18: Re-enable e2e tests skip-marked in β1

**Files:**
- Modify: `tests/daemon/test_jobs_e2e.py`
- Modify: `tests/daemon/test_watchdog_e2e.py`
- Modify: `tests/e2e/test_project_settings_e2e.py` (3 tests)

These had `pytest.mark.skip` with TODO(β2) reasons. β2 has now made the underlying routes work. Remove the skip markers, adapt test bodies to new URL shapes / response formats.

- [ ] **Step 1: Read each file**

```bash
cat tests/daemon/test_jobs_e2e.py | head -20
cat tests/daemon/test_watchdog_e2e.py | head -20
cat tests/e2e/test_project_settings_e2e.py | head -40
```

- [ ] **Step 2: Remove skip markers**

For each, remove `pytestmark = pytest.mark.skip(...)` line at top of file. Adapt assertions:
- `test_jobs_e2e.py` — `GET /jobs` now returns cross-vault list; assertions should use `?project=NAME` filter or expect list with `project_name` field.
- `test_watchdog_e2e.py` — `/health` response has `vaults[name].watchdog_running` instead of top-level `watchdog_running`.
- `test_project_settings_e2e.py` — `PATCH /settings/{name}` already works; the skip reason was about the now-removed `daemon.config.vault_root`. Re-enable as-is and verify.

- [ ] **Step 3: Run slow suite**

```
pytest -m slow -v 2>&1 | tail -30
```

If a test still fails, debug the remaining issue (likely an off-by-one or response shape mismatch).

- [ ] **Step 4: Commit**

```bash
git add tests/daemon/test_jobs_e2e.py tests/daemon/test_watchdog_e2e.py tests/e2e/test_project_settings_e2e.py
git commit -m "test(e2e): re-enable 6 tests skip-marked in β1, adapt to β2 URLs/shape"
```

---

## Task 19: Final verification

**Files:** all

- [ ] **Step 1: Run fast suite**

```
pytest -q --ignore=tests/daemon/integration -k "not slow" 2>&1 | tail -10
```

Target: ~1180+ passed, 2 skipped (only `test_real_extraction` for missing API key + maybe one filesystem flaky).

- [ ] **Step 2: Run slow suite**

```
pytest -q -m slow 2>&1 | tail -10
```

Target: 10+ passed (β1's 4 + β2's re-enabled 6). 1 skipped (test_real_extraction).

- [ ] **Step 3: ruff + mypy**

```
ruff check claude_mnemos tests
mypy --strict claude_mnemos
```

Both clean.

- [ ] **Step 4: Hard-cut grep**

```bash
grep -rn "primary_runtime\|_primary_runtime\|_recompute_primary" claude_mnemos
grep -rn "primary_project" claude_mnemos/state
grep -rn "app.state.vault_root" claude_mnemos
grep -rn "request.app.state.vault_root" claude_mnemos
grep -rn "_vault(request)" claude_mnemos/daemon/routes
```

Expected: 0 matches everywhere (except possibly the `_vault` test name in `tests/`).

- [ ] **Step 5: Acceptance criteria walk-through**

For each AC in design §9:
1. Every per-project route has `{project}` first segment.
2. Unknown project → 404 `unknown_project`.
3. `app.state.vault_root` gone.
4. `daemon.primary_runtime`/`_primary_runtime`/`_recompute_primary` gone.
5. `GlobalSettings.primary_project` gone.
6. `/lost-sessions` cross-vault.
7. `/jobs` cross-vault + `?project=` filter.
8. `/dead-letter` cross-vault.
9. `/metrics/*` real cross-vault aggregation.
10. `/health` per-vault dict.
11. 6 e2e tests re-enabled.
12. Test suite green.
13. ruff + mypy clean.
14. CLI subcommands working with new URLs.

Each must point to a passing test or grep result.

- [ ] **Step 6: Branch summary**

```bash
git log --oneline main..HEAD
```

Should show ~20 focused commits (Task 1 through Task 19 merge prep).

```bash
git status
```

Clean.

---

## Spec coverage map

| Design §   | Plan task(s) |
|------------|--------------|
| 1.1 (background) | n/a |
| 1.2 (goal) | All tasks |
| 1.3 (non-goals) | Documented; no tasks |
| 1.4 (spec alignment) | Tasks 2-14 (per-route migrations + cross-vault) |
| 2.1 (path-prefix routing) | Tasks 2-9 |
| 2.2 (global routes) | Tasks 10-14 |
| 2.3 (`get_runtime` helper) | Task 1 |
| 2.4 (cross-vault aggregation pattern) | Task 1 (`all_runtimes`) |
| 2.5 (`MnemosDaemon` cleanup) | Task 15 |
| 2.6 (`app.py` cleanup) | Task 15 |
| 3.1 sessions | Task 2 |
| 3.2 snapshots | Task 3 |
| 3.3 pages | Task 4 |
| 3.4 trash | Task 5 |
| 3.5 lint | Task 6 |
| 3.6 ontology | Task 7 |
| 3.7 activity | Task 8 |
| 3.8 vault | Task 9 |
| 3.9 lost_sessions | Task 10 |
| 3.10 jobs | Task 11 |
| 3.11 dead_letter | Task 12 |
| 3.12 metrics | Task 13 |
| 3.13 health | Task 14 |
| 4 (state to remove) | Task 15 |
| 5.1 (SessionEnd hook) | n/a (no change) |
| 5.2 (CLI updates) | Task 17 |
| 5.3 (MCP) | Task 16 |
| 5.4 (other plugins/hooks) | n/a (β2 doesn't touch) |
| 6 (testing strategy) | Tasks 2-14 (per-task TDD) + Tasks 10-14 (cross-vault) + Task 18 (e2e) |
| 7 (file-level summary) | Files map at top |
| 8 (risks/rollback) | n/a operational |
| 9 (acceptance criteria) | Task 19 step 5 |
| 10 (open questions) | n/a (decisions baked in) |
| 11 (out of scope) | n/a |

No uncovered spec requirements.
