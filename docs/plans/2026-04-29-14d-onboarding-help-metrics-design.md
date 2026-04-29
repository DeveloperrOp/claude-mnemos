# Plan #14d — Onboarding wizard + Help + Metrics charts + polish (design)

**Date:** 2026-04-29
**Status:** Design
**Goal:** Replace the last 3 #14a Placeholder routes (`/onboarding`, `/help`, `/metrics`) with working pages, add an onboarding wizard for first-run users with no projects, add full usage charts with project filter + timeline + top sessions, ship a 5-section Help page, and clean up technical debt accumulated across #14b-1/2/c.

---

## 1. Background

After #14c the dashboard wires every disabled mutation. The only routes still rendering `<Placeholder />` are `/onboarding`, `/help`, `/metrics`. The Overview page already has a `<NoProjectsCallout>` that shows a CLI-only hint when no projects are mounted — this is the obvious entry point for the wizard.

The backend exposes:
- **Project CRUD** (`POST /projects`, `PATCH /projects/{name}`, `DELETE /projects/{name}`) — recon confirmed all three exist with stable Pydantic shapes; project create implicitly mounts the vault. Frontend has only `listProjects()` today; mutations are missing.
- **Metrics** — 4 pre-aggregated endpoints: `/metrics/usage`, `/metrics/usage/by-project`, `/metrics/usage/top-sessions`, `/metrics/usage/timeline?period=Nd`. The frontend wraps only the first two.
- **Help/Onboarding** — pure frontend; no backend involvement.

### Scope decision

Single plan. Recon suggested splitting into 14d-1 (onboarding) + 14d-2 (help+metrics+polish), but each subsystem stands at 3–5 tasks; combined ≈ 13–15 tasks — same shape as #14b-2 (15) and #14c (12). Splitting adds two extra merges with no real isolation gain. **Stay monolithic.**

### What's deliberately out of scope

- Backend changes. Zero new endpoints. Period parser stays `Nd` only.
- Cost projection. Backend has no cost field; we'd hardcode pricing tables that decay. Skip.
- Onboarding "ingest first session" step. Lost-sessions scanner from #14b-2 already covers the "find existing sessions" use case; the wizard ends after `POST /projects` succeeds and routes to the new project.
- Help content depth — sections are stubs with placeholder copy lines, not a finished manual. Real prose lands later.
- Code-split bundle. Tried it would change `vite.config.ts` and tree shake; out of scope unless trivial. Note it as remaining debt.
- Markdown rendering for Help — keep plain JSX with shadcn primitives, simpler than asynchronously loading markdown blobs.
- Real-time chart streaming. The 30-s `refetchInterval` from existing hooks is enough.

---

## 2. Architecture

### 2.1 Onboarding wizard

**Trigger surface:**
- `<NoProjectsCallout>` (already on Overview) gets a primary "Create project" button → navigates to `/onboarding`.
- TopBar `<ProjectSwitcher>` gets a `+ New project` item that does the same.

