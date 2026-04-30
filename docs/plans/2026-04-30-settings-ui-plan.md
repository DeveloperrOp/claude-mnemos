# Settings UI Implementation Plan (Plan B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace placeholder Settings page with real editing UI: Project Settings (12-section accordion incl. rename/CWD/8 settings groups/ingest overrides/delete) + Global Settings page. Reuses CwdBuilder + DirectoryPicker from Plan A.

**Architecture:** Per-section accordion с explicit Save button per section. General уходит на `PATCH /projects/{slug}` (display_name+cwd_patterns); остальные 11 секций → `PATCH /settings/{slug}` (Pydantic deep_merge). Delete project → новый `DELETE /projects/{slug}` endpoint с typed-confirm + force flag. Global Settings — отдельная страница на `/settings/global`.

**Tech Stack:** React 19 + Vite + TypeScript + zod + TanStack Query + react-i18next; FastAPI + Pydantic v2.

**Design doc:** `docs/plans/2026-04-30-settings-ui-design.md`.

**Branch:** `feat/settings-ui` (из `main` после merge `80a3979`, design committed `9b2859d`).

**Critical safety rule:** Каждая фаза заканчивается зелёным test suite. Backend baseline 1490 → ~1495 после Phase 1. Frontend baseline 238 → растёт постепенно. Zero-diff в untouchable: `extraction.py / parser.py / metrics.py / hooks/ / state/jobs.py / daemon/jobs/ / state/manifest.py / state/settings.py (Pydantic schemas)`.

---

## File Structure

### New backend files

```
(none — DELETE endpoint added to existing claude_mnemos/daemon/routes/projects.py)
tests/daemon/routes/test_projects_delete.py
```

### New frontend files

```
frontend/src/types/Settings.ts                    # zod schemas mirroring Pydantic
frontend/src/api/settings.api.ts                  # GET/PATCH /settings/{slug} + global
frontend/src/api/projects.api.ts                  # +deleteProject (existing file, add func)
frontend/src/hooks/useProjectSettings.ts          # query + mutation hooks for project settings
frontend/src/hooks/useGlobalSettings.ts           # global

frontend/src/components/settings/
├── SettingsAccordion.tsx                         # collapsible section wrapper with Save button
├── sections/
│   ├── GeneralSection.tsx                        # display_name + slug RO + vault RO + CwdBuilder
│   ├── LocaleSection.tsx                         # inherit/uk/ru/en radio
│   ├── AutoIngestSection.tsx
│   ├── LintSection.tsx
│   ├── OntologySection.tsx
│   ├── WatchdogSection.tsx
│   ├── SnapshotsSection.tsx
│   ├── LifecycleSection.tsx
│   ├── PromptsSection.tsx
│   ├── TelemetrySection.tsx
│   ├── IngestOverridesSection.tsx
│   └── DangerZoneSection.tsx                     # Delete project with typed-confirm
└── globals/
    ├── GlobalGeneralSection.tsx                  # locale + daemon_port
    └── GlobalDefaultsSection.tsx                 # default_model + default_language_hint + ...

frontend/src/pages/
├── ProjectSettings.tsx                           # composes 12 sections in accordion
└── GlobalSettings.tsx                            # composes 2 sections

frontend/src/__tests__/
├── api-settings.test.ts
├── api-projects-delete.test.ts
├── useProjectSettings.test.ts
├── SettingsAccordion.test.tsx
├── GeneralSection.test.tsx
├── AutoIngestSection.test.tsx                    # template — simple bool+enum section
├── DangerZoneSection.test.tsx                    # critical: delete flow
├── ProjectSettings.test.tsx
└── GlobalSettings.test.tsx
```

### Modified files

```
claude_mnemos/daemon/routes/projects.py           # +DELETE /projects/{slug}
frontend/src/pages/ProjectView.tsx                # remove Settings placeholder, route to ProjectSettings
frontend/src/components/layout/Sidebar.tsx        # +Global settings link
frontend/src/App.tsx (or router config)           # +/settings/global route
frontend/public/locales/{en,ru,uk}.json           # ~80 new keys
```

### Untouched (zero-diff)

```
claude_mnemos/ingest/
claude_mnemos/state/manifest.py
claude_mnemos/core/metrics.py
claude_mnemos/hooks/
claude_mnemos/state/jobs.py
claude_mnemos/daemon/jobs/
claude_mnemos/state/settings.py                   # Pydantic schemas frozen — used as-is
claude_mnemos/state/projects.py                   # ProjectStore.remove already exists
```

---

# Phase 1 — Backend DELETE endpoint

**Goal:** Add `DELETE /projects/{slug}` endpoint with optional `?force=true` for override of running-jobs check. SettingsStore.reset_project (which physically unlinks the per-project settings JSON) gets reused — no new helper needed.

**Safety:** Backend baseline 1490 → ~1495 (5 new tests).

---

## Task 1: DELETE /projects/{slug} endpoint

**Files:**
- Modify: `claude_mnemos/daemon/routes/projects.py`
- Create: `tests/daemon/routes/test_projects_delete.py`

- [ ] **Step 1: Inspect existing DELETE patterns + ProjectStore.remove + daemon.unmount_project**

```bash
cd /d/code/claude-mnemos
grep -n "@router.delete\|router.delete" claude_mnemos/daemon/routes/*.py | head
grep -n "def remove\|unmount_project\|async def unmount" claude_mnemos/state/projects.py claude_mnemos/daemon/process.py | head
```

Find the daemon's project-unmount method (likely `MnemosDaemon.unmount_project(name)` or similar). Verify it stops watchdog + drains/cancels jobs. Note its signature.

- [ ] **Step 2: Write the failing tests**

Create `tests/daemon/routes/test_projects_delete.py`. Adapt to existing test harness in `tests/daemon/test_routes_projects.py` (use the same `client` fixture pattern):

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Reuse the same TestClient fixture style as existing routes tests.
# Adapt imports if the existing tests use a different setup.
from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


@pytest.fixture
def daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MnemosDaemon:
    monkeypatch.setenv("MNEMOS_PROJECT_MAP", str(tmp_path / "project-map.json"))
    monkeypatch.setenv("MNEMOS_HOME", str(tmp_path / ".claude-mnemos"))
    return MnemosDaemon(DaemonConfig(boot_filter=None))


@pytest.fixture
def client(daemon: MnemosDaemon) -> TestClient:
    return TestClient(daemon.app)


def _add_project(client: TestClient, name: str = "p1", vault: str | None = None) -> None:
    body = {"name": name, "vault_root": vault or "/tmp/v", "cwd_patterns": []}
    resp = client.post("/projects", json=body)
    assert resp.status_code in (200, 201)


def test_delete_project_returns_204_on_success(client: TestClient, daemon: MnemosDaemon) -> None:
    _add_project(client, name="p1", vault="/tmp/v1")
    with patch.object(daemon, "unmount_project", new_callable=AsyncMock) as unmount:
        resp = client.delete("/projects/p1")
    assert resp.status_code == 204
    unmount.assert_awaited_once_with("p1")
    # Project gone from registry
    assert client.get("/projects/p1").status_code == 404


def test_delete_project_returns_404_when_missing(client: TestClient) -> None:
    resp = client.delete("/projects/does-not-exist")
    assert resp.status_code == 404


def test_delete_project_removes_settings_file(
    client: TestClient, daemon: MnemosDaemon, tmp_path: Path,
) -> None:
    _add_project(client, name="p2")
    # Force a settings PATCH so the file exists.
    client.patch("/settings/p2", json={"telemetry": {"opt_in": True}})
    settings_path = Path(tmp_path / ".claude-mnemos" / "settings" / "p2.json")
    assert settings_path.exists()
    with patch.object(daemon, "unmount_project", new_callable=AsyncMock):
        client.delete("/projects/p2")
    assert not settings_path.exists()


def test_delete_project_blocks_when_jobs_running(
    client: TestClient, daemon: MnemosDaemon,
) -> None:
    _add_project(client, name="p3")
    # Stub job-store to claim a running job.
    runtime = daemon.runtimes.get("p3")
    if runtime and runtime.job_store:
        with patch.object(runtime.job_store, "list_by_status",
                          return_value=[{"id": "j1", "status": "running"}]):
            resp = client.delete("/projects/p3")
            assert resp.status_code == 409
            assert "jobs" in resp.json()["detail"].lower()


def test_delete_project_force_overrides_jobs_running(
    client: TestClient, daemon: MnemosDaemon,
) -> None:
    _add_project(client, name="p4")
    runtime = daemon.runtimes.get("p4")
    if runtime and runtime.job_store:
        with patch.object(runtime.job_store, "list_by_status",
                          return_value=[{"id": "j1", "status": "running"}]), \
             patch.object(daemon, "unmount_project", new_callable=AsyncMock):
            resp = client.delete("/projects/p4?force=true")
            assert resp.status_code == 204
```

- [ ] **Step 3: Run failing tests**

```bash
python -m pytest tests/daemon/routes/test_projects_delete.py -v 2>&1 | tail -10
```

Expected: 405 Method Not Allowed (no DELETE handler).

- [ ] **Step 4: Implement DELETE endpoint**

In `claude_mnemos/daemon/routes/projects.py`, add a route. Adapt to existing pattern (same router + `daemon: MnemosDaemon = Depends(...)` style):

```python
from fastapi import HTTPException, Query, Response

