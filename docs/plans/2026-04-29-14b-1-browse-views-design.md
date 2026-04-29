# Plan #14b-1: Browse views (Pages, Sessions, Activity) — design

**Status:** DRAFT
**Date:** 2026-04-29
**Branch:** `feat/14b-1-browse-views`
**Predecessor:** Plan #14a (`60f30b3`, 2026-04-29)
**Successors:** #14b-2 (operational views) → #14c (mutations + editor) → #14d (onboarding + help + metrics)

---

## 1. Background and goals

### 1.1 Context

After Plan #14a the dashboard scaffold runs at `http://localhost:5757/`: TopBar + Sidebar + Overview project cards + ProjectView shell with 8 navigation tiles. Every per-project tile (`/project/{name}/{pages,sessions,activity,suggestions,trash,snapshots,health,settings}`) currently routes to a generic `<Placeholder>` component. The user can navigate but cannot read anything from inside a project.

### 1.2 Goal of #14b-1

Replace the Placeholder stubs for the 4 most-used "browse the brain" pages with working read-only UIs:

1. **Pages browser** (`/project/{name}/pages`) — list every wiki page under the vault with filters by type/flavor/status, sort, search, and a card view linking to Page detail.
2. **Page detail** (`/project/{name}/pages/{page_id}`) — render frontmatter (title, status, confidence bar, flavor tags, provenance), markdown body, backlinks panel, and an "Open in Obsidian" button.
3. **Sessions list + detail** (`/project/{name}/sessions` + `/project/{name}/sessions/{sid}`) — list ingested chats with status filter and timing/token metadata; detail page shows full session card.
4. **Activity Center** (`/project/{name}/activity` + `/project/{name}/activity/{id}`) — list operations grouped by day (Today / Yesterday / Earlier this week / Older), each entry shows op-type icon + summary + affected pages count + Detail link; detail page shows full entry with metadata + can-undo flag (undo button is `disabled` and points to "coming in #14c").

After #14b-1 the user can:

- Open a project, click "📚 Pages" → see the wiki contents with filters.
- Click any page card → see the rendered markdown + backlinks.
- Click "💬 Sessions" → see all ingested chats and per-chat token costs.
- Click "📜 Activity" → see what the daemon has been doing (ingest, lint autofix, ontology apply, manual edits, snapshots).

### 1.3 Non-goals (deferred)

- Mutations on pages (verify/archive/delete/edit) — **#14c**.
- Snapshot browser, Trash browser, Lost Sessions scanner, Suggestions panel, Failed Jobs (Dead-Letter), Health page — **#14b-2**.
- Onboarding wizard, full Help system, Metrics charts with recharts — **#14d**.
- Pagination / virtualization beyond the spec's basic "showing N of M" pattern — vaults of 200+ pages render fine; if it becomes a bottleneck add `react-virtual` later.
- Search inside page bodies — only title-search in #14b-1; full-text via spec's tiered query is its own future plan.
- Custom syntax highlighting for code blocks — `react-markdown` defaults are enough.
- Wiki-link navigation rendering inside markdown body (just clickable plain links to other pages) — full backlink graph traversal not required for MVP.

### 1.4 Spec alignment

| Spec | #14b-1 coverage |
|---|---|
| §11.1 frontend structure | Adds `pages/PagesBrowser.tsx`, `pages/PageDetail.tsx`, `pages/Sessions.tsx`, `pages/SessionDetail.tsx`, `pages/ActivityCenter.tsx`, `pages/ActivityDetail.tsx`. |
| §12.4 Pages Browser | Filter sidebar (type/flavor/status), grid card view, sort by updated/created/title, view toggle Grid/Table → **grid only in #14b-1**, table view deferred. |
| §12.5 Page Detail | Header (type, status, confidence bar, flavor tags, provenance), markdown body, backlinks panel, Open-in-Obsidian, Copy wikilink. **Edit/Verify/Delete buttons render disabled with "→ #14c" hint.** |
| §12.6 Activity Center | Group by day (Today/Yesterday/3-7 days/Earlier/⚠ Needs attention). Each entry: timestamp, op-icon, summary, affected pages count, Detail. **Undo button disabled with "→ #14c" hint.** |

---

## 2. Architecture

### 2.1 Type / schema additions

New zod schemas in `frontend/src/types/`:

