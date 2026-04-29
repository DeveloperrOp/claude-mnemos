# Operational views (Trash, Snapshots, Lost Sessions, Suggestions, Failed Jobs, Health) Implementation Plan (Plan #14b-2)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** Replace 5 remaining #14a Placeholder routes (`/trash`, `/snapshots`, `/lost-sessions`, `/suggestions`, `/health`) with working read-only pages, plus add new global `/dead-letter` + `/dead-letter/:jobId` routes. After #14b-2 the user can browse soft-deleted pages, snapshot backups, ontology suggestions, lost-session scanner output, dead-letter queue, and per-vault health detail.

**Architecture:** Pure frontend. New zod schemas mirror backend Pydantic models in `state/`/`core/` (each schema task starts with a grep-verify step). New API modules wrap existing #13b-β2 endpoints. New TanStack Query hooks (one notable mutation: `useLostSessionsScan` invalidates the cache, not a vault mutation). New widgets: TrashRow, SnapshotCard, LostSessionRow, SuggestionCard, DeadLetterRow, ProjectBadge, KindBadge. Two filter sidebars (SnapshotFilters by kind, SuggestionFilters by status). 7 pages replace existing Placeholders or add new global routes. All other write actions (Restore/Delete/Approve/Retry/Import/Ignore) render `disabled` with `→ #14c` tooltips.

**Tech Stack:** React 19, TanStack Query 5, react-router 7, zod 3, axios, Tailwind v4, shadcn/ui, Vitest + Testing Library, i18next. Reuses MarkdownView + ConfidenceBar + StatusBadge + FlavorTags from #14b-1.

**Design doc:** `docs/plans/2026-04-29-14b-2-operational-views-design.md` — read before each task.

---

## Files map

**Create (frontend types):**
- `frontend/src/types/Trash.ts`
- `frontend/src/types/Snapshot.ts`
- `frontend/src/types/LostSession.ts`
- `frontend/src/types/Suggestion.ts`
- `frontend/src/types/Job.ts`

**Create (frontend api):**
- `frontend/src/api/trash.api.ts`
- `frontend/src/api/snapshots.api.ts`
- `frontend/src/api/lost_sessions.api.ts`
- `frontend/src/api/suggestions.api.ts`
- `frontend/src/api/dead_letter.api.ts`

**Create (frontend hooks):**
- `frontend/src/hooks/useTrash.ts`
- `frontend/src/hooks/useSnapshots.ts`
- `frontend/src/hooks/useLostSessions.ts`
- `frontend/src/hooks/useLostSessionsScan.ts`
- `frontend/src/hooks/useSuggestions.ts`
- `frontend/src/hooks/useDeadLetter.ts`
- `frontend/src/hooks/useDeadLetterEntry.ts`

**Create (frontend widgets):**
- `frontend/src/components/widgets/ProjectBadge.tsx`
- `frontend/src/components/widgets/KindBadge.tsx`
- `frontend/src/components/widgets/TrashRow.tsx`
- `frontend/src/components/widgets/SnapshotCard.tsx`
- `frontend/src/components/widgets/LostSessionRow.tsx`
- `frontend/src/components/widgets/SuggestionCard.tsx`
- `frontend/src/components/widgets/DeadLetterRow.tsx`

**Create (frontend filters):**
- `frontend/src/components/filters/SnapshotFilters.tsx`
- `frontend/src/components/filters/SuggestionFilters.tsx`

**Create (frontend pages):**
- `frontend/src/pages/Trash.tsx`
- `frontend/src/pages/Snapshots.tsx`
- `frontend/src/pages/LostSessions.tsx`
- `frontend/src/pages/Suggestions.tsx`
- `frontend/src/pages/DeadLetter.tsx`
- `frontend/src/pages/DeadLetterDetail.tsx`
- `frontend/src/pages/Health.tsx`

**Create (frontend tests):** ~14 test files mirroring api/widget/page boundaries.

**Modify:**
- `frontend/src/App.tsx` — replace 5 Placeholder routes with real components; add 2 new global routes (`/dead-letter`, `/dead-letter/:jobId`).
- `frontend/src/components/layout/Sidebar.tsx` — add "Failed Jobs" entry under Global section.
- `frontend/public/locales/{uk,ru,en}.json` — ~120 new keys.

---

## Task 1: Trash types + API + hook

**Files:**
- Create: `frontend/src/types/Trash.ts`, `frontend/src/api/trash.api.ts`, `frontend/src/hooks/useTrash.ts`, `frontend/src/__tests__/api-trash.test.ts`

- [ ] **Step 1: Verify backend Pydantic shape (NO commit)**

```bash
cd /d/code/claude-mnemos
grep -A 15 "^class TrashEntry\b" claude_mnemos/core/trash.py
grep -A 10 "list_trash_endpoint" claude_mnemos/daemon/routes/trash.py
```

Confirm field names exactly. Notable: `original_path`, `operation_type`, `page_basename`, `restore_blocked_reason` are all `str | None` (nullable). `restorable: bool`. Response wraps as `{ entries: [...], total: int }`.

- [ ] **Step 2: Write the failing tests**

```ts
// frontend/src/__tests__/api-trash.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listTrash } from "../api/trash.api";

describe("trash api", () => {
  beforeEach(() => vi.spyOn(apiClient, "get"));
  afterEach(() => vi.restoreAllMocks());

  it("listTrash parses entries + total", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        entries: [
          {
            trash_id: "t1",
            deleted_at: "2026-04-29T12:00:00Z",
            original_path: "wiki/concepts/foo.md",
            operation_type: "manual_delete",
            page_basename: "foo",
            restorable: true,
            restore_blocked_reason: null,
          },
        ],
        total: 1,
      },
    });
    const out = await listTrash("alpha");
    expect(out.entries[0]?.trash_id).toBe("t1");
    expect(out.entries[0]?.restorable).toBe(true);
    expect(out.total).toBe(1);
  });

  it("listTrash rejects malformed payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { entries: [{ trash_id: 42 }], total: 1 },
    });
    await expect(listTrash("alpha")).rejects.toThrow();
  });

  it("listTrash accepts entry with all-null optionals", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        entries: [
          {
            trash_id: "t2",
            deleted_at: "2026-04-29T12:00:00Z",
            original_path: null,
            operation_type: null,
            page_basename: null,
            restorable: false,
            restore_blocked_reason: "metadata_corrupt",
          },
        ],
        total: 1,
      },
    });
    const out = await listTrash("alpha");
    expect(out.entries[0]?.restorable).toBe(false);
    expect(out.entries[0]?.restore_blocked_reason).toBe("metadata_corrupt");
  });
});
```

- [ ] **Step 3: Run** → FAIL.

```
cd frontend && pnpm test api-trash
```

- [ ] **Step 4: Implement types**

```ts
// frontend/src/types/Trash.ts
import { z } from "zod";

export const TrashEntrySchema = z.object({
  trash_id: z.string(),
  deleted_at: z.string(),
  original_path: z.string().nullable(),
  operation_type: z.string().nullable(),
  page_basename: z.string().nullable(),
  restorable: z.boolean(),
  restore_blocked_reason: z.string().nullable(),
});
export type TrashEntry = z.infer<typeof TrashEntrySchema>;

export const TrashListResponseSchema = z.object({
  entries: z.array(TrashEntrySchema),
  total: z.number().int().nonnegative(),
});
```

- [ ] **Step 5: Implement api module**

```ts
// frontend/src/api/trash.api.ts
import { apiClient } from "./client";
import {
  TrashListResponseSchema,
  type TrashEntry,
} from "@/types/Trash";

export async function listTrash(
  project: string,
): Promise<{ entries: TrashEntry[]; total: number }> {
  const r = await apiClient.get(`/trash/${encodeURIComponent(project)}`);
  return TrashListResponseSchema.parse(r.data);
}
```

- [ ] **Step 6: Implement hook**

```ts
// frontend/src/hooks/useTrash.ts
import { useQuery } from "@tanstack/react-query";
import { listTrash } from "@/api/trash.api";

export function useTrash(project: string | undefined) {
  return useQuery({
    queryKey: ["trash", project],
    queryFn: () => listTrash(project!),
    enabled: !!project,
    refetchInterval: 5_000,
  });
}
```

- [ ] **Step 7: Run** → PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/Trash.ts frontend/src/api/trash.api.ts frontend/src/hooks/useTrash.ts frontend/src/__tests__/api-trash.test.ts
git commit -m "feat(frontend): Trash types + API + useTrash hook"
```

---

## Task 2: Snapshot types + API + hook

**Files:**
- Create: `frontend/src/types/Snapshot.ts`, `frontend/src/api/snapshots.api.ts`, `frontend/src/hooks/useSnapshots.ts`, `frontend/src/__tests__/api-snapshots.test.ts`

- [ ] **Step 1: Verify backend shape**

```bash
grep -A 15 "^class SnapshotInfo\b\|^SnapshotKind " claude_mnemos/core/snapshots.py
grep -A 5 "list_snapshots_endpoint" claude_mnemos/daemon/routes/snapshots.py
```

Confirm: `SnapshotKind = Literal["pre-op", "daily", "manual"]`. `SnapshotInfo` fields: `name`, `kind`, `timestamp`, `op_id` (`str | None`), `op_type` (`str | None`), `label` (`str | None`), `size_bytes` (`int = 0`), `path` (`str`). Endpoint returns `{ snapshots: [...] }` (NO total).

- [ ] **Step 2: Write the failing tests**

```ts
// frontend/src/__tests__/api-snapshots.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listSnapshots } from "../api/snapshots.api";