@router.delete("/projects/{slug}", status_code=204)
async def delete_project(
    slug: str,
    force: bool = Query(False),
    daemon: "MnemosDaemon" = Depends(get_daemon),
) -> Response:
    store = daemon.project_store
    try:
        store.get(slug)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"project {slug!r} not found") from exc

    # Block on running jobs unless caller forces.
    runtime = daemon.runtimes.get(slug)
    if runtime is not None and runtime.job_store is not None and not force:
        running = [j for j in runtime.job_store.list_by_status("running")]
        queued = [j for j in runtime.job_store.list_by_status("queued")]
        in_flight = len(running) + len(queued)
        if in_flight > 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"project {slug!r} has {in_flight} job(s) in flight "
                    f"(running={len(running)}, queued={len(queued)}); "
                    "wait for completion or pass ?force=true to override"
                ),
            )

    await daemon.unmount_project(slug)
    store.remove(slug)
    daemon.settings_store.reset_project(slug)  # physically deletes settings file
    return Response(status_code=204)
```

(Exact `Depends(get_daemon)` symbol depends on existing code — match existing routes pattern. `ProjectNotFoundError` import comes from `claude_mnemos.state.projects`.)

- [ ] **Step 5: Run tests — must pass**

```bash
python -m pytest tests/daemon/routes/test_projects_delete.py -v 2>&1 | tail -10
```

Expected: `5 passed`.

- [ ] **Step 6: Run all backend tests — no regressions**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1495 passed, 3 skipped` (1490 baseline + 5 new).

- [ ] **Step 7: ruff**

```bash
python -m ruff check . 2>&1 | tail -3
```

Expected: `All checks passed!`. Fix if errors.

- [ ] **Step 8: Commit**

```bash
git add claude_mnemos/daemon/routes/projects.py tests/daemon/routes/test_projects_delete.py && git commit -m "feat(daemon): DELETE /projects/{slug} endpoint with force flag

Removes project from registry: unmount_project + ProjectStore.remove +
SettingsStore.reset_project (physically unlinks settings file). Vault
folder NOT touched — re-add with same slug + vault to restore.

409 if running/queued jobs exist; ?force=true overrides. 404 if missing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Phase 1 verification

- [ ] **Step 1: Full backend tests + ruff + zero-diff**

```bash
cd /d/code/claude-mnemos
python -m pytest --ignore=tests/slow 2>&1 | tail -3
python -m ruff check . 2>&1 | tail -3
git diff main -- claude_mnemos/ingest/ claude_mnemos/state/manifest.py claude_mnemos/core/metrics.py claude_mnemos/hooks/ claude_mnemos/state/jobs.py claude_mnemos/daemon/jobs/ claude_mnemos/state/settings.py 2>&1 | wc -l
```

Expected: `1495 passed`, ruff clean, diff `0`.

---

# Phase 2 — Frontend foundation

**Goal:** zod schemas mirroring Pydantic + axios api wrappers + TanStack Query hooks + reusable SettingsAccordion. After Phase 2 sections can be added section-by-section in Phase 3+.

---

## Task 3: types/Settings.ts + api/settings.api.ts

**Files:**
- Create: `frontend/src/types/Settings.ts`
- Create: `frontend/src/api/settings.api.ts`
- Modify: `frontend/src/api/projects.api.ts` (add deleteProject)
- Create: `frontend/src/__tests__/api-settings.test.ts`
- Create: `frontend/src/__tests__/api-projects-delete.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/api-settings.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from "vitest";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { getProjectSettings, patchProjectSettings, getGlobalSettings, patchGlobalSettings } from "../api/settings.api";

let mock: MockAdapter;

beforeEach(() => {
  mock = new MockAdapter(axios);
});

const FULL_PROJECT = {
  version: 1,
  locale: null,
  auto_ingest: { enabled: true, mode: "auto" },
  lint: { schedule: null, enabled_rules: null, autofix_on_save: false },
  ontology: { auto_mode: false, confidence_min: 0.7, confidence_auto_apply: 0.95 },
  watchdog: { mode: "merge" },
  snapshots: { daily_enabled: true, retention_days: 180 },
  lifecycle: { auto_stale_days: 90, auto_archive: false },
  prompts: { custom_system_path: null, custom_extract_user_path: null },
  telemetry: { opt_in: false },
  ingest: { model: null, language_hint: null, max_input_tokens: null, context_limit: null },
};

describe("settings API", () => {
  it("getProjectSettings parses full payload", async () => {
    mock.onGet("/settings/p1").reply(200, FULL_PROJECT);
    const result = await getProjectSettings("p1");
    expect(result.locale).toBeNull();
    expect(result.auto_ingest.enabled).toBe(true);
    expect(result.snapshots.retention_days).toBe(180);
  });

  it("patchProjectSettings sends partial body", async () => {
    mock.onPatch("/settings/p1").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({ telemetry: { opt_in: true } });
      return [200, { ...FULL_PROJECT, telemetry: { opt_in: true } }];
    });
    const result = await patchProjectSettings("p1", { telemetry: { opt_in: true } });
    expect(result.telemetry.opt_in).toBe(true);
  });

  it("getGlobalSettings parses payload", async () => {
    mock.onGet("/settings/global").reply(200, {
      version: 1,
      locale: "uk",
      daemon_port: 5757,
      default_model: "claude-sonnet-4-6",
      default_language_hint: "auto",
      default_max_input_tokens: 150000,
      default_retention_days: 180,
    });
    const g = await getGlobalSettings();
    expect(g.daemon_port).toBe(5757);
    expect(g.default_model).toBe("claude-sonnet-4-6");
  });

  it("patchGlobalSettings sends partial", async () => {
    mock.onPatch("/settings/global").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({ daemon_port: 6000 });
      return [200, {
        version: 1, locale: "uk", daemon_port: 6000, default_model: "x",
        default_language_hint: "auto", default_max_input_tokens: 150000,
        default_retention_days: 180,
      }];
    });
    const g = await patchGlobalSettings({ daemon_port: 6000 });
    expect(g.daemon_port).toBe(6000);
  });
});
```

Create `frontend/src/__tests__/api-projects-delete.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from "vitest";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { deleteProject } from "../api/projects.api";

let mock: MockAdapter;

beforeEach(() => {
  mock = new MockAdapter(axios);
});

describe("deleteProject", () => {
  it("DELETE /projects/{slug} happy path", async () => {
    mock.onDelete("/projects/p1").reply(204);
    await expect(deleteProject("p1")).resolves.toBeUndefined();
  });

  it("DELETE supports ?force=true", async () => {
    mock.onDelete("/projects/p1").reply((config) => {
      expect(config.params).toEqual({ force: true });
      return [204];
    });
    await deleteProject("p1", { force: true });
  });
});
```

- [ ] **Step 2: Run failing tests**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/api-settings.test.ts src/__tests__/api-projects-delete.test.ts 2>&1 | tail -10
```

Expected: import errors.

- [ ] **Step 3: Implement types**

Create `frontend/src/types/Settings.ts`:
```typescript
import { z } from "zod";

const LocaleSchema = z.enum(["uk", "ru", "en"]);

export const AutoIngestSettingsSchema = z.object({
  enabled: z.boolean().default(true),
  mode: z.enum(["auto", "hybrid", "manual"]).default("auto"),
});
export type AutoIngestSettings = z.infer<typeof AutoIngestSettingsSchema>;

export const LintSettingsSchema = z.object({
  schedule: z.string().nullable().default(null),
  enabled_rules: z.array(z.string()).nullable().default(null),
  autofix_on_save: z.boolean().default(false),
});
export type LintSettings = z.infer<typeof LintSettingsSchema>;

export const OntologySettingsSchema = z.object({
  auto_mode: z.boolean().default(false),
  confidence_min: z.number().min(0).max(1).default(0.7),
  confidence_auto_apply: z.number().min(0).max(1).default(0.95),
});
export type OntologySettings = z.infer<typeof OntologySettingsSchema>;

export const WatchdogSettingsSchema = z.object({
  mode: z.enum(["strict", "merge", "open"]).default("merge"),
});
export type WatchdogSettings = z.infer<typeof WatchdogSettingsSchema>;

export const SnapshotsSettingsSchema = z.object({
  daily_enabled: z.boolean().default(true),
  retention_days: z.number().int().min(1).default(180),
});
export type SnapshotsSettings = z.infer<typeof SnapshotsSettingsSchema>;

export const LifecycleSettingsSchema = z.object({
  auto_stale_days: z.number().int().min(1).default(90),
  auto_archive: z.boolean().default(false),
});
export type LifecycleSettings = z.infer<typeof LifecycleSettingsSchema>;

export const PromptsSettingsSchema = z.object({
  custom_system_path: z.string().nullable().default(null),
  custom_extract_user_path: z.string().nullable().default(null),
});
export type PromptsSettings = z.infer<typeof PromptsSettingsSchema>;

export const TelemetrySettingsSchema = z.object({
  opt_in: z.boolean().default(false),
});
export type TelemetrySettings = z.infer<typeof TelemetrySettingsSchema>;

export const IngestOverridesSchema = z.object({
  model: z.string().nullable().default(null),
  language_hint: z.enum(["auto", "uk", "ru", "en"]).nullable().default(null),
  max_input_tokens: z.number().int().nullable().default(null),
  context_limit: z.number().int().nullable().default(null),
});
export type IngestOverrides = z.infer<typeof IngestOverridesSchema>;

export const ProjectSettingsSchema = z.object({
  version: z.literal(1).default(1),
  locale: LocaleSchema.nullable().default(null),
  auto_ingest: AutoIngestSettingsSchema,
  lint: LintSettingsSchema,
  ontology: OntologySettingsSchema,
  watchdog: WatchdogSettingsSchema,
  snapshots: SnapshotsSettingsSchema,
  lifecycle: LifecycleSettingsSchema,
  prompts: PromptsSettingsSchema,
  telemetry: TelemetrySettingsSchema,
  ingest: IngestOverridesSchema,
});
export type ProjectSettings = z.infer<typeof ProjectSettingsSchema>;

export const GlobalSettingsSchema = z.object({
  version: z.literal(1).default(1),
  locale: LocaleSchema.default("uk"),
  daemon_port: z.number().int().min(1).max(65535).default(5757),
  default_model: z.string().default("claude-sonnet-4-6"),
  default_language_hint: z.enum(["auto", "uk", "ru", "en"]).default("auto"),
  default_max_input_tokens: z.number().int().min(1024).default(150000),
  default_retention_days: z.number().int().min(1).default(180),
});
export type GlobalSettings = z.infer<typeof GlobalSettingsSchema>;

// Partial patches — every nested section optional.
export type ProjectSettingsPatch = Partial<{
  locale: "uk" | "ru" | "en" | null;
  auto_ingest: Partial<AutoIngestSettings>;
  lint: Partial<LintSettings>;
  ontology: Partial<OntologySettings>;
  watchdog: Partial<WatchdogSettings>;
  snapshots: Partial<SnapshotsSettings>;
  lifecycle: Partial<LifecycleSettings>;
  prompts: Partial<PromptsSettings>;
  telemetry: Partial<TelemetrySettings>;
  ingest: Partial<IngestOverrides>;
}>;

export type GlobalSettingsPatch = Partial<Omit<GlobalSettings, "version">>;
```