- **`WikiPage.ts`** — mirrors `claude_mnemos/core/models.py::WikiPageFrontmatter`:
  ```ts
  PageType = "entity" | "concept" | "source"
  PageStatus = "draft" | "reviewed" | "verified" | "stale" | "archived"
  PageFlavor = "pattern" | "mistake" | "decision" | "lesson" | "reference"
  WikiPageFrontmatterSchema = z.object({
    title, type, status, confidence (0..1),
    flavor[], sources[], related[],
    created (date), updated (date),
    provenance: { extracted, inferred, ambiguous } | null,
    agent_written: bool,
    last_human_edit: datetime | null,
  })
  PageDetailSchema = z.object({ path, frontmatter, body: string })
  PageListSchema = z.object({ pages: string[] })           // just paths
  PageBacklinksSchema = z.object({ backlinks: string[] })
  ```

- **`Session.ts`** — mirrors `claude_mnemos/core/sessions.py::SessionView`:
  ```ts
  SessionStatus = "ingested" | "queued" | "running" | "failed" | "dead_letter"   // verify in code
  SessionViewSchema = z.object({
    session_id, status,
    transcript_path: string | null,
    ingested_at: datetime | null,
    model: string | null,
    input_tokens: number | null,
    output_tokens: number | null,
    raw_transcript_bytes: number | null,
    created_pages: string[],
    error: string | null,
  })
  SessionListSchema = z.object({ sessions: SessionView[], total: number })
  ```

- **`Activity.ts`** — mirrors `claude_mnemos/state/activity.py::ActivityEntry`:
  ```ts
  ActivityOperationType = "ingest" | "lint_autofix" | "ontology_apply" | "manual_patch" | "manual_soft_delete" | "manual_restore" | "human_edit_detected" | ...    // verify
  ActivityStatus = "success" | "partial" | "failed"     // verify
  ActivityEntrySchema = z.object({
    id, timestamp,
    operation_type: ActivityOperationType,
    status: ActivityStatus,
    snapshot_path: string | null,
    can_undo: bool,
    undone: bool,
    undone_at: datetime | null,
    undone_by_id: string | null,
    affected_pages: string[],
    metadata: Record<string, unknown>,
  })
  ActivityListSchema = z.object({ entries: ActivityEntry[], total: number })
  ```