describe("snapshots api", () => {
  beforeEach(() => vi.spyOn(apiClient, "get"));
  afterEach(() => vi.restoreAllMocks());

  it("listSnapshots parses array", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        snapshots: [
          {
            name: "pre-op-2026-04-29-12-00-00-abc-ingest",
            kind: "pre-op",
            timestamp: "2026-04-29T12:00:00Z",
            op_id: "abc",
            op_type: "ingest",
            label: null,
            size_bytes: 1024,
            path: ".backups/pre-op-2026-04-29-12-00-00-abc-ingest",
          },
          {
            name: "daily-2026-04-29-04-00-00",
            kind: "daily",
            timestamp: "2026-04-29T04:00:00Z",
            op_id: null,
            op_type: null,
            label: null,
            size_bytes: 2048,
            path: ".backups/daily-2026-04-29-04-00-00",
          },
        ],
      },
    });
    const out = await listSnapshots("alpha");
    expect(out).toHaveLength(2);
    expect(out[0]?.kind).toBe("pre-op");
    expect(out[1]?.kind).toBe("daily");
  });

  it("listSnapshots rejects unknown kind", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        snapshots: [
          { name: "x", kind: "weird", timestamp: "2026-04-29T12:00:00Z",
            op_id: null, op_type: null, label: null, size_bytes: 0, path: "x" },
        ],
      },
    });
    await expect(listSnapshots("alpha")).rejects.toThrow();
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement**

```ts
// frontend/src/types/Snapshot.ts
import { z } from "zod";

export const SnapshotKindSchema = z.enum(["pre-op", "daily", "manual"]);
export type SnapshotKind = z.infer<typeof SnapshotKindSchema>;

export const SnapshotInfoSchema = z.object({
  name: z.string(),
  kind: SnapshotKindSchema,
  timestamp: z.string(),
  op_id: z.string().nullable(),
  op_type: z.string().nullable(),
  label: z.string().nullable(),
  size_bytes: z.number().int().nonnegative(),
  path: z.string(),
});
export type SnapshotInfo = z.infer<typeof SnapshotInfoSchema>;

export const SnapshotListResponseSchema = z.object({
  snapshots: z.array(SnapshotInfoSchema),
});
```

```ts
// frontend/src/api/snapshots.api.ts
import { apiClient } from "./client";
import {
  SnapshotListResponseSchema,
  type SnapshotInfo,
} from "@/types/Snapshot";

export async function listSnapshots(
  project: string,
): Promise<SnapshotInfo[]> {
  const r = await apiClient.get(`/snapshots/${encodeURIComponent(project)}`);
  return SnapshotListResponseSchema.parse(r.data).snapshots;
}
```

```ts
// frontend/src/hooks/useSnapshots.ts
import { useQuery } from "@tanstack/react-query";
import { listSnapshots } from "@/api/snapshots.api";

export function useSnapshots(project: string | undefined) {
  return useQuery({
    queryKey: ["snapshots", project],
    queryFn: () => listSnapshots(project!),
    enabled: !!project,
    refetchInterval: 30_000,
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/Snapshot.ts frontend/src/api/snapshots.api.ts frontend/src/hooks/useSnapshots.ts frontend/src/__tests__/api-snapshots.test.ts
git commit -m "feat(frontend): Snapshot types + API + useSnapshots hook"
```

---

## Task 3: LostSession types + API + hooks (incl. scan mutation)

**Files:**
- Create: `frontend/src/types/LostSession.ts`, `frontend/src/api/lost_sessions.api.ts`, `frontend/src/hooks/useLostSessions.ts`, `frontend/src/hooks/useLostSessionsScan.ts`, `frontend/src/__tests__/api-lost-sessions.test.ts`

- [ ] **Step 1: Verify backend shape**

```bash
grep -A 10 "^class LostSession\b" claude_mnemos/core/lost_sessions.py
grep -A 15 "list_lost_route\|_scan_all_vaults" claude_mnemos/daemon/routes/lost_sessions.py
```

Confirm: LostSession fields = `session_id, transcript_path, sha, size_bytes, mtime`. The cross-vault route ALSO injects `project_name` per item via `d["project_name"] = runtime.name`. Response = `{ sessions: [...], total }`.

- [ ] **Step 2: Write the failing tests**

```ts
// frontend/src/__tests__/api-lost-sessions.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listLostSessions, scanLostSessions } from "../api/lost_sessions.api";

describe("lost-sessions api", () => {
  beforeEach(() => vi.spyOn(apiClient, "get").mockClear());

  afterEach(() => vi.restoreAllMocks());

  it("listLostSessions parses cross-vault sessions", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        sessions: [
          {
            session_id: "abc",
            transcript_path: "/x/raw/chats/abc.md",
            sha: "deadbeef",
            size_bytes: 1024,
            mtime: "2026-04-29T12:00:00Z",
            project_name: "alpha",
          },
        ],
        total: 1,
      },
    });
    const out = await listLostSessions();
    expect(out.sessions[0]?.project_name).toBe("alpha");
    expect(out.total).toBe(1);
  });

  it("scanLostSessions invokes POST /lost-sessions/scan", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      data: { sessions: [], total: 0 },
    });
    await scanLostSessions();
    expect(post).toHaveBeenCalledWith("/lost-sessions/scan");
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement**

```ts
// frontend/src/types/LostSession.ts
import { z } from "zod";

export const LostSessionSchema = z.object({
  session_id: z.string(),
  transcript_path: z.string(),
  sha: z.string(),
  size_bytes: z.number().int().nonnegative(),
  mtime: z.string(),
  project_name: z.string(),
});
export type LostSession = z.infer<typeof LostSessionSchema>;

export const LostSessionListResponseSchema = z.object({
  sessions: z.array(LostSessionSchema),
  total: z.number().int().nonnegative(),
});
```

```ts
// frontend/src/api/lost_sessions.api.ts
import { apiClient } from "./client";
import {
  LostSessionListResponseSchema,
  type LostSession,
} from "@/types/LostSession";

export async function listLostSessions(): Promise<{
  sessions: LostSession[];
  total: number;
}> {
  const r = await apiClient.get("/lost-sessions");
  return LostSessionListResponseSchema.parse(r.data);
}

export async function scanLostSessions(): Promise<{
  sessions: LostSession[];
  total: number;
}> {
  const r = await apiClient.post("/lost-sessions/scan");
  return LostSessionListResponseSchema.parse(r.data);
}
```

```ts
// frontend/src/hooks/useLostSessions.ts
import { useQuery } from "@tanstack/react-query";
import { listLostSessions } from "@/api/lost_sessions.api";

export function useLostSessions() {
  return useQuery({
    queryKey: ["lost-sessions"],
    queryFn: listLostSessions,
    refetchInterval: 30_000,
  });
}
```

```ts
// frontend/src/hooks/useLostSessionsScan.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { scanLostSessions } from "@/api/lost_sessions.api";

export function useLostSessionsScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: scanLostSessions,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
    },
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/LostSession.ts frontend/src/api/lost_sessions.api.ts frontend/src/hooks/useLostSessions.ts frontend/src/hooks/useLostSessionsScan.ts frontend/src/__tests__/api-lost-sessions.test.ts
git commit -m "feat(frontend): LostSession types + API + useLostSessions/Scan hooks"
```

---

## Task 4: Suggestion types + API + hook

**Files:**
- Create: `frontend/src/types/Suggestion.ts`, `frontend/src/api/suggestions.api.ts`, `frontend/src/hooks/useSuggestions.ts`, `frontend/src/__tests__/api-suggestions.test.ts`

- [ ] **Step 1: Verify backend shape**

```bash
grep -B 2 -A 20 "^class SuggestionFrontmatter\b\|^class Suggestion\b\|^SuggestionStatus\|^SuggestionOperation" claude_mnemos/state/ontology.py
grep -A 15 "list_suggestions_endpoint" claude_mnemos/daemon/routes/ontology.py
```

Confirm: `SuggestionStatus = Literal["pending", "approved", "rejected", "deferred"]`. `SuggestionOperation = Literal["merge_entities", "rename_entity", "delete_page"]`. Frontmatter has `id, created, operation, status, confidence, affected_pages (min_length=1), proposed_target | null, reason, applied_at | null, applied_op_id | null`. Suggestion = `{ frontmatter, body }`.

- [ ] **Step 2: Write the failing tests**

```ts
// frontend/src/__tests__/api-suggestions.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listSuggestions } from "../api/suggestions.api";

describe("suggestions api", () => {
  beforeEach(() => vi.spyOn(apiClient, "get"));
  afterEach(() => vi.restoreAllMocks());

  it("listSuggestions parses suggestions + total", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        suggestions: [
          {
            frontmatter: {
              id: "ont-2026-04-29-abc123",
              created: "2026-04-29T12:00:00Z",
              operation: "merge_entities",
              status: "pending",
              confidence: 0.85,
              affected_pages: ["wiki/entities/foo.md", "wiki/entities/foo-2.md"],
              proposed_target: "wiki/entities/foo.md",
              reason: "duplicate names",
              applied_at: null,
              applied_op_id: null,
            },
            body: "## Reasoning\n\nSame entity, different spellings.",
          },
        ],
        total: 1,
      },
    });
    const out = await listSuggestions("alpha");
    expect(out.suggestions[0]?.frontmatter.operation).toBe("merge_entities");
    expect(out.suggestions[0]?.body).toContain("Reasoning");
    expect(out.total).toBe(1);
  });

  it("listSuggestions passes status query", async () => {
    const spy = vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { suggestions: [], total: 0 },
    });
    await listSuggestions("alpha", { status: "approved" });
    expect(spy).toHaveBeenCalledWith(
      "/ontology/alpha/suggestions",
      expect.objectContaining({ params: { status: "approved" } }),
    );
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement**

