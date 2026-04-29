# Plan #14a: Frontend foundation + Overview — design

**Status:** DRAFT
**Date:** 2026-04-29
**Branch:** `feat/14a-frontend-foundation`
**Predecessor:** Plan #13b-β2 (`91d31dd`, 2026-04-28)
**Successors:** #14b (read-only views) → #14c (mutations) → #14d (onboarding + help + metrics polish)

---

## 1. Background and goals

### 1.1 Context

After Plan #13b-β2 the daemon HTTP API surface is complete: every per-project route uses `{project}` path-prefix, cross-vault aggregation works for `/jobs`, `/dead-letter`, `/lost-sessions`, `/metrics/*`, `/health`. There is currently **no frontend** in the repo — `mnemos daemon start` exposes JSON-only endpoints on `:5757`.

### 1.2 Goal of #14a (MVP)

Stand up the React+shadcn/ui frontend project scaffolding and ship the smallest user-visible deliverable: open `http://localhost:5757/` in a browser and see a dashboard with the project list, basic per-project stats, the global usage widget, and a working sidebar/topbar. Everything else (read-only views, mutations, onboarding, help, full metrics charts) is deferred to #14b/#14c/#14d.

After #14a the user can:

1. Run `mnemos daemon start` (single project or `--all`).
2. Open `http://localhost:5757/` in any modern browser.
3. See:
   - Top bar: logo, project switcher, usage widget (tokens injected today, sessions covered, compression ratio), alerts bell, settings/help/locale buttons.
   - Sidebar: 11 navigation entries (most are placeholders linking to "coming in #14b" stubs; only Overview is fully wired).
   - Main content: Overview page with cards for every registered project — each card shows name, vault path, health badge (green/yellow/red), per-project token metrics, and a "Open" button into ProjectView.
   - ProjectView page (clicked from Overview): vault path, session counts, last activity timestamp, dead-letter count, watchdog status. Nothing more in #14a (the 11 sub-sections come in #14b–#14d).
4. Switch UI language between UK / RU / EN.
5. See a toast on daemon-down (when daemon stops the dashboard polling fails gracefully).

### 1.3 Non-goals (deferred to later #14 sub-plans)

- All read-only views beyond Overview + ProjectView shell (Pages browser, Sessions, Activity, Trash, Snapshots, Lost Sessions, Suggestions, Failed Jobs, Health page) — **#14b**.
- All mutations (page edit, snapshot create/restore, trash restore, activity undo, lint run, ontology approve, settings PATCH, deletes with tier-confirms) — **#14c**.
- Onboarding wizard, full Help system, full Metrics page with recharts — **#14d**.
- Authentication / multi-user — out of v1 entirely.
- Mobile responsive design — desktop-first; basic shrinking acceptable, no mobile-tuned views.
- Playwright e2e tests — Vitest + RTL component tests only in #14a; e2e potentially in #14e.

### 1.4 Spec alignment

| Spec section | #14a coverage |
|---|---|
| §11.1 project structure | Build the `frontend/` tree exactly per spec, but only populate the files needed for #14a. |
| §11.2 stack | All listed deps installed. |
| §11.3 state mgmt | TanStack Query for server state, Zustand for UI state, no Redux/Context. |
| §11.4 routing | All routes declared, but most pages are placeholder stubs ("Coming in #14b"). Only `/`, `/project/:name`, and `/help` (single-page placeholder) render content. |
| §11.5 i18next | Loaded with UK primary, RU + EN fallback. Locale files seeded with `common`/`navigation`/`overview` keys; rest filled in later sub-plans. |
| §12.1 layout | TopBar + Sidebar + main content shell exactly as drawn. |
| §12.2 Overview | Implemented fully (project list with health badges + savings widget). |
| §12.3 Project View | Shell only — top stats panel + 11-tab nav. Each tab opens a placeholder page until #14b. |

---

## 2. Architecture

### 2.1 Repository layout