**Wizard structure** (`frontend/src/pages/Onboarding.tsx`):
- Single page, no multi-step modal — vertical form with three sections.
- **Section 1 — Project name.** Free-form input with live validation (regex `^[a-z0-9][a-z0-9_-]{0,63}$`). On invalid input the Submit button is disabled and a hint shows the rule.
- **Section 2 — Vault path.** Free-form text input. Hint: "Absolute path. The directory will be created if missing." No client-side filesystem checks (we don't have any).
- **Section 3 — CWD patterns** (optional, advanced collapsible). Multi-line textarea, comma- or newline-separated. Used by the daemon to map `claude code` sessions to this project. Default empty.
- **Submit:** POST `/projects` via `useProjectCreate`. On success: toast `Project created`, invalidate `["projects"]`, navigate to `/project/{name}` (which now lights up because the vault is mounted).
- **Errors:** `409 name_conflict` → inline error under name field. `500 mount_failed` → red callout with `detail` body. Other errors → `extractApiError` toast.

**Cancel** (button or Sidebar nav) — no dirty-state guard for now: form is short, low risk of accidental loss, and adding ConfirmDialog complicates a path that's already gated behind one button click.

The wizard is **not** the only way to create a project — power users can still `mnemos project add` from CLI. The wizard is a UI surface for the same operation.

### 2.2 Help page

`frontend/src/pages/Help.tsx` rewrites today's one-paragraph stub. Structure:

```
[Sticky in-page nav: 5 anchors]
[Section: Quickstart]    — install, mount first vault, daemon start
[Section: Concepts]       — projects, sessions, pages, suggestions, snapshots, dead-letter
[Section: Workflows]      — daily ingest, manual snapshot before risky op, restore from trash, approve suggestion
[Section: Troubleshooting] — daemon down, ingest failing, dead-letter accumulating, mount failed
[Section: About]          — version, links to GitHub/spec/issues
```

Each section is a `<section id="...">` with shadcn `<Card>` for sub-blocks. Copy is short (1–3 paragraphs each), all English in en.json + UK/RU translations. **No markdown rendering** — JSX with i18next interpolation handles bold + code via `<strong>` and `<code>` tags.

Version comes from `useHealth()` (already exposes `version` field). Links in About are static strings.

### 2.3 Metrics page

`frontend/src/pages/Metrics.tsx`. Three blocks stacked vertically:

**Block 1 — Period filter.** Pills `[7d | 30d | 90d]` (default 30d). Single shared period state drives the other two blocks via React state.

**Block 2 — Timeline chart.** Uses `/metrics/usage/timeline?period={period}`. Two stacked bars per day: tokens_input + tokens_output. Sessions count rendered as a thin overlay line (secondary axis). recharts `<ComposedChart>`.

**Block 3 — By-project usage table** + **Top sessions table.** Side-by-side on `xl:` viewports, stacked below.
- By-project: tabular `[project | sessions | tokens_input | tokens_output | tokens_per_byte]` rows from `/metrics/usage/by-project?period={period}`.
- Top sessions: `[project | session_id | ingested_at | tokens_total]` from `/metrics/usage/top-sessions?limit=10`. Note: this endpoint is **window-agnostic** — show this in a sub-label so users don't expect filtering.

**Charts library: `recharts` (~95KB gz)** added as a dependency. shadcn ships a `chart` component wrapping recharts with project-themed colors — install it via `shadcn add chart`. Bundle goes from 274 KB → ~370 KB gzip. That's a hit but acceptable for a metrics page that loads on-demand. **Optional polish:** lazy-load Metrics route via `React.lazy` to keep the initial bundle below 280 KB.

Empty state: when 0 vaults mounted, the timeline returns all-zero days; render an "Empty data" overlay on the chart instead of a misleading flat line.

### 2.4 Polish (debts from #14b/c)

Five small fixes piggy-backed onto this plan because they're low-risk and complementary:

1. **`MAX_ATTEMPTS = 4` constant unify.** Today duplicated in `DeadLetterRow.tsx` and `DeadLetterDetail.tsx`. Move to `frontend/src/types/Job.ts` as `JOB_MAX_ATTEMPTS`.
2. **Datetime localization.** Add `frontend/src/lib/datetime.ts` with `formatDateTime(iso, locale)` using `Intl.DateTimeFormat`. Apply in `LostSessionRow`, `DeadLetterRow`, `DeadLetterDetail`, `SnapshotCard`, `TrashRow`, `SessionCard`. Format: locale-short (e.g. `04/29/2026, 12:00 PM` in en, `29.04.2026, 12:00` in uk/ru).
3. **DeadLetterDetail post-Dismiss redirect.** After `dismiss.mutate(...)` succeeds, navigate back to `/dead-letter` (today the page just shows whatever cached data it has, which is wrong because the job is gone).
4. **Dead `*_disabled` locale keys.** Sweep en/uk/ru for keys ending in `_disabled` that no longer have any code referencing them. Delete them. Verify with `grep -r` before deleting.
5. **Lazy-load Metrics route.** `const Metrics = lazy(() => import("./pages/Metrics"))` + `<Suspense fallback={<Skeleton />}>` wrapper around its route. Keeps recharts off the initial chunk.

Lazy-load Help similarly — pure JSX, ~5 KB so impact is minimal but it's free wins.

### 2.5 Non-changes

- No new shadcn primitives beyond `chart` (which pulls recharts).
- No new query keys outside the metrics ones.
- No changes to existing widgets except wiring `formatDateTime` and the `JOB_MAX_ATTEMPTS` import.
- `<NoProjectsCallout>` keeps its CLI hint as fallback text, just adds the wizard CTA above it.

---

## 3. Data flow

### Onboarding

```
User → Onboarding form
  ↓ submit
useProjectCreate.mutate({ name, vault_root, cwd_patterns })
  ↓
POST /projects (creates + mounts atomically)
  ↓
onSuccess:
  - invalidateQueries(["projects"])
  - toast.success
  - navigate to /project/{name}
onError:
  - 409 → inline "name already exists"
  - 500 → red callout with err.detail
  - * → toast.error(extractApiError)
```

### Metrics

```
Period state (useState) → 3 hooks fire in parallel:
  - useUsageTimeline(period) → /metrics/usage/timeline?period=Nd
  - useUsageByProject(period) → /metrics/usage/by-project?period=Nd  (already exists, expand period arg)
  - useTopSessions(limit=10) → /metrics/usage/top-sessions?limit=10  (NEW)

Each refetchInterval: 60_000 (charts don't need 30s).
```

### Help

```
Pure render. useHealth() for version. Static i18n strings everywhere else.
```

---

## 4. New / changed files

**New:**
- `frontend/src/api/projects.api.ts` — extend with `createProject`, `patchProject`, `deleteProject`
- `frontend/src/api/metrics.api.ts` — extend with `getTimeline`, `getTopSessions`
- `frontend/src/types/UsageTimeline.ts` (new zod schema for timeline points)
- `frontend/src/types/TopSession.ts` (new zod schema)
- `frontend/src/hooks/useProjectCreate.ts`
- `frontend/src/hooks/useProjectPatch.ts` (kept for completeness; not used in this plan but matches pattern; **actually skip — YAGNI**)
- `frontend/src/hooks/useProjectDelete.ts` (same — **skip**)
- `frontend/src/hooks/useUsageTimeline.ts`
- `frontend/src/hooks/useTopSessions.ts`
- `frontend/src/lib/datetime.ts` (new helper)
- `frontend/src/pages/Onboarding.tsx`
- `frontend/src/pages/Metrics.tsx`
- `frontend/src/components/widgets/UsageTimelineChart.tsx`
- `frontend/src/components/widgets/UsageByProjectTable.tsx`
- `frontend/src/components/widgets/TopSessionsTable.tsx`
- `frontend/src/components/ui/chart.tsx` (shadcn-generated)
- ~10 new test files

**Modified:**
- `frontend/src/App.tsx` — wire 3 routes, lazy-load Metrics + Help
- `frontend/src/pages/Help.tsx` — full rewrite with 5 sections
- `frontend/src/components/widgets/NoProjectsCallout.tsx` — add "Create project" CTA above CLI hint
- `frontend/src/components/layout/ProjectSwitcher.tsx` — add `+ New project` menu item
- `frontend/src/components/widgets/{LostSessionRow,DeadLetterRow,SnapshotCard,TrashRow,SessionCard}.tsx` — replace raw ISO dates with `formatDateTime`
- `frontend/src/pages/DeadLetterDetail.tsx` — navigate back after Dismiss
- `frontend/src/types/Job.ts` — export `JOB_MAX_ATTEMPTS`
- `frontend/src/components/widgets/DeadLetterRow.tsx` + `frontend/src/pages/DeadLetterDetail.tsx` — use `JOB_MAX_ATTEMPTS`
- `frontend/public/locales/{en,uk,ru}.json` — add `onboarding.*`, `help.*`, `metrics.*` blocks; remove dead `*_disabled` keys
- `frontend/package.json` — add `recharts`

---

## 5. Translation keys (~80 new)

- `onboarding.*` — title, subtitle, name_label, name_hint, name_invalid, name_taken, vault_label, vault_hint, cwd_label, cwd_hint, advanced_toggle, submit, cancel, mount_failed_title, success_toast.
- `help.*` — title + 5 nested sections (`quickstart`, `concepts`, `workflows`, `troubleshooting`, `about`), each with `heading` + `body` (multi-paragraph) + per-card `card_*_title/body` keys (~3 cards per section).
- `metrics.*` — title, period_filter_label, period_7d/30d/90d, timeline_title, timeline_legend_input, timeline_legend_output, timeline_legend_sessions, timeline_empty, by_project_title, top_sessions_title, top_sessions_subtitle (e.g. "All-time top by tokens"), table column headers.
- `nav.create_project`, `no_projects.cta`.

UK/RU per established style.

---

## 6. New deps

`recharts@^2.x` (~95 KB gz). Pulls in `react-smooth`, `lodash-es`. Tree-shakes well.

`shadcn add chart` generates `frontend/src/components/ui/chart.tsx` — a thin wrapper around recharts components with theme integration (CSS variables for series colors). We use a subset (`<ChartContainer>`, `<ChartTooltip>`, `<ChartLegend>`).

---

## 7. Testing strategy

- **API mutation tests** for `createProject` (success path + 409 + 500 mapping).
- **Hook tests** for `useProjectCreate` (toast + invalidate + navigate behavior NOT tested here — that's component-level).
- **API query tests** for `getTimeline`, `getTopSessions` (zod parse, malformed payload rejection).
- **Onboarding form tests:** invalid name disables submit; valid name + path enables submit; 409 surfaces inline; 500 surfaces callout; success navigates to project view.
- **Metrics page tests:** mocks 3 endpoints, asserts chart container present, asserts table rows render. Charts are SVG so we can `getByText` on legend labels and table headers.
- **Help page tests:** smoke test that all 5 section anchors render with their headings.
- **Polish coverage:** `formatDateTime` unit tests; DeadLetterDetail-after-Dismiss navigation test.

Total new Vitest: ~30–40 tests on top of #14c's 150.

ESLint + tsc clean (allow 2 pre-existing shadcn warnings, plus possibly 1–2 new ones from chart.tsx — same `react-refresh/only-export-components` pattern).

---

## 8. Acceptance criteria

1. ✅ `/onboarding` route renders the wizard. Form validates name regex, hints required vault path, creates+mounts on submit.
2. ✅ Wizard surfaces 409/500 backend errors actionably (inline + callout); generic errors via toast.
3. ✅ Successful creation invalidates projects query and navigates to `/project/{name}`.
4. ✅ `<NoProjectsCallout>` and `<ProjectSwitcher>` both link to `/onboarding`.
5. ✅ `/help` renders 5 sections with sticky in-page nav. Version pulled from `useHealth()`.
6. ✅ `/metrics` renders period filter + timeline chart + by-project table + top sessions table.
7. ✅ Empty-data state shown when 0 vaults / 0 days. Chart axes don't bug out on empty arrays.
8. ✅ Top sessions clearly labeled as window-agnostic.
9. ✅ Datetimes across all widgets render via `formatDateTime` (locale-aware).
10. ✅ `JOB_MAX_ATTEMPTS` constant; no more duplicates.
11. ✅ DeadLetterDetail navigates back after Dismiss.
12. ✅ Dead `*_disabled` locale keys removed; `grep -r "_disabled"` returns only currently-used keys.
13. ✅ Metrics + Help routes are `React.lazy`-loaded; initial bundle stays under 285 KB gzip.
14. ✅ Vitest grows by ~30–40; all pass.
15. ✅ ESLint + tsc clean; backend pytest unchanged.

---

## 9. Risks

- **recharts bundle weight.** Even with lazy-loading, full recharts evaluation on first Metrics view is ~95 KB. Acceptable. Alternatives (visx, lightweight d3-only charts) are worse trade-offs for the surface area.
- **Onboarding wizard error messaging.** Backend 500 `mount_failed` is a generic error; we surface `detail` verbatim. Some details are admin-grade ("EBADF on /var/foo"). Tolerated — power users running this app are devs anyway.
- **Help content drift.** Hardcoded copy in i18n files becomes outdated. Mitigated by keeping it short and pointing to spec links in About.
- **Dead-locale-key sweep.** Risk of false positives (key referenced via dynamic `t(\`a.${variable}\`)`). Mitigation: only delete keys that grep finds as static literals nowhere.
- **Lazy-loading regression.** If `Suspense` boundary leaks routing context, tests might fail. Mitigation: wrap inside RouterProvider.

---

## 10. Out of scope / deferred

- Onboarding "first ingest" step.
- Markdown-driven Help (vs JSX).
- Cost projection charts.
- Code-split per-route beyond Metrics + Help.
- Dynamic theme colors for chart series.
- Period beyond `Nd` (`/metrics/usage?period=2w` etc.).
- Onboarding from-empty-vault detection (offer to scan / migrate).
- ProjectPatch / ProjectDelete UI (CLI only for now).

These all roll forward to later plans or stay CLI-only.

---

## 11. Spec coverage map

| § | Plan tasks |
|---|---|
| 2.1 Onboarding wizard | Tasks 1, 2, 3 (api+hook, form, callout/switcher integration) |
| 2.2 Help page | Task 9 |
| 2.3 Metrics page | Tasks 4, 5, 6, 7, 8 (api+types, hooks, chart, tables, page) |
| 2.4 Polish | Tasks 10–13 (datetime, MAX_ATTEMPTS, dismiss redirect, locale sweep, lazy-load) |
| 5 i18n | distributed per-task |
| 6 deps | Task 4 (shadcn add chart) |
| 8 ACs | Task 14 (final verification) |

---

(end of design)
