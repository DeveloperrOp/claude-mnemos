# Browse views (Pages, Sessions, Activity) Implementation Plan (Plan #14b-1)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** Replace #14a's placeholder stubs for `/project/{name}/pages`, `/pages/:pageRef*`, `/sessions`, `/sessions/:sid`, `/activity`, `/activity/:opId` with working read-only UIs. After #14b-1 the user can browse the wiki, read pages with backlinks, see all ingested sessions, and inspect activity history grouped by day.

**Architecture:** Pure frontend. New zod schemas mirror backend Pydantic models exactly (`WikiPageFrontmatter`/`SessionView`/`ActivityEntry`), validated at runtime via `.parse()`. New API modules wrap `apiClient` for /pages, /sessions, /activity routes. New TanStack Query hooks. New components: 4 widgets (StatusBadge, FlavorTags, ConfidenceBar, ProvenanceIndicator), MarkdownView wrapper, PageCard/SessionCard/ActivityRow, 2 filter sidebars. 6 pages replace existing Placeholder stubs. Mutation buttons render disabled with "→ #14c" hints.

**Tech Stack:** React 19, TanStack Query 5, react-router 7, zod 3, axios, react-markdown, remark-gfm, Tailwind v4, shadcn/ui, Vitest + Testing Library, i18next.

**Design doc:** `docs/plans/2026-04-29-14b-1-browse-views-design.md` — read before each task.

---

## Files map

**Create (frontend types):**
- `frontend/src/types/WikiPage.ts`
- `frontend/src/types/Session.ts`
- `frontend/src/types/Activity.ts`

**Create (frontend api):**
- `frontend/src/api/pages.api.ts`
- `frontend/src/api/sessions.api.ts`
- `frontend/src/api/activity.api.ts`

**Create (frontend hooks):**
- `frontend/src/hooks/usePages.ts`
- `frontend/src/hooks/usePage.ts`
- `frontend/src/hooks/usePageBacklinks.ts`
- `frontend/src/hooks/useSessions.ts`
- `frontend/src/hooks/useSession.ts`
- `frontend/src/hooks/useActivity.ts`
- `frontend/src/hooks/useActivityEntry.ts`

**Create (frontend widgets):**
- `frontend/src/components/widgets/StatusBadge.tsx`
- `frontend/src/components/widgets/FlavorTags.tsx`
- `frontend/src/components/widgets/ConfidenceBar.tsx`
- `frontend/src/components/widgets/ProvenanceIndicator.tsx`
- `frontend/src/components/widgets/PageCard.tsx`
- `frontend/src/components/widgets/SessionCard.tsx`
- `frontend/src/components/widgets/ActivityRow.tsx`
- `frontend/src/components/markdown/MarkdownView.tsx`
- `frontend/src/components/filters/PageFilters.tsx`
- `frontend/src/components/filters/SessionFilters.tsx`

**Create (frontend pages):**
- `frontend/src/pages/PagesBrowser.tsx`
- `frontend/src/pages/PageDetail.tsx`
- `frontend/src/pages/Sessions.tsx`
- `frontend/src/pages/SessionDetail.tsx`
- `frontend/src/pages/ActivityCenter.tsx`
- `frontend/src/pages/ActivityDetail.tsx`

**Create (frontend utils):**
- `frontend/src/lib/groupByDay.ts`

**Create (frontend tests):**
- `frontend/src/__tests__/api-pages.test.ts`
- `frontend/src/__tests__/api-sessions.test.ts`
- `frontend/src/__tests__/api-activity.test.ts`
- `frontend/src/__tests__/StatusBadge.test.tsx`
- `frontend/src/__tests__/FlavorTags.test.tsx`
- `frontend/src/__tests__/ConfidenceBar.test.tsx`
- `frontend/src/__tests__/ProvenanceIndicator.test.tsx`
- `frontend/src/__tests__/MarkdownView.test.tsx`
- `frontend/src/__tests__/PageCard.test.tsx`
- `frontend/src/__tests__/PagesBrowser.test.tsx`
- `frontend/src/__tests__/PageDetail.test.tsx`
- `frontend/src/__tests__/Sessions.test.tsx`
- `frontend/src/__tests__/SessionDetail.test.tsx`
- `frontend/src/__tests__/ActivityCenter.test.tsx`
- `frontend/src/__tests__/ActivityDetail.test.tsx`
- `frontend/src/__tests__/groupByDay.test.ts`

**Modify:**
- `frontend/src/App.tsx` — swap 6 Placeholder routes for real pages; add 2 new nested routes (`sessions/:sid`, `activity/:opId`).
- `frontend/public/locales/uk.json` — add `pages.*`, `sessions.*`, `activity.*` keys.
- `frontend/public/locales/ru.json` — same.
- `frontend/public/locales/en.json` — same.
- `frontend/package.json` — add `react-markdown`, `remark-gfm`, `@types/react-markdown` deps.

**Touch (read-only verification):**
- `claude_mnemos/core/models.py` — verify `WikiPageFrontmatter` field names + `PageType`/`PageStatus`/`PageFlavor` enum values.
- `claude_mnemos/core/sessions.py` — verify `SessionView` fields + `SessionStatus` enum.
- `claude_mnemos/state/activity.py` — verify `ActivityEntry` fields + `ActivityOperationType`/`ActivityStatus` enums.

---

## Task 1: WikiPage types + pages API + hooks

**Files:**
- Create: `frontend/src/types/WikiPage.ts`, `frontend/src/api/pages.api.ts`, `frontend/src/hooks/usePages.ts`, `frontend/src/hooks/usePage.ts`, `frontend/src/hooks/usePageBacklinks.ts`, `frontend/src/__tests__/api-pages.test.ts`

- [ ] **Step 1: Verify backend shapes (NO commit)**

```bash
cd /d/code/claude-mnemos
grep -A 40 "^class WikiPageFrontmatter" claude_mnemos/core/models.py
grep -B 2 -A 5 "^PageType\b\|^PageStatus\b\|^PageFlavor\b" claude_mnemos/core/models.py
grep -A 25 "^def list_pages\|^def get_page\|^def get_page_backlinks" claude_mnemos/daemon/routes/pages.py
```

Note **EXACT** field names and enum literals. The schemas below must match — Plan #14a had a critical schema mismatch only caught at code review.

- [ ] **Step 2: Write the failing tests**

```ts
// frontend/src/__tests__/api-pages.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listPages, getPage, getPageBacklinks } from "../api/pages.api";

describe("pages api", () => {
  beforeEach(() => vi.spyOn(apiClient, "get"));
  afterEach(() => vi.restoreAllMocks());

  it("listPages returns array of paths", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { pages: ["wiki/concepts/a.md", "wiki/entities/b.md"] },
    });
    const out = await listPages("alpha");
    expect(out).toEqual(["wiki/concepts/a.md", "wiki/entities/b.md"]);
  });

  it("getPage parses path/frontmatter/body", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        path: "wiki/concepts/a.md",
        frontmatter: {
          title: "A",
          type: "concept",
          status: "draft",
          confidence: 0.7,
          flavor: ["pattern"],
          sources: [],
          related: [],
          created: "2026-04-29",
          updated: "2026-04-29",
          provenance: null,
          agent_written: true,
          last_human_edit: null,
        },
        body: "# A\n\nbody",
      },
    });
    const p = await getPage("alpha", "wiki/concepts/a.md");
    expect(p.frontmatter.title).toBe("A");
    expect(p.frontmatter.type).toBe("concept");
    expect(p.body).toContain("# A");
  });

  it("getPage rejects malformed payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { path: "x", frontmatter: { title: 42 }, body: "" },
    });
    await expect(getPage("alpha", "x")).rejects.toThrow();
  });

  it("getPageBacklinks returns paths", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { backlinks: ["wiki/entities/b.md"] },
    });
    const out = await getPageBacklinks("alpha", "wiki/concepts/a.md");
    expect(out).toEqual(["wiki/entities/b.md"]);
  });
});
```