```ts
// frontend/src/types/Suggestion.ts
import { z } from "zod";

export const SuggestionStatusSchema = z.enum([
  "pending",
  "approved",
  "rejected",
  "deferred",
]);
export type SuggestionStatus = z.infer<typeof SuggestionStatusSchema>;

export const SuggestionOperationSchema = z.enum([
  "merge_entities",
  "rename_entity",
  "delete_page",
]);
export type SuggestionOperation = z.infer<typeof SuggestionOperationSchema>;

export const SuggestionFrontmatterSchema = z.object({
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
});
export type SuggestionFrontmatter = z.infer<typeof SuggestionFrontmatterSchema>;

export const SuggestionSchema = z.object({
  frontmatter: SuggestionFrontmatterSchema,
  body: z.string(),
});
export type Suggestion = z.infer<typeof SuggestionSchema>;

export const SuggestionListResponseSchema = z.object({
  suggestions: z.array(SuggestionSchema),
  total: z.number().int().nonnegative(),
});
```

```ts
// frontend/src/api/suggestions.api.ts
import { apiClient } from "./client";
import {
  SuggestionListResponseSchema,
  type Suggestion,
} from "@/types/Suggestion";

export interface ListSuggestionsOptions {
  status?: string;
}

export async function listSuggestions(
  project: string,
  opts: ListSuggestionsOptions = {},
): Promise<{ suggestions: Suggestion[]; total: number }> {
  const params: Record<string, string> = {};
  if (opts.status) params.status = opts.status;
  const r = await apiClient.get(
    `/ontology/${encodeURIComponent(project)}/suggestions`,
    { params },
  );
  return SuggestionListResponseSchema.parse(r.data);
}
```

```ts
// frontend/src/hooks/useSuggestions.ts
import { useQuery } from "@tanstack/react-query";
import { listSuggestions, type ListSuggestionsOptions } from "@/api/suggestions.api";

export function useSuggestions(
  project: string | undefined,
  opts: ListSuggestionsOptions = {},
) {
  return useQuery({
    queryKey: ["suggestions", project, opts.status ?? null],
    queryFn: () => listSuggestions(project!, opts),
    enabled: !!project,
    refetchInterval: 5_000,
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/Suggestion.ts frontend/src/api/suggestions.api.ts frontend/src/hooks/useSuggestions.ts frontend/src/__tests__/api-suggestions.test.ts
git commit -m "feat(frontend): Suggestion types + API + useSuggestions hook"
```

---

## Task 5: Job types + dead-letter API + hooks

**Files:**
- Create: `frontend/src/types/Job.ts`, `frontend/src/api/dead_letter.api.ts`, `frontend/src/hooks/useDeadLetter.ts`, `frontend/src/hooks/useDeadLetterEntry.ts`, `frontend/src/__tests__/api-dead-letter.test.ts`

- [ ] **Step 1: Verify backend shape**

```bash
grep -B 1 -A 20 "^class Job\b\|^JobStatus\|^JobKind" claude_mnemos/state/jobs.py
grep -A 25 "list_dead_letter\|get_dead_letter\b" claude_mnemos/daemon/routes/dead_letter.py
```

Confirm `JobStatus` literal values exactly. Likely `Literal["queued", "running", "succeeded", "failed", "cancelled", "dead_letter"]` — adapt schema if any value differs. `Job` fields: `id, kind, payload, status, attempt, next_attempt_at, created_at, started_at | null, finished_at | null, error | null, error_traceback | null`. Cross-vault routes inject `project_name`. Response shape: `/dead-letter` returns `{ jobs: [...] }`; `/dead-letter/{id}` returns single Job dict.

- [ ] **Step 2: Write the failing tests**

```ts
// frontend/src/__tests__/api-dead-letter.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listDeadLetter, getDeadLetter } from "../api/dead_letter.api";

describe("dead-letter api", () => {
  beforeEach(() => vi.spyOn(apiClient, "get"));
  afterEach(() => vi.restoreAllMocks());

  it("listDeadLetter parses cross-vault jobs", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        jobs: [
          {
            id: "j1",
            kind: "ingest",
            payload: { transcript_path: "/x.md" },
            status: "dead_letter",
            attempt: 4,
            next_attempt_at: "2026-04-29T12:00:00Z",
            created_at: "2026-04-29T11:00:00Z",
            started_at: "2026-04-29T11:01:00Z",
            finished_at: "2026-04-29T11:05:00Z",
            error: "Rate limit",
            error_traceback: "Traceback (most recent call last):\n  ...",
            project_name: "alpha",
          },
        ],
      },
    });
    const out = await listDeadLetter();
    expect(out[0]?.project_name).toBe("alpha");
    expect(out[0]?.attempt).toBe(4);
  });

  it("getDeadLetter parses single job", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        id: "j1",
        kind: "ingest",
        payload: {},
        status: "dead_letter",
        attempt: 4,
        next_attempt_at: "2026-04-29T12:00:00Z",
        created_at: "2026-04-29T11:00:00Z",
        started_at: null,
        finished_at: null,
        error: null,
        error_traceback: null,
        project_name: "alpha",
      },
    });
    const j = await getDeadLetter("j1");
    expect(j.id).toBe("j1");
    expect(j.project_name).toBe("alpha");
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement**

```ts
// frontend/src/types/Job.ts
import { z } from "zod";

export const JobKindSchema = z.string();
export type JobKind = z.infer<typeof JobKindSchema>;

export const JobStatusSchema = z.enum([
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "dead_letter",
]);
export type JobStatus = z.infer<typeof JobStatusSchema>;

export const JobSchema = z.object({
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
  project_name: z.string(),
});
export type Job = z.infer<typeof JobSchema>;

export const DeadLetterListResponseSchema = z.object({
  jobs: z.array(JobSchema),
});
```

```ts
// frontend/src/api/dead_letter.api.ts
import { apiClient } from "./client";
import {
  DeadLetterListResponseSchema,
  JobSchema,
  type Job,
} from "@/types/Job";

export interface ListDeadLetterOptions {
  limit?: number;
  offset?: number;
}

export async function listDeadLetter(
  opts: ListDeadLetterOptions = {},
): Promise<Job[]> {
  const params: Record<string, number> = {};
  if (opts.limit !== undefined) params.limit = opts.limit;
  if (opts.offset !== undefined) params.offset = opts.offset;
  const r = await apiClient.get("/dead-letter", { params });
  return DeadLetterListResponseSchema.parse(r.data).jobs;
}

export async function getDeadLetter(jobId: string): Promise<Job> {
  const r = await apiClient.get(`/dead-letter/${encodeURIComponent(jobId)}`);
  return JobSchema.parse(r.data);
}
```

```ts
// frontend/src/hooks/useDeadLetter.ts
import { useQuery } from "@tanstack/react-query";
import { listDeadLetter, type ListDeadLetterOptions } from "@/api/dead_letter.api";

export function useDeadLetter(opts: ListDeadLetterOptions = {}) {
  return useQuery({
    queryKey: ["dead-letter", opts.limit ?? null, opts.offset ?? null],
    queryFn: () => listDeadLetter(opts),
    refetchInterval: 5_000,
  });
}
```

```ts
// frontend/src/hooks/useDeadLetterEntry.ts
import { useQuery } from "@tanstack/react-query";
import { getDeadLetter } from "@/api/dead_letter.api";

