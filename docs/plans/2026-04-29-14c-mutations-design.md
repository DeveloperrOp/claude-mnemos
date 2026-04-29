# Plan #14c — Mutations + page editor + 3-tier confirms (design)

**Date:** 2026-04-29
**Status:** Design
**Goal:** Replace every `disabled={true}` mutation button in the dashboard with a wired action backed by a real backend endpoint, fronted by a 3-tier confirm system and toast notifications. Add a page editor for `/pages/:project/*` to enable in-app frontmatter + body edits.

---

## 1. Background

After Plans #14a, #14b-1, #14b-2 the dashboard renders every read-only operational view but every mutation button is `disabled` with a `→ #14c` tooltip. The backend already exposes the full mutation surface (recon confirmed 19 endpoints across `claude_mnemos/daemon/routes/*.py`). #14c wires the UI to those endpoints, adds the safety primitives the destructive ones need, and ships a workable page editor.

### What's already true

- 19 disabled buttons across 10 widgets/pages (full inventory in §3).
- All endpoints exist with stable Pydantic response shapes (no backend work in #14c).
- `sonner` toast lib + `<Toaster />` wrapper exist in `frontend/src/components/ui/sonner.tsx` but are not mounted.
- A Zustand `notifications.store.ts` exists, used by nobody. **Drop it** — duplication.
- `shadcn` ui kit currently has button/badge/card/dropdown-menu/skeleton/sonner/tooltip. **No Dialog/AlertDialog**. We add one.
- No markdown editor / form library installed. We don't need one (see §5).

### What we don't do here

- No new endpoints. No backend changes.
- No optimistic UI. Mutations refetch via `invalidateQueries` after success; the 5s/30s poll keeps everything fresh.
- No bulk operations (Empty Trash exists in backend but no UI surface today; defer).
- No page-create flow (no backend endpoint anyway).
- No page-history/diff view.

---

## 2. Architecture

### 2.1 Three-tier confirm system

A `Tier` enumeration drives every destructive action through one of three UX paths:

| Tier | Trigger | UX | When |
|---|---|---|---|
| **1 — Direct** | Button click → mutate immediately. Toast on result. | `<Button onClick={mutate}>` | Reversible/cheap (Verify, Reject, Defer, Retry, Ingest, Suggestion approve for non-delete). |
| **2 — Confirm** | Button click → `<ConfirmDialog>` with title + description + Cancel + Confirm. Confirm triggers mutate. | `<AlertDialog>` (Radix) | Destructive but recoverable: Restore-from-trash, Snapshot-delete, Page-delete (soft-delete, recoverable from trash), Lost-Session Ignore, DLQ Dismiss, Activity Undo, Approve `delete_page` is **Tier 3** instead. |
| **3 — Typed confirm** | Button click → `<TypedConfirmDialog>`: title + danger description + label + a literal string the user must type into a text input before Confirm enables. | `<AlertDialog>` with controlled `disabled` Confirm | Irreversible / vault-wide: Trash permanent-delete (typed phrase = page basename), Snapshot vault-restore (typed phrase = snapshot name), Suggestion approve when operation is `delete_page` (typed phrase = page basename). |

**Two reusable primitives**:

```tsx
// frontend/src/components/widgets/ConfirmDialog.tsx
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel,
  destructive = false,
  onConfirm,
  isPending = false,
}: ConfirmDialogProps) { /* AlertDialog wrapping */ }

// frontend/src/components/widgets/TypedConfirmDialog.tsx
export function TypedConfirmDialog({
  open, onOpenChange,
  title, description,
  expectedPhrase,        // user must type this exactly
  phraseLabel,           // "Type the page name to confirm"
  confirmLabel,          // "Delete forever"
  onConfirm,
  isPending,
}: TypedConfirmDialogProps) { /* same shell + controlled input */ }
```

Both use the same shadcn `<AlertDialog>` underneath (added via `shadcn add alert-dialog`).

### 2.2 Toast notifications

Mount `<Toaster />` once in `frontend/src/App.tsx` near `<RouterProvider>`. Use `sonner`'s imperative API directly:

```tsx
import { toast } from "sonner";
toast.success(t("trash.restored_toast", { name: e.page_basename }));
toast.error(extractError(err));
```

A small helper extracts user-friendly errors from axios responses:

```tsx
// frontend/src/lib/error.ts
export function extractApiError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    return err.response?.data?.detail ?? err.message;
  }
  return err instanceof Error ? err.message : String(err);
}
```

**Drop** `frontend/src/stores/notifications.store.ts` and its tests. It's dead code.

### 2.3 Mutation hooks

One hook per endpoint, in `frontend/src/hooks/`. All follow this template:

```tsx
export function useRestoreTrash(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (trash_id: string) => restoreTrash(project, trash_id),
    onSuccess: (data, trash_id) => {
      void qc.invalidateQueries({ queryKey: ["trash", project] });
      void qc.invalidateQueries({ queryKey: ["pages", project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("trash.restored_toast"));
    },
    onError: (err) => {
      toast.error(extractApiError(err));
    },
  });
}
```

Cache invalidation rules per hook are spelled out in §4 and again per-task in the implementation plan.

### 2.4 Page editor

The page edit experience is a **separate route**, not a modal. Page bodies can be many KB of markdown — modal is the wrong primitive. Current `PageDetail` Edit button navigates to `/project/:name/pages/*/edit` (a new route).

`PageEdit.tsx`:
- Shows the current page in a 2-column layout: form on the left, preview on the right.
- **Frontmatter form**: a flat set of inputs for the editable fields (`title`, `type`, `status`, `flavor`, `confidence`, free-form `aliases`). Type/status/flavor render as `<select>` from the same enums used in `WikiPage` schema. Confidence is `<input type="number" step="0.05" min="0" max="1">`. Aliases is a comma-separated string serialized to/from `string[]` in the body submit.
- **Body editor**: a `<textarea>` with monospaced font + autosize. No fancy editor. Plain markdown.
- **Preview**: re-uses existing `<MarkdownView>` on the right column with the live textarea content.
- **Save**: calls `usePagePatch(project, pageRef)` mutation → PATCH `/pages/{project}/{pageRef}` with `{frontmatter, body}`. On success, toast + navigate back to detail view.
- **Cancel**: navigate back without saving. If the form is dirty, fire a `<ConfirmDialog>` ("Discard unsaved changes?").

Form state is plain `useState`. Validation is ad-hoc: confidence in [0, 1], required title, type/status/flavor must be from enum (enforced by `<select>`). No `react-hook-form`, no `zod` resolver — overkill for this surface.

### 2.5 Suggestion Defer date picker

POST `/ontology/{p}/suggestions/{id}/defer` doesn't accept a date in current implementation, but the backend `Suggestion.deferred_until` field exists. **#14c does not change the backend** — Defer is a Tier-1 direct mutation (no date input). If/when the backend adds `defer_until: date | None` body, plumb a date picker. **Out of scope for #14c.**

### 2.6 LostSessions Import flow

Each row already carries `project_name`. The Import button POSTs `/lost-sessions/{sid}/import` with `{project_name}`. Tier 1 (direct) — backend just enqueues a job; user can dismiss the queued job from DLQ if it goes wrong. Toast: "Import queued, job {id}".

If the cross-vault inference is wrong (wrong project), user has no override here — they can `mnemos session import --project=...` from CLI. Polish for #14d.

### 2.7 Manual snapshot create

POST `/snapshots/{project}` with optional `label` already exists; no UI today. Add a "Create snapshot" button on the Snapshots page header (above the filter row) → opens a tiny dialog with one input (label, optional, ≤128 chars) → Tier 1 confirm via dialog (technically not a "confirm dialog" — it's a "create dialog" — but reuses the AlertDialog primitive with one extra input). Skip if YAGNI bites; included because it's 30 minutes and removes a CLI gap.

---

## 3. Inventory of buttons → tiers → endpoints

| File:Line | Action | Tier | Backend |
|---|---|---|---|
| `widgets/TrashRow.tsx`:41 | Restore | **2** | POST `/trash/{p}/{id}/restore` |
| `widgets/TrashRow.tsx`:45 | Delete permanently | **3** (type page basename) | DELETE `/trash/{p}/{id}` |
| `widgets/SnapshotCard.tsx`:53 | Restore vault | **3** (type snapshot name) | POST `/snapshots/{p}/{name}/restore` |
| `widgets/SnapshotCard.tsx`:57 | Delete snapshot | **2** | DELETE `/snapshots/{p}/{name}` |
| `widgets/LostSessionRow.tsx`:32 | Import | **1** | POST `/lost-sessions/{sid}/import` |
| `widgets/LostSessionRow.tsx`:36 | Ignore | **2** | POST `/lost-sessions/{sid}/ignore` |
| `widgets/SuggestionCard.tsx`:96 | Approve (non-delete) | **2** | POST `.../approve` |
| `widgets/SuggestionCard.tsx`:96 | Approve (`delete_page`) | **3** (type basename) | POST `.../approve` |
| `widgets/SuggestionCard.tsx`:100 | Reject | **1** | POST `.../reject` |
| `widgets/SuggestionCard.tsx`:104 | Defer | **1** | POST `.../defer` |
| `widgets/DeadLetterRow.tsx`:44 | Retry | **1** | POST `/dead-letter/{id}/retry` |
| `widgets/DeadLetterRow.tsx`:48 | Dismiss | **2** | DELETE `/dead-letter/{id}` |
| `widgets/ActivityRow.tsx`:63 | Undo (only when `can_undo && !undone`) | **2** | POST `/activity/{p}/{op}/undo` |
| `pages/PageDetail.tsx`:59 | Edit | navigate | new route `/project/:p/pages/*/edit` |
| `pages/PageDetail.tsx`:62 | Verify | **1** | POST `/pages/{p}/{ref}/verify` |
| `pages/PageDetail.tsx`:65 | Delete | **2** | DELETE `/pages/{p}/{ref}` |
| `pages/SessionDetail.tsx`:43 | Ingest | **1** | POST `/sessions/{p}/{sid}/ingest` |
| `pages/DeadLetterDetail.tsx`:38 | Retry | **1** | POST `/dead-letter/{id}/retry` |
| `pages/DeadLetterDetail.tsx`:42 | Dismiss | **2** | DELETE `/dead-letter/{id}` |
| `pages/ActivityDetail.tsx`:41 | Undo | **2** | POST `/activity/{p}/{op}/undo` |

Plus one new surface: **Snapshots page — "Create snapshot" header button** (Tier 1 with 1-field dialog).

That's **18 wired actions** + **1 new editor route** + **1 new create-snapshot button**. Total: 20.

---

## 4. Cache invalidation matrix

After each successful mutation, invalidate these query keys:

| Mutation | Invalidate |
|---|---|
| Trash restore | `trash`, `pages`, `activity` |
| Trash delete permanent | `trash` |
| Snapshot create | `snapshots` |
| Snapshot delete | `snapshots` |
| Snapshot vault-restore | `snapshots`, `pages`, `sessions`, `activity` (everything; vault state changed) |
| Suggestion approve | `suggestions`, `pages`, `activity` (page mutations occurred) |
| Suggestion reject | `suggestions` |
| Suggestion defer | `suggestions` |
| DLQ retry | `dead-letter`, `dead-letter-entry`, `health` |
| DLQ dismiss | `dead-letter`, `dead-letter-entry` |
| LostSession import | `lost-sessions`, `dead-letter`, `health`, `sessions` |
| LostSession ignore | `lost-sessions` |
| Page patch | `page` (specific path), `pages`, `page-backlinks`, `activity` |
| Page verify | same as page patch |
| Page delete | `pages`, `page` (specific), `trash`, `activity` |
| Session ingest | `session` (specific), `sessions`, `pages`, `activity`, `health` |
| Activity undo | `activity`, `pages`, `sessions`, `trash` |

We use `invalidateQueries({ queryKey: ["pages", project] })` (project-scoped where applicable) — TanStack matches by prefix.

---

## 5. Translation keys (~60 new)

Extend existing locale blocks:

- `trash.*` — `restored_toast`, `delete_permanent_modal_title`, `delete_permanent_modal_desc`, `delete_permanent_typed_label`, `restore_modal_title`, `restore_modal_desc`, `restore_button`, `delete_permanent_button`, `permanently_deleted_toast`.
- `snapshots.*` — `restore_modal_title`, `restore_modal_desc`, `restore_typed_label`, `restored_toast`, `delete_modal_title`, `delete_modal_desc`, `deleted_toast`, `created_toast`, `create_button`, `create_modal_title`, `create_label_label`, `create_label_placeholder`.
- `suggestions.*` — `approved_toast`, `rejected_toast`, `deferred_toast`, `approve_modal_title`, `approve_modal_desc`, `approve_delete_typed_label`.
- `dead_letter.*` — `retried_toast`, `dismissed_toast`, `dismiss_modal_title`, `dismiss_modal_desc`.
- `lost_sessions.*` — `imported_toast`, `ignored_toast`, `ignore_modal_title`, `ignore_modal_desc`.
- `activity.*` — `undone_toast`, `undo_modal_title`, `undo_modal_desc`.
- `pages.*` — `edit_button`, `verify_button`, `delete_button`, `verified_toast`, `deleted_toast` (already exists?), `delete_modal_title`, `delete_modal_desc`, `editor.title`, `editor.body_label`, `editor.preview`, `editor.save`, `editor.cancel`, `editor.discard_modal_title`, `editor.discard_modal_desc`, `editor.title_field`, `editor.type`, `editor.status`, `editor.flavor`, `editor.confidence`, `editor.aliases`, `editor.aliases_hint`, `editor.saved_toast`.
- `sessions.*` — `ingested_toast`, `ingest_button`.
- `confirm.*` (shared) — `cancel`, `confirm`, `working`, `typed_confirm_input_placeholder`.

UK/RU/EN per established style.

---

## 6. New shadcn dependency

`shadcn add alert-dialog` (pulls `@radix-ui/react-alert-dialog`). Bundle impact ~6 KB gzip.

That's the only dependency added in #14c. No editor lib, no form lib, no date picker.

---

## 7. Testing strategy

Per task, TDD as in #14b-1/2:

- **Mutation hooks**: unit tests with `vi.mock("../api/client")` mocking `apiClient.post/patch/delete`. Verify payload, query-cache invalidation, and toast on success/error. Use `QueryClientProvider` and `Toaster` mounted in test setup.

- **ConfirmDialog / TypedConfirmDialog primitives**: render tests with `userEvent` — confirm button disabled until phrase matches; cancel closes dialog; confirm triggers callback.

- **Pages**: render with mocked endpoint; click button → assert dialog → confirm → assert mutation fired → assert toast. For Tier 1 buttons, no dialog, just click → mutation → toast. Snapshot the rendered toast text.

- **PageEdit**: render with mocked PATCH; type into textarea + frontmatter inputs → click Save → assert PATCH body shape → assert navigation. Also test Cancel-with-dirty-form → discard dialog. Test confidence validation rejecting >1.

Total expected: ~30-40 new Vitest tests on top of #14b-2's 118.

Backend pytest: zero new code, zero regression expected.

ESLint + tsc: clean (allow the 2 pre-existing shadcn warnings).

---

## 8. Acceptance criteria

1. Every formerly-disabled mutation button is now active (or, in PageDetail's case, navigates to the editor route).
2. Tier 2 actions show an `<AlertDialog>` confirm before mutating.
3. Tier 3 actions require typing an expected phrase; Confirm button is disabled until phrase matches exactly.
4. Every successful mutation emits a `toast.success` with a localized message; every failed mutation emits `toast.error` with backend `detail` or `err.message`.
5. After successful mutations, related queries are invalidated and the UI reflects the change within one refetch interval.
6. PageEdit at `/project/:p/pages/*/edit` saves frontmatter+body via PATCH; preview updates as user types; cancel-when-dirty prompts discard.
7. Snapshots page has a "Create snapshot" button that POSTs `/snapshots/{project}` with optional label.
8. Toaster mounts once globally.
9. Dead Zustand `notifications.store.ts` removed.
10. Backend pytest still 1202 passed (no backend changes).
11. Frontend Vitest grows by ~30-40 tests; all pass.
12. ESLint clean; tsc strict clean.
13. Production build still around 260-275 KB gzip (alert-dialog + new code: +5-10 KB).
14. All copy in en/uk/ru.

---

## 9. Risks

- **Approve-for-delete-page typed-confirm**: requires reading the suggestion to know the basename. The frontend already has `affected_pages` in the schema — extract the first one as `expected_phrase`. If it's a long path (`wiki/concepts/foo.md`), use `basename(path).replace(".md", "")` as the phrase. Need helper.
- **Vault restore is brutal** — it reverts EVERY file. Tier 3 with `expectedPhrase = snapshot.name` is hard but appropriate. If user double-typo's, that's the safety. Note in description: "This will revert ALL pages in the vault to the state at this snapshot. Operations performed since this snapshot will be lost."
- **Page editor concurrent edits**: no optimistic locking. If two clients edit the same page, last write wins. The backend's `apply_patch` creates a pre-op snapshot, so it's recoverable, but the user gets no warning. Acceptable for v1 (single user).
- **Page DELETE is soft**: routes to trash. Tooltip + toast should make this clear ("Moved to trash. Restore from /project/.../trash").

---

## 10. Out of scope / deferred

- Optimistic UI / rollback (refetch is fine).
- Bulk operations (Empty Trash, multi-select restore, etc.) — backend supports Empty Trash but UI defers to #14d polish.
- Page history / diff viewer.
- Page-create flow (no backend endpoint).
- Inline markdown WYSIWYG (tiptap/lexical).
- Defer-suggestion date picker (no backend body field).
- LostSession import-to-different-project override (use CLI).
- Snapshot label edit / pin.
- Activity Undo with cherry-pick subset.

These all roll forward to #14d or later.

---

## 11. File map

**New files:**
- `frontend/src/components/widgets/ConfirmDialog.tsx`
- `frontend/src/components/widgets/TypedConfirmDialog.tsx`
- `frontend/src/components/ui/alert-dialog.tsx` (shadcn-generated)
- `frontend/src/lib/error.ts` (extractApiError helper)
- `frontend/src/lib/pageBasename.ts` (basename for typed-confirm)
- `frontend/src/hooks/useTrashRestore.ts`
- `frontend/src/hooks/useTrashDelete.ts`
- `frontend/src/hooks/useSnapshotCreate.ts`
- `frontend/src/hooks/useSnapshotDelete.ts`
- `frontend/src/hooks/useSnapshotRestore.ts`
- `frontend/src/hooks/useSuggestionApprove.ts`
- `frontend/src/hooks/useSuggestionReject.ts`
- `frontend/src/hooks/useSuggestionDefer.ts`
- `frontend/src/hooks/useDeadLetterRetry.ts`
- `frontend/src/hooks/useDeadLetterDismiss.ts`
- `frontend/src/hooks/useLostSessionImport.ts`
- `frontend/src/hooks/useLostSessionIgnore.ts`
- `frontend/src/hooks/usePagePatch.ts`
- `frontend/src/hooks/usePageVerify.ts`
- `frontend/src/hooks/usePageDelete.ts`
- `frontend/src/hooks/useSessionIngest.ts`
- `frontend/src/hooks/useActivityUndo.ts`
- `frontend/src/api/{trash,snapshots,suggestions,dead_letter,lost_sessions,pages,sessions,activity}.api.ts` — extend with mutation functions (these files already exist for queries).
- `frontend/src/pages/PageEdit.tsx` (~150 LOC)
- `frontend/src/__tests__/ConfirmDialog.test.tsx`
- `frontend/src/__tests__/TypedConfirmDialog.test.tsx`
- `frontend/src/__tests__/api-trash-mutations.test.ts`
- `frontend/src/__tests__/api-snapshots-mutations.test.ts`
- `frontend/src/__tests__/api-suggestions-mutations.test.ts`
- `frontend/src/__tests__/api-dead-letter-mutations.test.ts`
- `frontend/src/__tests__/api-lost-sessions-mutations.test.ts`
- `frontend/src/__tests__/api-pages-mutations.test.ts`
- `frontend/src/__tests__/api-sessions-mutations.test.ts`
- `frontend/src/__tests__/api-activity-mutations.test.ts`
- `frontend/src/__tests__/PageEdit.test.tsx`
- (Page tests for each updated widget grow with new "click → confirm → mutate" flows; widgets/pages get test additions, not new files.)

**Modified files:**
- `frontend/src/App.tsx` — mount `<Toaster />`, add `/project/:p/pages/*/edit` route.
- All 7 widget files (TrashRow, SnapshotCard, LostSessionRow, SuggestionCard, DeadLetterRow, ActivityRow) — wire onClick + dialogs.
- `frontend/src/pages/{PageDetail,SessionDetail,DeadLetterDetail,ActivityDetail,Snapshots}.tsx` — wire onClick + dialogs (Snapshots also gets "Create snapshot" button).
- `frontend/src/lib/utils.ts` — possibly tiny additions.
- `frontend/public/locales/{en,uk,ru}.json` — ~60 new keys.

**Deleted files:**
- `frontend/src/stores/notifications.store.ts`
- `frontend/src/__tests__/notifications.store.test.ts` (if it exists)

---

## 12. Spec coverage map (cross-check during plan-writing)

Every section of this spec must map to a task in the implementation plan. Loose mapping:

| Spec § | Plan tasks |
|---|---|
| §2.1 Tier system + dialogs | Setup + dialog primitives |
| §2.2 Toast | Toaster mount + helper |
| §2.3 Mutation hooks | One task per domain (trash, snapshots, suggestions, dead-letter, lost-sessions, pages, sessions, activity) |
| §2.4 Page editor | Dedicated task |
| §2.7 Manual snapshot | Dedicated task |
| §3 Wiring | Integrated into per-domain tasks |
| §5 i18n | Each task adds its own keys |
| §6 alert-dialog dep | Setup task |
| §8 ACs | Final-verification task |

---

(end of design)