Each schema validates at runtime via `.parse()`. **Important:** before merging, verify enum literal values against the backend Pydantic models (Plan #14a had a critical schema mismatch caught only at code review). The implementer's first task in this plan is to grep the backend models and ensure all enums/fields match exactly.

### 2.2 API layer

New `frontend/src/api/` modules:

```ts
// pages.api.ts
export async function listPages(project: string): Promise<string[]>
export async function getPage(project: string, pageRef: string): Promise<PageDetail>
export async function getPageBacklinks(project: string, pageRef: string): Promise<string[]>

// sessions.api.ts (project-scoped per β2)
export async function listSessions(project: string, opts?: { status?, limit? }): Promise<{ sessions: SessionView[]; total: number }>
export async function getSession(project: string, sid: string): Promise<SessionView>

// activity.api.ts
export async function listActivity(project: string, opts?: { limit?: number; offset?: number }): Promise<{ entries: ActivityEntry[]; total: number }>
export async function getActivity(project: string, opId: string): Promise<ActivityEntry>
```

URLs use the existing β2 path-prefix contract. `pageRef` is a relative path like `wiki/concepts/foo.md` and must be passed unencoded — FastAPI's `{page_ref:path}` matches multi-segment refs.

### 2.3 Hook layer

New `frontend/src/hooks/`:

```ts
usePages(project)              // 30s polling — list of paths
usePage(project, pageRef)      // 60s polling — full page
usePageBacklinks(project, pageRef)
useSessions(project, opts)     // 5s polling
useSession(project, sid)
useActivity(project, opts)     // 5s polling
useActivityEntry(project, opId)
```

For Pages browser filter-by-frontmatter: the list endpoint returns only paths. To filter by `type`/`flavor`/`status` we need each page's frontmatter. Option chosen: in `PagesBrowser.tsx` use `useQueries()` to **concurrent-fetch** detail for every path returned by `usePages`. For vaults <200 pages this is fast enough; 200+ → loading indicator stays visible until all complete; cards render incrementally as data arrives. Documented as a known perf trade-off; if it becomes a real problem we add a backend `GET /pages/{project}/index` endpoint that returns frontmatter for every page in one go (out of scope for #14b-1).

### 2.4 Routing changes

`frontend/src/App.tsx` already declares the routes; we just swap `<Placeholder>` for the real pages:

```tsx
{ path: "pages", element: <PagesBrowser /> },                // was Placeholder
{ path: "pages/:pageRef*", element: <PageDetail /> },        // was Placeholder, "*" splat to catch nested paths
{ path: "sessions", element: <Sessions /> },                 // was Placeholder
{ path: "sessions/:sid", element: <SessionDetail /> },       // NEW
{ path: "activity", element: <ActivityCenter /> },           // was Placeholder
{ path: "activity/:opId", element: <ActivityDetail /> },     // NEW
```

The `pages/:pageId` route from #14a becomes `pages/:pageRef*` (splat) so paths like `wiki/concepts/foo.md` are captured. react-router v7 splat syntax: `pages/*` and read `useParams<{ "*": string }>` then re-key as `pageRef`. (Or use `pages/:pageRef+` if available — verify in the implementer task.)

### 2.5 Component additions

```
frontend/src/components/
├── widgets/
│   ├── ConfidenceBar.tsx           # 4-segment bar with breakdown tooltip
│   ├── StatusBadge.tsx             # 5 page-status colours
│   ├── FlavorTags.tsx              # multi-tag display
│   ├── ProvenanceIndicator.tsx     # extracted/inferred/ambiguous %
│   ├── PageCard.tsx                # used by PagesBrowser
│   ├── SessionCard.tsx             # used by Sessions
│   └── ActivityRow.tsx             # used by ActivityCenter
├── filters/
│   ├── PageFilters.tsx             # sidebar: type/flavor/status checkboxes + sort + search
│   └── SessionFilters.tsx          # status select + limit
├── markdown/
│   └── MarkdownView.tsx            # wraps react-markdown with sane defaults
```

### 2.6 Translation keys

New keys added to `frontend/public/locales/{uk,ru,en}.json` under sections:

- `pages.*` — title, type/flavor/status filter labels, sort options, "Open in Obsidian", "Copy wikilink", "No pages found", "Loading frontmatter...", confidence/provenance tooltips, "Edit"/"Verify"/"Delete" buttons (disabled — point at #14c), backlinks panel.
- `sessions.*` — list headers (session_id, model, tokens, status, ingested_at), status enum labels, "No sessions yet" empty state, "Created pages" header.
- `activity.*` — operation_type labels (ingest, lint_autofix, ontology_apply, manual_patch, manual_soft_delete, manual_restore, human_edit_detected, ...), day-group headers (today/yesterday/this_week/older/needs_attention), "Undo" button (disabled — points at #14c), affected pages count.

~80–100 new keys per locale. Implementer's first task verifies exact backend enum strings.

### 2.7 Data flow

**Pages browser:**

```
usePages(project) → ["wiki/x/foo.md", "wiki/y/bar.md", ...]
          ↓
useQueries(map paths to usePage) → [{path, frontmatter, body}, ...]
          ↓
PageFilters reads ui state (type/flavor/status/sort/search) from local component state
          ↓
filtered & sorted → PageCard grid
```

**Page detail:**

```
useParams() → { name, pageRef }
          ↓
usePage(name, pageRef)        → renders frontmatter header + body
usePageBacklinks(name, pageRef) → renders backlinks panel
```

**Sessions list:**

```
useSessions(project, { status, limit }) → render SessionCard list
```

Filter UI uses local component state, not Zustand (per-page filters are not persisted across navigations).

**Activity Center:**

```
useActivity(project, { limit: 200 }) → entries
          ↓
groupByDay(entries) → { today: [...], yesterday: [...], thisWeek: [...], older: [...], needsAttention: [...] }
          ↓
render section per group
```

`needsAttention` group surfaces entries with `status === "failed"` OR `operation_type === "ingest"` AND `metadata.quarantined === true`. Sorted by timestamp desc within each group.

### 2.8 Markdown rendering

`react-markdown` v9 + `remark-gfm` for tables/footnotes. No custom syntax highlight in #14b-1. Wikilinks rendering: in v1 we render `[[foo]]` as plain text (not links). The Page detail page has its own backlinks panel + Open-in-Obsidian, so users can navigate via filesystem; in-page wiki link parsing is deferred (it's nice-to-have).

`MarkdownView` is a thin wrapper:

```tsx
<MarkdownView body={page.body} />
  → react-markdown with remark-gfm, prose-styled (Tailwind typography plugin if installed; else custom CSS in globals.css for h1/h2/h3/code/pre).
```

### 2.9 Backend changes

**None.** All endpoints needed (`GET /pages/{project}`, `GET /pages/{project}/{page_ref:path}`, `GET /pages/{project}/{page_ref:path}/backlinks`, `GET /sessions/{project}` + detail, `GET /activity/{project}` + detail) already shipped in #13b-β2. This sub-plan is pure frontend.

The only backend touchpoint is verifying enum string values during schema definition — read-only inspection.

---

## 3. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Schema mismatch (recurring problem from #14a) | Implementer's first task: grep backend models for ALL field names and enum values used by #14b-1 schemas; document exact match. Add at least one round-trip test that boots a real `MnemosDaemon` + small fake vault and parses every relevant response. |
| Concurrent useQueries on N pages slow / batches network | Hard-cap useQueries to N=200; if list returns more, render only the first 200 with a "showing 200 of M, refine filters" hint. Add backend aggregated endpoint in a future plan if it becomes routine. |
| react-router splat for nested page paths | Verify v7 syntax in Task 1 of plan; fallback to `*` wildcard + `useParams<{ "*": string }>`. |
| Markdown XSS via page bodies | react-markdown defaults are safe (no raw HTML); do **not** enable `rehype-raw`. |
| Activity entry's `metadata` is `Record<string, unknown>` — schema can't validate fully | Use `z.record(z.string(), z.unknown())` (already pattern from β2 work). Render metadata as JSON pretty-print with collapsible accordion. |
| Unknown enum values from backend (forward compat) | zod `.catch()` for enums OR use `z.string()` and switch in components; pick one (recommend `z.string()` for `operation_type` since list will grow over time). |

---

## 4. Acceptance criteria

#14b-1 is done when:

1. ✅ All 4 page types render real data:
   - Pages browser → list of paths with frontmatter, filters work, click opens detail.
   - Page detail → frontmatter header + markdown body + backlinks panel, "Open in Obsidian" link.
   - Sessions list → SessionCard list with status filter and tokens columns; click opens detail.
   - Activity Center → entries grouped by day, each row has op-icon + summary + count.
2. ✅ Per-project routes working: `/project/{name}/pages`, `/pages/:pageRef*`, `/sessions`, `/sessions/:sid`, `/activity`, `/activity/:opId`.
3. ✅ Unknown project (e.g. `/project/ghost/pages`) → graceful 404 page (reuse `UnknownProject` from #14a).
4. ✅ Unknown page / unknown session / unknown activity ID → in-page "not found" message with link back.
5. ✅ Empty states have friendly copy in UK/RU/EN.
6. ✅ `WikiPageFrontmatter`/`SessionView`/`ActivityEntry` zod schemas exactly match backend Pydantic models — verified by at least one round-trip test against a real `TestClient(create_app())` with a fake vault.
7. ✅ All buttons that imply mutation are disabled with a tooltip pointing at the relevant future plan (#14c for edit/verify/delete/undo).
8. ✅ Vitest suite green: ~30+ new tests on top of #14a's 35.
9. ✅ ESLint + tsc strict clean.
10. ✅ Backend ruff + mypy stay clean (no backend code touched, but verification kept).
11. ✅ Manual smoke: build frontend → run daemon with at least one populated vault → click through every #14b-1 page in browser, including localised UI.

---

## 5. Open questions resolved by this design

| Question | Decision | Rationale |
|---|---|---|
| Decompose #14b? | Yes — into #14b-1 (browse) + #14b-2 (operational). | Each ~12-15 tasks; comparable to #14a. Browse is most-used UX → ship first. |
| Card view or table view in Pages browser? | **Card grid only** in #14b-1; table view deferred. | YAGNI — cards work for typical N≤200. Spec lists both as toggleable; we ship the more design-heavy one first. |
| Wikilinks rendered as links in body? | No — plain text in #14b-1. | Backlinks panel covers cross-page nav; in-body link parsing is a polish item. |
| `useQueries` concurrent fetch vs aggregated endpoint? | useQueries for #14b-1; aggregated endpoint deferred. | Backend already done; ship UI first; optimise if measured. |
| Activity grouping logic? | Today / Yesterday / Earlier this week / Older / ⚠ Needs attention. | Spec §12.6 verbatim. |
| In-page Edit/Verify/Delete/Undo controls in #14b-1? | Render **disabled** with tooltips pointing at #14c. | Sets the surface contract early; buttons exist day-one and are wired in #14c. |
| Mutation hooks in #14b-1? | Not added — only read hooks. | YAGNI; #14c brings them. |
| Tests scope? | RTL component tests for each page (loading/empty/populated/unknown) + schema parse tests; no e2e. | Mirrors #14a's approach. |

---

## 6. Out of scope (deferred)

- Trash, Snapshots, Lost Sessions, Suggestions, Failed Jobs (Dead-Letter), Health page → **#14b-2** (next sub-plan).
- All mutations (page edit/verify/archive/delete/undo + snapshot create/restore + ontology approve + lint run) → **#14c**.
- Onboarding wizard + 5-section Help + full Metrics page with recharts → **#14d**.
- Dark mode / theme switcher → **#14d** polish.
- Wikilink-in-body rendering as React `<Link>`s → potentially **#14d** polish or own micro-plan.
- Backend aggregated `/pages/{project}/index` endpoint → measure first.
- Tablet/mobile responsive layouts → never (v1 non-goal).
