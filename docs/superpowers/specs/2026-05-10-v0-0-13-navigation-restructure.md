# v0.0.13 — Navigation restructure

> **Status:** approved 2026-05-10 by Ярик. One implementation plan;
> subagent-driven execution. i18n audit deferred to v0.0.14.

## Problem

Three concrete UX bugs surfaced while Ярик lived in the dashboard:

1. **Sidebar half-disabled.** The sidebar shows all 10 project nav items
   even when no project is selected. Project items render greyed-out with
   a "select a project" tooltip. Visually noisy, conceptually unclear —
   the user wonders what those items do and why they exist if they're
   unusable.

2. **ProjectView duplicates the sidebar.** Visiting
   `/project/:name` (the project's "home") renders 8 large tile cards,
   each linking to a sub-page (Pages, Sessions, Activity, Suggestions,
   Trash, Snapshots, Health, Settings). The sidebar already has those
   exact same links. Two ways to navigate to the same place — wasted
   space and decision friction.

3. **Hybrid global/project items in the sidebar.** Lost Sessions sits
   inside the `PROJECT_ITEMS` array but with `requiresProject: false` —
   it's a global view (cross-vault). Failed Jobs (Dead Letter) lives in
   `GLOBAL_ITEMS`. The user can't tell from the sidebar grouping which
   items are scoped to the current project and which aren't.

## Goal

Reorganize so:
- **Project-scoped navigation** lives in the sidebar, only when there IS
  a project context.
- **Global navigation** lives in a top header, always visible.
- **ProjectView** stops duplicating navigation; it shows project-specific
  data (stats + inject preview), nothing else.
- **No disabled sidebar items.** If you can't navigate there from where
  you are, the link doesn't exist in the UI right now.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ HEADER                                                               │
│ [logo] [Project picker ▼]  ··  [Lost] [Failed] [Metrics] [Help]     │
│                                [Global Settings] [RU/UK/EN]          │
├──────────────┬───────────────────────────────────────────────────────┤
│ SIDEBAR      │ CONTENT                                               │
│ (only when   │                                                       │
│  in project) │                                                       │
│              │                                                       │
│ 📊 Overview  │                                                       │
│ ──Project──  │                                                       │
│ 📚 Pages     │                                                       │
│ 💬 Sessions  │                                                       │
│ 🌊 Queue     │                                                       │
│ 📜 Activity  │                                                       │
│ 💡 Sugges…   │                                                       │
│ 🗑️ Trash     │                                                       │
│ 💾 Snapshots │                                                       │
│ 🩺 Health    │                                                       │
│ ⚙ Settings   │                                                       │
└──────────────┴───────────────────────────────────────────────────────┘
```

### Header (new component)

`frontend/src/components/layout/Header.tsx`. Always rendered.

Left side:
- Brand mark linking to `/` (Overview).
- Project picker dropdown.

Right side:
- Lost Sessions link → `/lost-sessions`
- Failed Jobs link → `/dead-letter`
- Metrics link → `/metrics`
- Help link → `/help`
- Global Settings → `/settings/global`
- Locale switcher (RU / UK / EN — already exists in current top-right)

### Project picker

A dropdown in the header. State derived from the URL: when on
`/project/:name/*` show that project's display name; otherwise show
"Все проекти" / "All projects".

Items in the dropdown:
1. "All projects" → `/`
2. divider
3. Each project from `useProjects()` → `/project/<name>`
4. divider
5. "+ New project" → `/onboarding`

Selecting a project from a non-project page lands on
`/project/<name>` (= ProjectView, the project home).
Selecting from inside a project: same. The picker doesn't try to
preserve the sub-route between projects (you go to that project's
home), because the route map differs per-project rarely matters.

### Sidebar (redesigned)

`frontend/src/components/layout/Sidebar.tsx`.

Visibility: rendered ONLY when the route matches `/project/:name/*`.
On `/`, `/lost-sessions`, `/dead-letter`, `/metrics`, `/help`,
`/settings/global`, `/diagnostics`, `/onboarding*` — sidebar is
unmounted. Content area takes the full width.

Items (project-scoped, no global mixed in):

| Icon | Label key | Route |
|---|---|---|
| 📊 | `navigation.project_overview` | `/project/:name` |
| 📚 | `navigation.pages` | `/project/:name/pages` |
| 💬 | `navigation.sessions` | `/project/:name/sessions` |
| 🌊 | `navigation.queue` | `/project/:name/queue` |
| 📜 | `navigation.activity` | `/project/:name/activity` |
| 💡 | `navigation.suggestions` | `/project/:name/suggestions` |
| 🗑️ | `navigation.trash` | `/project/:name/trash` |
| 💾 | `navigation.snapshots` | `/project/:name/snapshots` |
| 🩺 | `navigation.health` | `/project/:name/health` |
| ⚙ | `navigation.settings` | `/project/:name/settings` |

Removed from sidebar:
- Lost Sessions (it was global, moved to header)
- Failed Jobs / Dead Letter (was global, moved to header)
- Metrics, Help, Global Settings (were global, moved to header)

The `disabled` rendering branch and `navigation.disabled_hint` locale
key are deleted — there are no disabled items anymore.

### Layout shell

`frontend/src/components/layout/Layout.tsx`.

Becomes:

```tsx
<div>
  <Header />
  <div className="flex">
    <ProjectSidebarMaybe />
    <main className="flex-1"><Outlet /></main>
  </div>
</div>
```

Where `ProjectSidebarMaybe` is `<Sidebar/>` if the current route starts
with `/project/`, else `null`. Use `useMatch` from react-router or
`useLocation` + a simple prefix check.

### ProjectView simplified

`frontend/src/pages/ProjectView.tsx`.

Removed:
- The `TILES` array (8 tiles).
- The grid that renders tile cards.

Kept:
- Project header (display name, vault path, "Open in Obsidian" button).
- 4 stat cards (sessions covered, jobs queued, jobs running, jobs
  dead-letter).
- `<InjectPreview project={name} />` block.

After removal the page is a clean compact dashboard for one project.
Sidebar handles all navigation away from this page.

## Locale changes

Add new keys in `frontend/public/locales/{en,uk,ru}.json` under a new
`header` namespace:

```json
"header": {
  "brand": "claude-mnemos",
  "project_picker": {
    "all_projects": "All projects",
    "new_project": "+ New project",
    "switch_to": "Switch to {{name}}"
  },
  "links": {
    "lost_sessions": "Lost Sessions",
    "failed_jobs": "Failed Jobs",
    "metrics": "Metrics",
    "help": "Help",
    "global_settings": "Global Settings"
  }
}
```

Plus translations in uk.json/ru.json mirroring. Existing
`navigation.*` keys for moved items (lost_sessions, failed_jobs,
metrics, help, global_settings) — keep them, since the project tile
labels in the legacy code referenced the same keys; they may resurface
later. Only delete `navigation.disabled_hint` (the tooltip for
disabled items).

Add `navigation.project_overview` ("Project Overview" / «Огляд
проєкту» / «Обзор проекта») — sidebar's first item.

## Tests

### Backend
None — this release is frontend-only.

### Frontend (Vitest)

`frontend/src/__tests__/Sidebar.test.tsx`:
- Sidebar mounts only inside a project route. Render `Sidebar` inside a
  `MemoryRouter` initialized at `/`; assert it returns null. Repeat for
  `/lost-sessions`. Then mount at `/project/foo`; assert all 10 project
  items render.
- No item renders with `data-disabled`.

`frontend/src/__tests__/Header.test.tsx` (NEW):
- Renders brand link, project picker, global link cluster.
- Project picker shows "All projects" when route doesn't match a
  project.
- Project picker shows project display name when on
  `/project/foo`.
- Selecting a project from the picker navigates to
  `/project/<name>`.

`frontend/src/__tests__/Layout.test.tsx` (UPDATE if exists, ELSE NEW):
- Sidebar is in the DOM only on project routes.
- Header is in the DOM on every route.

`frontend/src/__tests__/ProjectView.test.tsx` (UPDATE):
- Drop assertions about 8 tile titles.
- Add assertion: page renders header + 4 stat cards + InjectPreview;
  no element with the role/text of a tile card array remains.

## Out of scope

- **Mobile responsive nav** — Ярик is on desktop. Skip until a real
  use case appears.
- **i18n audit / hardcoded strings sweep** — separate v0.0.14 spec.
- **Keyboard shortcuts** — out of scope; current setup has none, this
  isn't the place to add them.
- **Picker remembers last sub-route per project** — over-engineering.

## Acceptance criteria

A successful v0.0.13 release means:
- Visiting `/` shows Header + content (no sidebar). KPI / Lost Sessions
  metrics still match (no regression in v0.0.12 work).
- Visiting `/project/claude-mnemos-dev` shows Header (with picker
  reading "Claude Mnemos Dev"), Sidebar with 10 project items, Content
  showing project header + 4 stat cards + InjectPreview only (NO 8
  tile cards).
- Switching projects via the header picker re-renders sidebar items
  but keeps the user on the new project's home page.
- Locale switcher in Ukrainian / Russian shows all translated header
  + sidebar text. (English fallback only when key missing in locale —
  that's an i18n debt for v0.0.14.)
- No `data-disabled` sidebar items in the DOM under any state.
- Backend test count unchanged. Frontend Vitest count modestly up
  (new Header tests, modified Sidebar/ProjectView/Layout tests).

## Self-review

- **Placeholder scan:** All component file paths absolute. Header
  component spec'd by region (left/right). Picker dropdown items
  enumerated. No "TBD".
- **Internal consistency:** Header is "always rendered"; sidebar is
  conditional on `/project/:name/*`. ProjectView removes navigation
  tiles, leaving a stat-only view that complements the new sidebar.
  No two components claim the same responsibility.
- **Scope:** Frontend only, ~5-6 files, single release. Clean
  decomposition into ~5-6 tasks for the implementation plan.
- **Ambiguity check:**
  - When the picker is opened on `/onboarding/advanced` it should
    still show "All projects" (no project context). Confirmed.
  - The picker's "+ New project" links to `/onboarding` (welcome
    screen), not directly to the form. Onboarding has its own
    routing.
  - Sidebar item `📊 Project Overview` always points at
    `/project/:name` (matches `<NavLink end>` so it's only active
    on the exact route, not on sub-routes). Already the existing
    pattern.