```
D:/code/claude-mnemos/
├── claude_mnemos/                 # existing Python package
│   ├── daemon/
│   │   ├── app.py                 # MODIFIED: mount StaticFiles after API routers
│   │   └── static/                # NEW: build output (gitignored except .gitkeep)
│   │       ├── .gitkeep
│   │       └── (built by `frontend/`)
│   └── ...
│
├── frontend/                      # NEW
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── components.json            # shadcn/ui
│   ├── index.html
│   ├── .eslintrc.json (or eslint.config.js for v9)
│   ├── .gitignore
│   ├── public/
│   │   ├── favicon.svg
│   │   └── locales/
│   │       ├── uk.json
│   │       ├── ru.json
│   │       └── en.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── i18n.ts
│       ├── pages/
│       │   ├── Overview.tsx
│       │   ├── ProjectView.tsx
│       │   ├── Help.tsx           # placeholder (full content in #14d)
│       │   └── Placeholder.tsx    # generic "Coming in #14b" stub
│       ├── components/
│       │   ├── ui/                # shadcn/ui — installed via `pnpm dlx shadcn add ...`
│       │   ├── layout/
│       │   │   ├── Layout.tsx
│       │   │   ├── TopBar.tsx
│       │   │   ├── Sidebar.tsx
│       │   │   └── ProjectSwitcher.tsx
│       │   └── widgets/
│       │       ├── HealthBadge.tsx
│       │       ├── UsageWidget.tsx
│       │       └── ProjectCard.tsx
│       ├── hooks/
│       │   ├── useProjects.ts
│       │   ├── useProjectHealth.ts
│       │   └── useUsage.ts
│       ├── stores/
│       │   ├── ui.store.ts
│       │   └── notifications.store.ts
│       ├── api/
│       │   ├── client.ts          # axios instance + base URL
│       │   ├── projects.api.ts
│       │   ├── health.api.ts
│       │   └── metrics.api.ts
│       ├── types/
│       │   ├── Project.ts
│       │   ├── Health.ts
│       │   └── UsageSummary.ts
│       └── styles/
│           └── globals.css
│
├── docs/plans/
│   ├── 2026-04-29-14a-frontend-foundation-design.md  ← this file
│   └── 2026-04-29-14a-frontend-foundation-plan.md
└── ...
```

`frontend/` is at the repo root (sibling to `claude_mnemos/`). The build outputs `index.html` + `assets/` to `claude_mnemos/daemon/static/`. Daemon serves that directory via FastAPI `StaticFiles(html=True)`.

### 2.2 Build / serve flow

**Production (single user end-state):**

```
$ cd frontend && pnpm install && pnpm build
  → outputs to ../claude_mnemos/daemon/static/

$ mnemos daemon start
  → FastAPI on :5757
  → /projects, /sessions/{p}, /metrics/* etc. — JSON API (already β2)
  → /assets/*.js, /assets/*.css — static files
  → /  and  /project/:name  and any other React-router path → index.html (SPA fallback)
```

**Development (frontend changes):**

```
Terminal 1: $ mnemos daemon start --all       # daemon on :5757
Terminal 2: $ cd frontend && pnpm dev          # vite on :5173

→ Browser: http://localhost:5173
  vite proxies API calls (everything matching /(projects|sessions|jobs|metrics|health|...))
  to http://127.0.0.1:5757
```

Vite proxy config covers every existing daemon route prefix. Frontend code uses `import.meta.env.VITE_DAEMON_BASE_URL` (defaults to `""` so requests stay relative — proxied in dev, served by daemon in prod).

### 2.3 FastAPI static file mount

`claude_mnemos/daemon/app.py:create_app` gets a final mount:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

# ... existing routers + exception handlers ...

