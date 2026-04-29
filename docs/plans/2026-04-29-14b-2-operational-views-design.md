# Plan #14b-2: Operational views (Trash, Snapshots, Lost Sessions, Suggestions, Failed Jobs, Health) — design

**Status:** DRAFT
**Date:** 2026-04-29
**Branch:** `feat/14b-2-operational-views`
**Predecessor:** Plan #14b-1 (`c0f4929`, 2026-04-29)
**Successors:** #14c (mutations + page editor) → #14d (onboarding + help + metrics polish)

---

## 1. Background and goals

### 1.1 Context

After #14b-1 the dashboard renders 6 working pages: Pages browser, Page detail, Sessions list/detail, Activity Center + detail. The remaining 6 placeholder routes from #14a are the **operational views** — pages the user reaches less frequently but that surface vault state, recovery options, and daemon-level diagnostics:

- `/project/{name}/trash` — soft-deleted pages waiting for restore or permanent delete.
- `/project/{name}/snapshots` — pre-op + daily + manual backups.
- `/project/{name}/suggestions` — Ontology suggestions (merge/rename/delete page) needing HITL review.
- `/lost-sessions` — cross-vault scanner for transcripts not yet ingested.
- `/project/{name}/health` — per-vault detail expansion of the global `/health` endpoint.
- (no separate route for Failed Jobs — embedded as a section inside `/project/{name}/health` per spec §12.7, AND a global `/dead-letter` cross-vault list reachable via the alerts bell tooltip).

### 1.2 Goal of #14b-2

Replace the 5 remaining Placeholder routes with read-only working pages, and add 1 new global route (`/dead-letter`) for cross-vault Failed Jobs view. After #14b-2 the user can:

- Navigate to Trash, see all soft-deleted pages with deleted_at timestamps and restore-blocked reasons; restore/permanent-delete actions are visible but disabled (→ #14c).
- Navigate to Snapshots, see all `.backups/` entries grouped by kind (pre-op/daily/manual) with timestamps, sizes, and labels; restore/delete buttons disabled (→ #14c).
- Navigate to Lost Sessions, see the cross-vault scan with project_name attribution, SHA, transcript path, mtime; import/ignore buttons disabled (→ #14c).
- Navigate to Suggestions, see all pending ontology suggestions with operation type, affected pages, confidence, body (markdown); approve/reject/defer buttons disabled (→ #14c).
- Navigate to Failed Jobs (Dead-Letter) global list, see cross-vault failures with per-job project_name + reason + retry count; per-job detail with full traceback; retry/dismiss disabled (→ #14c).
- Navigate to per-project Health page, see vault-level detail: watchdog status + per-status job counts + scheduler jobs registered for this vault.

All write actions render `disabled` with `→ #14c` tooltips, mirroring the #14b-1 pattern.

### 1.3 Non-goals (deferred)

- All mutations (trash restore, snapshot restore, lost-session import, ontology approve, dead-letter retry, undo) — **#14c**.
- Onboarding wizard, full Help system, full Metrics charts — **#14d**.
- Pagination beyond simple page-1 limit (cross-vault Failed Jobs uses backend `limit=50` default; if vault piles up DLQ items, `?limit=200` is enough until #14d adds proper pagination UX).
- Search/filter inside Trash/Snapshots/Suggestions beyond the spec-mandated minimum (status filter for Suggestions, kind filter for Snapshots).
- Custom syntax highlighting in Suggestion bodies — react-markdown defaults sufficient.

### 1.4 Spec alignment

| Spec | #14b-2 coverage |
|---|---|
| §12.7 Failed Jobs (Dead-Letter) | Global list at `/dead-letter` with retry/dismiss/View-details buttons (all disabled in #14b-2). |
| §12 Project View → 11 разделов | Trash, Snapshots, Suggestions, Health all rendered as full pages (placeholder stubs from #14a replaced). |
| §13.2 Lost Sessions wizard | Cross-vault scanner is the read-only side; import via UI is #14c territory. |

---

## 2. Architecture

### 2.1 Type / schema additions

New zod schemas in `frontend/src/types/`:

- **`Trash.ts`** — mirrors `claude_mnemos/core/trash.py::TrashEntry`:
  ```ts
  TrashEntrySchema = z.object({
    trash_id: z.string(),
    deleted_at: z.string(),                    // datetime
    original_path: z.string().nullable(),
    operation_type: z.string().nullable(),
    page_basename: z.string().nullable(),
    restorable: z.boolean(),
    restore_blocked_reason: z.string().nullable(),
  })
  TrashListResponseSchema = z.object({
    entries: z.array(TrashEntrySchema),
    total: z.number().int().nonnegative(),
  })
  ```

- **`Snapshot.ts`** — mirrors `claude_mnemos/core/snapshots.py::SnapshotInfo`:
  ```ts
  SnapshotKindSchema = z.enum(["pre-op", "daily", "manual"])
  SnapshotInfoSchema = z.object({
    name: z.string(),
    kind: SnapshotKindSchema,
    timestamp: z.string(),                     // datetime
    op_id: z.string().nullable(),
    op_type: z.string().nullable(),
    label: z.string().nullable(),
    size_bytes: z.number().int().nonnegative().default(0),
    path: z.string(),                          // posix-style relative-to-vault
  })
  SnapshotListResponseSchema = z.object({
    snapshots: z.array(SnapshotInfoSchema),
  })
  ```
  Note: `/snapshots/{project}` does NOT return `total` — only `snapshots[]`.

- **`LostSession.ts`** — mirrors `claude_mnemos/core/lost_sessions.py::LostSession` plus the `project_name` field that the cross-vault route adds:
  ```ts
  LostSessionSchema = z.object({
    session_id: z.string(),
    transcript_path: z.string(),
    sha: z.string(),
    size_bytes: z.number().int().nonnegative(),
    mtime: z.string(),                         // datetime
    project_name: z.string(),                  // injected by route
  })
  LostSessionListResponseSchema = z.object({
    sessions: z.array(LostSessionSchema),
    total: z.number().int().nonnegative(),
  })
  ```

- **`Suggestion.ts`** — mirrors `claude_mnemos/state/ontology.py::SuggestionFrontmatter` + `Suggestion`:
  ```ts
  SuggestionStatusSchema = z.enum(["pending", "approved", "rejected", "deferred"])
  SuggestionOperationSchema = z.enum(["merge_entities", "rename_entity", "delete_page"])
  SuggestionFrontmatterSchema = z.object({
    id: z.string(),
    created: z.string(),
    operation: SuggestionOperationSchema,
    status: SuggestionStatusSchema,
    confidence: z.number().min(0).max(1),
    affected_pages: z.array(z.string()).min(1),
    proposed_target: z.string().nullable(),
    reason: z.string(),
    applied_at: z.string().nullable(),
    applied_op_id: z.string().nullable(),
  })
  SuggestionSchema = z.object({
    frontmatter: SuggestionFrontmatterSchema,
    body: z.string(),
  })
  SuggestionListResponseSchema = z.object({
    suggestions: z.array(SuggestionSchema),
    total: z.number().int().nonnegative(),
  })
  ```

- **`Job.ts`** — mirrors `claude_mnemos/state/jobs.py::Job` + the `project_name` injection on cross-vault `/dead-letter` routes:
  ```ts
  JobKindSchema = z.string()                   // open enum: "ingest" + future kinds
  JobStatusSchema = z.enum([
    "queued", "running", "succeeded", "failed", "cancelled", "dead_letter",
  ])
  JobSchema = z.object({
    id: z.string(),
    kind: JobKindSchema,
    payload: z.record(z.string(), z.unknown()),
    status: JobStatusSchema,
    attempt: z.number().int().nonnegative(),
    next_attempt_at: z.string(),
    created_at: z.string(),
    started_at: z.string().nullable(),
    finished_at: z.string().nullable(),
    error: z.string().nullable(),
    error_traceback: z.string().nullable(),
    project_name: z.string(),                  // injected by /dead-letter routes
  })
  DeadLetterListResponseSchema = z.object({
    jobs: z.array(JobSchema),
  })
  ```
  Note: `/dead-letter` returns just `{ jobs }`, no `total`. `/dead-letter/{id}` returns a single job. Verify exact `JobStatus` values against backend `state/jobs.py::JobStatus` Literal — the implementer's first task per-domain is to grep and confirm; if backend has, e.g., `"cancelled"` not in the enum, drop it from the schema.

**Reused from earlier plans:**
- `Health.ts`, `VaultHealth` (already in #14a) — Health page expands existing data.
- `WikiPageFrontmatter`, `ActivityEntry` from #14b-1 — not needed here.

### 2.2 API layer

New `frontend/src/api/` modules:

```ts
// trash.api.ts
export async function listTrash(project: string): Promise<{ entries: TrashEntry[]; total: number }>

// snapshots.api.ts
export async function listSnapshots(project: string): Promise<SnapshotInfo[]>

// lost_sessions.api.ts
export async function listLostSessions(): Promise<{ sessions: LostSession[]; total: number }>

// suggestions.api.ts (ontology suggestions, project-scoped)
export async function listSuggestions(project: string, opts?: { status?: string }): Promise<{ suggestions: Suggestion[]; total: number }>

// dead_letter.api.ts
export async function listDeadLetter(opts?: { limit?: number; offset?: number }): Promise<Job[]>
export async function getDeadLetter(jobId: string): Promise<Job>
```

### 2.3 Hook layer

```ts
useTrash(project)              // 5s poll
useSnapshots(project)          // 30s poll (slow-changing)
useLostSessions()              // 30s poll (synchronous scan is expensive, don't hammer)
useSuggestions(project, opts)  // 5s poll
useDeadLetter(opts)            // 5s poll
useDeadLetterEntry(jobId)      // 5s poll
```

`useHealth` already exists from #14a; no new hook for the Health page — it just consumes the existing one.

### 2.4 Routing

`frontend/src/App.tsx` updates: replace 5 Placeholder routes with real components, add 1 new global route:

```tsx
{ path: "trash", element: <Trash /> },                                 // was Placeholder
{ path: "snapshots", element: <Snapshots /> },                         // was Placeholder
{ path: "suggestions", element: <Suggestions /> },                     // was Placeholder
{ path: "health", element: <Health /> },                               // was Placeholder

// Top-level (already declared as Placeholder in #14a):
{ path: "lost-sessions", element: <LostSessions /> },                  // was Placeholder

// NEW top-level:
{ path: "dead-letter", element: <DeadLetter /> },
{ path: "dead-letter/:jobId", element: <DeadLetterDetail /> },
```

### 2.5 Component additions

```
frontend/src/components/
├── widgets/
│   ├── TrashRow.tsx
│   ├── SnapshotCard.tsx
│   ├── LostSessionRow.tsx
│   ├── SuggestionCard.tsx
│   ├── DeadLetterRow.tsx
│   ├── ProjectBadge.tsx              # small chip with project name (used in cross-vault rows)
│   └── KindBadge.tsx                 # small chip for snapshot kind / suggestion operation
├── filters/
│   ├── SnapshotFilters.tsx           # kind filter (pre-op | daily | manual | all)
│   └── SuggestionFilters.tsx         # status filter (pending | all | approved | rejected | deferred)
```

### 2.6 Pages

```
frontend/src/pages/
├── Trash.tsx                  # /project/:name/trash
├── Snapshots.tsx              # /project/:name/snapshots
├── Suggestions.tsx            # /project/:name/suggestions
├── Health.tsx                 # /project/:name/health
├── LostSessions.tsx           # /lost-sessions  (cross-vault, no :name in URL)
├── DeadLetter.tsx             # /dead-letter
└── DeadLetterDetail.tsx       # /dead-letter/:jobId
```

### 2.7 Translation keys

New keys added to `frontend/public/locales/{uk,ru,en}.json` under top-level sections:

- `trash.*` — title, list/empty/loading, restore/permanent-delete (disabled labels), restore_blocked, "deleted at", restore-blocked reasons.
- `snapshots.*` — kind labels (pre-op/daily/manual), filters, label/op_id/op_type, size formatted, "no snapshots", restore/delete (disabled).
- `lost_sessions.*` — title, scan-all (button — disabled? actually the read-only `/lost-sessions/scan` POST is a refetch trigger, NOT a mutation; we can wire it as a refetch action on the page, since it just invalidates the cache and rescans), per-row import/ignore (disabled), columns (project, sha truncated, size, mtime).
  - **Decision:** `Scan` button IS active in #14b-2 — it just triggers a refetch (POSTs to `/lost-sessions/scan`). It's not a "mutation" in the wiki-data sense; it's a server-side cache invalidation that refreshes the list. Document as the one exception.
- `suggestions.*` — title, status labels, operation labels (merge_entities/rename_entity/delete_page), confidence label, affected_pages count, proposed_target, reason, body header, approve/reject/defer (all disabled).
- `dead_letter.*` — title, columns (project, kind, attempt, finished_at, error message), retry/dismiss (disabled), per-detail traceback header, "no failed jobs".
- `health.*` — vault watchdog status (running/down), job counts, scheduler jobs panel header, alerts count, "vault not mounted".

~120 new keys per locale.

### 2.8 Page-by-page detail

#### `Trash.tsx`

Layout: list of rows, each row shows:
- `page_basename` (or `original_path` fallback) as a monospace label.
- `deleted_at` formatted as relative time.
- `operation_type` (chip, lowercase like `"manual_delete"`).
- `restorable` indicator (✓ green / ✗ red); when not restorable, show `restore_blocked_reason` muted.
- Disabled buttons: "Restore" + "Delete permanently".

Empty state: friendly "Trash is empty" copy.

#### `Snapshots.tsx`

Layout: filter bar (kind: all/pre-op/daily/manual) + grid of `<SnapshotCard>`.

Each card shows:
- `kind` badge (pre-op/daily/manual color-coded).
- `name` as file-like header.
- `timestamp` formatted.
- `op_id` + `op_type` (when present, for pre-op snapshots).
- `label` (when present).
- `size_bytes` formatted as KB/MB.
- Disabled buttons: "Restore" + "Delete".

Empty state: "No snapshots yet — daily snapshots will appear after midnight UTC".

#### `Suggestions.tsx`

Layout: status filter (default `pending`; options `pending | approved | rejected | deferred | all`) + list of `<SuggestionCard>`.

Each card:
- `frontmatter.id` (monospace).
- `frontmatter.operation` badge.
- `frontmatter.status` badge (5 colors).
- `frontmatter.confidence` via `<ConfidenceBar>` (already in #14b-1).
- `frontmatter.affected_pages` listed as page links (using `pageHref`).
- `frontmatter.proposed_target` (when present, e.g. for rename target).
- `frontmatter.reason` shown as italics.
- `body` rendered via `<MarkdownView>`.
- Disabled buttons: "Approve" + "Reject" + "Defer".

Empty state: "No pending suggestions".

#### `LostSessions.tsx`

Layout: header with `Scan` button (active — triggers `apiClient.post("/lost-sessions/scan")` then `queryClient.invalidateQueries(["lost-sessions"])`) + list of `<LostSessionRow>`.

Each row:
- `<ProjectBadge>` showing `project_name`.
- `session_id` truncated.
- `sha` truncated to first 8 chars.
- `size_bytes` formatted.
- `mtime` formatted.
- `transcript_path` as path tooltip on hover.
- Disabled buttons: "Import" + "Ignore".

Empty state: "All transcripts are accounted for. No lost sessions."

DaemonDownAlert if `/lost-sessions` errors (cross-vault, no project context, just like #14a Overview).

#### `DeadLetter.tsx`

Layout: list of `<DeadLetterRow>` rows, sorted by `finished_at` desc.

Each row:
- `<ProjectBadge>` showing `project_name`.
- `kind` chip.
- `attempt` count (e.g. "Attempt 4/4").
- `finished_at` formatted.
- `error` message (truncated to 1 line, full on hover).
- Disabled buttons: "Retry" + "Dismiss".
- Click row → navigates to `/dead-letter/:jobId`.

Empty state: "No failed jobs. Daemon is healthy."

#### `DeadLetterDetail.tsx`

Header: project + job_id + status + finished_at.

Body:
- Definition list: kind, attempts, created_at, started_at, finished_at, payload (JSON pretty).
- Error message (full).
- `error_traceback` rendered in `<pre>` with monospace + scrollable.
- Disabled buttons: "Retry" + "Dismiss".

Not-found state: friendly link back to `/dead-letter`.

#### `Health.tsx`

Layout: per-project page (uses `useParams<{ name }>`).

Reads `useHealth()` (already from #14a) and selects `vaults[name]`. Shows:
- Watchdog status (running/down with colored badge).
- Job counts (queued/running/dead_letter — three stat cards).
- Scheduler jobs filtered to this vault: `health.scheduler_jobs.filter(j => j.id.endsWith(`:${name}`))` rendered as a table (id, next_run_time, trigger).
- Total alerts count (from `/health` global; vault attribution requires future endpoint, out of scope).
- "Failed jobs in this project" count + link to `/dead-letter?project={name}` (filter param works in backend per #13b-β2).

If the project is not mounted (no entry in `health.vaults`), show "Vault not mounted" callout.

### 2.9 Sidebar updates

Sidebar's existing project nav already includes Trash, Snapshots, Health, Suggestions entries — they currently link to placeholder routes. After #14b-2 those links route to working pages.

Sidebar does NOT need a "Dead Letter" entry under per-project — it's a global cross-vault concern reachable via:
- The TopBar alerts bell (already routes to `/help` placeholder; we'll add `/dead-letter` to its menu in #14d, OR we can just add a small link in the per-project Health page).
- A direct URL.

For #14b-2 we add a small link from the Health page's "Failed jobs in this project" stat card to `/dead-letter?project={name}`. Top-level navigation to global `/dead-letter` is added to the sidebar's "global" section (alongside Metrics + Help).

**Sidebar additions:**
```
Global section (already has Metrics + Help):
+ Failed Jobs → /dead-letter   (icon: ⚠)
```

### 2.10 Backend changes

**None.** All endpoints needed already shipped in #13b-β2:
- `GET /trash/{project}` — `routes/trash.py`
- `GET /snapshots/{project}` — `routes/snapshots.py`
- `GET /lost-sessions` + `POST /lost-sessions/scan` — `routes/lost_sessions.py` (cross-vault)
- `GET /ontology/{project}/suggestions` — `routes/ontology.py`
- `GET /dead-letter` + `GET /dead-letter/{id}` — `routes/dead_letter.py` (cross-vault)
- `GET /health` — `routes/health.py` (already consumed by #14a; we just expand the UI)

Schema verification (per #14b-1 lesson) is mandatory at the start of each domain task — grep the Pydantic source and write the zod to match.

---

## 3. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Schema mismatches (recurring problem) | Each domain task starts with `grep -A 20 "^class XxxX"` against the relevant Pydantic file. Test asserts known-good shape. |
| Cross-vault routes (`/lost-sessions`, `/dead-letter`) return shapes that include `project_name` injected by the route — easy to miss when reading the underlying Pydantic | Verify against the route handler, not just the model. The plan task lists both files to grep. |
| `LostSessions` scan-button as the one active "non-readonly" interaction | Documented as a refetch trigger, not a vault mutation. Implementation calls `queryClient.invalidateQueries` after POST. |
| Bundle size growth (already at 252 KB gzip) | No new heavy deps in #14b-2 (everything reuses #14b-1 widgets + react-markdown). Bundle stays roughly flat. |
| Health page drift from `/health` shape if backend evolves | Reuse the existing `Health.ts` zod schema from #14a; fail-fast on parse error already implemented. |
| Pre-existing CLI test pollution (12 backend failures on main) | Out of scope; #14b-2 is pure frontend. |

---

## 4. Acceptance criteria

#14b-2 is done when:

1. ✅ All 7 routes render real data (Trash, Snapshots, LostSessions, Suggestions, DeadLetter, DeadLetterDetail, Health).
2. ✅ Per-project routes return 404 page for unknown projects (via `useProjects().data?.find`).
3. ✅ Each page has loading state, empty state, error state.
4. ✅ All cross-vault rows show `<ProjectBadge>` with the right `project_name`.
5. ✅ All mutation buttons (Restore/Delete/Approve/Reject/Defer/Retry/Dismiss/Import/Ignore) render `disabled` with `→ #14c` tooltips.
6. ✅ The single exception — `LostSessions` scan button — is active and triggers a refetch (uses `useMutation` + `invalidateQueries`, NOT a state-mutation hook).
7. ✅ Suggestions body renders via `<MarkdownView>` (XSS-safe).
8. ✅ DeadLetterDetail shows full traceback in a scrollable `<pre>`.
9. ✅ Health page shows per-vault detail; "Vault not mounted" callout for missing projects.
10. ✅ Sidebar "Failed Jobs" entry under Global section navigates to `/dead-letter`.
11. ✅ Schemas verified against backend Pydantic — round-trip tested in api-* tests.
12. ✅ Vitest suite green; ~30+ new tests on top of #14b-1's 86.
13. ✅ ESLint + tsc strict clean; pre-existing 2 shadcn warnings only.
14. ✅ Backend ruff/mypy unchanged (no backend code touched).
15. ✅ Manual smoke: build → daemon serves → click through every #14b-2 page.

---

## 5. Open questions resolved

| Question | Decision | Rationale |
|---|---|---|
| Single plan or decompose? | Single plan (~16-18 tasks, comparable to #14b-1) | All 6 pages share the same patterns; splitting adds overhead without isolation benefit. |
| `LostSessions.scan` button — disabled or active? | **Active.** | It's a server-side cache refetch, not a vault mutation. Pure read flow with side-effect on daemon's cache. |
| Failed Jobs as project-scoped or global? | Global `/dead-letter` route + sidebar entry; project Health page links to filtered `/dead-letter?project={name}` | Spec §12.7 puts Failed Jobs INSIDE Project View → Очередь, but the backend route is global cross-vault. Compromise: global URL + per-project filter via URL param. |
| Suggestion body markdown rendering? | Yes, via existing `<MarkdownView>` from #14b-1 | Suggestions describe vault changes that may include wikilinks / lists. Plain text is harder to read. |
| Confidence display on Suggestions? | Reuse `<ConfidenceBar>` from #14b-1 | Same widget for the same concept (LLM confidence). |
| Per-page filter state? | Local component `useState` (not Zustand) | Same pattern as #14b-1 PageFilters. |
| Pagination beyond default limit? | No — single-page render up to ~50 items per route | Trash/snapshots/suggestions/dead-letter typically small N; if a vault gets unwieldy add pagination in a polish plan. |
| "Кnd badge" color scheme | pre-op = amber, daily = blue, manual = emerald | Matches the conceptual difference: pre-op = automatic safety; daily = scheduled; manual = user-initiated. |

---

## 6. Out of scope (deferred)

- Mutations (restore/delete/approve/reject/defer/retry/dismiss/import/ignore) — **#14c**.
- 3-tier confirmation dialogs (Tier 1 simple / Tier 2 typed / Tier 3 typed + cooldown) — **#14c**.
- Onboarding wizard, Help system, full Metrics charts — **#14d**.
- Per-vault alerts attribution endpoint (currently `/health` returns global `alerts_count` only) — backend follow-up if needed.
- Pagination UI for cross-vault Failed Jobs / Lost Sessions when N > 50 — polish plan.
- Code-splitting `react-markdown` into Suggestions+PageDetail routes only — deferred polish.