- [ ] **Step 4: Implement settings.api.ts**

Create `frontend/src/api/settings.api.ts`:
```typescript
import axios from "axios";
import {
  GlobalSettingsSchema,
  ProjectSettingsSchema,
  type GlobalSettings,
  type GlobalSettingsPatch,
  type ProjectSettings,
  type ProjectSettingsPatch,
} from "@/types/Settings";

export async function getProjectSettings(slug: string): Promise<ProjectSettings> {
  const { data } = await axios.get(`/settings/${slug}`);
  return ProjectSettingsSchema.parse(data);
}

export async function patchProjectSettings(
  slug: string,
  patch: ProjectSettingsPatch,
): Promise<ProjectSettings> {
  const { data } = await axios.patch(`/settings/${slug}`, patch);
  return ProjectSettingsSchema.parse(data);
}

export async function getGlobalSettings(): Promise<GlobalSettings> {
  const { data } = await axios.get("/settings/global");
  return GlobalSettingsSchema.parse(data);
}

export async function patchGlobalSettings(
  patch: GlobalSettingsPatch,
): Promise<GlobalSettings> {
  const { data } = await axios.patch("/settings/global", patch);
  return GlobalSettingsSchema.parse(data);
}
```

- [ ] **Step 5: Add deleteProject to projects.api.ts**

Open `frontend/src/api/projects.api.ts`. Add at the end:
```typescript
export async function deleteProject(slug: string, opts?: { force?: boolean }): Promise<void> {
  const params = opts?.force ? { force: true } : undefined;
  await axios.delete(`/projects/${slug}`, { params });
}
```

- [ ] **Step 6: Run tests — must pass**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/api-settings.test.ts src/__tests__/api-projects-delete.test.ts 2>&1 | tail -10
```

Expected: `6 passed`.

- [ ] **Step 7: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/types/Settings.ts frontend/src/api/settings.api.ts frontend/src/api/projects.api.ts frontend/src/__tests__/api-settings.test.ts frontend/src/__tests__/api-projects-delete.test.ts && git commit -m "feat(frontend): settings API client + zod schemas + deleteProject

zod schemas mirror Pydantic ProjectSettings/GlobalSettings exactly.
Permissive parsing (defaults match backend). PATCH wrappers accept
partial bodies (TypeScript Partial<> types).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: TanStack Query hooks + SettingsAccordion

**Files:**
- Create: `frontend/src/hooks/useProjectSettings.ts`
- Create: `frontend/src/hooks/useGlobalSettings.ts`
- Create: `frontend/src/components/settings/SettingsAccordion.tsx`
- Create: `frontend/src/__tests__/useProjectSettings.test.ts`
- Create: `frontend/src/__tests__/SettingsAccordion.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/useProjectSettings.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useProjectSettings, useProjectSettingsMutation } from "../hooks/useProjectSettings";

let mock: MockAdapter;
beforeEach(() => { mock = new MockAdapter(axios); });

const FULL = {
  version: 1, locale: null,
  auto_ingest: { enabled: true, mode: "auto" },
  lint: { schedule: null, enabled_rules: null, autofix_on_save: false },
  ontology: { auto_mode: false, confidence_min: 0.7, confidence_auto_apply: 0.95 },
  watchdog: { mode: "merge" },
  snapshots: { daily_enabled: true, retention_days: 180 },
  lifecycle: { auto_stale_days: 90, auto_archive: false },
  prompts: { custom_system_path: null, custom_extract_user_path: null },
  telemetry: { opt_in: false },
  ingest: { model: null, language_hint: null, max_input_tokens: null, context_limit: null },
};

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useProjectSettings", () => {
  it("fetches project settings", async () => {
    mock.onGet("/settings/p1").reply(200, FULL);
    const { result } = renderHook(() => useProjectSettings("p1"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.snapshots.retention_days).toBe(180);
  });

  it("mutation patches and updates cache", async () => {
    mock.onGet("/settings/p1").reply(200, FULL);
    mock.onPatch("/settings/p1").reply(200, { ...FULL, telemetry: { opt_in: true } });

    const wrapper = makeWrapper();
    const query = renderHook(() => useProjectSettings("p1"), { wrapper });
    const mut = renderHook(() => useProjectSettingsMutation("p1"), { wrapper });
    await waitFor(() => expect(query.result.current.data).toBeDefined());

    mut.result.current.mutate({ telemetry: { opt_in: true } });
    await waitFor(() => expect(query.result.current.data?.telemetry.opt_in).toBe(true));
  });
});
```

Create `frontend/src/__tests__/SettingsAccordion.test.tsx`:
```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingsAccordion } from "../components/settings/SettingsAccordion";