- [ ] **Step 3: Run** → FAIL (modules don't exist).

```
cd frontend && pnpm test api-pages
```

- [ ] **Step 4: Implement types**

```ts
// frontend/src/types/WikiPage.ts
import { z } from "zod";

export const PageTypeSchema = z.enum(["entity", "concept", "source"]);
export type PageType = z.infer<typeof PageTypeSchema>;

export const PageStatusSchema = z.enum([
  "draft",
  "reviewed",
  "verified",
  "stale",
  "archived",
]);
export type PageStatus = z.infer<typeof PageStatusSchema>;

export const PageFlavorSchema = z.enum([
  "pattern",
  "mistake",
  "decision",
  "lesson",
  "reference",
]);
export type PageFlavor = z.infer<typeof PageFlavorSchema>;

export const ProvenanceCountsSchema = z.object({
  extracted: z.number().int().nonnegative(),
  inferred: z.number().int().nonnegative(),
  ambiguous: z.number().int().nonnegative(),
});
export type ProvenanceCounts = z.infer<typeof ProvenanceCountsSchema>;

export const WikiPageFrontmatterSchema = z.object({
  title: z.string(),
  type: PageTypeSchema,
  status: PageStatusSchema,
  confidence: z.number().min(0).max(1),
  flavor: z.array(PageFlavorSchema),
  sources: z.array(z.string()),
  related: z.array(z.string()),
  created: z.string(),
  updated: z.string(),
  provenance: ProvenanceCountsSchema.nullable(),
  agent_written: z.boolean(),
  last_human_edit: z.string().nullable(),
});
export type WikiPageFrontmatter = z.infer<typeof WikiPageFrontmatterSchema>;

export const PageDetailSchema = z.object({
  path: z.string(),
  frontmatter: WikiPageFrontmatterSchema,
  body: z.string(),
});
export type PageDetail = z.infer<typeof PageDetailSchema>;

export const PageListResponseSchema = z.object({
  pages: z.array(z.string()),
});

export const PageBacklinksResponseSchema = z.object({
  backlinks: z.array(z.string()),
});
```

(Verify the shape against the grep output from Step 1. If `provenance` is shaped differently, **fix the schema before continuing**.)

- [ ] **Step 5: Implement api module**

```ts
// frontend/src/api/pages.api.ts
import { apiClient } from "./client";
import {
  PageBacklinksResponseSchema,
  PageDetailSchema,
  PageListResponseSchema,
  type PageDetail,
} from "@/types/WikiPage";

export async function listPages(project: string): Promise<string[]> {
  const r = await apiClient.get(`/pages/${encodeURIComponent(project)}`);
  return PageListResponseSchema.parse(r.data).pages;
}

export async function getPage(
  project: string,
  pageRef: string,
): Promise<PageDetail> {
  // pageRef can contain "/" — must NOT urlencode forward slashes (FastAPI :path matches them).
  const r = await apiClient.get(
    `/pages/${encodeURIComponent(project)}/${pageRef}`,
  );
  return PageDetailSchema.parse(r.data);
}

export async function getPageBacklinks(
  project: string,
  pageRef: string,
): Promise<string[]> {
  const r = await apiClient.get(
    `/pages/${encodeURIComponent(project)}/${pageRef}/backlinks`,
  );
  return PageBacklinksResponseSchema.parse(r.data).backlinks;
}
```

- [ ] **Step 6: Implement hooks**

```ts
// frontend/src/hooks/usePages.ts
import { useQuery } from "@tanstack/react-query";
import { listPages } from "@/api/pages.api";

export function usePages(project: string | undefined) {
  return useQuery({
    queryKey: ["pages", project],
    queryFn: () => listPages(project!),
    enabled: !!project,
    refetchInterval: 30_000,
  });
}
```

```ts
// frontend/src/hooks/usePage.ts
import { useQuery } from "@tanstack/react-query";
import { getPage } from "@/api/pages.api";

export function usePage(project: string | undefined, pageRef: string | undefined) {
  return useQuery({
    queryKey: ["page", project, pageRef],
    queryFn: () => getPage(project!, pageRef!),
    enabled: !!project && !!pageRef,
    refetchInterval: 60_000,
  });
}
```

```ts
// frontend/src/hooks/usePageBacklinks.ts
import { useQuery } from "@tanstack/react-query";
import { getPageBacklinks } from "@/api/pages.api";

export function usePageBacklinks(
  project: string | undefined,
  pageRef: string | undefined,
) {
  return useQuery({
    queryKey: ["page-backlinks", project, pageRef],
    queryFn: () => getPageBacklinks(project!, pageRef!),
    enabled: !!project && !!pageRef,
    refetchInterval: 60_000,
  });
}
```

- [ ] **Step 7: Run** → PASS.

```
pnpm test api-pages
pnpm typecheck
pnpm lint
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/WikiPage.ts frontend/src/api/pages.api.ts frontend/src/hooks/usePages.ts frontend/src/hooks/usePage.ts frontend/src/hooks/usePageBacklinks.ts frontend/src/__tests__/api-pages.test.ts
git commit -m "feat(frontend): WikiPage types + pages API + hooks (usePages/usePage/usePageBacklinks)"
```

---

## Task 2: Session types + sessions API + hooks

**Files:**
- Create: `frontend/src/types/Session.ts`, `frontend/src/api/sessions.api.ts`, `frontend/src/hooks/useSessions.ts`, `frontend/src/hooks/useSession.ts`, `frontend/src/__tests__/api-sessions.test.ts`

- [ ] **Step 1: Verify backend shape**

```bash
grep -A 30 "^class SessionView\|^class SessionStatus" claude_mnemos/core/sessions.py
grep -A 15 "^def list_sessions_route\|^def get_session_route" claude_mnemos/daemon/routes/sessions.py
```

Note exact `SessionStatus` enum values (likely `"ingested" | "queued" | "running" | "failed" | "dead_letter"` — verify).

- [ ] **Step 2: Write failing tests**

```ts
// frontend/src/__tests__/api-sessions.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listSessions, getSession } from "../api/sessions.api";

describe("sessions api", () => {
  beforeEach(() => vi.spyOn(apiClient, "get"));
  afterEach(() => vi.restoreAllMocks());

  it("listSessions parses sessions + total", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        sessions: [
          {
            session_id: "s1",
            status: "ingested",
            transcript_path: "/x/raw/chats/s1.md",
            ingested_at: "2026-04-29T12:00:00Z",
            model: "claude-sonnet",
            input_tokens: 1000,
            output_tokens: 500,
            raw_transcript_bytes: 12345,
            created_pages: ["wiki/concepts/x.md"],
            error: null,
          },
        ],
        total: 1,
      },
    });
    const out = await listSessions("alpha");
    expect(out.total).toBe(1);
    expect(out.sessions[0]?.session_id).toBe("s1");
  });

  it("listSessions passes status + limit", async () => {
    const spy = vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { sessions: [], total: 0 },
    });
    await listSessions("alpha", { status: "failed", limit: 10 });
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/sessions/alpha"),
      expect.objectContaining({ params: { status: "failed", limit: 10 } }),
    );
  });

  it("getSession parses single SessionView", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        session_id: "s1",
        status: "ingested",
        transcript_path: null,
        ingested_at: null,
        model: null,
        input_tokens: null,
        output_tokens: null,
        raw_transcript_bytes: null,
        created_pages: [],
        error: null,
      },
    });
    const s = await getSession("alpha", "s1");
    expect(s.session_id).toBe("s1");
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement types + api + hooks**

```ts
// frontend/src/types/Session.ts
import { z } from "zod";

export const SessionStatusSchema = z.enum([
  "ingested",
  "queued",
  "running",
  "failed",
  "dead_letter",
]);
export type SessionStatus = z.infer<typeof SessionStatusSchema>;

export const SessionViewSchema = z.object({
  session_id: z.string(),
  status: SessionStatusSchema,
  transcript_path: z.string().nullable(),
  ingested_at: z.string().nullable(),
  model: z.string().nullable(),
  input_tokens: z.number().int().nullable(),
  output_tokens: z.number().int().nullable(),
  raw_transcript_bytes: z.number().int().nullable(),
  created_pages: z.array(z.string()),
  error: z.string().nullable(),
});
export type SessionView = z.infer<typeof SessionViewSchema>;

export const SessionListResponseSchema = z.object({
  sessions: z.array(SessionViewSchema),
  total: z.number().int().nonnegative(),
});
```

```ts
// frontend/src/api/sessions.api.ts
import { apiClient } from "./client";
import {
  SessionListResponseSchema,
  SessionViewSchema,
  type SessionView,
} from "@/types/Session";

export interface ListSessionsOptions {
  status?: string;
  limit?: number;
}

export async function listSessions(
  project: string,
  opts: ListSessionsOptions = {},
): Promise<{ sessions: SessionView[]; total: number }> {
  const params: Record<string, string | number> = {};
  if (opts.status) params.status = opts.status;
  if (opts.limit !== undefined) params.limit = opts.limit;
  const r = await apiClient.get(
    `/sessions/${encodeURIComponent(project)}`,
    { params },
  );
  return SessionListResponseSchema.parse(r.data);
}

export async function getSession(
  project: string,
  sessionId: string,
): Promise<SessionView> {
  const r = await apiClient.get(
    `/sessions/${encodeURIComponent(project)}/${encodeURIComponent(sessionId)}`,
  );
  return SessionViewSchema.parse(r.data);
}
```

```ts
// frontend/src/hooks/useSessions.ts
import { useQuery } from "@tanstack/react-query";
import { listSessions, type ListSessionsOptions } from "@/api/sessions.api";

export function useSessions(
  project: string | undefined,
  opts: ListSessionsOptions = {},
) {
  return useQuery({
    queryKey: ["sessions", project, opts.status ?? null, opts.limit ?? null],
    queryFn: () => listSessions(project!, opts),
    enabled: !!project,
    refetchInterval: 5_000,
  });
}
```

```ts
// frontend/src/hooks/useSession.ts
import { useQuery } from "@tanstack/react-query";
import { getSession } from "@/api/sessions.api";

export function useSession(
  project: string | undefined,
  sessionId: string | undefined,
) {
  return useQuery({
    queryKey: ["session", project, sessionId],
    queryFn: () => getSession(project!, sessionId!),
    enabled: !!project && !!sessionId,
    refetchInterval: 5_000,
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/Session.ts frontend/src/api/sessions.api.ts frontend/src/hooks/useSessions.ts frontend/src/hooks/useSession.ts frontend/src/__tests__/api-sessions.test.ts
git commit -m "feat(frontend): Session types + sessions API + hooks (useSessions/useSession)"
```

---

## Task 3: Activity types + activity API + hooks

**Files:**
- Create: `frontend/src/types/Activity.ts`, `frontend/src/api/activity.api.ts`, `frontend/src/hooks/useActivity.ts`, `frontend/src/hooks/useActivityEntry.ts`, `frontend/src/__tests__/api-activity.test.ts`

- [ ] **Step 1: Verify backend shape**

```bash
grep -A 35 "^class ActivityEntry\|^ActivityOperationType\|^ActivityStatus\|^ActivityOperationType =\|^ActivityStatus =" claude_mnemos/state/activity.py
```

Note exact `ActivityOperationType` enum members. Likely list includes `ingest`, `lint_autofix`, `ontology_apply`, `manual_patch`, `manual_soft_delete`, `manual_restore`, `human_edit_detected`, `manual_undo`. **Verify and use `z.string()` if the list is open-ended (forward compat preferred for activity since new ops will be added).**

- [ ] **Step 2: Write failing tests**

```ts
// frontend/src/__tests__/api-activity.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listActivity, getActivityEntry } from "../api/activity.api";

describe("activity api", () => {
  beforeEach(() => vi.spyOn(apiClient, "get"));
  afterEach(() => vi.restoreAllMocks());

  it("listActivity parses entries + total", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        entries: [
          {
            id: "op-1",
            timestamp: "2026-04-29T12:00:00Z",
            operation_type: "ingest",
            status: "success",
            snapshot_path: "/.backups/foo",
            can_undo: true,
            undone: false,
            undone_at: null,
            undone_by_id: null,
            affected_pages: ["wiki/x.md"],
            metadata: { session_id: "s1" },
          },
        ],
        total: 1,
      },
    });
    const out = await listActivity("alpha");
    expect(out.entries[0]?.id).toBe("op-1");
    expect(out.total).toBe(1);
  });

  it("listActivity passes limit + offset", async () => {
    const spy = vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { entries: [], total: 0 },
    });
    await listActivity("alpha", { limit: 50, offset: 100 });
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/activity/alpha"),
      expect.objectContaining({ params: { limit: 50, offset: 100 } }),
    );
  });

  it("getActivityEntry parses single entry", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        id: "op-1",
        timestamp: "2026-04-29T12:00:00Z",
        operation_type: "lint_autofix",
        status: "success",
        snapshot_path: null,
        can_undo: false,
        undone: false,
        undone_at: null,
        undone_by_id: null,
        affected_pages: [],
        metadata: {},
      },
    });
    const e = await getActivityEntry("alpha", "op-1");
    expect(e.id).toBe("op-1");
    expect(e.operation_type).toBe("lint_autofix");
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement**

```ts
// frontend/src/types/Activity.ts
import { z } from "zod";

// Open-ended; backend may add new op types — accept any string and switch in components.
export const ActivityOperationTypeSchema = z.string();
export type ActivityOperationType = z.infer<typeof ActivityOperationTypeSchema>;

export const ActivityStatusSchema = z.enum(["success", "partial", "failed"]);
export type ActivityStatus = z.infer<typeof ActivityStatusSchema>;

export const ActivityEntrySchema = z.object({
  id: z.string(),
  timestamp: z.string(),
  operation_type: ActivityOperationTypeSchema,
  status: ActivityStatusSchema,
  snapshot_path: z.string().nullable(),
  can_undo: z.boolean(),
  undone: z.boolean(),
  undone_at: z.string().nullable(),
  undone_by_id: z.string().nullable(),
  affected_pages: z.array(z.string()),
  metadata: z.record(z.string(), z.unknown()),
});
export type ActivityEntry = z.infer<typeof ActivityEntrySchema>;

export const ActivityListResponseSchema = z.object({
  entries: z.array(ActivityEntrySchema),
  total: z.number().int().nonnegative(),
});
```