# Mount frontend static files (built by `frontend/`).
# html=True enables SPA fallback: any path not matching a file → index.html.
# Mount LAST so REST routes win on conflicts.
static_dir = Path(__file__).parent / "static"
if (static_dir / "index.html").is_file():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
```

If `static_dir/index.html` does not exist (developer hasn't built yet), the mount is skipped — daemon still works as JSON-only API. This avoids hard-coupling backend tests to frontend build artefacts.

`claude_mnemos/daemon/static/.gitkeep` ensures the directory exists in git; everything else under it is gitignored.

### 2.4 Tech stack — pinned versions

| Library | Version | Purpose |
|---|---|---|
| **react** | ^19.0.0 | UI framework |
| **react-dom** | ^19.0.0 | DOM renderer |
| **react-router** | ^7.1.0 | Routing (the new `react-router` not `-dom`) |
| **vite** | ^6.0.0 | Build tool, dev server |
| **typescript** | ^5.7.0 | Type safety |
| **@vitejs/plugin-react** | ^4.3.0 | Vite React HMR |
| **tailwindcss** | ^4.0.0 | Styling |
| **@tailwindcss/postcss** | ^4.0.0 | Tailwind v4 PostCSS plugin |
| **@radix-ui/react-***  | latest | shadcn/ui primitives |
| **lucide-react** | ^0.460.0 | Icons |
| **clsx** + **tailwind-merge** | latest | Class composition (`cn()` helper) |
| **class-variance-authority** | latest | shadcn/ui variants |
| **@tanstack/react-query** | ^5.62.0 | Server state |
| **@tanstack/react-query-devtools** | ^5.62.0 | Dev tools |
| **zustand** | ^5.0.0 | UI state |
| **zod** | ^3.24.0 | Runtime schemas |
| **axios** | ^1.7.0 | HTTP client |
| **i18next** | ^24.0.0 | i18n |
| **react-i18next** | ^15.0.0 | React binding |
| **i18next-http-backend** | ^3.0.0 | Load locale JSON |
| **i18next-browser-languagedetector** | ^8.0.0 | Auto-detect |
| **dayjs** | ^1.11.0 | Date formatting |
| **vitest** | ^2.1.0 | Test runner |
| **@testing-library/react** | ^16.0.0 | Component tests |
| **@testing-library/jest-dom** | ^6.6.0 | Matchers |
| **jsdom** | ^25.0.0 | Test DOM |
| **@types/react** | ^19.0.0 | Type defs |
| **@types/react-dom** | ^19.0.0 | Type defs |
| **eslint** | ^9.15.0 | Linting |
| **typescript-eslint** | ^8.15.0 | TS rules |

`pnpm` as the package manager (faster than npm, doesn't pollute with `node_modules` symlinks Windows-unfriendly — actually pnpm is fine on Windows; npm also works. Preference: **pnpm**, but document `npm` as fallback).

### 2.5 Routing

`src/App.tsx` declares all routes per spec §11.4 even though most are placeholders in #14a:

```tsx
const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "/onboarding", element: <Placeholder section="Onboarding" plan="#14d" /> },
      {
        path: "/project/:name",
        children: [
          { index: true, element: <ProjectView /> },
          { path: "pages", element: <Placeholder section="Pages browser" plan="#14b" /> },
          { path: "pages/:pageId", element: <Placeholder section="Page detail" plan="#14b" /> },
          { path: "sessions", element: <Placeholder section="Sessions" plan="#14b" /> },
          { path: "activity", element: <Placeholder section="Activity Center" plan="#14b" /> },
          { path: "suggestions", element: <Placeholder section="Suggestions" plan="#14b" /> },
          { path: "trash", element: <Placeholder section="Trash" plan="#14b" /> },
          { path: "snapshots", element: <Placeholder section="Snapshots" plan="#14b" /> },
          { path: "health", element: <Placeholder section="Health" plan="#14b" /> },
          { path: "settings", element: <Placeholder section="Settings" plan="#14c" /> },
        ],
      },
      { path: "/lost-sessions", element: <Placeholder section="Lost Sessions" plan="#14b" /> },
      { path: "/help", element: <Help /> },
      { path: "/metrics", element: <Placeholder section="Metrics" plan="#14d" /> },
      { path: "/settings/global", element: <Placeholder section="Global Settings" plan="#14c" /> },
    ],
  },
]);
```

`<Placeholder>` is a 30-line component with friendly copy: "Этот раздел появится в плане {plan}. Пока что можно посмотреть [Обзор](/)."

### 2.6 API client + types

`src/api/client.ts`:

```ts
import axios from "axios";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_DAEMON_BASE_URL ?? "",
  timeout: 5000,
});

apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    // Surface daemon-down via a flag for the UI; let TanStack Query handle retries.
    return Promise.reject(err);
  }
);
```

`src/api/projects.api.ts`:

```ts
import { z } from "zod";
import { apiClient } from "./client";

export const ProjectMapEntrySchema = z.object({
  name: z.string(),
  vault_root: z.string(),
  cwd_patterns: z.array(z.string()),
});
export type ProjectMapEntry = z.infer<typeof ProjectMapEntrySchema>;

const ProjectsListSchema = z.array(ProjectMapEntrySchema);

export async function listProjects(): Promise<ProjectMapEntry[]> {
  const r = await apiClient.get("/projects");
  return ProjectsListSchema.parse(r.data);
}
```

`src/api/health.api.ts`:

```ts
export const VaultHealthSchema = z.object({
  watchdog_running: z.boolean(),
  jobs_queued: z.number(),
  jobs_running: z.number(),
  jobs_dead_letter: z.number(),
});