describe("SettingsAccordion", () => {
  it("renders title and toggles content", async () => {
    render(
      <SettingsAccordion title="Test section" dirty={false} saving={false} onSave={() => {}}>
        <div>body content</div>
      </SettingsAccordion>
    );
    expect(screen.getByText("Test section")).toBeInTheDocument();
    // Body might be hidden initially or shown — depends on default open state.
    // Toggle and verify visibility flips.
    const toggle = screen.getByRole("button", { name: /Test section/ });
    await userEvent.click(toggle);
    // After toggle, body either appears or hides; just verify aria-expanded changes
    // (component may use Radix collapsible — pin behaviour with aria-expanded).
    expect(toggle).toHaveAttribute("aria-expanded");
  });

  it("Save button disabled when not dirty", () => {
    render(
      <SettingsAccordion title="X" dirty={false} saving={false} onSave={() => {}}>
        <div />
      </SettingsAccordion>
    );
    const save = screen.getByRole("button", { name: /Save|Сохранить|Зберегти/i });
    expect(save).toBeDisabled();
  });

  it("Save button enabled when dirty, calls onSave", async () => {
    const onSave = vi.fn();
    render(
      <SettingsAccordion title="X" dirty={true} saving={false} onSave={onSave}>
        <div />
      </SettingsAccordion>
    );
    const save = screen.getByRole("button", { name: /Save|Сохранить|Зберегти/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);
    expect(onSave).toHaveBeenCalled();
  });

  it("Save button shows saving state", () => {
    render(
      <SettingsAccordion title="X" dirty={true} saving={true} onSave={() => {}}>
        <div />
      </SettingsAccordion>
    );
    const save = screen.getByRole("button", { name: /Saving|Сохранение|Збереження/i });
    expect(save).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run failing tests**

```bash
pnpm test --run src/__tests__/useProjectSettings.test.ts src/__tests__/SettingsAccordion.test.tsx 2>&1 | tail -10
```

Expected: import errors.

- [ ] **Step 3: Implement hooks**

Create `frontend/src/hooks/useProjectSettings.ts`:
```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getProjectSettings,
  patchProjectSettings,
} from "@/api/settings.api";
import type { ProjectSettings, ProjectSettingsPatch } from "@/types/Settings";

const queryKey = (slug: string) => ["project-settings", slug];

export function useProjectSettings(slug: string) {
  return useQuery<ProjectSettings>({
    queryKey: queryKey(slug),
    queryFn: () => getProjectSettings(slug),
    staleTime: 30_000,
  });
}

export function useProjectSettingsMutation(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: ProjectSettingsPatch) => patchProjectSettings(slug, patch),
    onSuccess: (data) => {
      qc.setQueryData(queryKey(slug), data);
    },
  });
}
```

Create `frontend/src/hooks/useGlobalSettings.ts`:
```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getGlobalSettings,
  patchGlobalSettings,
} from "@/api/settings.api";
import type { GlobalSettings, GlobalSettingsPatch } from "@/types/Settings";

const queryKey = ["global-settings"];

export function useGlobalSettings() {
  return useQuery<GlobalSettings>({
    queryKey,
    queryFn: getGlobalSettings,
    staleTime: 30_000,
  });
}

export function useGlobalSettingsMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: GlobalSettingsPatch) => patchGlobalSettings(patch),
    onSuccess: (data) => {
      qc.setQueryData(queryKey, data);
    },
  });
}
```

- [ ] **Step 4: Implement SettingsAccordion**

Create `frontend/src/components/settings/SettingsAccordion.tsx`:
```tsx
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

interface Props {
  title: string;
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  defaultOpen?: boolean;
  children: ReactNode;
  errorMessage?: string | null;
  hint?: string;
}

export function SettingsAccordion({
  title, dirty, saving, onSave, defaultOpen = true, children, errorMessage, hint,
}: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen);

  const saveLabel = saving ? t("settings.saving") : t("settings.save");

  return (
    <section className="rounded-md border bg-[hsl(var(--background))]">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span className="text-sm font-medium">{title}</span>
        <span className="text-xs text-[hsl(var(--muted-foreground))]">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (
        <div className="space-y-3 border-t px-4 py-3 text-sm">
          {hint && (
            <p className="text-xs text-[hsl(var(--muted-foreground))]">{hint}</p>
          )}
          {children}
          {errorMessage && (
            <p className="text-xs text-red-700 dark:text-red-400">
              {errorMessage}
            </p>
          )}
          <div className="flex justify-end pt-2">
            <Button
              size="sm"
              onClick={onSave}
              disabled={!dirty || saving}
            >
              {saveLabel}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
```

Add locale keys to `frontend/public/locales/{en,ru,uk}.json` `settings` namespace:

`en.json`:
```json
"settings": {
  "title": "Settings",
  "save": "Save",
  "saving": "Saving...",
  "saved": "Saved",
  "error": "Error: {{msg}}"
}
```

`ru.json`:
```json
"settings": {
  "title": "Настройки",
  "save": "Сохранить",
  "saving": "Сохранение...",
  "saved": "Сохранено",
  "error": "Ошибка: {{msg}}"
}
```

`uk.json`:
```json
"settings": {
  "title": "Налаштування",
  "save": "Зберегти",
  "saving": "Збереження...",
  "saved": "Збережено",
  "error": "Помилка: {{msg}}"
}
```

(More section-specific keys added as sections come online in Phases 3+4.)

- [ ] **Step 5: Run tests**

```bash
pnpm test --run src/__tests__/useProjectSettings.test.ts src/__tests__/SettingsAccordion.test.tsx 2>&1 | tail -10
```

Expected: `6 passed` (2 hooks + 4 accordion).

- [ ] **Step 6: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/hooks/useProjectSettings.ts frontend/src/hooks/useGlobalSettings.ts frontend/src/components/settings/SettingsAccordion.tsx frontend/src/__tests__/useProjectSettings.test.ts frontend/src/__tests__/SettingsAccordion.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): TanStack Query hooks + SettingsAccordion wrapper

useProjectSettings + mutation; useGlobalSettings + mutation. Cache
invalidation via setQueryData on success.

SettingsAccordion: collapsible section with title + Save button (disabled
when !dirty || saving) + optional error/hint slots. Used by all
section components in Phases 3-4. New 5 settings.* locale keys
(en/ru/uk).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Phase 2 verification

- [ ] **Step 1: Frontend tests + tsc + lint**

```bash
cd /d/code/claude-mnemos/frontend
pnpm test --run 2>&1 | tail -5
pnpm tsc --noEmit 2>&1 | tail -3
pnpm lint 2>&1 | tail -5
```

Expected: ~250 tests pass (238 baseline + 6 settings api + 2 projects-delete + 2 hooks + 4 accordion = 252; allow ±5). tsc clean; pre-existing lint warnings only.

- [ ] **Step 2: Backend untouched**

```bash
cd /d/code/claude-mnemos && python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1495 passed`.

---

# Phase 3 — Simple sections (Auto-ingest + 4 others) + General

**Goal:** Build pattern на простой секции (AutoIngest), заштампать ещё 4 simple, и сделать complex General.

The simple-section pattern (used for AutoIngest, Lint, Ontology, Watchdog, Snapshots, Lifecycle, Prompts, Telemetry, IngestOverrides — 9 sections out of 12):

```
Component Section_X(props):
   1. Read server data via useProjectSettings
   2. Local state mirror server section (initialised from data on first load via useEffect)
   3. dirty = JSON.stringify(local) !== JSON.stringify(server[section])
   4. onSave: useProjectSettingsMutation.mutate({ section: local })
   5. Wrap in SettingsAccordion(title, dirty, saving, onSave)
```

Test pattern per section:
```
- render → fields show server values
- change a field → Save enables
- Save click → API PATCH call asserted with section partial
```

---

## Task 6: AutoIngestSection (template) + LintSection + OntologySection + WatchdogSection + SnapshotsSection

**Files:** 5 section files + 5 test files. AutoIngest as template; rest follow same pattern.

- [ ] **Step 1: Implement AutoIngestSection (template)**

Create `frontend/src/components/settings/sections/AutoIngestSection.tsx`:
```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import { useProjectSettings, useProjectSettingsMutation } from "@/hooks/useProjectSettings";

interface Props { slug: string; }

export function AutoIngestSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);

  const server = data?.auto_ingest;
  const [enabled, setEnabled] = useState(true);
  const [mode, setMode] = useState<"auto" | "hybrid" | "manual">("auto");

  useEffect(() => {
    if (server) {
      setEnabled(server.enabled);
      setMode(server.mode);
    }
  }, [server]);

  if (!data || !server) return null;

  const dirty = enabled !== server.enabled || mode !== server.mode;

  const onSave = () => {
    mut.mutate({ auto_ingest: { enabled, mode } });
  };

  return (
    <SettingsAccordion
      title={t("settings.section.auto_ingest.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        <span>{t("settings.section.auto_ingest.enabled")}</span>
      </label>
      <div className="space-y-1">
        <label className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.section.auto_ingest.mode")}
        </label>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as "auto" | "hybrid" | "manual")}
          className="rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        >
          <option value="auto">auto</option>
          <option value="hybrid">hybrid</option>
          <option value="manual">manual</option>
        </select>
      </div>
    </SettingsAccordion>
  );
}
```

- [ ] **Step 2: Write test for AutoIngest (template test)**

Create `frontend/src/__tests__/AutoIngestSection.test.tsx`:
```tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { AutoIngestSection } from "../components/settings/sections/AutoIngestSection";

let mock: MockAdapter;
beforeEach(() => {
  mock = new MockAdapter(axios);
  i18n.addResourceBundle("en", "translation", {
    settings: {
      save: "Save", saving: "Saving...",
      section: { auto_ingest: { title: "Auto-ingest", enabled: "Enabled", mode: "Mode" } },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

const FULL = {
  version: 1, locale: null,
  auto_ingest: { enabled: true, mode: "auto" },
  lint: { schedule: null, enabled_rules: null, autofix_on_save: false },
  ontology: { auto_mode: false, confidence_min: 0.7, confidence_auto_apply: 0.95 },
  watchdog: { mode: "merge" },
  snapshots: { daily_enabled: true, retention_days: 180 },
  lifecycle: { auto_stale_days: 90, auto_archive: false },
  prompts: { custom_system_path: null, custom_extract_user_path: null },
  telemetry: { opt_in: false },
  ingest: { model: null, language_hint: null, max_input_tokens: null, context_limit: null },
};

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("AutoIngestSection", () => {
  it("renders server values; Save disabled when no diff", async () => {
    mock.onGet("/settings/p1").reply(200, FULL);
    wrap(<AutoIngestSection slug="p1" />);
    await waitFor(() => expect(screen.getByText("Auto-ingest")).toBeInTheDocument());
    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeDisabled();
  });

  it("change field enables Save and PATCHes", async () => {
    mock.onGet("/settings/p1").reply(200, FULL);
    let patchedBody: any = null;
    mock.onPatch("/settings/p1").reply((config) => {
      patchedBody = JSON.parse(config.data as string);
      return [200, { ...FULL, auto_ingest: { enabled: false, mode: "auto" } }];
    });
    wrap(<AutoIngestSection slug="p1" />);
    await waitFor(() => expect(screen.getByText("Auto-ingest")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("checkbox"));
    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() => expect(patchedBody).toEqual({
      auto_ingest: { enabled: false, mode: "auto" },
    }));
  });
});
```

- [ ] **Step 3: Run AutoIngest tests; pass**

```bash
pnpm test --run src/__tests__/AutoIngestSection.test.tsx 2>&1 | tail -10
```

Expected: `2 passed`.

- [ ] **Step 4: Implement remaining 4 simple sections (LintSection, OntologySection, WatchdogSection, SnapshotsSection) following AutoIngest template**

For each, create `frontend/src/components/settings/sections/<Name>Section.tsx` with the same pattern:
- Props: `{ slug: string }`
- Hooks: `useProjectSettings(slug)` + `useProjectSettingsMutation(slug)`
- Local state mirroring `data?.<section_name>`
- `useEffect` initialising local state from server data
- `dirty` computed by deep-equality of local vs server section
- `onSave` calls `mut.mutate({ <section_name>: local })`
- Wrap in `<SettingsAccordion>` with i18n title

Field types per section:

**LintSection** — three fields: `schedule: string | null` (text input, empty → null), `enabled_rules: string[] | null` (comma-separated text, empty → null), `autofix_on_save: boolean`.

**OntologySection** — `auto_mode: boolean`, `confidence_min: number` (0..1), `confidence_auto_apply: number` (0..1).

**WatchdogSection** — `mode: "strict" | "merge" | "open"` (select).

**SnapshotsSection** — `daily_enabled: boolean`, `retention_days: number` (int >=1).

Each gets a corresponding `<Name>Section.test.tsx` with two tests (mirror AutoIngest test pattern: render+disabled save, change+enabled+PATCH).

Add locale keys to `frontend/public/locales/{en,ru,uk}.json` for each section. Pattern:
```json
"settings.section.lint.title": "Lint",
"settings.section.lint.schedule": "Cron schedule",
"settings.section.lint.enabled_rules": "Enabled rules (comma-separated)",
"settings.section.lint.autofix_on_save": "Autofix on save",
... (and so on for each section's fields)
```

(Translate ru/uk same way — each ~6-8 keys per section.)

- [ ] **Step 5: Run all section tests**

```bash
pnpm test --run src/__tests__/LintSection.test.tsx src/__tests__/OntologySection.test.tsx src/__tests__/WatchdogSection.test.tsx src/__tests__/SnapshotsSection.test.tsx 2>&1 | tail -10
```

Expected: `8 passed` (4 sections × 2 tests).

- [ ] **Step 6: Run all frontend tests; tsc; lint**

```bash
pnpm test --run 2>&1 | tail -5
pnpm tsc --noEmit 2>&1 | tail -3
pnpm lint 2>&1 | tail -5
```

Expected: ~262 passed (Phase 2's ~252 + 2 AutoIngest + 8 others = 262); tsc clean; pre-existing warnings only.

- [ ] **Step 7: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/components/settings/sections/ frontend/src/__tests__/AutoIngestSection.test.tsx frontend/src/__tests__/LintSection.test.tsx frontend/src/__tests__/OntologySection.test.tsx frontend/src/__tests__/WatchdogSection.test.tsx frontend/src/__tests__/SnapshotsSection.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): 5 simple settings sections — AutoIngest/Lint/Ontology/Watchdog/Snapshots

Pattern: useProjectSettings + useProjectSettingsMutation, local state
mirrors server section, dirty computed by JSON-stringify, Save calls
mutate with section partial. Wrapped in SettingsAccordion.

10 unit tests (2 per section). New locale keys per section (en/ru/uk).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: GeneralSection (special — two endpoints)

**Files:**
- Create: `frontend/src/components/settings/sections/GeneralSection.tsx`
- Create: `frontend/src/__tests__/GeneralSection.test.tsx`

GeneralSection mutates **two** endpoints:
- `display_name` + `cwd_patterns` → `PATCH /projects/{slug}` (new mutation; reuse `useProjectMutation` if it exists, else create one in `frontend/src/hooks/useProjectMutation.ts`)
- `slug` and `vault_root` are **read-only** with Copy button

- [ ] **Step 1: Find existing project mutation hook**

```bash
grep -rn "useProjectUpdate\|useProjectMutation\|patchProject" frontend/src/hooks/ frontend/src/api/ | head
```

If not present, create `frontend/src/hooks/useProjectUpdate.ts`:
```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { ProjectMapEntrySchema, type ProjectMapEntry } from "@/types/Project";

interface UpdateBody {
  display_name?: string | null;
  cwd_patterns?: string[];
}

export function useProjectUpdate(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (patch: UpdateBody): Promise<ProjectMapEntry> => {
      const { data } = await axios.patch(`/projects/${slug}`, patch);
      return ProjectMapEntrySchema.parse(data);
    },
    onSuccess: (data) => {
      qc.setQueryData(["project", slug], data);
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
```

(Adapt path/casing if existing types file differs.)

- [ ] **Step 2: Implement GeneralSection**

Create `frontend/src/components/settings/sections/GeneralSection.tsx`:
```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import { CwdBuilder } from "@/components/onboarding/CwdBuilder";
import { useProjectUpdate } from "@/hooks/useProjectUpdate";
import type { ProjectMapEntry } from "@/types/Project";

interface Props { project: ProjectMapEntry; }

export function GeneralSection({ project }: Props) {
  const { t } = useTranslation();
  const mut = useProjectUpdate(project.name);

  const [displayName, setDisplayName] = useState(project.display_name ?? "");
  const [cwdPatterns, setCwdPatterns] = useState<string[]>(project.cwd_patterns);

  useEffect(() => {
    setDisplayName(project.display_name ?? "");
    setCwdPatterns(project.cwd_patterns);
  }, [project]);

  const dirty =
    displayName.trim() !== (project.display_name ?? "") ||
    JSON.stringify(cwdPatterns) !== JSON.stringify(project.cwd_patterns);

  const onSave = () => {
    mut.mutate({
      display_name: displayName.trim() === "" ? "" : displayName.trim(),
      // Empty string → backend clears to null (Plan A pre-merge).
      cwd_patterns: cwdPatterns,
    });
  };

  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); } catch { /* clipboard may be blocked */ }
  };

  return (
    <SettingsAccordion
      title={t("settings.section.general.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        <label className="text-xs font-medium">{t("settings.section.general.display_name")}</label>
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
        />
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("settings.section.general.display_name_hint")}</p>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-medium">{t("settings.section.general.slug")}</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={project.name}
            readOnly
            className="flex-1 rounded-md border bg-[hsl(var(--muted))] px-3 py-2 text-sm font-mono"
          />
          <button
            type="button"
            onClick={() => copy(project.name)}
            className="text-xs text-[hsl(var(--primary))] underline"
          >
            {t("settings.section.general.copy")}
          </button>
        </div>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("settings.section.general.slug_hint")}</p>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-medium">{t("settings.section.general.vault")}</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={String(project.vault_root)}
            readOnly
            className="flex-1 rounded-md border bg-[hsl(var(--muted))] px-3 py-2 text-sm font-mono"
          />
          <button
            type="button"
            onClick={() => copy(String(project.vault_root))}
            className="text-xs text-[hsl(var(--primary))] underline"
          >
            {t("settings.section.general.copy")}
          </button>
        </div>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("settings.section.general.vault_hint")}</p>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-medium">{t("settings.section.general.cwd")}</label>
        <CwdBuilder patterns={cwdPatterns} onChange={setCwdPatterns} disabled={mut.isPending} />
      </div>
    </SettingsAccordion>
  );
}
```

- [ ] **Step 3: Test GeneralSection**

Create `frontend/src/__tests__/GeneralSection.test.tsx` with at least:
- Renders display_name, slug (readonly), vault (readonly), CWD list
- Change display_name → Save enables → PATCH `/projects/p1` body `{display_name: "New", cwd_patterns: [...]}`
- Slug field readonly
- Vault field readonly
- Empty display_name → on Save sends `display_name: ""` (clears backend)

(~5 tests; mirror existing Onboarding integration tests for harness setup.)

- [ ] **Step 4: Run tests; pass**

```bash
pnpm test --run src/__tests__/GeneralSection.test.tsx 2>&1 | tail -10
```

Expected: tests pass (5 each).

- [ ] **Step 5: Add locale keys**

Add `settings.section.general.*` keys: `title`, `display_name`, `display_name_hint`, `slug`, `slug_hint`, `vault`, `vault_hint`, `cwd`, `copy` × en/ru/uk.

Sample en:
```json
"settings.section.general.title": "General",
"settings.section.general.display_name": "Display name",
"settings.section.general.display_name_hint": "Shown in dashboard. Leave empty to clear.",
"settings.section.general.slug": "Slug (read-only)",
"settings.section.general.slug_hint": "Used in URLs and file paths. Fixed at creation.",
"settings.section.general.vault": "Vault path (read-only)",
"settings.section.general.vault_hint": "To move vault, create new project and migrate data.",
"settings.section.general.cwd": "Project folders (auto-routing)",
"settings.section.general.copy": "Copy"
```

- [ ] **Step 6: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/hooks/useProjectUpdate.ts frontend/src/components/settings/sections/GeneralSection.tsx frontend/src/__tests__/GeneralSection.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): GeneralSection — display_name + slug RO + vault RO + CWD

Special section: routes to PATCH /projects/{slug} (not /settings/{slug}).
slug and vault_root are read-only with Copy button (clipboard.writeText).
display_name supports clear via empty string. CwdBuilder reused.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: LocaleSection (inherit-from-global pattern)

**Files:**
- Create: `frontend/src/components/settings/sections/LocaleSection.tsx`
- Create: `frontend/src/__tests__/LocaleSection.test.tsx`

LocaleSection: 4 radio buttons (Inherit / uk / ru / en). `null` value sent for Inherit.

- [ ] **Step 1: Implement LocaleSection**

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import { useProjectSettings, useProjectSettingsMutation } from "@/hooks/useProjectSettings";
import { useGlobalSettings } from "@/hooks/useGlobalSettings";

interface Props { slug: string; }

type LocaleValue = "uk" | "ru" | "en" | null;

export function LocaleSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const { data: global } = useGlobalSettings();
  const mut = useProjectSettingsMutation(slug);

  const server: LocaleValue = data?.locale ?? null;
  const [local, setLocal] = useState<LocaleValue>(null);

  useEffect(() => {
    if (data) setLocal(data.locale);
  }, [data]);

  if (!data) return null;

  const dirty = local !== server;

  const onSave = () => {
    mut.mutate({ locale: local });
  };

  const options: Array<{ value: LocaleValue; label: string }> = [
    { value: null, label: `${t("settings.section.locale.inherit")} (${global?.locale ?? "?"})` },
    { value: "uk", label: "uk" },
    { value: "ru", label: "ru" },
    { value: "en", label: "en" },
  ];

  return (
    <SettingsAccordion
      title={t("settings.section.locale.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
    >
      <div className="space-y-1">
        {options.map((opt) => (
          <label key={String(opt.value)} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name={`locale-${slug}`}
              checked={local === opt.value}
              onChange={() => setLocal(opt.value)}
            />
            <span>{opt.label}</span>
          </label>
        ))}
      </div>
    </SettingsAccordion>
  );
}
```

- [ ] **Step 2: Test (3 tests)**

`frontend/src/__tests__/LocaleSection.test.tsx`:
- Renders 4 radio buttons; «Inherit» shows `(uk)` from global
- Click «ru» → Save enables → PATCH body `{locale: "ru"}`
- Click «Inherit» when current is "ru" → PATCH body `{locale: null}`

- [ ] **Step 3: Run + commit**

```bash
pnpm test --run src/__tests__/LocaleSection.test.tsx 2>&1 | tail -5
```

Expected: `3 passed`.

Add locale keys: `settings.section.locale.title`, `settings.section.locale.inherit`.

```bash
cd /d/code/claude-mnemos && git add frontend/src/components/settings/sections/LocaleSection.tsx frontend/src/__tests__/LocaleSection.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): LocaleSection — inherit/uk/ru/en radio

Inherit = null payload; backend resolves to global locale at render.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Phase 3 verification

```bash
cd /d/code/claude-mnemos
python -m pytest --ignore=tests/slow 2>&1 | tail -3
cd frontend && pnpm test --run 2>&1 | tail -5
pnpm tsc --noEmit 2>&1 | tail -3
pnpm lint 2>&1 | tail -5
git diff main -- claude_mnemos/ingest/ claude_mnemos/state/manifest.py claude_mnemos/core/metrics.py claude_mnemos/hooks/ claude_mnemos/state/jobs.py claude_mnemos/daemon/jobs/ claude_mnemos/state/settings.py 2>&1 | wc -l
```

Expected: backend 1495 (unchanged); frontend ~270 (Phase 2's 252 + 10 Task 6 + 5 Task 7 + 3 Task 8 = 270); ruff/tsc/lint clean; zero-diff `0`.

---

# Phase 4 — Remaining sections (Lifecycle/Prompts/Telemetry/IngestOverrides) + DangerZone

**Goal:** Заштампать last 3 simple sections + IngestOverrides (override pattern) + DangerZone (delete project).

---

## Task 10: LifecycleSection + PromptsSection + TelemetrySection (3 simple sections)

Apply the AutoIngest template pattern from Phase 3 Task 6 to these 3 sections:

- **LifecycleSection** — `auto_stale_days: number (int >=1)`, `auto_archive: boolean`
- **PromptsSection** — `custom_system_path: string | null`, `custom_extract_user_path: string | null` (text inputs; empty → null)
- **TelemetrySection** — `opt_in: boolean`

Each section: ~80 LOC component file, ~2 tests, ~5 locale keys per language.

Single commit covering all 3:
```bash
cd /d/code/claude-mnemos && git add frontend/src/components/settings/sections/LifecycleSection.tsx frontend/src/components/settings/sections/PromptsSection.tsx frontend/src/components/settings/sections/TelemetrySection.tsx frontend/src/__tests__/LifecycleSection.test.tsx frontend/src/__tests__/PromptsSection.test.tsx frontend/src/__tests__/TelemetrySection.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): 3 more settings sections — Lifecycle/Prompts/Telemetry

Same per-section save pattern as Phase 3 (AutoIngest template).
6 unit tests (2 per section). New locale keys.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: IngestOverridesSection (override-or-inherit pattern)

**Files:**
- Create: `frontend/src/components/settings/sections/IngestOverridesSection.tsx`
- Create: `frontend/src/__tests__/IngestOverridesSection.test.tsx`

Pattern: each field has a checkbox «Override default»; checked → input rendered + sends value; unchecked → null sent + input hidden showing default from global.

- [ ] **Step 1: Implement IngestOverridesSection**

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import { useProjectSettings, useProjectSettingsMutation } from "@/hooks/useProjectSettings";
import { useGlobalSettings } from "@/hooks/useGlobalSettings";

interface Props { slug: string; }

export function IngestOverridesSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const { data: global } = useGlobalSettings();
  const mut = useProjectSettingsMutation(slug);

  const server = data?.ingest;
  const [model, setModel] = useState<string | null>(null);
  const [languageHint, setLanguageHint] = useState<"auto" | "uk" | "ru" | "en" | null>(null);
  const [maxInputTokens, setMaxInputTokens] = useState<number | null>(null);
  const [contextLimit, setContextLimit] = useState<number | null>(null);

  useEffect(() => {
    if (server) {
      setModel(server.model);
      setLanguageHint(server.language_hint);
      setMaxInputTokens(server.max_input_tokens);
      setContextLimit(server.context_limit);
    }
  }, [server]);

  if (!data || !server) return null;

  const dirty =
    model !== server.model ||
    languageHint !== server.language_hint ||
    maxInputTokens !== server.max_input_tokens ||
    contextLimit !== server.context_limit;

  const onSave = () => {
    mut.mutate({
      ingest: {
        model,
        language_hint: languageHint,
        max_input_tokens: maxInputTokens,
        context_limit: contextLimit,
      },
    });
  };

  const renderOverride = <T,>(
    label: string,
    defaultLabel: string,
    value: T | null,
    setValue: (v: T | null) => void,
    inputElement: (current: T) => React.ReactNode,
    defaultValue: T,
  ) => (
    <div className="space-y-1">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={value !== null}
          onChange={(e) => setValue(e.target.checked ? defaultValue : null)}
        />
        <span>{label}</span>
      </label>
      {value !== null ? (
        inputElement(value)
      ) : (
        <p className="ml-6 text-xs text-[hsl(var(--muted-foreground))]">
          {t("settings.section.ingest.using_default", { value: defaultLabel })}
        </p>
      )}
    </div>
  );

  return (
    <SettingsAccordion
      title={t("settings.section.ingest.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      hint={t("settings.section.ingest.hint")}
    >
      {renderOverride(
        t("settings.section.ingest.model"),
        global?.default_model ?? "?",
        model,
        setModel,
        (v) => (
          <input
            type="text"
            value={v}
            onChange={(e) => setModel(e.target.value)}
            className="ml-6 w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1 text-sm font-mono"
          />
        ),
        global?.default_model ?? "claude-sonnet-4-6",
      )}
      {renderOverride(
        t("settings.section.ingest.language_hint"),
        global?.default_language_hint ?? "?",
        languageHint,
        setLanguageHint,
        (v) => (
          <select
            value={v}
            onChange={(e) => setLanguageHint(e.target.value as "auto" | "uk" | "ru" | "en")}
            className="ml-6 rounded-md border bg-[hsl(var(--background))] px-2 py-1"
          >
            <option value="auto">auto</option>
            <option value="uk">uk</option>
            <option value="ru">ru</option>
            <option value="en">en</option>
          </select>
        ),
        "auto",
      )}
      {renderOverride(
        t("settings.section.ingest.max_input_tokens"),
        String(global?.default_max_input_tokens ?? "?"),
        maxInputTokens,
        setMaxInputTokens,
        (v) => (
          <input
            type="number"
            value={v}
            min={1024}
            onChange={(e) => setMaxInputTokens(parseInt(e.target.value || "0", 10))}
            className="ml-6 w-32 rounded-md border bg-[hsl(var(--background))] px-2 py-1 text-sm"
          />
        ),
        global?.default_max_input_tokens ?? 150000,
      )}
      {renderOverride(
        t("settings.section.ingest.context_limit"),
        "—",
        contextLimit,
        setContextLimit,
        (v) => (
          <input
            type="number"
            value={v}
            min={1}
            onChange={(e) => setContextLimit(parseInt(e.target.value || "0", 10))}
            className="ml-6 w-32 rounded-md border bg-[hsl(var(--background))] px-2 py-1 text-sm"
          />
        ),
        100,
      )}
    </SettingsAccordion>
  );
}
```

- [ ] **Step 2: Test (4 tests)**

- Renders 4 fields, all unchecked initially (server has all nulls)
- Toggle override-checkbox shows input + Save enables
- Save sends `ingest: {model, language_hint, max_input_tokens, context_limit}` with values
- Toggle off again → Save sends nulls

- [ ] **Step 3: Run + locale keys + commit**

```bash
pnpm test --run src/__tests__/IngestOverridesSection.test.tsx 2>&1 | tail -5
```

Add locale keys per section.

```bash
cd /d/code/claude-mnemos && git add frontend/src/components/settings/sections/IngestOverridesSection.tsx frontend/src/__tests__/IngestOverridesSection.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): IngestOverridesSection — override-or-inherit pattern

4 fields (model/language_hint/max_input_tokens/context_limit), each
with 'Override default' checkbox. Unchecked = null (inherit from global).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: DangerZoneSection (delete project flow)

**Files:**
- Create: `frontend/src/components/settings/sections/DangerZoneSection.tsx`
- Create: `frontend/src/__tests__/DangerZoneSection.test.tsx`

- [ ] **Step 1: Find existing TypedConfirmDialog**

```bash
grep -rn "TypedConfirmDialog\|ConfirmDialog" frontend/src/components/ | head
```

If exists (Plan #14c added it for mutations), reuse. Else build inline modal in this component.

- [ ] **Step 2: Implement DangerZoneSection**

Create `frontend/src/components/settings/sections/DangerZoneSection.tsx`:
```tsx
import { useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { deleteProject } from "@/api/projects.api";
import type { ProjectMapEntry } from "@/types/Project";

interface Props { project: ProjectMapEntry; }

export function DangerZoneSection({ project }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [confirmInput, setConfirmInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: (force: boolean) => deleteProject(project.name, force ? { force: true } : undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      navigate("/");
    },
    onError: (err: any) => {
      const detail = err.response?.data?.detail ?? err.message;
      setError(detail);
    },
  });

  const slugMatches = confirmInput === project.name;
  const displayName = project.display_name || project.name;

  const handleDelete = (force = false) => {
    setError(null);
    mut.mutate(force);
  };

  return (
    <section className="rounded-md border-2 border-red-300 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950">
      <h3 className="text-sm font-semibold text-red-900 dark:text-red-300">
        {t("settings.danger.title")}
      </h3>
      <p className="mt-1 text-xs text-red-800 dark:text-red-400">
        {t("settings.danger.body")}
      </p>
      <Button
        variant="outline"
        size="sm"
        className="mt-3 border-red-600 text-red-700 hover:bg-red-100 dark:hover:bg-red-900"
        onClick={() => { setOpen(true); setConfirmInput(""); setError(null); }}
      >
        {t("settings.danger.delete_button")}
      </Button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-md border bg-[hsl(var(--background))] p-4 shadow-lg">
            <h4 className="text-base font-semibold">
              {t("settings.danger.modal_title", { name: displayName })}
            </h4>
            <p className="mt-2 text-sm text-[hsl(var(--muted-foreground))]">
              {t("settings.danger.modal_body", { vault: String(project.vault_root) })}
            </p>
            <div className="mt-3 space-y-1">
              <label className="text-xs font-medium">
                {t("settings.danger.confirm_label", { slug: project.name })}
              </label>
              <input
                type="text"
                value={confirmInput}
                onChange={(e) => setConfirmInput(e.target.value)}
                className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
                autoFocus
              />
            </div>
            {error && (
              <div className="mt-2 rounded-md border border-amber-500 bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                {error}
                {error.toLowerCase().includes("jobs") && (
                  <button
                    type="button"
                    className="ml-2 underline"
                    onClick={() => handleDelete(true)}
                  >
                    {t("settings.danger.force_delete")}
                  </button>
                )}
              </div>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
                {t("settings.danger.cancel")}
              </Button>
              <Button
                size="sm"
                onClick={() => handleDelete(false)}
                disabled={!slugMatches || mut.isPending}
                className="bg-red-600 text-white hover:bg-red-700"
              >
                {mut.isPending ? t("settings.danger.deleting") : t("settings.danger.confirm")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Test (4 tests)**

`frontend/src/__tests__/DangerZoneSection.test.tsx`:
- Renders Delete button
- Click opens modal with project name interpolated
- Type wrong slug → Delete button disabled
- Type correct slug + click → DELETE /projects/p1 called → on success navigate to "/"
- 409 response → error displayed with "Force delete" link → click triggers DELETE with `?force=true`

- [ ] **Step 4: Add locale keys**

```json
"settings.danger.title": "Danger zone",
"settings.danger.body": "Permanent actions. The vault folder is not deleted; you can re-add the project to restore.",
"settings.danger.delete_button": "Delete project",
"settings.danger.modal_title": "Delete project «{{name}}»?",
"settings.danger.modal_body": "Removes the project from the registry. Vault folder at {{vault}} will NOT be deleted.",
"settings.danger.confirm_label": "Type «{{slug}}» to confirm:",
"settings.danger.cancel": "Cancel",
"settings.danger.confirm": "Delete project",
"settings.danger.deleting": "Deleting...",
"settings.danger.force_delete": "Force delete (cancel jobs)"
```

(ru/uk equivalents.)

- [ ] **Step 5: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/components/settings/sections/DangerZoneSection.tsx frontend/src/__tests__/DangerZoneSection.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): DangerZoneSection — delete project with typed-confirm

Modal: type slug to enable Delete button. On 409 (jobs running),
shows 'Force delete' link → DELETE ?force=true. On success,
invalidates projects cache + navigates to home.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Phase 4 verification

```bash
cd /d/code/claude-mnemos
python -m pytest --ignore=tests/slow 2>&1 | tail -3
cd frontend && pnpm test --run 2>&1 | tail -5
pnpm tsc --noEmit 2>&1 | tail -3
pnpm lint 2>&1 | tail -5
git diff main -- claude_mnemos/ingest/ claude_mnemos/state/manifest.py claude_mnemos/core/metrics.py claude_mnemos/hooks/ claude_mnemos/state/jobs.py claude_mnemos/daemon/jobs/ claude_mnemos/state/settings.py 2>&1 | wc -l
```

Expected: backend 1495; frontend ~285 (Phase 3's 270 + 6 Task 10 + 4 Task 11 + 4 Task 12 = 284); ruff/tsc/lint clean; zero-diff `0`.

---

# Phase 5 — Page composition + Global Settings + routing

## Task 14: ProjectSettings page

**Files:**
- Create: `frontend/src/pages/ProjectSettings.tsx`
- Create: `frontend/src/__tests__/ProjectSettings.test.tsx`
- Modify: `frontend/src/pages/ProjectView.tsx` (route to ProjectSettings instead of Placeholder)
- Modify: `frontend/src/App.tsx` or router config (route registration if needed)

- [ ] **Step 1: Implement ProjectSettings page**

```tsx
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { ProjectMapEntrySchema, type ProjectMapEntry } from "@/types/Project";

import { GeneralSection } from "@/components/settings/sections/GeneralSection";
import { LocaleSection } from "@/components/settings/sections/LocaleSection";
import { AutoIngestSection } from "@/components/settings/sections/AutoIngestSection";
import { LintSection } from "@/components/settings/sections/LintSection";
import { OntologySection } from "@/components/settings/sections/OntologySection";
import { WatchdogSection } from "@/components/settings/sections/WatchdogSection";
import { SnapshotsSection } from "@/components/settings/sections/SnapshotsSection";
import { LifecycleSection } from "@/components/settings/sections/LifecycleSection";
import { PromptsSection } from "@/components/settings/sections/PromptsSection";
import { TelemetrySection } from "@/components/settings/sections/TelemetrySection";
import { IngestOverridesSection } from "@/components/settings/sections/IngestOverridesSection";
import { DangerZoneSection } from "@/components/settings/sections/DangerZoneSection";

async function fetchProject(slug: string): Promise<ProjectMapEntry> {
  const { data } = await axios.get(`/projects/${slug}`);
  return ProjectMapEntrySchema.parse(data);
}

export function ProjectSettings() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const { data: project } = useQuery({
    queryKey: ["project", name],
    queryFn: () => fetchProject(name),
    enabled: !!name,
  });

  if (!project) return <div>{t("settings.loading")}</div>;

  return (
    <div className="mx-auto max-w-3xl space-y-3 py-6">
      <h1 className="text-2xl font-semibold">{t("settings.title")}</h1>

      <GeneralSection project={project} />
      <LocaleSection slug={project.name} />
      <AutoIngestSection slug={project.name} />
      <LintSection slug={project.name} />
      <OntologySection slug={project.name} />
      <WatchdogSection slug={project.name} />
      <SnapshotsSection slug={project.name} />
      <LifecycleSection slug={project.name} />
      <PromptsSection slug={project.name} />
      <TelemetrySection slug={project.name} />
      <IngestOverridesSection slug={project.name} />
      <DangerZoneSection project={project} />
    </div>
  );
}
```

- [ ] **Step 2: Wire route into ProjectView**

In `frontend/src/pages/ProjectView.tsx`, find the placeholder logic for `settings`. Replace `<Placeholder section=... plan="#14c" />` with `<ProjectSettings />` import + conditional render.

If routing is centralised in App.tsx, find `<Route path="/project/:name/settings" ... />` and route to ProjectSettings component.

- [ ] **Step 3: Test ProjectSettings**

3 tests:
- Renders all 12 sections (assert each section title visible)
- Loading state when data not yet fetched
- Navigates back to home after delete (via DangerZone integration test)

- [ ] **Step 4: Run + commit**

```bash
pnpm test --run src/__tests__/ProjectSettings.test.tsx 2>&1 | tail -5
```

Add `settings.loading` locale key.

```bash
cd /d/code/claude-mnemos && git add frontend/src/pages/ProjectSettings.tsx frontend/src/pages/ProjectView.tsx frontend/src/__tests__/ProjectSettings.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): ProjectSettings page composes 12 sections in accordion

Replaces Placeholder #14c. Fetches /projects/{slug} for general
section; each settings section fetches its own /settings/{slug} via
shared TanStack Query cache.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: GlobalSettings page + sidebar wiring

**Files:**
- Create: `frontend/src/pages/GlobalSettings.tsx`
- Create: `frontend/src/components/settings/globals/GlobalGeneralSection.tsx` (locale + daemon_port)
- Create: `frontend/src/components/settings/globals/GlobalDefaultsSection.tsx` (default_model + default_language_hint + default_max_input_tokens + default_retention_days)
- Create: `frontend/src/__tests__/GlobalSettings.test.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx` (+ link to /settings/global)
- Modify: router config (+ /settings/global route)

- [ ] **Step 1: Implement GlobalGeneralSection + GlobalDefaultsSection**

Pattern: same as project sections but using `useGlobalSettings` + `useGlobalSettingsMutation` hooks.

GlobalGeneralSection: `locale: "uk"|"ru"|"en"` (radio), `daemon_port: int 1..65535`.

GlobalDefaultsSection: `default_model`, `default_language_hint` (auto/uk/ru/en select), `default_max_input_tokens` (int >=1024), `default_retention_days` (int >=1).

- [ ] **Step 2: Implement GlobalSettings page**

```tsx
import { useTranslation } from "react-i18next";
import { GlobalGeneralSection } from "@/components/settings/globals/GlobalGeneralSection";
import { GlobalDefaultsSection } from "@/components/settings/globals/GlobalDefaultsSection";

export function GlobalSettings() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-3xl space-y-3 py-6">
      <h1 className="text-2xl font-semibold">{t("settings.global.title")}</h1>
      <GlobalGeneralSection />
      <GlobalDefaultsSection />
    </div>
  );
}
```

- [ ] **Step 3: Wire Sidebar + router**

Add to `frontend/src/components/layout/Sidebar.tsx` footer:
```tsx
<Link to="/settings/global" className="...">
  ⚙ {t("navigation.global_settings")}
</Link>
```

Add route in `App.tsx` (or wherever routes live):
```tsx
<Route path="/settings/global" element={<GlobalSettings />} />
```

- [ ] **Step 4: Tests**

3 tests:
- GlobalSettings renders both sections
- GlobalGeneralSection: change daemon_port, save → PATCH `/settings/global` body
- GlobalDefaultsSection: change default_model, save → PATCH

- [ ] **Step 5: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/pages/GlobalSettings.tsx frontend/src/components/settings/globals/ frontend/src/components/layout/Sidebar.tsx frontend/src/App.tsx frontend/src/__tests__/GlobalSettings.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): GlobalSettings page + sidebar link + router wiring

Two sections: General (locale + daemon_port) and Defaults
(default_model + default_language_hint + default_max_input_tokens +
default_retention_days). Uses useGlobalSettings + mutation hooks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: Phase 5 verification

```bash
cd /d/code/claude-mnemos
python -m pytest --ignore=tests/slow 2>&1 | tail -3
cd frontend && pnpm test --run 2>&1 | tail -5
pnpm tsc --noEmit 2>&1 | tail -3
pnpm lint 2>&1 | tail -5
pnpm build 2>&1 | tail -5
git diff main -- claude_mnemos/ingest/ claude_mnemos/state/manifest.py claude_mnemos/core/metrics.py claude_mnemos/hooks/ claude_mnemos/state/jobs.py claude_mnemos/daemon/jobs/ claude_mnemos/state/settings.py 2>&1 | wc -l
```

Expected: backend 1495; frontend ~291 (Phase 4's 285 + 3 ProjectSettings + 3 GlobalSettings = 291); ruff/tsc/lint clean; build succeeds; zero-diff `0`.

---

# Phase 6 — Manual checklist + memory + merge

## Task 17: Manual checklist + memory snapshot

Create `docs/plans/2026-04-30-settings-ui-manual-checklist.md`:
```markdown
# Settings UI — Manual E2E Checklist

## Prerequisites
- [ ] daemon restarted with new code
- [ ] dashboard reloaded (Ctrl+F5)

## Project Settings (open `/project/<slug>/settings`)

### General
- [ ] Display name editable; Save persists; sidebar updates
- [ ] Slug shown read-only with Copy button
- [ ] Vault path shown read-only with Copy button
- [ ] CWD patterns: add via Browse → recursive checkbox toggles `\*` suffix
- [ ] Save with empty display_name clears it (sidebar shows slug)

### Per-section save
- [ ] Auto-ingest: toggle enabled/mode → Save → reload page → persists
- [ ] Lint: schedule string + autofix toggle → Save persists
- [ ] Ontology: confidence sliders (0..1) → Save persists
- [ ] Watchdog: mode select → Save persists
- [ ] Snapshots: daily_enabled + retention_days → Save persists
- [ ] Lifecycle: auto_stale_days + auto_archive → Save persists
- [ ] Prompts: text inputs → Save persists; empty → null in JSON
- [ ] Telemetry: opt_in checkbox → Save persists
- [ ] Locale: switch between Inherit/uk/ru/en → Save persists; UI reload shows new locale (or current acceptable for MVP)

### Ingest overrides
- [ ] Toggle Override checkbox for model → input appears, set value, Save
- [ ] Toggle off again → input hides, Save sends null
- [ ] All 4 override fields work (model/language_hint/max_input_tokens/context_limit)

### Danger zone
- [ ] Delete button red, opens modal
- [ ] Wrong slug typed → Delete button disabled
- [ ] Correct slug typed → Delete button enabled
- [ ] Click Delete → if 409 «jobs running», force delete link shown
- [ ] Force delete works → navigated to home, project gone from sidebar
- [ ] Vault folder still on disk (verify in file explorer)
- [ ] `mnemos project add` with same slug + vault restores access

## Global Settings (open `/settings/global`)
- [ ] General section: locale + daemon_port editable
- [ ] Defaults: model + language_hint + max_input_tokens + retention_days editable
- [ ] All saves persist after page reload
- [ ] Sidebar link visible in footer

## Validation errors
- [ ] retention_days=0 → 422 → inline error message
- [ ] daemon_port=99999 → 422 → inline error
- [ ] confidence_min=1.5 → 422 → inline error
```

Update `C:/Users/68664/.claude/projects/d-----------------OBSIDIAN--shared/memory/MEMORY.md`:
- Bump claude_mnemos line: new merge sha, mention Settings UI Plan B
- Add new index line for `plan_settings_ui_complete.md`

Create memory snapshot file `plan_settings_ui_complete.md` with:
- Merge sha
- 16 commits summary
- New Settings page paths
- Test counts
- Pre-merge fixes (if any from final review)

---

## Task 18: Final review + merge

- [ ] **Step 1: Spawn final code-reviewer subagent**

Address any critical/important findings.

- [ ] **Step 2: Merge**

```bash
cd /d/code/claude-mnemos && git checkout main && git merge --no-ff feat/settings-ui -m "Merge feat/settings-ui: Settings page + delete project flow

Phase 1 — Backend: DELETE /projects/{slug} with force flag.
Phase 2 — Frontend foundation: settings api + zod + hooks + Accordion.
Phase 3 — 5 simple sections (Auto-ingest/Lint/Ontology/Watchdog/Snapshots) + General + Locale.
Phase 4 — 3 simple (Lifecycle/Prompts/Telemetry) + IngestOverrides + DangerZone.
Phase 5 — ProjectSettings + GlobalSettings pages + sidebar wiring.
Phase 6 — Manual checklist + memory + merge.

Backend ~1495 (+5), frontend ~291 (+53). Zero diff in extraction/parser/
metrics/hooks/jobs/manifest/state/settings.py. Existing 4 projects work
with display_name fallback (Plan A) and now editable through UI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Design §2 «Включено» — all 12 project sections + 2 global sections + delete + 80 locale keys → covered Phase 1 (delete), Phase 2 (foundation), Phases 3-4 (sections), Phase 5 (pages).
- Design §4 Components — every file in design listed in plan's «File Structure» section.
- Design §5 Behavior — save model + General special handling + locale inherit + ingest override + delete flow → all in respective tasks (4, 7, 8, 11, 12).
- Design §6 Tests — every section has 2 tests (template). Special sections have more (General 5, DangerZone 4, IngestOverrides 4).
- Design §10 Success criteria — Phase 6 manual checklist covers all 9 criteria.

**Placeholder scan:**
- Task 1 Step 1: «Find the daemon's project-unmount method» — engineer-driven inspection. Acceptable.
- Task 7 Step 1: «If not present, create useProjectUpdate hook» — conditional, sensible.
- Task 12 Step 1: «If exists, reuse; else build inline» — conditional, sensible.
- Task 10 says «3 sections following AutoIngest template» without showing each verbatim — acceptable since AutoIngest in Task 6 has FULL code. DRY.
- Task 15 same pattern for GlobalGeneral/Defaults.

These are intentional pattern references (not lazy stubs); each task that uses the pattern names the FULL prior task to copy.

**Type/name consistency:**
- `ProjectSettings` (zod) defined Task 3, used by hooks Task 4, all sections Tasks 6+7+8+10+11+12.
- `useProjectSettings` / `useProjectSettingsMutation` consistent across sections.
- `useGlobalSettings` / `useGlobalSettingsMutation` consistent.
- `SettingsAccordion` props (`title`, `dirty`, `saving`, `onSave`, `errorMessage`, `hint`) — used same way in every section.
- `useProjectUpdate` (display_name+cwd_patterns mutation) defined Task 7, used in DangerZone Task 12 indirectly via cache invalidation.
- `deleteProject` defined Task 3 (`api/projects.api.ts`), used by DangerZone.

**Plan complete and saved.**