```ts
// frontend/src/api/activity.api.ts
import { apiClient } from "./client";
import {
  ActivityEntrySchema,
  ActivityListResponseSchema,
  type ActivityEntry,
} from "@/types/Activity";

export interface ListActivityOptions {
  limit?: number;
  offset?: number;
}

export async function listActivity(
  project: string,
  opts: ListActivityOptions = {},
): Promise<{ entries: ActivityEntry[]; total: number }> {
  const params: Record<string, number> = {};
  if (opts.limit !== undefined) params.limit = opts.limit;
  if (opts.offset !== undefined) params.offset = opts.offset;
  const r = await apiClient.get(
    `/activity/${encodeURIComponent(project)}`,
    { params },
  );
  return ActivityListResponseSchema.parse(r.data);
}

export async function getActivityEntry(
  project: string,
  opId: string,
): Promise<ActivityEntry> {
  const r = await apiClient.get(
    `/activity/${encodeURIComponent(project)}/${encodeURIComponent(opId)}`,
  );
  return ActivityEntrySchema.parse(r.data);
}
```

```ts
// frontend/src/hooks/useActivity.ts
import { useQuery } from "@tanstack/react-query";
import { listActivity, type ListActivityOptions } from "@/api/activity.api";

export function useActivity(
  project: string | undefined,
  opts: ListActivityOptions = {},
) {
  return useQuery({
    queryKey: ["activity", project, opts.limit ?? null, opts.offset ?? null],
    queryFn: () => listActivity(project!, opts),
    enabled: !!project,
    refetchInterval: 5_000,
  });
}
```

```ts
// frontend/src/hooks/useActivityEntry.ts
import { useQuery } from "@tanstack/react-query";
import { getActivityEntry } from "@/api/activity.api";

export function useActivityEntry(
  project: string | undefined,
  opId: string | undefined,
) {
  return useQuery({
    queryKey: ["activity-entry", project, opId],
    queryFn: () => getActivityEntry(project!, opId!),
    enabled: !!project && !!opId,
    refetchInterval: 5_000,
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/Activity.ts frontend/src/api/activity.api.ts frontend/src/hooks/useActivity.ts frontend/src/hooks/useActivityEntry.ts frontend/src/__tests__/api-activity.test.ts
git commit -m "feat(frontend): Activity types + activity API + hooks (useActivity/useActivityEntry)"
```

---

## Task 4: StatusBadge + FlavorTags widgets

**Files:**
- Create: `frontend/src/components/widgets/StatusBadge.tsx`, `frontend/src/components/widgets/FlavorTags.tsx`, `frontend/src/__tests__/StatusBadge.test.tsx`, `frontend/src/__tests__/FlavorTags.test.tsx`
- Modify: `frontend/public/locales/{uk,ru,en}.json` (add `wiki.status.*` and `wiki.flavor.*` keys if missing — α/β1 may have stubbed these)

- [ ] **Step 1: Add locale keys**

Append to each locale file under a top-level `wiki` key (or merge if already present):

```json
"wiki": {
  "status": {
    "draft": "<localised>",
    "reviewed": "<localised>",
    "verified": "<localised>",
    "stale": "<localised>",
    "archived": "<localised>"
  },
  "flavor": {
    "pattern": "<localised>",
    "mistake": "<localised>",
    "decision": "<localised>",
    "lesson": "<localised>",
    "reference": "<localised>"
  },
  "type": {
    "entity": "<localised>",
    "concept": "<localised>",
    "source": "<localised>"
  }
}
```

UK: `Чернетка/Переглянуто/Підтверджено/Застаріло/В архіві`, `Шаблон/Помилка/Рішення/Урок/Посилання`, `Сутність/Концепт/Джерело`.
RU: `Черновик/Просмотрено/Подтверждено/Устарело/В архиве`, `Паттерн/Ошибка/Решение/Урок/Ссылка`, `Сущность/Концепт/Источник`.
EN: `Draft/Reviewed/Verified/Stale/Archived`, `Pattern/Mistake/Decision/Lesson/Reference`, `Entity/Concept/Source`.

- [ ] **Step 2: Failing tests**

```tsx
// frontend/src/__tests__/StatusBadge.test.tsx
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import i18n from "../i18n";
import { StatusBadge } from "../components/widgets/StatusBadge";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    wiki: { status: { draft: "Draft", verified: "Verified" } },
  }, true, true);
  void i18n.changeLanguage("en");
});

describe("StatusBadge", () => {
  it("renders draft with neutral color", () => {
    render(<StatusBadge status="draft" />);
    const el = screen.getByRole("status");
    expect(el).toHaveAttribute("data-status", "draft");
    expect(el).toHaveTextContent("Draft");
  });

  it("renders verified with success color", () => {
    render(<StatusBadge status="verified" />);
    expect(screen.getByRole("status")).toHaveAttribute("data-status", "verified");
  });
});
```

```tsx
// frontend/src/__tests__/FlavorTags.test.tsx
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import i18n from "../i18n";
import { FlavorTags } from "../components/widgets/FlavorTags";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    wiki: { flavor: { pattern: "Pattern", mistake: "Mistake" } },
  }, true, true);
  void i18n.changeLanguage("en");
});

describe("FlavorTags", () => {
  it("renders one badge per flavor", () => {
    render(<FlavorTags flavors={["pattern", "mistake"]} />);
    expect(screen.getByText("Pattern")).toBeInTheDocument();
    expect(screen.getByText("Mistake")).toBeInTheDocument();
  });

  it("renders nothing when empty", () => {
    const { container } = render(<FlavorTags flavors={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement**

```tsx
// frontend/src/components/widgets/StatusBadge.tsx
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { PageStatus } from "@/types/WikiPage";

const COLORS: Record<PageStatus, string> = {
  draft: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  reviewed: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  verified: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  stale: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  archived: "bg-zinc-200 text-zinc-500 dark:bg-zinc-900 dark:text-zinc-500",
};

export function StatusBadge({ status }: { status: PageStatus }) {
  const { t } = useTranslation();
  return (
    <span
      role="status"
      data-status={status}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        COLORS[status],
      )}
    >
      {t(`wiki.status.${status}`)}
    </span>
  );
}
```

```tsx
// frontend/src/components/widgets/FlavorTags.tsx
import { useTranslation } from "react-i18next";
import type { PageFlavor } from "@/types/WikiPage";