export const HealthSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  version: z.string(),
  uptime_s: z.number(),
  alerts_count: z.number(),
  vaults: z.record(z.string(), VaultHealthSchema),
  jobs_alert: z.boolean(),
});

export type Health = z.infer<typeof HealthSchema>;

export async function getHealth(): Promise<Health> {
  const r = await apiClient.get("/health");
  return HealthSchema.parse(r.data);
}
```

`src/api/metrics.api.ts`:

```ts
export const UsageSummarySchema = z.object({
  period: z.string(),
  total_tokens_injected: z.number(),
  tokens_full: z.number(),
  sessions_covered: z.number(),
  avg_compression_ratio: z.number(),
  events_count: z.number(),
});
export type UsageSummary = z.infer<typeof UsageSummarySchema>;

export async function getUsage(period = "30d"): Promise<UsageSummary> {
  const r = await apiClient.get("/metrics/usage", { params: { period } });
  return UsageSummarySchema.parse(r.data);
}

export async function getUsageByProject(period = "30d") {
  const r = await apiClient.get("/metrics/usage/by-project", { params: { period } });
  return r.data; // shape: { projects: [{project, ...}] }
}
```

Hooks wrap with TanStack Query:

```ts
// src/hooks/useProjects.ts
export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    refetchInterval: 5000,
  });
}

// src/hooks/useProjectHealth.ts
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 5000,
  });
}