export function useDeadLetterEntry(jobId: string | undefined) {
  return useQuery({
    queryKey: ["dead-letter-entry", jobId],
    queryFn: () => getDeadLetter(jobId!),
    enabled: !!jobId,
    refetchInterval: 5_000,
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/Job.ts frontend/src/api/dead_letter.api.ts frontend/src/hooks/useDeadLetter.ts frontend/src/hooks/useDeadLetterEntry.ts frontend/src/__tests__/api-dead-letter.test.ts
git commit -m "feat(frontend): Job types + dead-letter API + hooks"
```

---

## Task 6: ProjectBadge + KindBadge widgets

**Files:**
- Create: `frontend/src/components/widgets/ProjectBadge.tsx`, `frontend/src/components/widgets/KindBadge.tsx`, `frontend/src/__tests__/ProjectBadge.test.tsx`, `frontend/src/__tests__/KindBadge.test.tsx`

- [ ] **Step 1: Failing tests**

```tsx
// frontend/src/__tests__/ProjectBadge.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { ProjectBadge } from "../components/widgets/ProjectBadge";

describe("ProjectBadge", () => {
  it("renders project name", () => {
    render(
      <MemoryRouter>
        <ProjectBadge name="alpha" />
      </MemoryRouter>,
    );
    expect(screen.getByText("alpha")).toBeInTheDocument();
  });

  it("links to project view by default", () => {
    render(
      <MemoryRouter>
        <ProjectBadge name="alpha" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "alpha" })).toHaveAttribute(
      "href",
      "/project/alpha",
    );
  });

  it("renders as plain span when linkTo=false", () => {
    render(<ProjectBadge name="alpha" linkTo={false} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("alpha")).toBeInTheDocument();
  });
});
```

```tsx
// frontend/src/__tests__/KindBadge.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { KindBadge } from "../components/widgets/KindBadge";

describe("KindBadge", () => {
  it("renders the label", () => {
    render(<KindBadge label="pre-op" tone="amber" />);
    expect(screen.getByText("pre-op")).toBeInTheDocument();
  });

  it("applies the tone via data-tone", () => {
    render(<KindBadge label="daily" tone="blue" />);
    expect(screen.getByText("daily")).toHaveAttribute("data-tone", "blue");
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/widgets/ProjectBadge.tsx
import { Link } from "react-router";
import { cn } from "@/lib/utils";

interface Props {
  name: string;
  linkTo?: boolean;
  className?: string;
}

export function ProjectBadge({ name, linkTo = true, className }: Props) {
  const baseClasses = cn(
    "inline-flex items-center rounded-md bg-[hsl(var(--muted))] px-1.5 py-0.5 font-mono text-xs text-[hsl(var(--muted-foreground))]",
    className,
  );
  if (!linkTo) return <span className={baseClasses}>{name}</span>;
  return (
    <Link
      to={`/project/${encodeURIComponent(name)}`}
      className={cn(baseClasses, "hover:bg-[hsl(var(--accent))] hover:underline")}
    >
      {name}
    </Link>
  );
}
```

```tsx
// frontend/src/components/widgets/KindBadge.tsx
import { cn } from "@/lib/utils";

export type KindTone = "amber" | "blue" | "emerald" | "zinc" | "rose";

const TONES: Record<KindTone, string> = {
  amber:   "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  blue:    "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  emerald: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  zinc:    "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  rose:    "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
};

interface Props {
  label: string;
  tone: KindTone;
  className?: string;
}

export function KindBadge({ label, tone, className }: Props) {
  return (
    <span
      data-tone={tone}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
    >
      {label}
    </span>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/ProjectBadge.tsx frontend/src/components/widgets/KindBadge.tsx frontend/src/__tests__/ProjectBadge.test.tsx frontend/src/__tests__/KindBadge.test.tsx
git commit -m "feat(frontend): ProjectBadge + KindBadge widgets"
```

---

## Task 7: TrashRow widget + Trash page

**Files:**
- Create: `frontend/src/components/widgets/TrashRow.tsx`, `frontend/src/pages/Trash.tsx`, `frontend/src/__tests__/Trash.test.tsx`
- Modify: `frontend/public/locales/{uk,ru,en}.json` (add `trash.*` keys)

- [ ] **Step 1: Add locale keys**

Append to each locale under top-level `trash`:

```json
"trash": {
  "title": "<localised>",
  "deleted_at": "<localised>",
  "operation_type": "<localised>",
  "restorable": "<localised>",
  "blocked": "<localised>",
  "restore_disabled": "<localised>",
  "delete_permanently_disabled": "<localised>",
  "no_entries": "<localised>",
  "showing_n": "{{count}} entries"
}
```

UK/RU/EN per established style.

- [ ] **Step 2: TrashRow component**

```tsx
// frontend/src/components/widgets/TrashRow.tsx
import { useTranslation } from "react-i18next";
import { Trash2, RotateCcw, AlertTriangle, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { TrashEntry } from "@/types/Trash";

export function TrashRow({ entry: e }: { entry: TrashEntry }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono">
            {e.page_basename ?? e.original_path ?? e.trash_id}
          </span>
          {e.operation_type && (
            <span className="rounded bg-[hsl(var(--muted))] px-1.5 py-0.5 text-xs text-[hsl(var(--muted-foreground))]">
              {e.operation_type}
            </span>
          )}
        </div>
        <div className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("trash.deleted_at")}: {e.deleted_at}
        </div>
        {!e.restorable && e.restore_blocked_reason && (
          <div className="mt-1 flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400">
            <AlertTriangle className="h-3 w-3" />
            <span>{t("trash.blocked")}: {e.restore_blocked_reason}</span>
          </div>
        )}
      </div>
      <div
        className={cn(
          "flex items-center gap-1 text-xs",
          e.restorable ? "text-emerald-600" : "text-zinc-500",
        )}
      >
        {e.restorable ? <Check className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
        <span>{t("trash.restorable")}</span>
      </div>
      <Button size="sm" variant="outline" disabled title={t("trash.restore_disabled")}>
        <RotateCcw className="mr-1 h-3 w-3" />
        {t("trash.restore_disabled")}
      </Button>
      <Button size="sm" variant="outline" disabled title={t("trash.delete_permanently_disabled")}>
        <Trash2 className="mr-1 h-3 w-3" />
        {t("trash.delete_permanently_disabled")}
      </Button>
    </div>
  );
}
```

- [ ] **Step 3: Failing test**

```tsx
// frontend/src/__tests__/Trash.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Trash } from "../pages/Trash";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    trash: {
      title: "Trash",
      deleted_at: "deleted at",
      operation_type: "op",
      restorable: "Restorable",
      blocked: "Blocked",
      restore_disabled: "Restore (#14c)",
      delete_permanently_disabled: "Delete (#14c)",
      no_entries: "No trash",
      showing_n: "{{count}} entries",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/project/alpha/trash"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/trash" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Trash", () => {
  it("renders entries", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        entries: [
          {
            trash_id: "t1",
            deleted_at: "2026-04-29T12:00:00Z",
            original_path: "wiki/concepts/foo.md",
            operation_type: "manual_delete",
            page_basename: "foo",
            restorable: true,
            restore_blocked_reason: null,
          },
        ],
        total: 1,
      },
    });
    render(wrap(<Trash />));
    await waitFor(() => expect(screen.getByText("foo")).toBeInTheDocument());
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { entries: [], total: 0 } });
    render(wrap(<Trash />));
    await waitFor(() => expect(screen.getByText(/no trash/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 4: Run** → FAIL.

- [ ] **Step 5: Implement Trash page**

```tsx
// frontend/src/pages/Trash.tsx
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useTrash } from "@/hooks/useTrash";
import { Skeleton } from "@/components/ui/skeleton";
import { TrashRow } from "@/components/widgets/TrashRow";

export function Trash() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const trashQuery = useTrash(project);

  if (!project) return null;
  if (trashQuery.isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    );
  }

  const entries = trashQuery.data?.entries ?? [];
  if (entries.length === 0) {
    return (
      <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
        {t("trash.no_entries")}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="text-xs text-[hsl(var(--muted-foreground))]">
        {t("trash.showing_n", { count: entries.length })}
      </div>
      {entries.map((e) => (
        <TrashRow key={e.trash_id} entry={e} />
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Run** → PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/widgets/TrashRow.tsx frontend/src/pages/Trash.tsx frontend/src/__tests__/Trash.test.tsx frontend/public/locales/
git commit -m "feat(frontend): TrashRow widget + Trash page"
```

---

## Task 8: SnapshotCard + SnapshotFilters + Snapshots page

**Files:**
- Create: `frontend/src/components/widgets/SnapshotCard.tsx`, `frontend/src/components/filters/SnapshotFilters.tsx`, `frontend/src/pages/Snapshots.tsx`, `frontend/src/__tests__/Snapshots.test.tsx`
- Modify: locale files (add `snapshots.*`)

- [ ] **Step 1: Add locale keys**

```json
"snapshots": {
  "title": "<localised>",
  "kind": { "pre-op": "<localised>", "daily": "<localised>", "manual": "<localised>", "all": "<localised>" },
  "filter_kind": "<localised>",
  "label": "<localised>",
  "op_id": "<localised>",
  "op_type": "<localised>",
  "size": "<localised>",
  "no_snapshots": "<localised>",
  "showing_n": "{{count}} snapshots",
  "restore_disabled": "<localised>",
  "delete_disabled": "<localised>"
}
```

- [ ] **Step 2: SnapshotFilters**

```tsx
// frontend/src/components/filters/SnapshotFilters.tsx
import { useTranslation } from "react-i18next";
import type { SnapshotKind } from "@/types/Snapshot";

export type KindFilter = SnapshotKind | "all";

interface Props {
  value: KindFilter;
  onChange: (v: KindFilter) => void;
}

const KINDS: KindFilter[] = ["all", "pre-op", "daily", "manual"];

export function SnapshotFilters({ value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-[hsl(var(--muted-foreground))]">
        {t("snapshots.filter_kind")}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as KindFilter)}
        className="rounded-md border bg-[hsl(var(--background))] px-2 py-1"
      >
        {KINDS.map((k) => (
          <option key={k} value={k}>
            {t(`snapshots.kind.${k}`)}
          </option>
        ))}
      </select>
    </div>
  );
}
```

- [ ] **Step 3: SnapshotCard**

```tsx
// frontend/src/components/widgets/SnapshotCard.tsx
import { useTranslation } from "react-i18next";
import { RotateCcw, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { KindBadge, type KindTone } from "./KindBadge";
import type { SnapshotInfo, SnapshotKind } from "@/types/Snapshot";

const KIND_TONE: Record<SnapshotKind, KindTone> = {
  "pre-op": "amber",
  daily: "blue",
  manual: "emerald",
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function SnapshotCard({ snapshot: s }: { snapshot: SnapshotInfo }) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <span className="break-all font-mono text-xs">{s.name}</span>
          <KindBadge label={t(`snapshots.kind.${s.kind}`)} tone={KIND_TONE[s.kind]} />
        </div>
      </CardHeader>
      <CardContent className="space-y-1 text-xs">
        <div className="text-[hsl(var(--muted-foreground))]">{s.timestamp}</div>
        {s.label && (
          <div>
            <span className="text-[hsl(var(--muted-foreground))]">{t("snapshots.label")}: </span>
            <span>{s.label}</span>
          </div>
        )}
        {s.op_id && (
          <div className="text-[hsl(var(--muted-foreground))]">
            {t("snapshots.op_id")}: <code>{s.op_id}</code>
            {s.op_type && (
              <>
                {" · "}{t("snapshots.op_type")}: <code>{s.op_type}</code>
              </>
            )}
          </div>
        )}
        <div className="text-[hsl(var(--muted-foreground))]">
          {t("snapshots.size")}: {formatBytes(s.size_bytes)}
        </div>
        <div className="flex items-center gap-2 pt-2">
          <Button size="sm" variant="outline" disabled title={t("snapshots.restore_disabled")}>
            <RotateCcw className="mr-1 h-3 w-3" />
            {t("snapshots.restore_disabled")}
          </Button>
          <Button size="sm" variant="outline" disabled title={t("snapshots.delete_disabled")}>
            <Trash2 className="mr-1 h-3 w-3" />
            {t("snapshots.delete_disabled")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Failing tests**

```tsx
// frontend/src/__tests__/Snapshots.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Snapshots } from "../pages/Snapshots";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    snapshots: {
      title: "Snapshots",
      kind: { "pre-op": "Pre-op", daily: "Daily", manual: "Manual", all: "All" },
      filter_kind: "Kind",
      label: "label", op_id: "op", op_type: "type", size: "size",
      no_snapshots: "No snapshots", showing_n: "{{count}} snapshots",
      restore_disabled: "Restore (#14c)", delete_disabled: "Delete (#14c)",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/project/alpha/snapshots"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/snapshots" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const SAMPLE = [
  {
    name: "pre-op-2026-04-29-12-00-00-abc-ingest",
    kind: "pre-op",
    timestamp: "2026-04-29T12:00:00Z",
    op_id: "abc",
    op_type: "ingest",
    label: null,
    size_bytes: 1024,
    path: ".backups/pre-op-2026-04-29-12-00-00-abc-ingest",
  },
  {
    name: "daily-2026-04-29-04-00-00",
    kind: "daily",
    timestamp: "2026-04-29T04:00:00Z",
    op_id: null,
    op_type: null,
    label: null,
    size_bytes: 2048,
    path: ".backups/daily-2026-04-29-04-00-00",
  },
];

describe("Snapshots", () => {
  it("renders cards from list", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { snapshots: SAMPLE } });
    render(wrap(<Snapshots />));
    await waitFor(() =>
      expect(
        screen.getByText("pre-op-2026-04-29-12-00-00-abc-ingest"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("daily-2026-04-29-04-00-00")).toBeInTheDocument();
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { snapshots: [] } });
    render(wrap(<Snapshots />));
    await waitFor(() =>
      expect(screen.getByText(/no snapshots/i)).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 5: Run** → FAIL.

- [ ] **Step 6: Implement Snapshots page**

```tsx
// frontend/src/pages/Snapshots.tsx
import { useState, useMemo } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useSnapshots } from "@/hooks/useSnapshots";
import { Skeleton } from "@/components/ui/skeleton";
import { SnapshotCard } from "@/components/widgets/SnapshotCard";
import { SnapshotFilters, type KindFilter } from "@/components/filters/SnapshotFilters";

export function Snapshots() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const [kind, setKind] = useState<KindFilter>("all");
  const snapshotsQuery = useSnapshots(project);

  const filtered = useMemo(() => {
    const all = snapshotsQuery.data ?? [];
    if (kind === "all") return all;
    return all.filter((s) => s.kind === kind);
  }, [snapshotsQuery.data, kind]);

  if (!project) return null;
  if (snapshotsQuery.isLoading) {
    return (
      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}
      </div>
    );
  }

  if ((snapshotsQuery.data ?? []).length === 0) {
    return (
      <div className="space-y-3">
        <SnapshotFilters value={kind} onChange={setKind} />
        <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
          {t("snapshots.no_snapshots")}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <SnapshotFilters value={kind} onChange={setKind} />
      <div className="text-xs text-[hsl(var(--muted-foreground))]">
        {t("snapshots.showing_n", { count: filtered.length })}
      </div>
      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
        {filtered.map((s) => <SnapshotCard key={s.name} snapshot={s} />)}
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Run** → PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/widgets/SnapshotCard.tsx frontend/src/components/filters/SnapshotFilters.tsx frontend/src/pages/Snapshots.tsx frontend/src/__tests__/Snapshots.test.tsx frontend/public/locales/
git commit -m "feat(frontend): SnapshotCard + SnapshotFilters + Snapshots page"
```

---

## Task 9: LostSessionRow + LostSessions page

**Files:**
- Create: `frontend/src/components/widgets/LostSessionRow.tsx`, `frontend/src/pages/LostSessions.tsx`, `frontend/src/__tests__/LostSessions.test.tsx`
- Modify: locale files (add `lost_sessions.*`)

- [ ] **Step 1: Add locale keys**

```json
"lost_sessions": {
  "title": "<localised>",
  "scan": "<localised>",
  "scanning": "<localised>",
  "session_id": "<localised>",
  "sha": "<localised>",
  "size": "<localised>",
  "mtime": "<localised>",
  "transcript": "<localised>",
  "no_lost": "<localised>",
  "showing_n": "{{count}} sessions",
  "import_disabled": "<localised>",
  "ignore_disabled": "<localised>"
}
```

- [ ] **Step 2: Implement LostSessionRow**

```tsx
// frontend/src/components/widgets/LostSessionRow.tsx
import { useTranslation } from "react-i18next";
import { Download, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectBadge } from "./ProjectBadge";
import type { LostSession } from "@/types/LostSession";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function LostSessionRow({ session: s }: { session: LostSession }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm">
      <ProjectBadge name={s.project_name} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="truncate font-mono text-xs" title={s.session_id}>
            {s.session_id.slice(0, 12)}…
          </span>
          <span className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("lost_sessions.sha")}: <code>{s.sha.slice(0, 8)}</code>
          </span>
        </div>
        <div className="text-xs text-[hsl(var(--muted-foreground))]" title={s.transcript_path}>
          {formatBytes(s.size_bytes)} · {s.mtime}
        </div>
      </div>
      <Button size="sm" variant="outline" disabled title={t("lost_sessions.import_disabled")}>
        <Download className="mr-1 h-3 w-3" />
        {t("lost_sessions.import_disabled")}
      </Button>
      <Button size="sm" variant="outline" disabled title={t("lost_sessions.ignore_disabled")}>
        <EyeOff className="mr-1 h-3 w-3" />
        {t("lost_sessions.ignore_disabled")}
      </Button>
    </div>
  );
}
```

- [ ] **Step 3: Failing test**

```tsx
// frontend/src/__tests__/LostSessions.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { LostSessions } from "../pages/LostSessions";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    lost_sessions: {
      title: "Lost sessions",
      scan: "Scan", scanning: "Scanning...",
      session_id: "session_id", sha: "sha", size: "size", mtime: "mtime",
      transcript: "transcript",
      no_lost: "All accounted for",
      showing_n: "{{count}} sessions",
      import_disabled: "Import (#14c)", ignore_disabled: "Ignore (#14c)",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter><QueryClientProvider client={qc}>{ui}</QueryClientProvider></MemoryRouter>
  );
}

describe("LostSessions", () => {
  it("renders sessions with project badges", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        sessions: [
          {
            session_id: "abc-very-long-id-string",
            transcript_path: "/x.md",
            sha: "deadbeefcafe",
            size_bytes: 1024,
            mtime: "2026-04-29T12:00:00Z",
            project_name: "alpha",
          },
        ],
        total: 1,
      },
    });
    render(wrap(<LostSessions />));
    await waitFor(() => expect(screen.getByText("alpha")).toBeInTheDocument());
  });

  it("Scan button triggers POST /lost-sessions/scan and refetch", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { sessions: [], total: 0 } });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { sessions: [], total: 0 } });
    const user = userEvent.setup();
    render(wrap(<LostSessions />));
    await waitFor(() => expect(screen.getByRole("button", { name: /scan/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /scan/i }));
    expect(post).toHaveBeenCalledWith("/lost-sessions/scan");
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { sessions: [], total: 0 } });
    render(wrap(<LostSessions />));
    await waitFor(() => expect(screen.getByText(/all accounted for/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 4: Run** → FAIL.

- [ ] **Step 5: Implement LostSessions page**

```tsx
// frontend/src/pages/LostSessions.tsx
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLostSessions } from "@/hooks/useLostSessions";
import { useLostSessionsScan } from "@/hooks/useLostSessionsScan";
import { LostSessionRow } from "@/components/widgets/LostSessionRow";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";

export function LostSessions() {
  const { t } = useTranslation();
  const lostQuery = useLostSessions();
  const scan = useLostSessionsScan();

  if (lostQuery.isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    );
  }
  if (lostQuery.isError) {
    return <DaemonDownAlert error={lostQuery.error} />;
  }

  const sessions = lostQuery.data?.sessions ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("lost_sessions.title")}</h1>
        <Button
          size="sm"
          variant="outline"
          onClick={() => scan.mutate()}
          disabled={scan.isPending}
        >
          <RefreshCw className={`mr-1 h-3 w-3 ${scan.isPending ? "animate-spin" : ""}`} />
          {scan.isPending ? t("lost_sessions.scanning") : t("lost_sessions.scan")}
        </Button>
      </div>

      {sessions.length === 0 ? (
        <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
          {t("lost_sessions.no_lost")}
        </div>
      ) : (
        <>
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("lost_sessions.showing_n", { count: sessions.length })}
          </div>
          <div className="space-y-2">
            {sessions.map((s) => (
              <LostSessionRow key={`${s.project_name}:${s.session_id}`} session={s} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Run** → PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/widgets/LostSessionRow.tsx frontend/src/pages/LostSessions.tsx frontend/src/__tests__/LostSessions.test.tsx frontend/public/locales/
git commit -m "feat(frontend): LostSessions page with cross-vault scan + active Scan button"
```

---

## Task 10: SuggestionCard + SuggestionFilters + Suggestions page

**Files:**
- Create: `frontend/src/components/widgets/SuggestionCard.tsx`, `frontend/src/components/filters/SuggestionFilters.tsx`, `frontend/src/pages/Suggestions.tsx`, `frontend/src/__tests__/Suggestions.test.tsx`
- Modify: locale files (add `suggestions.*`)

- [ ] **Step 1: Add locale keys**

```json
"suggestions": {
  "title": "<localised>",
  "filter_status": "<localised>",
  "status": {
    "pending": "<localised>",
    "approved": "<localised>",
    "rejected": "<localised>",
    "deferred": "<localised>",
    "all": "<localised>"
  },
  "operation": {
    "merge_entities": "<localised>",
    "rename_entity": "<localised>",
    "delete_page": "<localised>"
  },
  "confidence": "<localised>",
  "affected_pages": "<localised>",
  "proposed_target": "<localised>",
  "reason": "<localised>",
  "body_header": "<localised>",
  "no_suggestions": "<localised>",
  "showing_n": "{{count}} suggestions",
  "approve_disabled": "<localised>",
  "reject_disabled": "<localised>",
  "defer_disabled": "<localised>"
}
```

- [ ] **Step 2: SuggestionFilters**

```tsx
// frontend/src/components/filters/SuggestionFilters.tsx
import { useTranslation } from "react-i18next";
import type { SuggestionStatus } from "@/types/Suggestion";

export type StatusFilter = SuggestionStatus | "all";

const STATUSES: StatusFilter[] = ["pending", "approved", "rejected", "deferred", "all"];

interface Props {
  value: StatusFilter;
  onChange: (v: StatusFilter) => void;
}

export function SuggestionFilters({ value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-[hsl(var(--muted-foreground))]">
        {t("suggestions.filter_status")}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as StatusFilter)}
        className="rounded-md border bg-[hsl(var(--background))] px-2 py-1"
      >
        {STATUSES.map((s) => (
          <option key={s} value={s}>{t(`suggestions.status.${s}`)}</option>
        ))}
      </select>
    </div>
  );
}
```

- [ ] **Step 3: SuggestionCard**

```tsx
// frontend/src/components/widgets/SuggestionCard.tsx
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Check, X, Clock } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ConfidenceBar } from "./ConfidenceBar";
import { KindBadge, type KindTone } from "./KindBadge";
import { MarkdownView } from "@/components/markdown/MarkdownView";
import { pageHref } from "@/lib/pageHref";
import type { Suggestion, SuggestionOperation, SuggestionStatus } from "@/types/Suggestion";

const OP_TONE: Record<SuggestionOperation, KindTone> = {
  merge_entities: "blue",
  rename_entity: "amber",
  delete_page: "rose",
};

const STATUS_TONE: Record<SuggestionStatus, KindTone> = {
  pending: "amber",
  approved: "emerald",
  rejected: "rose",
  deferred: "zinc",
};

interface Props {
  project: string;
  suggestion: Suggestion;
}

export function SuggestionCard({ project, suggestion: s }: Props) {
  const { t } = useTranslation();
  const fm = s.frontmatter;
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <span className="font-mono text-xs">{fm.id}</span>
          <div className="flex items-center gap-1">
            <KindBadge label={t(`suggestions.operation.${fm.operation}`)} tone={OP_TONE[fm.operation]} />
            <KindBadge label={t(`suggestions.status.${fm.status}`)} tone={STATUS_TONE[fm.status]} />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center gap-3">
          <span className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("suggestions.confidence")}:
          </span>
          <ConfidenceBar value={fm.confidence} />
        </div>

        <div>
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("suggestions.affected_pages")}:
          </div>
          <ul className="mt-1 space-y-0.5 text-sm">
            {fm.affected_pages.map((p) => (
              <li key={p}>
                <Link to={pageHref(project, p)} className="text-[hsl(var(--primary))] hover:underline">
                  {p}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        {fm.proposed_target && (
          <div className="text-sm">
            <span className="text-[hsl(var(--muted-foreground))]">
              {t("suggestions.proposed_target")}:
            </span>{" "}
            <Link to={pageHref(project, fm.proposed_target)} className="text-[hsl(var(--primary))] hover:underline">
              {fm.proposed_target}
            </Link>
          </div>
        )}

        {fm.reason && (
          <div className="rounded-md bg-[hsl(var(--muted))] px-3 py-2 text-sm italic">
            {t("suggestions.reason")}: {fm.reason}
          </div>
        )}

        {s.body && (
          <details>
            <summary className="cursor-pointer text-xs text-[hsl(var(--muted-foreground))]">
              {t("suggestions.body_header")}
            </summary>
            <div className="mt-2">
              <MarkdownView body={s.body} />
            </div>
          </details>
        )}

        <div className="flex items-center gap-2 pt-1">
          <Button size="sm" variant="outline" disabled title={t("suggestions.approve_disabled")}>
            <Check className="mr-1 h-3 w-3" />
            {t("suggestions.approve_disabled")}
          </Button>
          <Button size="sm" variant="outline" disabled title={t("suggestions.reject_disabled")}>
            <X className="mr-1 h-3 w-3" />
            {t("suggestions.reject_disabled")}
          </Button>
          <Button size="sm" variant="outline" disabled title={t("suggestions.defer_disabled")}>
            <Clock className="mr-1 h-3 w-3" />
            {t("suggestions.defer_disabled")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Failing test**

```tsx
// frontend/src/__tests__/Suggestions.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Suggestions } from "../pages/Suggestions";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    suggestions: {
      title: "Suggestions",
      filter_status: "Status",
      status: { pending: "Pending", approved: "Approved", rejected: "Rejected", deferred: "Deferred", all: "All" },
      operation: { merge_entities: "Merge", rename_entity: "Rename", delete_page: "Delete" },
      confidence: "Confidence", affected_pages: "Affected", proposed_target: "Target",
      reason: "Reason", body_header: "Reasoning",
      no_suggestions: "No suggestions",
      showing_n: "{{count}} suggestions",
      approve_disabled: "Approve (#14c)", reject_disabled: "Reject (#14c)", defer_disabled: "Defer (#14c)",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/project/alpha/suggestions"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/suggestions" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Suggestions", () => {
  it("renders suggestions", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        suggestions: [
          {
            frontmatter: {
              id: "ont-2026-04-29-abc",
              created: "2026-04-29T12:00:00Z",
              operation: "merge_entities",
              status: "pending",
              confidence: 0.85,
              affected_pages: ["wiki/x.md", "wiki/y.md"],
              proposed_target: "wiki/x.md",
              reason: "duplicate",
              applied_at: null,
              applied_op_id: null,
            },
            body: "## Reasoning\n\ndetails",
          },
        ],
        total: 1,
      },
    });
    render(wrap(<Suggestions />));
    await waitFor(() => expect(screen.getByText("ont-2026-04-29-abc")).toBeInTheDocument());
    expect(screen.getByText("Merge")).toBeInTheDocument();
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { suggestions: [], total: 0 } });
    render(wrap(<Suggestions />));
    await waitFor(() => expect(screen.getByText(/no suggestions/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 5: Run** → FAIL.

- [ ] **Step 6: Implement Suggestions page**

```tsx
// frontend/src/pages/Suggestions.tsx
import { useState } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useSuggestions } from "@/hooks/useSuggestions";
import { Skeleton } from "@/components/ui/skeleton";
import { SuggestionCard } from "@/components/widgets/SuggestionCard";
import { SuggestionFilters, type StatusFilter } from "@/components/filters/SuggestionFilters";

export function Suggestions() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const [status, setStatus] = useState<StatusFilter>("pending");
  const suggestionsQuery = useSuggestions(project, { status });

  if (!project) return null;
  if (suggestionsQuery.isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2].map((i) => <Skeleton key={i} className="h-48" />)}
      </div>
    );
  }

  const items = suggestionsQuery.data?.suggestions ?? [];
  return (
    <div className="space-y-3">
      <SuggestionFilters value={status} onChange={setStatus} />
      {items.length === 0 ? (
        <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
          {t("suggestions.no_suggestions")}
        </div>
      ) : (
        <>
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("suggestions.showing_n", { count: items.length })}
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {items.map((s) => (
              <SuggestionCard
                key={s.frontmatter.id}
                project={project}
                suggestion={s}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Run** → PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/widgets/SuggestionCard.tsx frontend/src/components/filters/SuggestionFilters.tsx frontend/src/pages/Suggestions.tsx frontend/src/__tests__/Suggestions.test.tsx frontend/public/locales/
git commit -m "feat(frontend): SuggestionCard + filters + Suggestions page"
```

---

## Task 11: DeadLetterRow widget + DeadLetter page

**Files:**
- Create: `frontend/src/components/widgets/DeadLetterRow.tsx`, `frontend/src/pages/DeadLetter.tsx`, `frontend/src/__tests__/DeadLetter.test.tsx`
- Modify: locale files (add `dead_letter.*`)

- [ ] **Step 1: Add locale keys**

```json
"dead_letter": {
  "title": "<localised>",
  "no_failed": "<localised>",
  "showing_n": "{{count}} jobs",
  "kind": "<localised>",
  "attempt": "<localised>",
  "attempt_n_of_m": "Attempt {{n}}/{{max}}",
  "finished_at": "<localised>",
  "error": "<localised>",
  "traceback": "<localised>",
  "payload": "<localised>",
  "retry_disabled": "<localised>",
  "dismiss_disabled": "<localised>",
  "view_details": "<localised>",
  "not_found_title": "<localised>",
  "not_found_hint": "<localised>"
}
```

- [ ] **Step 2: DeadLetterRow**

```tsx
// frontend/src/components/widgets/DeadLetterRow.tsx
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { ChevronRight, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectBadge } from "./ProjectBadge";
import type { Job } from "@/types/Job";

const MAX_ATTEMPTS = 4;

export function DeadLetterRow({ job: j }: { job: Job }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm">
      <ProjectBadge name={j.project_name} />
      <span className="rounded bg-[hsl(var(--muted))] px-1.5 py-0.5 text-xs">
        {j.kind}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-xs" title={j.id}>
            {j.id.slice(0, 8)}…
          </span>
          <span className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("dead_letter.attempt_n_of_m", { n: j.attempt, max: MAX_ATTEMPTS })}
          </span>
          {j.finished_at && (
            <span className="text-xs text-[hsl(var(--muted-foreground))]">
              · {j.finished_at}
            </span>
          )}
        </div>
        {j.error && (
          <div className="truncate text-xs text-red-700 dark:text-red-400" title={j.error}>
            {j.error}
          </div>
        )}
      </div>
      <Button asChild size="sm" variant="ghost">
        <Link to={`/dead-letter/${encodeURIComponent(j.id)}`}>
          {t("dead_letter.view_details")}
          <ChevronRight className="ml-1 h-3 w-3" />
        </Link>
      </Button>
      <Button size="sm" variant="outline" disabled title={t("dead_letter.retry_disabled")}>
        <RotateCcw className="mr-1 h-3 w-3" />
        {t("dead_letter.retry_disabled")}
      </Button>
      <Button size="sm" variant="outline" disabled title={t("dead_letter.dismiss_disabled")}>
        <X className="mr-1 h-3 w-3" />
        {t("dead_letter.dismiss_disabled")}
      </Button>
    </div>
  );
}
```

- [ ] **Step 3: Failing test**

```tsx
// frontend/src/__tests__/DeadLetter.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { DeadLetter } from "../pages/DeadLetter";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    dead_letter: {
      title: "Failed jobs", no_failed: "No failed jobs",
      showing_n: "{{count}} jobs", attempt_n_of_m: "Attempt {{n}}/{{max}}",
      finished_at: "finished",
      retry_disabled: "Retry (#14c)", dismiss_disabled: "Dismiss (#14c)",
      view_details: "Detail",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter><QueryClientProvider client={qc}>{ui}</QueryClientProvider></MemoryRouter>
  );
}

describe("DeadLetter", () => {
  it("renders job rows with project badge", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        jobs: [
          {
            id: "j1-very-long-id",
            kind: "ingest",
            payload: {},
            status: "dead_letter",
            attempt: 4,
            next_attempt_at: "2026-04-29T12:00:00Z",
            created_at: "2026-04-29T11:00:00Z",
            started_at: "2026-04-29T11:01:00Z",
            finished_at: "2026-04-29T11:05:00Z",
            error: "Rate limit exceeded",
            error_traceback: null,
            project_name: "alpha",
          },
        ],
      },
    });
    render(wrap(<DeadLetter />));
    await waitFor(() => expect(screen.getByText("alpha")).toBeInTheDocument());
    expect(screen.getByText(/Rate limit/)).toBeInTheDocument();
  });

  it("shows empty state", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { jobs: [] } });
    render(wrap(<DeadLetter />));
    await waitFor(() => expect(screen.getByText(/no failed jobs/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 4: Run** → FAIL.

- [ ] **Step 5: Implement DeadLetter page**

```tsx
// frontend/src/pages/DeadLetter.tsx
import { useTranslation } from "react-i18next";
import { useDeadLetter } from "@/hooks/useDeadLetter";
import { Skeleton } from "@/components/ui/skeleton";
import { DeadLetterRow } from "@/components/widgets/DeadLetterRow";

export function DeadLetter() {
  const { t } = useTranslation();
  const dlQuery = useDeadLetter({ limit: 200 });

  if (dlQuery.isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    );
  }

  const jobs = dlQuery.data ?? [];
  if (jobs.length === 0) {
    return (
      <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
        {t("dead_letter.no_failed")}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">{t("dead_letter.title")}</h1>
      <div className="text-xs text-[hsl(var(--muted-foreground))]">
        {t("dead_letter.showing_n", { count: jobs.length })}
      </div>
      <div className="space-y-2">
        {jobs.map((j) => <DeadLetterRow key={j.id} job={j} />)}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Run** → PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/widgets/DeadLetterRow.tsx frontend/src/pages/DeadLetter.tsx frontend/src/__tests__/DeadLetter.test.tsx frontend/public/locales/
git commit -m "feat(frontend): DeadLetterRow widget + DeadLetter cross-vault page"
```

---

## Task 12: DeadLetterDetail page

**Files:**
- Create: `frontend/src/pages/DeadLetterDetail.tsx`, `frontend/src/__tests__/DeadLetterDetail.test.tsx`

- [ ] **Step 1: Failing test**

```tsx
// frontend/src/__tests__/DeadLetterDetail.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { DeadLetterDetail } from "../pages/DeadLetterDetail";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    dead_letter: {
      retry_disabled: "Retry (#14c)", dismiss_disabled: "Dismiss (#14c)",
      kind: "kind", attempt_n_of_m: "Attempt {{n}}/{{max}}",
      finished_at: "finished", error: "error", traceback: "Traceback",
      payload: "Payload",
      not_found_title: "Job not found", not_found_hint: "Back",
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
          <Route path="/dead-letter/:jobId" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("DeadLetterDetail", () => {
  it("renders job + traceback", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        id: "j1",
        kind: "ingest",
        payload: { transcript_path: "/x.md" },
        status: "dead_letter",
        attempt: 4,
        next_attempt_at: "2026-04-29T12:00:00Z",
        created_at: "2026-04-29T11:00:00Z",
        started_at: "2026-04-29T11:01:00Z",
        finished_at: "2026-04-29T11:05:00Z",
        error: "Rate limit",
        error_traceback: "Traceback line 1\nTraceback line 2",
        project_name: "alpha",
      },
    });
    render(wrap(<DeadLetterDetail />, "/dead-letter/j1"));
    await waitFor(() => expect(screen.getByText("j1")).toBeInTheDocument());
    expect(screen.getByText(/Traceback line 1/)).toBeInTheDocument();
  });

  it("shows not-found on 404", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("404"));
    render(wrap(<DeadLetterDetail />, "/dead-letter/missing"));
    await waitFor(() => expect(screen.getByText(/Job not found/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/pages/DeadLetterDetail.tsx
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProjectBadge } from "@/components/widgets/ProjectBadge";
import { useDeadLetterEntry } from "@/hooks/useDeadLetterEntry";

const MAX_ATTEMPTS = 4;

export function DeadLetterDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const { t } = useTranslation();
  const jobQuery = useDeadLetterEntry(jobId);

  if (jobQuery.isLoading) return <Skeleton className="h-64" />;
  if (jobQuery.isError) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("dead_letter.not_found_title")}</h1>
        <p className="text-[hsl(var(--muted-foreground))]">{jobId}</p>
        <Link to="/dead-letter" className="text-[hsl(var(--primary))] underline">
          {t("dead_letter.not_found_hint")}
        </Link>
      </div>
    );
  }

  const j = jobQuery.data!;

  return (
    <article className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between">
        <Link to="/dead-letter" className="text-sm text-[hsl(var(--primary))] underline">
          ←
        </Link>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled title={t("dead_letter.retry_disabled")}>
            <RotateCcw className="mr-1 h-3 w-3" />
            {t("dead_letter.retry_disabled")}
          </Button>
          <Button size="sm" variant="outline" disabled title={t("dead_letter.dismiss_disabled")}>
            <X className="mr-1 h-3 w-3" />
            {t("dead_letter.dismiss_disabled")}
          </Button>
        </div>
      </div>

      <header className="space-y-2 border-b pb-4">
        <div className="flex items-center gap-2">
          <ProjectBadge name={j.project_name} />
          <span className="font-mono text-xl">{j.id}</span>
        </div>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("dead_letter.attempt_n_of_m", { n: j.attempt, max: MAX_ATTEMPTS })}
          {j.finished_at && <> · {t("dead_letter.finished_at")}: {j.finished_at}</>}
        </p>
      </header>

      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-[hsl(var(--muted-foreground))]">{t("dead_letter.kind")}</dt>
        <dd><code>{j.kind}</code></dd>
        <dt className="text-[hsl(var(--muted-foreground))]">created_at</dt>
        <dd>{j.created_at}</dd>
        {j.started_at && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">started_at</dt>
            <dd>{j.started_at}</dd>
          </>
        )}
        {j.finished_at && (
          <>
            <dt className="text-[hsl(var(--muted-foreground))]">finished_at</dt>
            <dd>{j.finished_at}</dd>
          </>
        )}
      </dl>

      {j.error && (
        <section className="rounded bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-400">
          <div className="text-xs font-semibold uppercase">{t("dead_letter.error")}</div>
          <div>{j.error}</div>
        </section>
      )}

      {j.error_traceback && (
        <section>
          <h2 className="mb-2 text-sm font-semibold">{t("dead_letter.traceback")}</h2>
          <pre className="overflow-x-auto rounded bg-[hsl(var(--muted))] p-3 text-xs">
            {j.error_traceback}
          </pre>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold">{t("dead_letter.payload")}</h2>
        <pre className="overflow-x-auto rounded bg-[hsl(var(--muted))] p-3 text-xs">
          {JSON.stringify(j.payload, null, 2)}
        </pre>
      </section>
    </article>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/DeadLetterDetail.tsx frontend/src/__tests__/DeadLetterDetail.test.tsx
git commit -m "feat(frontend): DeadLetterDetail page (job + traceback + payload + project badge)"
```

---

## Task 13: Health page

**Files:**
- Create: `frontend/src/pages/Health.tsx`, `frontend/src/__tests__/Health.test.tsx`
- Modify: locale files (add `health.*`)

- [ ] **Step 1: Add locale keys**

```json
"health": {
  "title": "<localised>",
  "watchdog_running": "<localised>",
  "watchdog_down": "<localised>",
  "jobs_queued": "<localised>",
  "jobs_running": "<localised>",
  "jobs_dead_letter": "<localised>",
  "scheduler_jobs": "<localised>",
  "no_scheduler_jobs": "<localised>",
  "alerts_count": "<localised>",
  "vault_not_mounted_title": "<localised>",
  "vault_not_mounted_hint": "<localised>",
  "view_failed_jobs": "<localised>"
}
```

(Note: `health.ok/degraded/down` already exist from #14a — keep them.)

- [ ] **Step 2: Failing test**

```tsx
// frontend/src/__tests__/Health.test.tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Health } from "../pages/Health";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    health: {
      title: "Health",
      watchdog_running: "Watchdog running", watchdog_down: "Watchdog down",
      jobs_queued: "Queued", jobs_running: "Running", jobs_dead_letter: "Failed",
      scheduler_jobs: "Scheduler jobs", no_scheduler_jobs: "No scheduled",
      alerts_count: "Alerts",
      vault_not_mounted_title: "Vault not mounted",
      vault_not_mounted_hint: "Mount via mnemos daemon start",
      view_failed_jobs: "View failed",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode, path = "/project/alpha/health") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name/health" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Health", () => {
  it("shows per-vault status when mounted", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        status: "ok", version: "0.1", uptime_s: 0,
        scheduler_jobs: [
          { id: "daily_snapshot:alpha", next_run_time: "2026-04-30T04:00:00Z", trigger: "cron" },
          { id: "backups_cleanup:alpha", next_run_time: null, trigger: "cron" },
          { id: "daily_snapshot:beta", next_run_time: null, trigger: "cron" },
        ],
        alerts_count: 2,
        vaults: {
          alpha: { watchdog_running: true, jobs_queued: 3, jobs_running: 1, jobs_dead_letter: 0 },
        },
        jobs_alert: false,
      },
    });
    render(wrap(<Health />));
    await waitFor(() => expect(screen.getByText("Watchdog running")).toBeInTheDocument());
    // Alpha-only scheduler jobs (2 of 3 entries match)
    expect(screen.getByText("daily_snapshot:alpha")).toBeInTheDocument();
    expect(screen.queryByText("daily_snapshot:beta")).toBeNull();
  });

  it("shows not-mounted when vault is missing", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        status: "ok", version: "0.1", uptime_s: 0,
        scheduler_jobs: [], alerts_count: 0,
        vaults: {},  // alpha not mounted
        jobs_alert: false,
      },
    });
    render(wrap(<Health />));
    await waitFor(() =>
      expect(screen.getByText(/Vault not mounted/i)).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement**

```tsx
// frontend/src/pages/Health.tsx
import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHealth } from "@/hooks/useHealth";

export function Health() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const healthQuery = useHealth();

  if (!project) return null;
  if (healthQuery.isLoading) return <Skeleton className="h-64" />;

  const health = healthQuery.data;
  const vh = health?.vaults?.[project];

  if (!vh) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("health.vault_not_mounted_title")}</h1>
        <p className="text-[hsl(var(--muted-foreground))]">
          {project} — {t("health.vault_not_mounted_hint")}
        </p>
      </div>
    );
  }

  const projectSchedulerJobs =
    health?.scheduler_jobs?.filter((j) => j.id.endsWith(`:${project}`)) ?? [];

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">{t("health.title")}</h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card>
          <CardContent className="py-3">
            <div
              className={`text-sm font-semibold ${
                vh.watchdog_running
                  ? "text-emerald-700 dark:text-emerald-400"
                  : "text-amber-700 dark:text-amber-400"
              }`}
            >
              {vh.watchdog_running
                ? t("health.watchdog_running")
                : t("health.watchdog_down")}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 py-3">
            <div className="text-2xl font-semibold">{vh.jobs_queued}</div>
            <div className="text-xs uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
              {t("health.jobs_queued")}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 py-3">
            <div className="text-2xl font-semibold">{vh.jobs_running}</div>
            <div className="text-xs uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
              {t("health.jobs_running")}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 py-3">
            <div className="text-2xl font-semibold">{vh.jobs_dead_letter}</div>
            <div className="text-xs uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
              {t("health.jobs_dead_letter")}
            </div>
            {vh.jobs_dead_letter > 0 && (
              <Link
                to={`/dead-letter?project=${encodeURIComponent(project)}`}
                className="text-xs text-[hsl(var(--primary))] underline"
              >
                {t("health.view_failed_jobs")}
              </Link>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("health.scheduler_jobs")}</CardTitle>
        </CardHeader>
        <CardContent>
          {projectSchedulerJobs.length === 0 ? (
            <div className="text-sm text-[hsl(var(--muted-foreground))]">
              {t("health.no_scheduler_jobs")}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="py-1 font-medium">id</th>
                  <th className="py-1 font-medium">next_run_time</th>
                  <th className="py-1 font-medium">trigger</th>
                </tr>
              </thead>
              <tbody>
                {projectSchedulerJobs.map((j) => (
                  <tr key={j.id} className="border-b last:border-0">
                    <td className="py-1 font-mono text-xs">{j.id}</td>
                    <td className="py-1 text-xs">{j.next_run_time ?? "—"}</td>
                    <td className="py-1 text-xs">{j.trigger}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <div className="text-xs text-[hsl(var(--muted-foreground))]">
        {t("health.alerts_count")}: {health?.alerts_count ?? 0}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Health.tsx frontend/src/__tests__/Health.test.tsx frontend/public/locales/
git commit -m "feat(frontend): Health page (per-vault status + scheduler jobs filtered)"
```

---

## Task 14: Sidebar Failed Jobs entry + wire all routes

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Sidebar — add Failed Jobs to Global section**

Edit `frontend/src/components/layout/Sidebar.tsx`. Find the `GLOBAL_ITEMS` array (it has Metrics + Help). Add Failed Jobs:

```tsx
const GLOBAL_ITEMS: NavItem[] = [
  { to: () => "/dead-letter", label: "navigation.failed_jobs", icon: "⚠", requiresProject: false },
  { to: () => "/metrics", label: "navigation.metrics", icon: "📈", requiresProject: false },
  { to: () => "/help", label: "navigation.help", icon: "📖", requiresProject: false },
];
```

Add the locale key under each `navigation`:

```json
"navigation": {
  ...
  "failed_jobs": "<localised>"
}
```

UK = "Помилки", RU = "Ошибки", EN = "Failed jobs".

- [ ] **Step 2: App.tsx — wire all routes**

Edit `frontend/src/App.tsx`. Replace 5 Placeholder routes + add 2 new global routes:

```tsx
import { Trash } from "./pages/Trash";
import { Snapshots } from "./pages/Snapshots";
import { Suggestions } from "./pages/Suggestions";
import { Health } from "./pages/Health";
import { LostSessions } from "./pages/LostSessions";
import { DeadLetter } from "./pages/DeadLetter";
import { DeadLetterDetail } from "./pages/DeadLetterDetail";

// Inside the project/:name children, replace these 4 routes:
{ path: "trash", element: <Trash /> },                  // was Placeholder
{ path: "snapshots", element: <Snapshots /> },          // was Placeholder
{ path: "suggestions", element: <Suggestions /> },      // was Placeholder
{ path: "health", element: <Health /> },                // was Placeholder

// Top-level routes, replace lost-sessions:
{ path: "lost-sessions", element: <LostSessions /> },   // was Placeholder

// New top-level routes:
{ path: "dead-letter", element: <DeadLetter /> },
{ path: "dead-letter/:jobId", element: <DeadLetterDetail /> },
```

- [ ] **Step 3: Run all tests + typecheck + lint**

```bash
cd frontend
pnpm test
pnpm typecheck
pnpm lint
```

All green. Pre-existing 2 shadcn warnings still acceptable.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx frontend/public/locales/
git commit -m "feat(frontend): wire #14b-2 routes (Trash, Snapshots, Suggestions, Health, LostSessions, DeadLetter) + Sidebar Failed Jobs entry"
```

---

## Task 15: Build + final verification

- [ ] **Step 1: Production build**

```bash
cd /d/code/claude-mnemos/frontend
pnpm build
```

Expected: dist written to `../claude_mnemos/daemon/static/`. Bundle size grows modestly (~20-30 KB for the new pages); confirm no surprises.

- [ ] **Step 2: Full frontend tests + lint + typecheck**

```bash
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

No regressions (no backend code touched).

- [ ] **Step 4: Acceptance criteria walk-through (design §4)**

Verify each AC #1–#15 from `docs/plans/2026-04-29-14b-2-operational-views-design.md`:
1. ✅ All 7 routes render real data (Trash, Snapshots, LostSessions, Suggestions, DeadLetter, DeadLetterDetail, Health).
2. ✅ Per-project routes show 404 page for unknown project.
3. ✅ Loading/empty/error states present.
4. ✅ Cross-vault rows show ProjectBadge.
5. ✅ All mutation buttons disabled with `→ #14c` tooltip.
6. ✅ LostSessions Scan button is active and triggers refetch.
7. ✅ Suggestions body via MarkdownView.
8. ✅ DeadLetterDetail shows full traceback in scrollable `<pre>`.
9. ✅ Health page per-vault detail; not-mounted callout when missing.
10. ✅ Sidebar Failed Jobs links to `/dead-letter`.
11. ✅ Schemas verified — round-trip api-* tests for each domain.
12. ✅ Vitest suite green; ~30+ new tests on top of #14b-1's 86.
13. ✅ ESLint + tsc clean.
14. ✅ Backend ruff/mypy unchanged.
15. ✅ Manual smoke (optional).

- [ ] **Step 5: Branch summary**

```bash
git log --oneline main..HEAD
git status
```

~16-17 commits, working tree clean.

- [ ] **Step 6: Optional commit if anything dangling**

If the build produced a `pnpm-lock.yaml` change or other minor fixups, commit. Otherwise verification-only.

---

## Spec coverage map

| Design § | Plan task(s) |
|---|---|
| 1.x background/goals | All tasks |
| 2.1 type schemas | Tasks 1-5 |
| 2.2 API layer | Tasks 1-5 |
| 2.3 hook layer | Tasks 1-5 |
| 2.4 routing | Task 14 |
| 2.5 component additions | Tasks 6-12 |
| 2.6 pages | Tasks 7-13 |
| 2.7 translation keys | Tasks 7-14 (incremental adds) |
| 2.8 page-by-page detail | Tasks 7-13 |
| 2.9 sidebar updates | Task 14 |
| 2.10 backend changes (none) | Task 15 (verification) |
| 3 risks | n/a operational |
| 4 acceptance criteria | Task 15 step 4 |
| 5 open questions | n/a (decisions baked in) |
| 6 out of scope | n/a (deferred to #14c/#14d) |

No uncovered spec requirements.