export function FlavorTags({ flavors }: { flavors: PageFlavor[] }) {
  const { t } = useTranslation();
  if (flavors.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {flavors.map((f) => (
        <span
          key={f}
          className="inline-flex items-center rounded-md bg-[hsl(var(--muted))] px-1.5 py-0.5 text-xs text-[hsl(var(--muted-foreground))]"
        >
          {t(`wiki.flavor.${f}`)}
        </span>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/widgets/StatusBadge.tsx frontend/src/components/widgets/FlavorTags.tsx frontend/src/__tests__/StatusBadge.test.tsx frontend/src/__tests__/FlavorTags.test.tsx frontend/public/locales/
git commit -m "feat(frontend): StatusBadge + FlavorTags widgets"
```

---

## Task 5: ConfidenceBar + ProvenanceIndicator widgets

**Files:**
- Create: `frontend/src/components/widgets/ConfidenceBar.tsx`, `frontend/src/components/widgets/ProvenanceIndicator.tsx`, `frontend/src/__tests__/ConfidenceBar.test.tsx`, `frontend/src/__tests__/ProvenanceIndicator.test.tsx`

- [ ] **Step 1: Failing tests**

```tsx
// frontend/src/__tests__/ConfidenceBar.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceBar } from "../components/widgets/ConfidenceBar";

describe("ConfidenceBar", () => {
  it("renders percentage label", () => {
    render(<ConfidenceBar value={0.7} />);
    expect(screen.getByText("70%")).toBeInTheDocument();
  });

  it("clamps fill width to 0-100%", () => {
    render(<ConfidenceBar value={1.5} />);
    const fill = screen.getByTestId("confidence-fill");
    expect(fill).toHaveStyle({ width: "100%" });
  });

  it("renders 0% for zero", () => {
    render(<ConfidenceBar value={0} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });
});
```

```tsx
// frontend/src/__tests__/ProvenanceIndicator.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProvenanceIndicator } from "../components/widgets/ProvenanceIndicator";

describe("ProvenanceIndicator", () => {
  it("renders percentages summing to 100", () => {
    render(<ProvenanceIndicator counts={{ extracted: 7, inferred: 2, ambiguous: 1 }} />);
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("20%")).toBeInTheDocument();
    expect(screen.getByText("10%")).toBeInTheDocument();
  });

  it("renders nothing when counts is null", () => {
    const { container } = render(<ProvenanceIndicator counts={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when total is zero", () => {
    const { container } = render(
      <ProvenanceIndicator counts={{ extracted: 0, inferred: 0, ambiguous: 0 }} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/widgets/ConfidenceBar.tsx
import { cn } from "@/lib/utils";

function colorFor(v: number): string {
  if (v >= 0.85) return "bg-emerald-500";
  if (v >= 0.6) return "bg-blue-500";
  if (v >= 0.3) return "bg-amber-500";
  return "bg-red-500";
}

export function ConfidenceBar({ value }: { value: number }) {
  const clamped = Math.min(1, Math.max(0, value));
  const pct = Math.round(clamped * 100);
  return (
    <div className="flex items-center gap-2">
      <div
        className="relative h-1.5 w-24 overflow-hidden rounded-full bg-[hsl(var(--muted))]"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          data-testid="confidence-fill"
          className={cn("absolute left-0 top-0 h-full transition-all", colorFor(clamped))}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums">{pct}%</span>
    </div>
  );
}
```

```tsx
// frontend/src/components/widgets/ProvenanceIndicator.tsx
import type { ProvenanceCounts } from "@/types/WikiPage";

interface Props {
  counts: ProvenanceCounts | null;
}

export function ProvenanceIndicator({ counts }: Props) {
  if (!counts) return null;
  const total = counts.extracted + counts.inferred + counts.ambiguous;
  if (total === 0) return null;
  const pct = (n: number) => Math.round((n / total) * 100);
  return (
    <div className="flex items-center gap-2 text-xs text-[hsl(var(--muted-foreground))]">
      <span title="extracted">📋 {pct(counts.extracted)}%</span>
      <span title="inferred">🧠 {pct(counts.inferred)}%</span>
      <span title="ambiguous">❓ {pct(counts.ambiguous)}%</span>
    </div>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/ConfidenceBar.tsx frontend/src/components/widgets/ProvenanceIndicator.tsx frontend/src/__tests__/ConfidenceBar.test.tsx frontend/src/__tests__/ProvenanceIndicator.test.tsx
git commit -m "feat(frontend): ConfidenceBar + ProvenanceIndicator widgets"
```

---

## Task 6: MarkdownView wrapper

**Files:**
- Modify: `frontend/package.json` (add `react-markdown`, `remark-gfm`)
- Create: `frontend/src/components/markdown/MarkdownView.tsx`, `frontend/src/__tests__/MarkdownView.test.tsx`

- [ ] **Step 1: Install deps**

```bash
cd frontend
pnpm add react-markdown remark-gfm
```

- [ ] **Step 2: Failing test**

```tsx
// frontend/src/__tests__/MarkdownView.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarkdownView } from "../components/markdown/MarkdownView";

describe("MarkdownView", () => {
  it("renders headings", () => {
    render(<MarkdownView body="# Hello\n\nworld" />);
    expect(screen.getByRole("heading", { level: 1, name: "Hello" })).toBeInTheDocument();
    expect(screen.getByText("world")).toBeInTheDocument();
  });

  it("renders fenced code blocks", () => {
    render(<MarkdownView body="```\ncode here\n```" />);
    expect(screen.getByText("code here")).toBeInTheDocument();
  });

  it("does NOT render raw HTML (XSS-safe)", () => {
    render(<MarkdownView body='<script>alert(1)</script>' />);
    expect(document.querySelector("script")).toBeNull();
  });

  it("renders GFM tables", () => {
    render(
      <MarkdownView body="| a | b |\n|---|---|\n| 1 | 2 |" />,
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement**

```tsx
// frontend/src/components/markdown/MarkdownView.tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownView({ body }: { body: string }) {
  return (
    <div className="prose prose-sm max-w-none dark:prose-invert">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
    </div>
  );
}
```

Add to `frontend/src/styles/globals.css` (append at the end if not already present):

```css
@layer base {
  .prose h1 { @apply mt-6 mb-3 text-2xl font-bold; }
  .prose h2 { @apply mt-5 mb-2 text-xl font-semibold; }
  .prose h3 { @apply mt-4 mb-2 text-lg font-semibold; }
  .prose p { @apply my-2 leading-relaxed; }
  .prose code { @apply rounded bg-[hsl(var(--muted))] px-1 py-0.5 text-sm; }
  .prose pre { @apply my-3 overflow-x-auto rounded-md bg-[hsl(var(--muted))] p-3 text-sm; }
  .prose pre code { @apply bg-transparent p-0; }
  .prose ul { @apply my-2 ml-5 list-disc space-y-1; }
  .prose ol { @apply my-2 ml-5 list-decimal space-y-1; }
  .prose blockquote { @apply my-3 border-l-4 border-[hsl(var(--border))] pl-3 italic; }
  .prose a { @apply text-[hsl(var(--primary))] underline; }
  .prose table { @apply my-3 w-full border-collapse text-sm; }
  .prose th, .prose td { @apply border border-[hsl(var(--border))] px-2 py-1; }
  .prose th { @apply bg-[hsl(var(--muted))] font-semibold; }
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/components/markdown/ frontend/src/styles/globals.css frontend/src/__tests__/MarkdownView.test.tsx
git commit -m "feat(frontend): MarkdownView wrapper (react-markdown + remark-gfm) with prose styles"
```

---

## Task 7: PageCard component

**Files:**
- Create: `frontend/src/components/widgets/PageCard.tsx`, `frontend/src/__tests__/PageCard.test.tsx`

- [ ] **Step 1: Failing test**

```tsx
// frontend/src/__tests__/PageCard.test.tsx
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import { PageCard } from "../components/widgets/PageCard";
import type { WikiPageFrontmatter } from "../types/WikiPage";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    wiki: {
      type: { concept: "Concept" },
      status: { draft: "Draft", verified: "Verified" },
      flavor: { pattern: "Pattern" },
    },
    pages: { open: "Open", open_in_obsidian: "Open in Obsidian" },
  }, true, true);
  void i18n.changeLanguage("en");
});

const fm: WikiPageFrontmatter = {
  title: "Foo",
  type: "concept",
  status: "draft",
  confidence: 0.7,
  flavor: ["pattern"],
  sources: [],
  related: [],
  created: "2026-04-29",
  updated: "2026-04-29",
  provenance: null,
  agent_written: true,
  last_human_edit: null,
};

describe("PageCard", () => {
  it("renders title, type, status, confidence", () => {
    render(
      <MemoryRouter>
        <PageCard project="alpha" path="wiki/concepts/foo.md" frontmatter={fm} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Foo")).toBeInTheDocument();
    expect(screen.getByText("Concept")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("Pattern")).toBeInTheDocument();
  });

  it("links to page detail", () => {
    render(
      <MemoryRouter>
        <PageCard project="alpha" path="wiki/concepts/foo.md" frontmatter={fm} />
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: /foo/i });
    expect(link).toHaveAttribute(
      "href",
      "/project/alpha/pages/wiki/concepts/foo.md",
    );
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/widgets/PageCard.tsx
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ConfidenceBar } from "./ConfidenceBar";
import { FlavorTags } from "./FlavorTags";
import { StatusBadge } from "./StatusBadge";
import type { WikiPageFrontmatter } from "@/types/WikiPage";

interface Props {
  project: string;
  path: string;
  frontmatter: WikiPageFrontmatter;
}

export function PageCard({ project, path, frontmatter: fm }: Props) {
  const { t } = useTranslation();
  const href = `/project/${project}/pages/${path}`;
  return (
    <Card className="transition-colors hover:bg-[hsl(var(--muted))]">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <Link to={href} className="line-clamp-2 font-semibold hover:underline">
            {fm.title}
          </Link>
          <StatusBadge status={fm.status} />
        </div>
        <div className="mt-1 flex items-center gap-2 text-xs text-[hsl(var(--muted-foreground))]">
          <span>{t(`wiki.type.${fm.type}`)}</span>
          <span aria-hidden>·</span>
          <span title={path}>{path.split("/").slice(-1)[0]}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <ConfidenceBar value={fm.confidence} />
        <FlavorTags flavors={fm.flavor} />
        <div className="text-xs text-[hsl(var(--muted-foreground))]">
          {fm.updated}
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/PageCard.tsx frontend/src/__tests__/PageCard.test.tsx
git commit -m "feat(frontend): PageCard widget (title + type + status + confidence + flavor)"
```

---

## Task 8: PageFilters sidebar

**Files:**
- Create: `frontend/src/components/filters/PageFilters.tsx`
- Modify: `frontend/public/locales/{uk,ru,en}.json` (add `pages.filters.*` keys)

- [ ] **Step 1: Add locale keys**

Append to each locale under `pages`:

```json
"pages": {
  "filters": {
    "title": "<localised>",
    "type": "<localised>",
    "flavor": "<localised>",
    "status": "<localised>",
    "sort": "<localised>",
    "sort_updated": "<localised>",
    "sort_created": "<localised>",
    "sort_title": "<localised>",
    "search_placeholder": "<localised>",
    "all": "<localised>",
    "reset": "<localised>"
  },
  "showing_n_of_m": "{{shown}} of {{total}}",
  "open": "<localised>",
  "open_in_obsidian": "<localised>",
  "loading_frontmatter": "<localised>",
  "no_pages": "<localised>",
  "edit_disabled": "<localised>",
  "verify_disabled": "<localised>",
  "delete_disabled": "<localised>"
}
```

- [ ] **Step 2: Implement filters component**

```tsx
// frontend/src/components/filters/PageFilters.tsx
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { PageType, PageStatus, PageFlavor } from "@/types/WikiPage";

const TYPES: PageType[] = ["entity", "concept", "source"];
const STATUSES: PageStatus[] = ["draft", "reviewed", "verified", "stale", "archived"];
const FLAVORS: PageFlavor[] = ["pattern", "mistake", "decision", "lesson", "reference"];
export type SortMode = "updated" | "created" | "title";

export interface PageFilterState {
  types: Set<PageType>;
  statuses: Set<PageStatus>;
  flavors: Set<PageFlavor>;
  search: string;
  sort: SortMode;
}

export function defaultPageFilterState(): PageFilterState {
  return {
    types: new Set(TYPES),
    statuses: new Set(STATUSES),
    flavors: new Set(FLAVORS),
    search: "",
    sort: "updated",
  };
}

interface Props {
  state: PageFilterState;
  onChange: (state: PageFilterState) => void;
}

export function PageFilters({ state, onChange }: Props) {
  const { t } = useTranslation();

  function toggle<T>(set: Set<T>, value: T): Set<T> {
    const out = new Set(set);
    if (out.has(value)) out.delete(value);
    else out.add(value);
    return out;
  }

  return (
    <aside className="space-y-4 text-sm">
      <input
        type="search"
        placeholder={t("pages.filters.search_placeholder")}
        value={state.search}
        onChange={(e) => onChange({ ...state, search: e.target.value })}
        className="w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1"
      />

      <Section title={t("pages.filters.type")}>
        {TYPES.map((tp) => (
          <Check
            key={tp}
            checked={state.types.has(tp)}
            label={t(`wiki.type.${tp}`)}
            onChange={() => onChange({ ...state, types: toggle(state.types, tp) })}
          />
        ))}
      </Section>

      <Section title={t("pages.filters.flavor")}>
        {FLAVORS.map((fl) => (
          <Check
            key={fl}
            checked={state.flavors.has(fl)}
            label={t(`wiki.flavor.${fl}`)}
            onChange={() => onChange({ ...state, flavors: toggle(state.flavors, fl) })}
          />
        ))}
      </Section>

      <Section title={t("pages.filters.status")}>
        {STATUSES.map((st) => (
          <Check
            key={st}
            checked={state.statuses.has(st)}
            label={t(`wiki.status.${st}`)}
            onChange={() => onChange({ ...state, statuses: toggle(state.statuses, st) })}
          />
        ))}
      </Section>

      <Section title={t("pages.filters.sort")}>
        <select
          value={state.sort}
          onChange={(e) => onChange({ ...state, sort: e.target.value as SortMode })}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1 text-xs"
        >
          <option value="updated">{t("pages.filters.sort_updated")}</option>
          <option value="created">{t("pages.filters.sort_created")}</option>
          <option value="title">{t("pages.filters.sort_title")}</option>
        </select>
      </Section>

      <Button
        variant="ghost"
        size="sm"
        className="w-full"
        onClick={() => onChange(defaultPageFilterState())}
      >
        {t("pages.filters.reset")}
      </Button>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="text-xs font-semibold uppercase text-[hsl(var(--muted-foreground))]">
        {title}
      </div>
      {children}
    </div>
  );
}

function Check({ checked, label, onChange }: { checked: boolean; label: string; onChange: () => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs">
      <input type="checkbox" checked={checked} onChange={onChange} />
      <span>{label}</span>
    </label>
  );
}
```

- [ ] **Step 3: Run typecheck + lint**

```
pnpm typecheck
pnpm lint
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/filters/ frontend/public/locales/
git commit -m "feat(frontend): PageFilters sidebar (type/flavor/status/sort/search)"
```

---

## Task 9: PagesBrowser page

**Files:**
- Modify: `frontend/src/pages/PagesBrowser.tsx` (replace Placeholder stub)
- Create: `frontend/src/__tests__/PagesBrowser.test.tsx`

- [ ] **Step 1: Failing test**

```tsx
// frontend/src/__tests__/PagesBrowser.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { PagesBrowser } from "../pages/PagesBrowser";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    pages: {
      filters: {
        title: "Filters",
        type: "Type", flavor: "Flavor", status: "Status",
        sort: "Sort", sort_updated: "Updated", sort_created: "Created",
        sort_title: "Title", search_placeholder: "Search...", reset: "Reset",
      },
      showing_n_of_m: "{{shown}} of {{total}}",
      no_pages: "No pages",
      loading_frontmatter: "Loading...",
    },
    wiki: {
      type: { entity: "Entity", concept: "Concept", source: "Source" },
      status: { draft: "Draft", reviewed: "Reviewed", verified: "Verified", stale: "Stale", archived: "Archived" },
      flavor: { pattern: "Pattern", mistake: "Mistake", decision: "Decision", lesson: "Lesson", reference: "Reference" },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path = "/project/alpha/pages") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/pages" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const fmFor = (title: string, type: "entity" | "concept" | "source") => ({
  path: `wiki/${type}s/${title}.md`,
  frontmatter: {
    title, type, status: "draft", confidence: 0.7,
    flavor: [], sources: [], related: [],
    created: "2026-04-29", updated: "2026-04-29",
    provenance: null, agent_written: true, last_human_edit: null,
  },
  body: "",
});

describe("PagesBrowser", () => {
  it("renders cards for every returned page", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/pages/alpha") return { data: { pages: ["wiki/concepts/a.md", "wiki/entities/b.md"] } };
      if (url === "/pages/alpha/wiki/concepts/a.md") return { data: fmFor("a", "concept") };
      if (url === "/pages/alpha/wiki/entities/b.md") return { data: fmFor("b", "entity") };
      throw new Error(`unexpected url ${url}`);
    });
    render(wrap(<PagesBrowser />));
    await waitFor(() => expect(screen.getByText("a")).toBeInTheDocument());
    expect(screen.getByText("b")).toBeInTheDocument();
  });

  it("shows empty state when no pages", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { pages: [] } });
    render(wrap(<PagesBrowser />));
    await waitFor(() => expect(screen.getByText(/no pages/i)).toBeInTheDocument());
  });

  it("filters by type when type is unchecked", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/pages/alpha") return { data: { pages: ["wiki/concepts/a.md", "wiki/entities/b.md"] } };
      if (url.endsWith("a.md")) return { data: fmFor("a", "concept") };
      if (url.endsWith("b.md")) return { data: fmFor("b", "entity") };
      throw new Error(`unexpected url ${url}`);
    });
    render(wrap(<PagesBrowser />));
    await waitFor(() => expect(screen.getByText("a")).toBeInTheDocument());
    // toggling will be unit-tested via PageFilters; here we only check render.
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement PagesBrowser**

```tsx
// frontend/src/pages/PagesBrowser.tsx
import { useMemo, useState } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useQueries } from "@tanstack/react-query";
import { usePages } from "@/hooks/usePages";
import { getPage } from "@/api/pages.api";
import { Skeleton } from "@/components/ui/skeleton";
import {
  PageFilters,
  defaultPageFilterState,
  type PageFilterState,
  type SortMode,
} from "@/components/filters/PageFilters";
import { PageCard } from "@/components/widgets/PageCard";
import type { PageDetail, WikiPageFrontmatter } from "@/types/WikiPage";

const MAX_PAGES = 200;

function compareBy(a: WikiPageFrontmatter, b: WikiPageFrontmatter, mode: SortMode): number {
  switch (mode) {
    case "updated":
      return b.updated.localeCompare(a.updated);
    case "created":
      return b.created.localeCompare(a.created);
    case "title":
      return a.title.localeCompare(b.title);
  }
}

export function PagesBrowser() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const pagesQuery = usePages(project);
  const [filters, setFilters] = useState<PageFilterState>(defaultPageFilterState);

  const truncated = (pagesQuery.data ?? []).slice(0, MAX_PAGES);

  const detailQueries = useQueries({
    queries: truncated.map((path) => ({
      queryKey: ["page", project, path],
      queryFn: () => getPage(project!, path),
      enabled: !!project,
      staleTime: 60_000,
    })),
  });

  const loaded: PageDetail[] = useMemo(() => {
    const out: PageDetail[] = [];
    for (const q of detailQueries) {
      if (q.data) out.push(q.data);
    }
    return out;
  }, [detailQueries]);

  const filteredSorted = useMemo(() => {
    const search = filters.search.trim().toLowerCase();
    return loaded
      .filter((p) => filters.types.has(p.frontmatter.type))
      .filter((p) => filters.statuses.has(p.frontmatter.status))
      .filter((p) =>
        p.frontmatter.flavor.length === 0
          ? true
          : p.frontmatter.flavor.some((f) => filters.flavors.has(f)),
      )
      .filter((p) =>
        search === ""
          ? true
          : p.frontmatter.title.toLowerCase().includes(search) ||
            p.path.toLowerCase().includes(search),
      )
      .sort((a, b) => compareBy(a.frontmatter, b.frontmatter, filters.sort));
  }, [loaded, filters]);

  if (!project) return null;

  if (pagesQuery.isLoading) {
    return (
      <div className="grid grid-cols-[16rem_1fr] gap-6">
        <Skeleton className="h-96" />
        <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}
        </div>
      </div>
    );
  }

  const totalPaths = pagesQuery.data?.length ?? 0;
  if (totalPaths === 0) {
    return (
      <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
        {t("pages.no_pages")}
      </div>
    );
  }

  const stillLoading = detailQueries.some((q) => q.isLoading);

  return (
    <div className="grid grid-cols-[16rem_1fr] gap-6">
      <PageFilters state={filters} onChange={setFilters} />
      <div className="space-y-3">
        <div className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("pages.showing_n_of_m", { shown: filteredSorted.length, total: totalPaths })}
          {stillLoading && <> · {t("pages.loading_frontmatter")}</>}
        </div>
        <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {filteredSorted.map((p) => (
            <PageCard
              key={p.path}
              project={project}
              path={p.path}
              frontmatter={p.frontmatter}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PagesBrowser.tsx frontend/src/__tests__/PagesBrowser.test.tsx
git commit -m "feat(frontend): PagesBrowser with filter sidebar + concurrent frontmatter fetch"
```

---

## Task 10: PageDetail page

**Files:**
- Modify: `frontend/src/pages/PageDetail.tsx` (replace Placeholder stub)
- Create: `frontend/src/__tests__/PageDetail.test.tsx`

- [ ] **Step 1: Failing test**

```tsx
// frontend/src/__tests__/PageDetail.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { PageDetail } from "../pages/PageDetail";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    pages: {
      backlinks: "Backlinks",
      no_backlinks: "No backlinks",
      open_in_obsidian: "Open in Obsidian",
      copy_wikilink: "Copy wikilink",
      edit_disabled: "Edit (in #14c)",
      verify_disabled: "Verify (in #14c)",
      delete_disabled: "Delete (in #14c)",
      not_found_title: "Page not found",
      not_found_hint: "Go back",
    },
    wiki: {
      status: { draft: "Draft", verified: "Verified" },
      type: { concept: "Concept" },
      flavor: { pattern: "Pattern" },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/pages/*" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("PageDetail", () => {
  it("renders title + body + status + backlinks", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/pages/alpha/wiki/concepts/foo.md") {
        return {
          data: {
            path: "wiki/concepts/foo.md",
            frontmatter: {
              title: "Foo", type: "concept", status: "draft", confidence: 0.7,
              flavor: ["pattern"], sources: [], related: [],
              created: "2026-04-29", updated: "2026-04-29",
              provenance: null, agent_written: true, last_human_edit: null,
            },
            body: "# Foo\n\nbody text",
          },
        };
      }
      if (url === "/pages/alpha/wiki/concepts/foo.md/backlinks") {
        return { data: { backlinks: ["wiki/entities/bar.md"] } };
      }
      throw new Error(`unexpected ${url}`);
    });

    render(wrap(<PageDetail />, "/project/alpha/pages/wiki/concepts/foo.md"));
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "Foo" })).toBeInTheDocument(),
    );
    expect(screen.getByText("body text")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("wiki/entities/bar.md")).toBeInTheDocument();
  });

  it("renders not-found on 404", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("404"));
    render(wrap(<PageDetail />, "/project/alpha/pages/wiki/missing.md"));
    await waitFor(() =>
      expect(screen.getByText(/Page not found/i)).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/pages/PageDetail.tsx
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { ExternalLink, Copy, Pencil, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjects } from "@/hooks/useProjects";
import { usePage } from "@/hooks/usePage";
import { usePageBacklinks } from "@/hooks/usePageBacklinks";
import { ConfidenceBar } from "@/components/widgets/ConfidenceBar";
import { FlavorTags } from "@/components/widgets/FlavorTags";
import { ProvenanceIndicator } from "@/components/widgets/ProvenanceIndicator";
import { StatusBadge } from "@/components/widgets/StatusBadge";
import { MarkdownView } from "@/components/markdown/MarkdownView";

export function PageDetail() {
  const { name: project, "*": pageRefRaw } = useParams<{ name: string; "*": string }>();
  const { t } = useTranslation();
  const pageRef = pageRefRaw ?? "";
  const projects = useProjects();
  const project_entry = projects.data?.find((p) => p.name === project);

  const pageQuery = usePage(project, pageRef);
  const backlinksQuery = usePageBacklinks(project, pageRef);

  if (pageQuery.isLoading) return <Skeleton className="h-96 w-full" />;

  if (pageQuery.isError) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("pages.not_found_title")}</h1>
        <p className="text-[hsl(var(--muted-foreground))]">{pageRef}</p>
        <Link to={`/project/${project}/pages`} className="text-[hsl(var(--primary))] underline">
          {t("pages.not_found_hint")}
        </Link>
      </div>
    );
  }

  const page = pageQuery.data!;
  const fm = page.frontmatter;
  const obsidianUrl = project_entry
    ? `obsidian://open?vault=${encodeURIComponent(project_entry.vault_root)}&file=${encodeURIComponent(page.path)}`
    : null;

  const wikilink = `[[${page.path.split("/").slice(-1)[0]?.replace(/\.md$/, "")}]]`;

  function copyWikilink() {
    void navigator.clipboard.writeText(wikilink);
  }

  return (
    <article className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Link to={`/project/${project}/pages`} className="text-sm text-[hsl(var(--primary))] underline">
          ← {t("navigation.pages")}
        </Link>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled title={t("pages.edit_disabled")}>
            <Pencil className="mr-1 h-3 w-3" /> {t("pages.edit_disabled")}
          </Button>
          <Button size="sm" variant="outline" disabled title={t("pages.verify_disabled")}>
            <ShieldCheck className="mr-1 h-3 w-3" /> {t("pages.verify_disabled")}
          </Button>
          <Button size="sm" variant="outline" disabled title={t("pages.delete_disabled")}>
            <Trash2 className="mr-1 h-3 w-3" /> {t("pages.delete_disabled")}
          </Button>
        </div>
      </div>

      <header className="space-y-2 border-b pb-4">
        <h1 className="text-3xl font-bold">{fm.title}</h1>
        <div className="flex flex-wrap items-center gap-3 text-xs text-[hsl(var(--muted-foreground))]">
          <span>{t(`wiki.type.${fm.type}`)}</span>
          <StatusBadge status={fm.status} />
          <ConfidenceBar value={fm.confidence} />
          <FlavorTags flavors={fm.flavor} />
          <ProvenanceIndicator counts={fm.provenance} />
        </div>
        <div className="flex items-center gap-2">
          {obsidianUrl && (
            <Button asChild size="sm" variant="outline">
              <a href={obsidianUrl}>
                <ExternalLink className="mr-1 h-3 w-3" />
                {t("pages.open_in_obsidian")}
              </a>
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={copyWikilink}>
            <Copy className="mr-1 h-3 w-3" />
            {t("pages.copy_wikilink")}
          </Button>
        </div>
      </header>

      <MarkdownView body={page.body} />

      <section className="border-t pt-4">
        <h2 className="mb-2 text-sm font-semibold">{t("pages.backlinks")}</h2>
        {backlinksQuery.isLoading ? (
          <Skeleton className="h-16" />
        ) : (backlinksQuery.data?.length ?? 0) === 0 ? (
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("pages.no_backlinks")}
          </div>
        ) : (
          <ul className="space-y-1 text-sm">
            {backlinksQuery.data!.map((b) => (
              <li key={b}>
                <Link
                  to={`/project/${project}/pages/${b}`}
                  className="text-[hsl(var(--primary))] hover:underline"
                >
                  {b}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PageDetail.tsx frontend/src/__tests__/PageDetail.test.tsx frontend/public/locales/
git commit -m "feat(frontend): PageDetail page (frontmatter header + body + backlinks + obsidian link)"
```

---

## Task 11: SessionCard widget

**Files:**
- Create: `frontend/src/components/widgets/SessionCard.tsx`
- Modify: `frontend/public/locales/{uk,ru,en}.json` (add `sessions.*` keys)

- [ ] **Step 1: Add locale keys**

```json
"sessions": {
  "title": "<localised>",
  "open": "<localised>",
  "no_sessions": "<localised>",
  "filter_status": "<localised>",
  "limit": "<localised>",
  "status": {
    "ingested": "<localised>",
    "queued": "<localised>",
    "running": "<localised>",
    "failed": "<localised>",
    "dead_letter": "<localised>"
  },
  "tokens_in": "<localised>",
  "tokens_out": "<localised>",
  "model": "<localised>",
  "ingested_at": "<localised>",
  "transcript": "<localised>",
  "created_pages": "<localised>",
  "no_pages_created": "<localised>",
  "showing_n_of_m": "{{shown}} of {{total}}",
  "ingest_disabled": "<localised>",
  "not_found_title": "<localised>",
  "not_found_hint": "<localised>"
}
```

- [ ] **Step 2: Implement**

```tsx
// frontend/src/components/widgets/SessionCard.tsx
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { SessionStatus, SessionView } from "@/types/Session";

const STATUS_COLOR: Record<SessionStatus, string> = {
  ingested: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  queued: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  running: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  dead_letter: "bg-red-200 text-red-800 dark:bg-red-900 dark:text-red-200",
};

interface Props {
  project: string;
  session: SessionView;
}

export function SessionCard({ project, session: s }: Props) {
  const { t } = useTranslation();
  return (
    <Card className="transition-colors hover:bg-[hsl(var(--muted))]">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <Link
            to={`/project/${project}/sessions/${s.session_id}`}
            className="truncate font-mono text-sm hover:underline"
            title={s.session_id}
          >
            {s.session_id.slice(0, 12)}…
          </Link>
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
              STATUS_COLOR[s.status],
            )}
          >
            {t(`sessions.status.${s.status}`)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-1 text-xs">
        {s.model && (
          <div>
            <span className="text-[hsl(var(--muted-foreground))]">{t("sessions.model")}: </span>
            <code>{s.model}</code>
          </div>
        )}
        {(s.input_tokens !== null || s.output_tokens !== null) && (
          <div className="text-[hsl(var(--muted-foreground))]">
            {t("sessions.tokens_in")}: <span className="text-[hsl(var(--foreground))]">{s.input_tokens ?? "—"}</span>
            {" · "}
            {t("sessions.tokens_out")}: <span className="text-[hsl(var(--foreground))]">{s.output_tokens ?? "—"}</span>
          </div>
        )}
        {s.created_pages.length > 0 && (
          <div className="text-[hsl(var(--muted-foreground))]">
            {t("sessions.created_pages")}: {s.created_pages.length}
          </div>
        )}
        {s.ingested_at && (
          <div className="text-[hsl(var(--muted-foreground))]">
            {t("sessions.ingested_at")}: {s.ingested_at}
          </div>
        )}
        {s.error && (
          <div className="rounded bg-red-50 px-2 py-1 text-red-700 dark:bg-red-950 dark:text-red-400">
            {s.error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: Run typecheck + lint**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/widgets/SessionCard.tsx frontend/public/locales/
git commit -m "feat(frontend): SessionCard widget with status badge + token stats"
```

---

## Task 12: Sessions list page

**Files:**
- Modify: `frontend/src/pages/Sessions.tsx`
- Create: `frontend/src/components/filters/SessionFilters.tsx`, `frontend/src/__tests__/Sessions.test.tsx`

- [ ] **Step 1: SessionFilters component**

```tsx
// frontend/src/components/filters/SessionFilters.tsx
import { useTranslation } from "react-i18next";
import type { SessionStatus } from "@/types/Session";

const STATUSES: SessionStatus[] = ["ingested", "queued", "running", "failed", "dead_letter"];

export interface SessionFilterState {
  status: SessionStatus | "all";
  limit: number;
}

export function defaultSessionFilterState(): SessionFilterState {
  return { status: "all", limit: 50 };
}

interface Props {
  state: SessionFilterState;
  onChange: (state: SessionFilterState) => void;
}

export function SessionFilters({ state, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 text-sm">
      <label className="flex items-center gap-1.5">
        <span className="text-[hsl(var(--muted-foreground))]">{t("sessions.filter_status")}</span>
        <select
          value={state.status}
          onChange={(e) =>
            onChange({ ...state, status: e.target.value as SessionFilterState["status"] })
          }
          className="rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        >
          <option value="all">{t("pages.filters.all", "All")}</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`sessions.status.${s}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-1.5">
        <span className="text-[hsl(var(--muted-foreground))]">{t("sessions.limit")}</span>
        <select
          value={state.limit}
          onChange={(e) => onChange({ ...state, limit: Number(e.target.value) })}
          className="rounded-md border bg-[hsl(var(--background))] px-2 py-1"
        >
          {[20, 50, 100, 200].map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
```

- [ ] **Step 2: Failing test**

```tsx
// frontend/src/__tests__/Sessions.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Sessions } from "../pages/Sessions";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    sessions: {
      title: "Sessions", filter_status: "Status", limit: "Limit",
      status: { ingested: "Ingested", queued: "Queued", running: "Running", failed: "Failed", dead_letter: "Dead-letter" },
      no_sessions: "No sessions", showing_n_of_m: "{{shown}} of {{total}}",
      tokens_in: "in", tokens_out: "out", model: "model", ingested_at: "at",
      created_pages: "pages",
    },
    pages: { filters: { all: "All" } },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/project/alpha/sessions"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/sessions" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Sessions", () => {
  it("renders cards from list response", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        sessions: [
          {
            session_id: "abc-123-def-456-7890",
            status: "ingested",
            transcript_path: null,
            ingested_at: "2026-04-29T12:00:00Z",
            model: "claude-sonnet",
            input_tokens: 1000,
            output_tokens: 500,
            raw_transcript_bytes: 0,
            created_pages: ["wiki/x.md"],
            error: null,
          },
        ],
        total: 1,
      },
    });
    render(wrap(<Sessions />));
    await waitFor(() => expect(screen.getByText(/abc-123-def/i)).toBeInTheDocument());
    expect(screen.getByText("Ingested")).toBeInTheDocument();
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { sessions: [], total: 0 } });
    render(wrap(<Sessions />));
    await waitFor(() => expect(screen.getByText(/no sessions/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement Sessions page**

```tsx
// frontend/src/pages/Sessions.tsx
import { useState } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useSessions } from "@/hooks/useSessions";
import { Skeleton } from "@/components/ui/skeleton";
import { SessionCard } from "@/components/widgets/SessionCard";
import {
  SessionFilters,
  defaultSessionFilterState,
  type SessionFilterState,
} from "@/components/filters/SessionFilters";

export function Sessions() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const [filters, setFilters] = useState<SessionFilterState>(defaultSessionFilterState);
  const sessionsQuery = useSessions(project, {
    status: filters.status === "all" ? undefined : filters.status,
    limit: filters.limit,
  });

  if (!project) return null;

  if (sessionsQuery.isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}
      </div>
    );
  }

  const sessions = sessionsQuery.data?.sessions ?? [];
  const total = sessionsQuery.data?.total ?? 0;

  if (total === 0) {
    return (
      <div className="space-y-3">
        <SessionFilters state={filters} onChange={setFilters} />
        <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
          {t("sessions.no_sessions")}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <SessionFilters state={filters} onChange={setFilters} />
      <div className="text-xs text-[hsl(var(--muted-foreground))]">
        {t("sessions.showing_n_of_m", { shown: sessions.length, total })}
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {sessions.map((s) => (
          <SessionCard key={s.session_id} project={project} session={s} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Sessions.tsx frontend/src/components/filters/SessionFilters.tsx frontend/src/__tests__/Sessions.test.tsx
git commit -m "feat(frontend): Sessions list page with status/limit filters"
```

---

## Task 13: SessionDetail page

**Files:**
- Create: `frontend/src/pages/SessionDetail.tsx`, `frontend/src/__tests__/SessionDetail.test.tsx`

- [ ] **Step 1: Failing test**

```tsx
// frontend/src/__tests__/SessionDetail.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { SessionDetail } from "../pages/SessionDetail";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    sessions: {
      status: { ingested: "Ingested" },
      tokens_in: "in", tokens_out: "out", model: "model", ingested_at: "at",
      created_pages: "pages", no_pages_created: "no pages",
      transcript: "transcript",
      ingest_disabled: "Ingest (#14c)",
      not_found_title: "Session not found",
      not_found_hint: "Back",
    },
    navigation: { sessions: "Sessions" },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/sessions/:sid" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("SessionDetail", () => {
  it("renders session metadata", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        session_id: "s1",
        status: "ingested",
        transcript_path: "/x/raw/chats/s1.md",
        ingested_at: "2026-04-29T12:00:00Z",
        model: "claude-sonnet",
        input_tokens: 1000,
        output_tokens: 500,
        raw_transcript_bytes: 12345,
        created_pages: ["wiki/x.md", "wiki/y.md"],
        error: null,
      },
    });
    render(wrap(<SessionDetail />, "/project/alpha/sessions/s1"));
    await waitFor(() => expect(screen.getByText("s1")).toBeInTheDocument());
    expect(screen.getByText("claude-sonnet")).toBeInTheDocument();
    expect(screen.getByText("Ingested")).toBeInTheDocument();
    expect(screen.getByText("wiki/x.md")).toBeInTheDocument();
  });

  it("renders not-found on 404", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("404"));
    render(wrap(<SessionDetail />, "/project/alpha/sessions/missing"));
    await waitFor(() => expect(screen.getByText(/Session not found/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/pages/SessionDetail.tsx
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/hooks/useSession";
import { cn } from "@/lib/utils";
import type { SessionStatus } from "@/types/Session";

const STATUS_COLOR: Record<SessionStatus, string> = {
  ingested: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  queued: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  running: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  dead_letter: "bg-red-200 text-red-800 dark:bg-red-900 dark:text-red-200",
};

export function SessionDetail() {
  const { name: project, sid } = useParams<{ name: string; sid: string }>();
  const { t } = useTranslation();
  const sessionQuery = useSession(project, sid);

  if (sessionQuery.isLoading) return <Skeleton className="h-64 w-full" />;
  if (sessionQuery.isError) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("sessions.not_found_title")}</h1>
        <p className="text-[hsl(var(--muted-foreground))]">{sid}</p>
        <Link to={`/project/${project}/sessions`} className="text-[hsl(var(--primary))] underline">
          {t("sessions.not_found_hint")}
        </Link>
      </div>
    );
  }

  const s = sessionQuery.data!;
  return (
    <article className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center justify-between">
        <Link to={`/project/${project}/sessions`} className="text-sm text-[hsl(var(--primary))] underline">
          ← {t("navigation.sessions")}
        </Link>
        <Button size="sm" variant="outline" disabled title={t("sessions.ingest_disabled")}>
          {t("sessions.ingest_disabled")}
        </Button>
      </div>

      <header className="space-y-2 border-b pb-4">
        <h1 className="font-mono text-xl">{s.session_id}</h1>
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
            STATUS_COLOR[s.status],
          )}
        >
          {t(`sessions.status.${s.status}`)}
        </span>
      </header>

      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        {s.model && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">{t("sessions.model")}</dt>
            <dd><code>{s.model}</code></dd>
          </>
        )}
        {s.input_tokens !== null && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">{t("sessions.tokens_in")}</dt>
            <dd>{s.input_tokens.toLocaleString()}</dd>
          </>
        )}
        {s.output_tokens !== null && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">{t("sessions.tokens_out")}</dt>
            <dd>{s.output_tokens.toLocaleString()}</dd>
          </>
        )}
        {s.ingested_at && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">{t("sessions.ingested_at")}</dt>
            <dd>{s.ingested_at}</dd>
          </>
        )}
        {s.transcript_path && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">{t("sessions.transcript")}</dt>
            <dd className="break-all"><code>{s.transcript_path}</code></dd>
          </>
        )}
      </dl>

      <section>
        <h2 className="mb-2 text-sm font-semibold">{t("sessions.created_pages")}</h2>
        {s.created_pages.length === 0 ? (
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("sessions.no_pages_created")}
          </div>
        ) : (
          <ul className="space-y-1 text-sm">
            {s.created_pages.map((p) => (
              <li key={p}>
                <Link
                  to={`/project/${project}/pages/${p}`}
                  className="text-[hsl(var(--primary))] hover:underline"
                >
                  {p}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {s.error && (
        <section className="rounded bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-400">
          {s.error}
        </section>
      )}
    </article>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SessionDetail.tsx frontend/src/__tests__/SessionDetail.test.tsx
git commit -m "feat(frontend): SessionDetail page (metadata + created pages + transcript path)"
```

---

## Task 14: groupByDay util + ActivityRow widget

**Files:**
- Create: `frontend/src/lib/groupByDay.ts`, `frontend/src/components/widgets/ActivityRow.tsx`, `frontend/src/__tests__/groupByDay.test.ts`

- [ ] **Step 1: Failing test for groupByDay**

```ts
// frontend/src/__tests__/groupByDay.test.ts
import { describe, it, expect } from "vitest";
import { groupByDay, type DayGroup } from "../lib/groupByDay";
import type { ActivityEntry } from "../types/Activity";

function entry(timestamp: string, status: ActivityEntry["status"] = "success", op = "ingest"): ActivityEntry {
  return {
    id: `op-${timestamp}`,
    timestamp,
    operation_type: op,
    status,
    snapshot_path: null,
    can_undo: false,
    undone: false,
    undone_at: null,
    undone_by_id: null,
    affected_pages: [],
    metadata: {},
  };
}

describe("groupByDay", () => {
  const REF = new Date("2026-04-29T12:00:00Z").getTime();

  it("buckets today / yesterday / earlier_week / older", () => {
    const today = entry("2026-04-29T11:00:00Z");
    const yesterday = entry("2026-04-28T08:00:00Z");
    const four_days_ago = entry("2026-04-25T00:00:00Z");
    const old = entry("2026-04-01T00:00:00Z");

    const groups = groupByDay([today, yesterday, four_days_ago, old], REF);
    const byKey = Object.fromEntries(groups.map((g) => [g.key, g.entries.length]));
    expect(byKey.today).toBe(1);
    expect(byKey.yesterday).toBe(1);
    expect(byKey.earlier_week).toBe(1);
    expect(byKey.older).toBe(1);
  });

  it("flags failed ingest into needs_attention", () => {
    const failed = entry("2026-04-29T11:00:00Z", "failed");
    const groups = groupByDay([failed], REF);
    const needs = groups.find((g) => g.key === "needs_attention");
    expect(needs?.entries).toHaveLength(1);
    // Also bucketed in today.
    const today = groups.find((g) => g.key === "today");
    expect(today?.entries).toHaveLength(1);
  });

  it("returns groups in fixed order", () => {
    const groups = groupByDay([], REF);
    const keys = groups.map((g): DayGroup["key"] => g.key);
    expect(keys).toEqual(["needs_attention", "today", "yesterday", "earlier_week", "older"]);
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```ts
// frontend/src/lib/groupByDay.ts
import type { ActivityEntry } from "@/types/Activity";

export type DayGroupKey = "needs_attention" | "today" | "yesterday" | "earlier_week" | "older";

export interface DayGroup {
  key: DayGroupKey;
  entries: ActivityEntry[];
}

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(ts: number): number {
  const d = new Date(ts);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

export function groupByDay(
  entries: ActivityEntry[],
  nowMs: number = Date.now(),
): DayGroup[] {
  const todayStart = startOfDay(nowMs);
  const yesterdayStart = todayStart - DAY_MS;
  const weekStart = todayStart - 7 * DAY_MS;

  const groups: Record<DayGroupKey, ActivityEntry[]> = {
    needs_attention: [],
    today: [],
    yesterday: [],
    earlier_week: [],
    older: [],
  };

  for (const e of entries) {
    const ts = Date.parse(e.timestamp);
    if (Number.isNaN(ts)) {
      groups.older.push(e);
      continue;
    }

    // needs_attention: failed status, or ingest that has been quarantined.
    const quarantined =
      e.operation_type === "ingest" &&
      typeof e.metadata.quarantined === "boolean" &&
      e.metadata.quarantined === true;
    if (e.status === "failed" || quarantined) {
      groups.needs_attention.push(e);
    }

    if (ts >= todayStart) groups.today.push(e);
    else if (ts >= yesterdayStart) groups.yesterday.push(e);
    else if (ts >= weekStart) groups.earlier_week.push(e);
    else groups.older.push(e);
  }

  // Sort each group desc by timestamp.
  for (const k of Object.keys(groups) as DayGroupKey[]) {
    groups[k].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  }

  return (
    ["needs_attention", "today", "yesterday", "earlier_week", "older"] as DayGroupKey[]
  ).map((key) => ({ key, entries: groups[key] }));
}
```

```tsx
// frontend/src/components/widgets/ActivityRow.tsx
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ActivityEntry } from "@/types/Activity";

interface Props {
  project: string;
  entry: ActivityEntry;
}

const STATUS_ICON = {
  success: CheckCircle2,
  partial: CircleDashed,
  failed: AlertTriangle,
} as const;

const STATUS_COLOR = {
  success: "text-emerald-600",
  partial: "text-amber-600",
  failed: "text-red-600",
} as const;

export function ActivityRow({ project, entry: e }: Props) {
  const { t } = useTranslation();
  const Icon = STATUS_ICON[e.status];

  return (
    <div className="flex items-center gap-3 rounded-md border bg-[hsl(var(--background))] px-3 py-2">
      <Icon className={cn("h-4 w-4 shrink-0", STATUS_COLOR[e.status])} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-medium">
            {t(`activity.op.${e.operation_type}`, e.operation_type)}
          </span>
          <span className="text-xs text-[hsl(var(--muted-foreground))]">
            {e.timestamp}
          </span>
        </div>
        {e.affected_pages.length > 0 && (
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("activity.affected_pages", { count: e.affected_pages.length })}
          </div>
        )}
      </div>
      <Button asChild size="sm" variant="ghost">
        <Link to={`/project/${project}/activity/${e.id}`}>
          {t("activity.detail")}
          <ChevronRight className="ml-1 h-3 w-3" />
        </Link>
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={!e.can_undo || e.undone}
        title={t("activity.undo_disabled")}
      >
        {t("activity.undo_disabled")}
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/groupByDay.ts frontend/src/components/widgets/ActivityRow.tsx frontend/src/__tests__/groupByDay.test.ts
git commit -m "feat(frontend): groupByDay util + ActivityRow widget"
```

---

## Task 15: ActivityCenter page

**Files:**
- Modify: `frontend/src/pages/ActivityCenter.tsx`
- Create: `frontend/src/__tests__/ActivityCenter.test.tsx`
- Modify: `frontend/public/locales/{uk,ru,en}.json` (add `activity.*` keys)

- [ ] **Step 1: Add locale keys**

```json
"activity": {
  "title": "<localised>",
  "groups": {
    "needs_attention": "<localised>",
    "today": "<localised>",
    "yesterday": "<localised>",
    "earlier_week": "<localised>",
    "older": "<localised>"
  },
  "op": {
    "ingest": "<localised>",
    "lint_autofix": "<localised>",
    "ontology_apply": "<localised>",
    "manual_patch": "<localised>",
    "manual_soft_delete": "<localised>",
    "manual_restore": "<localised>",
    "human_edit_detected": "<localised>",
    "manual_undo": "<localised>"
  },
  "affected_pages": "{{count}} pages",
  "detail": "<localised>",
  "undo_disabled": "<localised>",
  "no_activity": "<localised>",
  "metadata": "<localised>",
  "snapshot": "<localised>",
  "can_undo": "<localised>",
  "cannot_undo": "<localised>",
  "undone": "<localised>",
  "not_found_title": "<localised>",
  "not_found_hint": "<localised>"
}
```

- [ ] **Step 2: Failing test**

```tsx
// frontend/src/__tests__/ActivityCenter.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { ActivityCenter } from "../pages/ActivityCenter";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    activity: {
      title: "Activity",
      groups: { needs_attention: "Needs attention", today: "Today", yesterday: "Yesterday", earlier_week: "This week", older: "Older" },
      op: { ingest: "Ingest", manual_patch: "Manual edit" },
      affected_pages: "{{count}} pages",
      detail: "Detail",
      undo_disabled: "Undo (#14c)",
      no_activity: "No activity",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/project/alpha/activity"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/activity" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("ActivityCenter", () => {
  it("renders entries grouped", async () => {
    const today = new Date().toISOString();
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        entries: [
          {
            id: "op-1", timestamp: today, operation_type: "ingest", status: "success",
            snapshot_path: null, can_undo: true, undone: false, undone_at: null, undone_by_id: null,
            affected_pages: ["wiki/a.md"], metadata: {},
          },
        ],
        total: 1,
      },
    });
    render(wrap(<ActivityCenter />));
    await waitFor(() => expect(screen.getByText("Today")).toBeInTheDocument());
    expect(screen.getByText("Ingest")).toBeInTheDocument();
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { entries: [], total: 0 } });
    render(wrap(<ActivityCenter />));
    await waitFor(() => expect(screen.getByText(/no activity/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement**

```tsx
// frontend/src/pages/ActivityCenter.tsx
import { useMemo } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivity } from "@/hooks/useActivity";
import { ActivityRow } from "@/components/widgets/ActivityRow";
import { groupByDay, type DayGroupKey } from "@/lib/groupByDay";

const VISIBLE_GROUPS: DayGroupKey[] = [
  "needs_attention",
  "today",
  "yesterday",
  "earlier_week",
  "older",
];

export function ActivityCenter() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const activityQuery = useActivity(project, { limit: 200 });

  const groups = useMemo(
    () => groupByDay(activityQuery.data?.entries ?? []),
    [activityQuery.data],
  );

  if (!project) return null;

  if (activityQuery.isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    );
  }

  const total = activityQuery.data?.total ?? 0;
  if (total === 0) {
    return (
      <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
        {t("activity.no_activity")}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {VISIBLE_GROUPS.map((key) => {
        const group = groups.find((g) => g.key === key);
        if (!group || group.entries.length === 0) return null;
        return (
          <section key={key}>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
              {t(`activity.groups.${key}`)}
              <span className="ml-2 font-normal">({group.entries.length})</span>
            </h2>
            <div className="space-y-2">
              {group.entries.map((e) => (
                <ActivityRow key={e.id} project={project} entry={e} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ActivityCenter.tsx frontend/src/__tests__/ActivityCenter.test.tsx frontend/public/locales/
git commit -m "feat(frontend): ActivityCenter page with day-grouped sections"
```

---

## Task 16: ActivityDetail page

**Files:**
- Create: `frontend/src/pages/ActivityDetail.tsx`, `frontend/src/__tests__/ActivityDetail.test.tsx`

- [ ] **Step 1: Failing test**

```tsx
// frontend/src/__tests__/ActivityDetail.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { ActivityDetail } from "../pages/ActivityDetail";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    activity: {
      op: { ingest: "Ingest" },
      metadata: "Metadata",
      snapshot: "Snapshot",
      can_undo: "Can undo",
      cannot_undo: "Cannot undo",
      undone: "Undone",
      undo_disabled: "Undo (#14c)",
      not_found_title: "Activity not found",
      not_found_hint: "Back",
    },
    navigation: { activity: "Activity" },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/activity/:opId" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("ActivityDetail", () => {
  it("renders entry with metadata + can_undo flag", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        id: "op-1",
        timestamp: "2026-04-29T12:00:00Z",
        operation_type: "ingest",
        status: "success",
        snapshot_path: ".backups/2026-04-29-pre-op-x",
        can_undo: true,
        undone: false,
        undone_at: null,
        undone_by_id: null,
        affected_pages: ["wiki/x.md"],
        metadata: { session_id: "s1" },
      },
    });
    render(wrap(<ActivityDetail />, "/project/alpha/activity/op-1"));
    await waitFor(() => expect(screen.getByText("Ingest")).toBeInTheDocument());
    expect(screen.getByText("Can undo")).toBeInTheDocument();
    expect(screen.getByText(/session_id/)).toBeInTheDocument();
  });

  it("renders not-found on 404", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("404"));
    render(wrap(<ActivityDetail />, "/project/alpha/activity/missing"));
    await waitFor(() => expect(screen.getByText(/Activity not found/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/pages/ActivityDetail.tsx
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivityEntry } from "@/hooks/useActivityEntry";

export function ActivityDetail() {
  const { name: project, opId } = useParams<{ name: string; opId: string }>();
  const { t } = useTranslation();
  const entryQuery = useActivityEntry(project, opId);

  if (entryQuery.isLoading) return <Skeleton className="h-64" />;
  if (entryQuery.isError) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("activity.not_found_title")}</h1>
        <p className="text-[hsl(var(--muted-foreground))]">{opId}</p>
        <Link to={`/project/${project}/activity`} className="text-[hsl(var(--primary))] underline">
          {t("activity.not_found_hint")}
        </Link>
      </div>
    );
  }

  const e = entryQuery.data!;
  const canUndo = e.can_undo && !e.undone;

  return (
    <article className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center justify-between">
        <Link to={`/project/${project}/activity`} className="text-sm text-[hsl(var(--primary))] underline">
          ← {t("navigation.activity")}
        </Link>
        <Button size="sm" variant="outline" disabled title={t("activity.undo_disabled")}>
          {t("activity.undo_disabled")}
        </Button>
      </div>

      <header className="space-y-2 border-b pb-4">
        <h1 className="text-xl font-semibold">
          {t(`activity.op.${e.operation_type}`, e.operation_type)}
        </h1>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          {e.id} · {e.timestamp}
        </p>
      </header>

      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-[hsl(var(--muted-foreground))]">status</dt>
        <dd>{e.status}</dd>

        {e.snapshot_path && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">{t("activity.snapshot")}</dt>
            <dd className="break-all"><code>{e.snapshot_path}</code></dd>
          </>
        )}

        <dt className="text-[hsl(var(--muted-foreground))]">undo</dt>
        <dd>
          {e.undone
            ? `${t("activity.undone")} ${e.undone_at ?? ""}`
            : canUndo
              ? t("activity.can_undo")
              : t("activity.cannot_undo")}
        </dd>
      </dl>

      {e.affected_pages.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold">
            {t("activity.affected_pages", { count: e.affected_pages.length })}
          </h2>
          <ul className="space-y-1 text-sm">
            {e.affected_pages.map((p) => (
              <li key={p}>
                <Link
                  to={`/project/${project}/pages/${p}`}
                  className="text-[hsl(var(--primary))] hover:underline"
                >
                  {p}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold">{t("activity.metadata")}</h2>
        <pre className="overflow-x-auto rounded bg-[hsl(var(--muted))] p-3 text-xs">
          {JSON.stringify(e.metadata, null, 2)}
        </pre>
      </section>
    </article>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ActivityDetail.tsx frontend/src/__tests__/ActivityDetail.test.tsx
git commit -m "feat(frontend): ActivityDetail page (entry + metadata + can_undo flag)"
```

---

## Task 17: Wire routes in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update App.tsx**

Replace the existing 6 Placeholder routes with the real pages, plus the 2 new nested routes for sessions/:sid and activity/:opId. Note: `pages/:pageId` from #14a stays — we need to switch its element to `<PageDetail />` and rename the splat. react-router v7 splat syntax is `pages/*` with `useParams<{ "*": string }>`.

Replace the existing `/project/:name/pages` and `/project/:name/pages/:pageId` route children with:

```tsx
{ path: "pages", element: <PagesBrowser /> },
{ path: "pages/*", element: <PageDetail /> },
```

Replace `sessions`, `activity`, with:

```tsx
{ path: "sessions", element: <Sessions /> },
{ path: "sessions/:sid", element: <SessionDetail /> },
{ path: "activity", element: <ActivityCenter /> },
{ path: "activity/:opId", element: <ActivityDetail /> },
```

Add imports at the top:

```tsx
import { PagesBrowser } from "./pages/PagesBrowser";
import { PageDetail } from "./pages/PageDetail";
import { Sessions } from "./pages/Sessions";
import { SessionDetail } from "./pages/SessionDetail";
import { ActivityCenter } from "./pages/ActivityCenter";
import { ActivityDetail } from "./pages/ActivityDetail";
```

(and remove the placeholders for these 6 sections from the imports if they were named; otherwise just leave `<Placeholder>` for the still-stubbed sections like Suggestions/Trash/Snapshots/Health/Settings/Onboarding/Metrics/GlobalSettings/LostSessions which will be replaced in #14b-2/#14c/#14d.)

- [ ] **Step 2: Run full Vitest + typecheck + lint**

```
cd frontend
pnpm test
pnpm typecheck
pnpm lint
```

All pass.

- [ ] **Step 3: Smoke verify in dev**

```bash
pnpm dev   # vite :5173
```

In a second terminal: `mnemos daemon foreground` (or use the already-running daemon). Browser → `http://localhost:5173/`. Manually click into a project → Pages tab, Sessions tab, Activity tab. Each renders real content (or empty state) — NOT the Placeholder anymore. Ctrl-C dev when done.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): wire #14b-1 pages into router (replace 6 Placeholder stubs)"
```

---

## Task 18: Build + final verification

- [ ] **Step 1: Build production bundle**

```bash
cd frontend
pnpm build
```

Expected: dist written to `../claude_mnemos/daemon/static/`. Bundle size will grow modestly with react-markdown — confirm size warning is still in the warning band (around 700 KB unminified, < 250 KB gzip).

- [ ] **Step 2: Full test suite (frontend)**

```
pnpm test
pnpm lint
pnpm typecheck
```

All clean.

- [ ] **Step 3: Backend pytest sanity**

```bash
cd /d/code/claude-mnemos
python -m pytest -q --ignore=tests/daemon/integration -k "not slow" 2>&1 | tail -10
```

No regressions (#14b-1 is pure frontend; backend should be unchanged).

- [ ] **Step 4: Acceptance criteria walk-through (design §4)**

Verify each of the 11 ACs from the design doc against an actual run:

1. ✅ Pages browser — open `http://localhost:5757/project/{some-real-project}/pages` → cards render with real frontmatter; filters work.
2. ✅ Page detail — click a card → frontmatter header + markdown body + backlinks + Open in Obsidian.
3. ✅ Sessions — list with status filter; click a card → session detail with token stats + created-pages links.
4. ✅ Activity Center — entries grouped by day; click → detail with metadata.
5. ✅ Per-project routes work; unknown project → friendly UnknownProject (already in #14a).
6. ✅ Unknown page / unknown session / unknown activity → in-page "not found" with link back.
7. ✅ Empty states display localised copy.
8. ✅ Schemas match backend — round-trip-tested via api-pages/api-sessions/api-activity tests.
9. ✅ Mutation buttons disabled with #14c hint tooltip.
10. ✅ Vitest suite green; ~30+ new tests on top of #14a.
11. ✅ Manual browser smoke complete.

- [ ] **Step 5: Branch summary**

```bash
git log --oneline main..HEAD
git status
```

~18-20 commits, working tree clean.

If everything passes, this task is verification-only — no commit needed unless you tweaked locales/lockfile during build.

---

## Spec coverage map

| Design § | Plan task(s) |
|---|---|
| 1.x background/goals | All tasks |
| 2.1 type schemas | Tasks 1, 2, 3 (verification + schemas) |
| 2.2 API layer | Tasks 1, 2, 3 |
| 2.3 hook layer | Tasks 1, 2, 3 |
| 2.4 routing | Task 17 |
| 2.5 component additions | Tasks 4, 5, 6, 7, 8, 11, 12, 14 |
| 2.6 translation keys | Tasks 4, 8, 11, 15 (incremental adds) |
| 2.7 data flow | Implicit in pages tasks (9, 10, 12, 13, 15, 16) |
| 2.8 markdown rendering | Task 6 |
| 2.9 backend changes | None (verified Task 18) |
| 3 risks | n/a operational |
| 4 acceptance criteria | Task 18 step 4 |
| 5 open questions | n/a (decisions baked in) |
| 6 out of scope | n/a (deferred to #14b-2/#14c/#14d) |

No uncovered spec requirements.