// src/hooks/useUsage.ts
export function useUsage(period = "30d") {
  return useQuery({
    queryKey: ["metrics", "usage", period],
    queryFn: () => getUsage(period),
    refetchInterval: 30_000, // metrics change slowly
  });
}
```

### 2.7 Layout

```tsx
// src/components/layout/Layout.tsx
export function Layout() {
  return (
    <div className="grid h-screen grid-rows-[auto_1fr] overflow-hidden">
      <TopBar />
      <div className="grid grid-cols-[16rem_1fr] overflow-hidden">
        <Sidebar />
        <main className="overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

**TopBar:**

```
┌──────────────────────────────────────────────────────────────────────┐
│ [logo] claude-mnemos    [Project: alpha ▾]    💉 8.2K · 5 · ×5.8     │
│                                          [🔔 3] [⚙] [?] [UK ▾]       │
└──────────────────────────────────────────────────────────────────────┘
```

- **Logo + title:** static.
- **ProjectSwitcher:** dropdown, lists `useProjects()`. If on `/project/:name`, current name is selected and switching navigates to `/project/<new>`. If on root `/`, label is "Все проекты" and selecting a project navigates to `/project/<chosen>`.
- **UsageWidget:** reads `useUsage("1d")`, displays `tokens_actual` formatted (8.2K), session count, compression ratio. Tooltip explains each number. If usage is zero (no events ever), shows "Пока без данных — начните работать с Claude Code" and a faint icon.
- **Bell:** alerts count from `useHealth().data.alerts_count`. Click → `/help` placeholder for now (proper alerts panel in #14b).
- **Settings/Help/Locale:** buttons that navigate to the respective routes / cycle the locale (uk → ru → en → uk).

**Sidebar:**

```
📊 Обзор                       (active when on /)
─── Project (alpha) ───────────
📚 Страницы → /project/alpha/pages
💬 Чаты → /project/alpha/sessions
🌊 Очередь → /project/alpha (placeholder; jobs in #14b)
📜 История → /project/alpha/activity
💡 Предложения → /project/alpha/suggestions
🔍 Потерянные → /lost-sessions
🗑️ Корзина → /project/alpha/trash
💾 Снапшоты → /project/alpha/snapshots
🩺 Здоровье → /project/alpha/health
⚙️ Настройки → /project/alpha/settings
─── Global ────────────────────
📈 Метрики → /metrics
📖 Помощь → /help
```

(Global settings reached via TopBar gear icon → `/settings/global`, not duplicated in sidebar — matches spec §12.1.)

If no project is active (root path), the per-project section is collapsed/disabled with a hint "Выберите проект из ProjectSwitcher". Sidebar collapse/expand persists in `ui.store` (Zustand).

### 2.8 Overview page

```tsx
// src/pages/Overview.tsx
export function Overview() {
  const { data: projects, isLoading, error } = useProjects();
  const { data: health } = useHealth();

  if (isLoading) return <SkeletonGrid />;
  if (error) return <DaemonDownAlert error={error} />;
  if (!projects?.length) return <NoProjectsCallout />;

  return (
    <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
      {projects.map((p) => (
        <ProjectCard
          key={p.name}
          project={p}
          health={health?.vaults?.[p.name]}
        />
      ))}
    </div>
  );
}
```

**ProjectCard** renders:
- Project name (link to `/project/<name>`).
- Vault path (truncated, full on hover).
- HealthBadge (green/yellow/red) — green when watchdog_running and dead_letter < 10, yellow when watchdog down OR dead_letter ≥ 10, red when both.
- Per-project usage stats: read from `useUsageByProject()` (added if there's a single batch fetch) — show `tokens_injected`, `sessions_covered`, `compression_ratio`. If no events: muted "Пока без данных".
- Jobs counters: `queued · running · dead_letter` from `health.vaults[name]`.
- Buttons: "Открыть" (navigate to ProjectView).

**NoProjectsCallout:** when `projects.length === 0`:

```
🧠 Мозги ваших проектов появятся здесь.

Зарегистрируйте первый проект:
  $ mnemos project add NAME --vault PATH

(в #14d появится кнопка для добавления через UI)
```

**DaemonDownAlert:** when API call fails:

```
⚠ Daemon недоступен.

Запустите daemon:
  $ mnemos daemon start

Дашборд автоматически переподключится.
```

### 2.9 ProjectView shell

```tsx
// src/pages/ProjectView.tsx
export function ProjectView() {
  const { name } = useParams<{ name: string }>();
  const { data: health } = useHealth();
  const { data: projects } = useProjects();
  const project = projects?.find((p) => p.name === name);

  if (!project) return <UnknownProject name={name!} />;
  const vh = health?.vaults?.[name!];

  return (
    <div className="space-y-6">
      <Header project={project} vault_health={vh} />
      <StatsGrid project={project} vault_health={vh} />
      <ComingSoonGrid project={project} />
    </div>
  );
}
```

`<Header>`: project name, vault path, "Открыть в Obsidian" button (`obsidian://open?vault=...&file=...`).

`<StatsGrid>`: 4 small cards — sessions covered (from `useUsageByProject`), watchdog status, jobs queue snapshot, dead-letter count.

`<ComingSoonGrid>`: 11 cards in a 4-column grid mapping to the Project View sections from spec §12.3. Each card:
- Title + emoji per spec.
- One-line description.
- "Coming in #14b/#14c" badge.
- Click navigates to the placeholder route (so the user sees consistent navigation).

This is enough to demonstrate the full navigation surface; #14b–#14d fill it in.

### 2.10 Internationalization

`frontend/public/locales/uk.json` (primary), `ru.json`, `en.json`. Same key tree per spec §11.5:

```json
{
  "common": { "loading": "Завантаження...", "save": "Зберегти", ... },
  "navigation": { "overview": "Огляд", "pages": "Сторінки", ... },
  "topbar": {
    "project_switcher": "Проєкт",
    "all_projects": "Всі проєкти",
    "alerts": "Сповіщення",
    "settings": "Налаштування",
    "help": "Допомога"
  },
  "overview": {
    "no_projects_title": "Мозок проєкту з'явиться тут",
    "no_projects_hint": "Зареєструйте проєкт командою mnemos project add",
    "daemon_down_title": "Демон недоступний"
  },
  "project_view": {
    "open_in_obsidian": "Відкрити в Obsidian",
    "watchdog_running": "Watchdog працює",
    "watchdog_down": "Watchdog зупинено"
  },
  "health": { "ok": "Добре", "degraded": "Деградовано", "down": "Недоступний" },
  "usage": { "tokens": "{{count}} токен", "tokens_plural": "{{count}} токенів", "sessions": "сесія", "sessions_plural": "сесій", "ratio": "стиснення ×{{ratio}}" }
}
```

Three files, ~80 keys each in #14a (covers TopBar/Sidebar/Overview/ProjectView shell). #14b–#14d will add keys for their pages.

`src/i18n.ts` per spec §11.5 — UK detected first, RU then EN as fallbacks.

### 2.11 Notifications / toasts

shadcn/ui `<Toaster />` at the root of `<Layout>`. `notifications.store.ts` (Zustand):

```ts
export const useNotifications = create<NotificationsState>((set) => ({
  toasts: [],
  push: (toast) => set((s) => ({ toasts: [...s.toasts, toast] })),
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
```

In #14a only the "daemon offline" toast is wired. #14c will wire mutation success/failure toasts.

### 2.12 Tests

**Vitest + RTL** for component tests. Setup `vitest.config.ts` with jsdom environment. Tests live in `frontend/src/**/__tests__/*.test.tsx`.

Coverage target for #14a (~10–15 tests):

- `TopBar` renders project switcher + usage widget.
- `Sidebar` highlights active route + collapses.
- `ProjectCard` renders health badge + stats + handles missing health gracefully.
- `Overview` shows empty state, loading state, error state, and project list.
- `ProjectView` shows unknown-project state for bad params.
- `i18n` switches locale and persists.
- `apiClient` defaults to relative URL when env var is unset.
- `useProjects()` polls correctly (mock timer test).

**No e2e** in #14a. **No backend Python tests added** (FastAPI static-mount has a single Python test verifying mount-skip when static is missing, mount-active when index.html exists).

---

## 3. Backend changes

Single-file edit: `claude_mnemos/daemon/app.py:create_app` mounts static files at the end. This is **idempotent** — when frontend isn't built, the mount is skipped, daemon serves JSON only (matches current behaviour).

```python
def create_app(daemon: Any | None = None) -> FastAPI:
    app = FastAPI(title="claude-mnemos daemon", version=__version__)
    app.state.daemon = daemon
    # ... include_router calls ...
    # ... exception handlers ...

    # NEW: serve frontend static files if built. SPA fallback = html=True.
    static_dir = Path(__file__).parent / "static"
    if (static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app
```

`Path` import added at top. `claude_mnemos/daemon/static/.gitkeep` committed; everything else under `static/` gitignored.

**Tests added** in `tests/daemon/test_app_static.py`:

```python
def test_static_mount_skipped_when_no_index_html(tmp_path, monkeypatch):
    # Patch __file__ via monkeypatching Path to point at empty dir
    # Verify create_app does not raise and routes still work.

def test_static_mount_active_when_index_html_exists(tmp_path, monkeypatch):
    # Place a fake index.html at static/, patch path resolution,
    # verify GET / returns the fake content.
```

### 3.1 Why daemon-served, not separate process?

Single-port, single-process means `mnemos daemon start` is enough — no second tool to manage. Spec §5.1 already shows the Browser → `:5757` → daemon in the architecture diagram.

### 3.2 Build automation

The user runs frontend build manually for now (`cd frontend && pnpm build`). Plan #14d (or a follow-up) can wire `pip install` to bundle the build artefacts via a build hook. **Not in #14a.**

`claude_mnemos/daemon/static/.gitignore`:

```
*
!.gitkeep
```

This way locally-built artefacts are tracked-by-developer but not in git.

---

## 4. Vite proxy config

`frontend/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    outDir: "../claude_mnemos/daemon/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy every daemon REST prefix to the running daemon.
      "/projects": "http://127.0.0.1:5757",
      "/sessions": "http://127.0.0.1:5757",
      "/snapshots": "http://127.0.0.1:5757",
      "/pages": "http://127.0.0.1:5757",
      "/trash": "http://127.0.0.1:5757",
      "/lint": "http://127.0.0.1:5757",
      "/ontology": "http://127.0.0.1:5757",
      "/activity": "http://127.0.0.1:5757",
      "/vault": "http://127.0.0.1:5757",
      "/lost-sessions": "http://127.0.0.1:5757",
      "/jobs": "http://127.0.0.1:5757",
      "/dead-letter": "http://127.0.0.1:5757",
      "/metrics": "http://127.0.0.1:5757",
      "/health": "http://127.0.0.1:5757",
      "/version": "http://127.0.0.1:5757",
      "/alerts": "http://127.0.0.1:5757",
      "/settings": "http://127.0.0.1:5757",
    },
  },
});
```

Long but explicit; trumps a path-prefix regex for clarity. (Catch-all `^/[a-z-]+$` is also viable; use the explicit list for greppability.)

---

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| shadcn/ui setup is finicky on Tailwind v4 | Tailwind v4 is GA; shadcn/ui supports it. Use the v4-aware install command. If trouble, downgrade to Tailwind v3.4 — well-trodden. Track in plan task 1. |
| React 19 breaking changes vs ecosystem | Most libs in the stack already support React 19 (Nov 2024 GA). If a peer-dep complains, pin React to 18.3 — fine for #14a. |
| Vite proxy doesn't cover newly-added daemon routes | Document the proxy table in `frontend/vite.config.ts` next to API client; future plans must update both. |
| Static mount conflicts with REST routes | Mounted last; FastAPI routers take precedence. Tested. |
| pnpm/npm registry blocked / offline | Document `npm install` as fallback; commit `package-lock.json` so version pins are reproducible. |
| User locale doesn't match UK/RU/EN | i18next falls back to EN. Future plans can add more. |
| TanStack Query cache eats memory across tab session | Default `staleTime` 30s, `gcTime` 5min. Polling intervals chosen conservative. |
| Built `static/` artefacts get out of sync with backend API | Frontend types are hand-maintained mirrors of Pydantic. Z.parse at API boundary catches schema drift loudly. |

---

## 6. Acceptance criteria

#14a is done when:

1. ✅ `frontend/` directory exists with `package.json`, `vite.config.ts`, `tsconfig.json`, `tailwind.config.ts`, `index.html`, full `src/` tree.
2. ✅ `cd frontend && pnpm install && pnpm build` succeeds (or `npm` equivalent), outputs to `claude_mnemos/daemon/static/`.
3. ✅ `claude_mnemos/daemon/app.py` mounts `static/` as last app mount; conditional on `index.html` existence; tested.
4. ✅ Running `mnemos daemon start --all` after a frontend build → `http://localhost:5757/` returns `index.html`.
5. ✅ Browser shows: TopBar (logo, project switcher, usage widget, bell, locale switch), Sidebar with 11+2 entries, Overview content with cards.
6. ✅ Cards display real data from `/projects`, `/health`, `/metrics/usage/by-project`.
7. ✅ Locale switcher cycles UK → RU → EN; copy updates immediately.
8. ✅ Daemon down → DaemonDownAlert shown; reconnects automatically when daemon restarts.
9. ✅ Empty project map → NoProjectsCallout shown.
10. ✅ Click into ProjectView → header + stats + 11 navigation tiles (each tile leads to a Placeholder page).
11. ✅ ProjectView for unknown project name → friendly "проект не найден" page with link back to Overview.
12. ✅ Vitest suite green (~10–15 tests).
13. ✅ `python -m pytest tests/daemon/test_app_static.py -v` green (1–2 tests).
14. ✅ ruff + mypy --strict on backend stay clean.
15. ✅ ESLint clean on `frontend/src/**`.

---

## 7. Open questions resolved by this design

| Question | Decision | Rationale |
|---|---|---|
| Where does built frontend live? | `claude_mnemos/daemon/static/` | Bundles into Python wheel; daemon serves it; single-port deployment. |
| Dev vs prod modes? | Vite dev `:5173` (proxies daemon `:5757`); prod `pnpm build` → daemon serves. | Standard React+FastAPI workflow. |
| Package manager? | pnpm preferred, npm fallback. | Faster, smaller `node_modules`. Lock file committed either way. |
| TanStack Query polling intervals? | `/projects` 5s, `/health` 5s, `/metrics` 30s. | Spec §5.2 Flow 4 hints 2–5s for active operations; metrics change slowly. |
| State libraries? | TanStack Query (server) + Zustand (UI). No Redux/Context. | Per spec §11.3. |
| i18next default locale? | UK primary, RU fallback, EN international fallback. | User in Ukraine (per memory user_profile.md). |
| Routes declared in #14a? | All — but most return Placeholder. | Sidebar/router contract stable from day one; future sub-plans only swap component bodies. |
| Tests in #14a? | Vitest + RTL component (~10–15) + 1–2 Python tests for static mount. No e2e. | E2e is its own complexity; component tests give the safety we need now. |

---

## 8. Out of scope (deferred)

- All non-Overview pages have proper UIs → #14b (read-only views), #14c (mutations + editor), #14d (onboarding + help + metrics polish).
- Authentication / multi-user / cloud sync → never (v1 non-goal per spec §1.3).
- Mobile-tuned views → never (v1 non-goal).
- E2e Playwright suite → potentially #14e or trailing follow-up.
- Build automation hook in `pip install` → potentially #14d or follow-up.
- Bundling locale JSON into the wheel → #14d (in #14a, locale files are served from `frontend/public/locales/` and copied into `static/locales/` by Vite).
- Dark theme / theme switcher → #14d polish.
- Keyboard shortcuts (cmd-k command palette) → out of v1 entirely.
