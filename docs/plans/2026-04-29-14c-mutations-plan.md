# Mutations + page editor + 3-tier confirms Implementation Plan (Plan #14c)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** Wire every disabled mutation button in the dashboard to a real backend endpoint, fronted by a 3-tier confirm system + sonner toasts, plus add a page editor for `/project/:p/pages/*/edit`.

**Architecture:** Pure frontend. No backend changes. New pieces: 1 shadcn `alert-dialog`, 2 dialog primitives (`ConfirmDialog`, `TypedConfirmDialog`), 16 mutation hooks (`useMutation` + `invalidateQueries` + sonner toast), 1 new page (`PageEdit`). Wires onClick handlers + Tier 2/3 dialogs into existing 7 widgets and 5 detail pages. Drops the unused `notifications.store.ts`. Toaster mounts once in `App.tsx`.

**Tech Stack:** React 19, TanStack Query 5, react-router 7, axios, zod 3, Tailwind v4, shadcn/ui, `@radix-ui/react-alert-dialog` (NEW), sonner 2.0 (already installed), Vitest + Testing Library, i18next.

**Design doc:** `docs/plans/2026-04-29-14c-mutations-design.md` — read before each task.

---

## Files map

**Create:**
- `frontend/src/components/ui/alert-dialog.tsx` (shadcn-generated)
- `frontend/src/components/widgets/ConfirmDialog.tsx`
- `frontend/src/components/widgets/TypedConfirmDialog.tsx`
- `frontend/src/lib/error.ts` (extractApiError)
- `frontend/src/lib/pageBasename.ts` (basename helper)
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
- `frontend/src/hooks/useActivityUndo.ts`
- `frontend/src/hooks/useSessionIngest.ts`
- `frontend/src/hooks/usePageVerify.ts`
- `frontend/src/hooks/usePageDelete.ts`
- `frontend/src/hooks/usePagePatch.ts`
- `frontend/src/pages/PageEdit.tsx`
- `frontend/src/__tests__/ConfirmDialog.test.tsx`
- `frontend/src/__tests__/TypedConfirmDialog.test.tsx`
- `frontend/src/__tests__/api-trash-mutations.test.ts`
- `frontend/src/__tests__/api-snapshots-mutations.test.ts`
- `frontend/src/__tests__/api-suggestions-mutations.test.ts`
- `frontend/src/__tests__/api-dead-letter-mutations.test.ts`
- `frontend/src/__tests__/api-lost-sessions-mutations.test.ts`
- `frontend/src/__tests__/api-activity-mutations.test.ts`
- `frontend/src/__tests__/api-sessions-mutations.test.ts`
- `frontend/src/__tests__/api-pages-mutations.test.ts`
- `frontend/src/__tests__/PageEdit.test.tsx`
- `frontend/src/__tests__/error.test.ts`
- `frontend/src/__tests__/pageBasename.test.ts`

**Modify:**
- `frontend/src/App.tsx` — mount `<Toaster />`, add `pages/*/edit` route.
- `frontend/src/api/{trash,snapshots,suggestions,dead_letter,lost_sessions,activity,sessions,pages}.api.ts` — add mutation functions to existing files.
- `frontend/src/components/widgets/{TrashRow,SnapshotCard,LostSessionRow,SuggestionCard,DeadLetterRow,ActivityRow}.tsx` — wire onClick + dialogs.
- `frontend/src/pages/{PageDetail,SessionDetail,DeadLetterDetail,ActivityDetail,Snapshots}.tsx` — wire onClick + dialogs.
- `frontend/public/locales/{en,uk,ru}.json` — ~60 new keys.
- `frontend/package.json` — add `@radix-ui/react-alert-dialog`.

**Delete:**
- `frontend/src/stores/notifications.store.ts`
- `frontend/src/__tests__/notifications.store.test.ts` (if exists)

---

## Task 1: Setup — alert-dialog, Toaster, helpers, drop notifications store

**Files:**
- Modify: `frontend/package.json` (add `@radix-ui/react-alert-dialog`)
- Create: `frontend/src/components/ui/alert-dialog.tsx`
- Create: `frontend/src/lib/error.ts`
- Create: `frontend/src/lib/pageBasename.ts`
- Create: `frontend/src/__tests__/error.test.ts`
- Create: `frontend/src/__tests__/pageBasename.test.ts`
- Modify: `frontend/src/App.tsx` (mount `<Toaster />`)
- Delete: `frontend/src/stores/notifications.store.ts`
- Delete: `frontend/src/__tests__/notifications.store.test.ts` (if exists)

- [ ] **Step 1: Install radix alert-dialog**

```bash
cd /d/code/claude-mnemos/frontend
pnpm add @radix-ui/react-alert-dialog
```

- [ ] **Step 2: Add shadcn alert-dialog component**

Create `frontend/src/components/ui/alert-dialog.tsx` (paste shadcn boilerplate):

```tsx
import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
import * as React from "react";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

function AlertDialog(props: React.ComponentProps<typeof AlertDialogPrimitive.Root>) {
  return <AlertDialogPrimitive.Root {...props} />;
}

function AlertDialogTrigger(props: React.ComponentProps<typeof AlertDialogPrimitive.Trigger>) {
  return <AlertDialogPrimitive.Trigger {...props} />;
}

function AlertDialogPortal(props: React.ComponentProps<typeof AlertDialogPrimitive.Portal>) {
  return <AlertDialogPrimitive.Portal {...props} />;
}

function AlertDialogOverlay({ className, ...props }: React.ComponentProps<typeof AlertDialogPrimitive.Overlay>) {
  return (
    <AlertDialogPrimitive.Overlay
      className={cn(
        "fixed inset-0 z-50 bg-black/50 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
        className,
      )}
      {...props}
    />
  );
}

function AlertDialogContent({ className, ...props }: React.ComponentProps<typeof AlertDialogPrimitive.Content>) {
  return (
    <AlertDialogPortal>
      <AlertDialogOverlay />
      <AlertDialogPrimitive.Content
        className={cn(
          "fixed top-[50%] left-[50%] z-50 grid w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border bg-background p-6 shadow-lg sm:max-w-lg",
          "duration-200 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          className,
        )}
        {...props}
      />
    </AlertDialogPortal>
  );
}

function AlertDialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-2 text-center sm:text-left", className)} {...props} />;
}

function AlertDialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)} {...props} />;
}

function AlertDialogTitle({ className, ...props }: React.ComponentProps<typeof AlertDialogPrimitive.Title>) {
  return <AlertDialogPrimitive.Title className={cn("text-lg font-semibold", className)} {...props} />;
}

function AlertDialogDescription({ className, ...props }: React.ComponentProps<typeof AlertDialogPrimitive.Description>) {
  return <AlertDialogPrimitive.Description className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

function AlertDialogAction({ className, ...props }: React.ComponentProps<typeof AlertDialogPrimitive.Action>) {
  return <AlertDialogPrimitive.Action className={cn(buttonVariants(), className)} {...props} />;
}

function AlertDialogCancel({ className, ...props }: React.ComponentProps<typeof AlertDialogPrimitive.Cancel>) {
  return <AlertDialogPrimitive.Cancel className={cn(buttonVariants({ variant: "outline" }), className)} {...props} />;
}

export {
  AlertDialog, AlertDialogTrigger, AlertDialogContent, AlertDialogHeader,
  AlertDialogFooter, AlertDialogTitle, AlertDialogDescription,
  AlertDialogAction, AlertDialogCancel,
};
```

- [ ] **Step 3: Write failing tests for error helper**

`frontend/src/__tests__/error.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { AxiosError, AxiosHeaders } from "axios";
import { extractApiError } from "../lib/error";

describe("extractApiError", () => {
  it("returns response.data.detail for axios error with detail", () => {
    const err = new AxiosError(
      "Request failed",
      "ERR_BAD_REQUEST",
      undefined,
      undefined,
      {
        status: 400,
        statusText: "Bad Request",
        data: { detail: "Snapshot already exists" },
        headers: {},
        config: { headers: new AxiosHeaders() },
      },
    );
    expect(extractApiError(err)).toBe("Snapshot already exists");
  });

  it("falls back to err.message for axios error without detail", () => {
    const err = new AxiosError("Network Error");
    expect(extractApiError(err)).toBe("Network Error");
  });

  it("returns Error.message for plain Error", () => {
    expect(extractApiError(new Error("boom"))).toBe("boom");
  });

  it("stringifies unknown values", () => {
    expect(extractApiError("oops")).toBe("oops");
    expect(extractApiError(42)).toBe("42");
  });
});
```

- [ ] **Step 4: Implement error helper**

`frontend/src/lib/error.ts`:

```ts
import axios from "axios";

export function extractApiError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
```

- [ ] **Step 5: Write failing tests for pageBasename**

`frontend/src/__tests__/pageBasename.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { pageBasename } from "../lib/pageBasename";

describe("pageBasename", () => {
  it("strips directory + .md extension", () => {
    expect(pageBasename("wiki/concepts/foo.md")).toBe("foo");
  });
  it("handles no directory", () => {
    expect(pageBasename("bar.md")).toBe("bar");
  });
  it("returns input when no slash and no md", () => {
    expect(pageBasename("baz")).toBe("baz");
  });
  it("returns last segment without .md", () => {
    expect(pageBasename("wiki/x/y/very-long-name.md")).toBe("very-long-name");
  });
});
```

- [ ] **Step 6: Implement pageBasename**

`frontend/src/lib/pageBasename.ts`:

```ts
export function pageBasename(path: string): string {
  const last = path.split("/").pop() ?? path;
  return last.endsWith(".md") ? last.slice(0, -3) : last;
}
```

- [ ] **Step 7: Mount Toaster in App.tsx**

Read current `frontend/src/App.tsx`. Add at the top:

```tsx
import { Toaster } from "@/components/ui/sonner";
```

Then inside the root JSX (before closing the QueryClientProvider/RouterProvider), add:

```tsx
<Toaster richColors position="bottom-right" />
```

(Placement: just before the final closing tag of whatever wrapper renders `<RouterProvider />` or routes.)

- [ ] **Step 8: Drop unused notifications store**

```bash
rm frontend/src/stores/notifications.store.ts
# also remove its test if it exists:
rm -f frontend/src/__tests__/notifications.store.test.ts
```

If anything imports it (`grep -r "notifications.store"` should be empty after #14b-2 — the recon confirmed nothing uses it).

- [ ] **Step 9: Run tests + tsc**

```bash
cd frontend
pnpm test
pnpm typecheck
```

Both should be clean. Tests should grow by 8 (4 error + 4 basename) — minus however many `notifications.store` had (≥1).

- [ ] **Step 10: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/components/ui/alert-dialog.tsx frontend/src/lib/error.ts frontend/src/lib/pageBasename.ts frontend/src/__tests__/error.test.ts frontend/src/__tests__/pageBasename.test.ts frontend/src/App.tsx
git rm frontend/src/stores/notifications.store.ts
git rm -f frontend/src/__tests__/notifications.store.test.ts
git commit -m "chore(frontend): #14c setup — alert-dialog, Toaster mount, helpers, drop notifications store"
```

---

## Task 2: ConfirmDialog + TypedConfirmDialog primitives

**Files:**
- Create: `frontend/src/components/widgets/ConfirmDialog.tsx`
- Create: `frontend/src/components/widgets/TypedConfirmDialog.tsx`
- Create: `frontend/src/__tests__/ConfirmDialog.test.tsx`
- Create: `frontend/src/__tests__/TypedConfirmDialog.test.tsx`

- [ ] **Step 1: Failing tests for ConfirmDialog**

`frontend/src/__tests__/ConfirmDialog.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../i18n";
import { ConfirmDialog } from "../components/widgets/ConfirmDialog";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    confirm: { cancel: "Cancel", confirm: "Confirm", working: "Working..." },
  }, true, true);
  void i18n.changeLanguage("en");
});

describe("ConfirmDialog", () => {
  it("renders title + description when open", () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Restore page?"
        description="This will move the page back to wiki/"
        confirmLabel="Restore"
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByText("Restore page?")).toBeInTheDocument();
    expect(screen.getByText(/This will move/)).toBeInTheDocument();
  });

  it("calls onConfirm on Confirm click", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="t" description="d"
        confirmLabel="Restore"
        onConfirm={onConfirm}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Restore" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onOpenChange(false) on Cancel", async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="t" description="d"
        confirmLabel="Restore"
        onConfirm={() => {}}
      />,
    );
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("disables Confirm when isPending", () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="t" description="d"
        confirmLabel="Restore"
        onConfirm={() => {}}
        isPending
      />,
    );
    expect(screen.getByRole("button", { name: /working/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run** → FAIL.

```
cd frontend && pnpm test ConfirmDialog
```

- [ ] **Step 3: Implement ConfirmDialog**

`frontend/src/components/widgets/ConfirmDialog.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  isPending?: boolean;
}

export function ConfirmDialog({
  open, onOpenChange,
  title, description,
  confirmLabel, cancelLabel,
  destructive = false,
  onConfirm,
  isPending = false,
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>
            {cancelLabel ?? t("confirm.cancel")}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={isPending}
            className={cn(destructive && "bg-red-600 text-white hover:bg-red-700")}
          >
            {isPending ? t("confirm.working") : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Failing tests for TypedConfirmDialog**

`frontend/src/__tests__/TypedConfirmDialog.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../i18n";
import { TypedConfirmDialog } from "../components/widgets/TypedConfirmDialog";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    confirm: {
      cancel: "Cancel", confirm: "Confirm", working: "Working...",
      typed_confirm_input_placeholder: "Type {{phrase}} to confirm",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

describe("TypedConfirmDialog", () => {
  it("Confirm disabled until typed phrase matches", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <TypedConfirmDialog
        open
        onOpenChange={() => {}}
        title="Permanent delete"
        description="This cannot be undone"
        expectedPhrase="foo"
        phraseLabel="Type the page name"
        confirmLabel="Delete forever"
        onConfirm={onConfirm}
      />,
    );
    const confirmBtn = screen.getByRole("button", { name: /delete forever/i });
    expect(confirmBtn).toBeDisabled();

    const input = screen.getByRole("textbox");
    await user.type(input, "fo");
    expect(confirmBtn).toBeDisabled();

    await user.type(input, "o");
    expect(confirmBtn).not.toBeDisabled();

    await user.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("rejects partial / wrong phrase", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <TypedConfirmDialog
        open
        onOpenChange={() => {}}
        title="t" description="d"
        expectedPhrase="alpha"
        phraseLabel="Type the name"
        confirmLabel="Delete"
        onConfirm={onConfirm}
      />,
    );
    await user.type(screen.getByRole("textbox"), "alphabet");
    expect(screen.getByRole("button", { name: /delete/i })).toBeDisabled();
  });
});
```

- [ ] **Step 6: Run** → FAIL.

- [ ] **Step 7: Implement TypedConfirmDialog**

`frontend/src/components/widgets/TypedConfirmDialog.tsx`:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface TypedConfirmDialogProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  title: string;
  description: string;
  expectedPhrase: string;
  phraseLabel: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  isPending?: boolean;
}

export function TypedConfirmDialog({
  open, onOpenChange,
  title, description,
  expectedPhrase,
  phraseLabel,
  confirmLabel, cancelLabel,
  onConfirm,
  isPending = false,
}: TypedConfirmDialogProps) {
  const { t } = useTranslation();
  const [typed, setTyped] = useState("");

  const matches = typed === expectedPhrase;

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setTyped("");
        onOpenChange(next);
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-2">
          <label className="text-sm font-medium">{phraseLabel}</label>
          <p className="text-xs text-[hsl(var(--muted-foreground))]">
            <code className="rounded bg-[hsl(var(--muted))] px-1.5 py-0.5">{expectedPhrase}</code>
          </p>
          <input
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            disabled={isPending}
            className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
            placeholder={t("confirm.typed_confirm_input_placeholder", { phrase: expectedPhrase })}
            autoFocus
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>
            {cancelLabel ?? t("confirm.cancel")}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={!matches || isPending}
            className="bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300"
          >
            {isPending ? t("confirm.working") : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [ ] **Step 8: Run** → PASS.

- [ ] **Step 9: Add `confirm.*` locale keys to en/uk/ru**

In each of `frontend/public/locales/{en,uk,ru}.json`, add top-level `confirm` block:

```json
"confirm": {
  "cancel": "...",
  "confirm": "...",
  "working": "...",
  "typed_confirm_input_placeholder": "Type {{phrase}} to confirm"
}
```

- en: `Cancel` / `Confirm` / `Working...` / `Type {{phrase}} to confirm`
- uk: `Скасувати` / `Підтвердити` / `Виконується...` / `Введіть {{phrase}} для підтвердження`
- ru: `Отмена` / `Подтвердить` / `Выполняется...` / `Введите {{phrase}} для подтверждения`

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/widgets/ConfirmDialog.tsx frontend/src/components/widgets/TypedConfirmDialog.tsx frontend/src/__tests__/ConfirmDialog.test.tsx frontend/src/__tests__/TypedConfirmDialog.test.tsx frontend/public/locales/
git commit -m "feat(frontend): ConfirmDialog + TypedConfirmDialog primitives + confirm locale keys"
```

---

## Task 3: Trash mutations + wire TrashRow

**Files:**
- Modify: `frontend/src/api/trash.api.ts` (add `restoreTrash`, `deleteTrash`)
- Create: `frontend/src/hooks/useTrashRestore.ts`, `frontend/src/hooks/useTrashDelete.ts`
- Create: `frontend/src/__tests__/api-trash-mutations.test.ts`
- Modify: `frontend/src/components/widgets/TrashRow.tsx` (wire dialogs + mutations)
- Modify: `frontend/public/locales/{en,uk,ru}.json` (add `trash.*` toast/modal keys)

- [ ] **Step 1: Failing test for api functions**

`frontend/src/__tests__/api-trash-mutations.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { restoreTrash, deleteTrash } from "../api/trash.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

describe("trash mutations", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });
  afterEach(() => vi.resetAllMocks());

  it("restoreTrash POSTs to /trash/{p}/{id}/restore", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, snapshot_path: ".backups/x", activity_id: "a1", restored_path: "wiki/foo.md" },
    });
    const out = await restoreTrash("alpha", "t1");
    expect(apiClient.post).toHaveBeenCalledWith("/trash/alpha/t1/restore");
    expect(out.success).toBe(true);
  });

  it("deleteTrash DELETEs /trash/{p}/{id}", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: null });
    await deleteTrash("alpha", "t1");
    expect(apiClient.delete).toHaveBeenCalledWith("/trash/alpha/t1");
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Add functions to `frontend/src/api/trash.api.ts`**

Append (preserve existing `listTrash`):

```ts
export interface RestoreTrashResult {
  success: boolean;
  snapshot_path: string | null;
  activity_id: string;
  restored_path: string;
}

export async function restoreTrash(
  project: string,
  trash_id: string,
): Promise<RestoreTrashResult> {
  const r = await apiClient.post(
    `/trash/${encodeURIComponent(project)}/${encodeURIComponent(trash_id)}/restore`,
  );
  return r.data as RestoreTrashResult;
}

export async function deleteTrash(project: string, trash_id: string): Promise<void> {
  await apiClient.delete(
    `/trash/${encodeURIComponent(project)}/${encodeURIComponent(trash_id)}`,
  );
}
```

- [ ] **Step 4: Implement `useTrashRestore`**

`frontend/src/hooks/useTrashRestore.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { restoreTrash } from "@/api/trash.api";
import { extractApiError } from "@/lib/error";

export function useTrashRestore(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (trash_id: string) => restoreTrash(project, trash_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["trash", project] });
      void qc.invalidateQueries({ queryKey: ["pages", project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("trash.restored_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 5: Implement `useTrashDelete`**

`frontend/src/hooks/useTrashDelete.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { deleteTrash } from "@/api/trash.api";
import { extractApiError } from "@/lib/error";

export function useTrashDelete(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (trash_id: string) => deleteTrash(project, trash_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["trash", project] });
      toast.success(t("trash.permanently_deleted_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 6: Run api-trash-mutations test** → PASS.

- [ ] **Step 7: Add locale keys**

Append to each locale's existing `trash` block:

```json
"restored_toast": "...",
"permanently_deleted_toast": "...",
"restore_modal_title": "...",
"restore_modal_desc": "...",
"restore_button": "...",
"delete_permanent_modal_title": "...",
"delete_permanent_modal_desc": "...",
"delete_permanent_typed_label": "...",
"delete_permanent_button": "..."
```

Suggested:
- en: `Restored` / `Permanently deleted` / `Restore page?` / `Move {{name}} back to its original location.` / `Restore` / `Permanently delete?` / `This cannot be undone. Type the page name to confirm.` / `Type the page name` / `Delete forever`
- uk: `Відновлено` / `Видалено назавжди` / `Відновити сторінку?` / `Перемістити {{name}} назад.` / `Відновити` / `Видалити назавжди?` / `Це незворотно. Введіть назву сторінки для підтвердження.` / `Введіть назву сторінки` / `Видалити назавжди`
- ru: `Восстановлено` / `Удалено навсегда` / `Восстановить страницу?` / `Переместить {{name}} обратно.` / `Восстановить` / `Удалить навсегда?` / `Это необратимо. Введите имя страницы для подтверждения.` / `Введите имя страницы` / `Удалить навсегда`

(Existing keys `restore_disabled`, `delete_permanently_disabled`, `restorable`, `blocked`, `deleted_at`, `no_entries`, `showing_n` stay; we can keep the `_disabled` keys as-is for now and reuse them as the active button label too.)

- [ ] **Step 8: Wire TrashRow**

Replace `frontend/src/components/widgets/TrashRow.tsx` with:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { Trash2, RotateCcw, AlertTriangle, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "./ConfirmDialog";
import { TypedConfirmDialog } from "./TypedConfirmDialog";
import { useTrashRestore } from "@/hooks/useTrashRestore";
import { useTrashDelete } from "@/hooks/useTrashDelete";
import { pageBasename } from "@/lib/pageBasename";
import { cn } from "@/lib/utils";
import type { TrashEntry } from "@/types/Trash";

export function TrashRow({ entry: e }: { entry: TrashEntry }) {
  const { t } = useTranslation();
  const { name: project } = useParams<{ name: string }>();
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const restore = useTrashRestore(project ?? "");
  const remove = useTrashDelete(project ?? "");

  const displayName = e.page_basename ?? (e.original_path ? pageBasename(e.original_path) : e.trash_id);

  return (
    <>
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
        <Button
          size="sm"
          variant="outline"
          disabled={!e.restorable || restore.isPending}
          onClick={() => setRestoreOpen(true)}
          title={e.restorable ? t("trash.restore_button") : t("trash.blocked")}
        >
          <RotateCcw className="mr-1 h-3 w-3" />
          {t("trash.restore_button")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={remove.isPending}
          onClick={() => setDeleteOpen(true)}
          title={t("trash.delete_permanent_button")}
        >
          <Trash2 className="mr-1 h-3 w-3" />
          {t("trash.delete_permanent_button")}
        </Button>
      </div>

      <ConfirmDialog
        open={restoreOpen}
        onOpenChange={setRestoreOpen}
        title={t("trash.restore_modal_title")}
        description={t("trash.restore_modal_desc", { name: displayName })}
        confirmLabel={t("trash.restore_button")}
        onConfirm={() => {
          restore.mutate(e.trash_id, { onSettled: () => setRestoreOpen(false) });
        }}
        isPending={restore.isPending}
      />

      <TypedConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("trash.delete_permanent_modal_title")}
        description={t("trash.delete_permanent_modal_desc")}
        expectedPhrase={displayName}
        phraseLabel={t("trash.delete_permanent_typed_label")}
        confirmLabel={t("trash.delete_permanent_button")}
        onConfirm={() => {
          remove.mutate(e.trash_id, { onSettled: () => setDeleteOpen(false) });
        }}
        isPending={remove.isPending}
      />
    </>
  );
}
```

- [ ] **Step 9: Update existing Trash page test mock to add updated keys**

Edit `frontend/src/__tests__/Trash.test.tsx` `addResourceBundle` block to include the new keys (`restored_toast`, `restore_modal_title`, etc.) so test renders without missing-key warnings. Append to the bundled object.

- [ ] **Step 10: Run all tests + tsc**

```bash
cd frontend && pnpm test && pnpm typecheck
```

All green.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/api/trash.api.ts frontend/src/hooks/useTrashRestore.ts frontend/src/hooks/useTrashDelete.ts frontend/src/__tests__/api-trash-mutations.test.ts frontend/src/__tests__/Trash.test.tsx frontend/src/components/widgets/TrashRow.tsx frontend/public/locales/
git commit -m "feat(frontend): wire Trash Restore (Tier 2) + Permanent-delete (Tier 3) mutations"
```

---

## Task 4: Snapshots mutations + wire SnapshotCard + Create button

**Files:**
- Modify: `frontend/src/api/snapshots.api.ts` (add `createSnapshot`, `deleteSnapshot`, `restoreSnapshot`)
- Create: `frontend/src/hooks/useSnapshotCreate.ts`, `useSnapshotDelete.ts`, `useSnapshotRestore.ts`
- Create: `frontend/src/__tests__/api-snapshots-mutations.test.ts`
- Modify: `frontend/src/components/widgets/SnapshotCard.tsx`
- Modify: `frontend/src/pages/Snapshots.tsx` (Create button + dialog)
- Modify: `frontend/public/locales/{en,uk,ru}.json`

- [ ] **Step 1: Failing test for api functions**

`frontend/src/__tests__/api-snapshots-mutations.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { createSnapshot, deleteSnapshot, restoreSnapshot } from "../api/snapshots.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

describe("snapshots mutations", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });
  afterEach(() => vi.resetAllMocks());

  it("createSnapshot POSTs with optional label", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        name: "manual-2026-04-29-12-00-00-x",
        kind: "manual", timestamp: "2026-04-29T12:00:00Z",
        op_id: null, op_type: null, label: "before-cleanup",
        size_bytes: 0, path: ".backups/manual-2026-04-29-12-00-00-x",
      },
    });
    const out = await createSnapshot("alpha", "before-cleanup");
    expect(apiClient.post).toHaveBeenCalledWith("/snapshots/alpha", { label: "before-cleanup" });
    expect(out.label).toBe("before-cleanup");
  });

  it("createSnapshot omits label when empty", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        name: "manual-x", kind: "manual", timestamp: "t",
        op_id: null, op_type: null, label: null, size_bytes: 0, path: "p",
      },
    });
    await createSnapshot("alpha");
    expect(apiClient.post).toHaveBeenCalledWith("/snapshots/alpha", {});
  });

  it("deleteSnapshot DELETEs", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: { deleted: "manual-x" } });
    await deleteSnapshot("alpha", "manual-x");
    expect(apiClient.delete).toHaveBeenCalledWith("/snapshots/alpha/manual-x");
  });

  it("restoreSnapshot POSTs to /snapshots/{p}/{name}/restore", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, snapshot: "manual-x", activity_id: "a1" },
    });
    const out = await restoreSnapshot("alpha", "manual-x");
    expect(apiClient.post).toHaveBeenCalledWith("/snapshots/alpha/manual-x/restore");
    expect(out.success).toBe(true);
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Add functions to `frontend/src/api/snapshots.api.ts`**

Append:

```ts
import type { SnapshotInfo } from "@/types/Snapshot";

export interface RestoreSnapshotResult {
  success: boolean;
  snapshot: string;
  activity_id: string;
}

export async function createSnapshot(
  project: string,
  label?: string,
): Promise<SnapshotInfo> {
  const body = label && label.trim() ? { label: label.trim() } : {};
  const r = await apiClient.post(
    `/snapshots/${encodeURIComponent(project)}`,
    body,
  );
  return r.data as SnapshotInfo;
}

export async function deleteSnapshot(project: string, name: string): Promise<void> {
  await apiClient.delete(
    `/snapshots/${encodeURIComponent(project)}/${encodeURIComponent(name)}`,
  );
}

export async function restoreSnapshot(
  project: string,
  name: string,
): Promise<RestoreSnapshotResult> {
  const r = await apiClient.post(
    `/snapshots/${encodeURIComponent(project)}/${encodeURIComponent(name)}/restore`,
  );
  return r.data as RestoreSnapshotResult;
}
```

- [ ] **Step 4: Implement `useSnapshotCreate`**

`frontend/src/hooks/useSnapshotCreate.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { createSnapshot } from "@/api/snapshots.api";
import { extractApiError } from "@/lib/error";

export function useSnapshotCreate(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (label?: string) => createSnapshot(project, label),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["snapshots", project] });
      toast.success(t("snapshots.created_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 5: Implement `useSnapshotDelete`**

`frontend/src/hooks/useSnapshotDelete.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { deleteSnapshot } from "@/api/snapshots.api";
import { extractApiError } from "@/lib/error";

export function useSnapshotDelete(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (name: string) => deleteSnapshot(project, name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["snapshots", project] });
      toast.success(t("snapshots.deleted_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 6: Implement `useSnapshotRestore`**

`frontend/src/hooks/useSnapshotRestore.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { restoreSnapshot } from "@/api/snapshots.api";
import { extractApiError } from "@/lib/error";

export function useSnapshotRestore(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (name: string) => restoreSnapshot(project, name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["snapshots", project] });
      void qc.invalidateQueries({ queryKey: ["pages", project] });
      void qc.invalidateQueries({ queryKey: ["sessions", project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("snapshots.restored_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 7: Run** → PASS.

- [ ] **Step 8: Add locale keys**

Append to each locale's `snapshots` block:

```json
"created_toast": "...",
"deleted_toast": "...",
"restored_toast": "...",
"restore_modal_title": "...",
"restore_modal_desc": "...",
"restore_typed_label": "...",
"restore_button": "...",
"delete_modal_title": "...",
"delete_modal_desc": "...",
"delete_button": "...",
"create_button": "...",
"create_modal_title": "...",
"create_label_label": "...",
"create_label_placeholder": "...",
"create_submit": "..."
```

- en: `Snapshot created` / `Snapshot deleted` / `Vault restored` / `Restore vault from snapshot?` / `This will revert ALL pages to the state at this snapshot. Operations performed since this snapshot will be lost.` / `Type the snapshot name` / `Restore` / `Delete snapshot?` / `Removes this backup. Cannot be undone.` / `Delete` / `Create snapshot` / `Create manual snapshot` / `Label (optional)` / `e.g. before-cleanup` / `Create`
- uk: `Снапшот створено` / `Снапшот видалено` / `Vault відновлено` / `Відновити vault зі снапшоту?` / `Це поверне УСІ сторінки до стану на момент снапшоту. Операції після нього будуть втрачені.` / `Введіть назву снапшоту` / `Відновити` / `Видалити снапшот?` / `Видаляє резервну копію. Незворотно.` / `Видалити` / `Створити снапшот` / `Створити ручний снапшот` / `Мітка (опціонально)` / `напр., перед-очищенням` / `Створити`
- ru: `Снапшот создан` / `Снапшот удалён` / `Vault восстановлен` / `Восстановить vault из снапшота?` / `Это вернёт ВСЕ страницы к состоянию на момент снапшота. Операции после него будут потеряны.` / `Введите имя снапшота` / `Восстановить` / `Удалить снапшот?` / `Удаляет резервную копию. Необратимо.` / `Удалить` / `Создать снапшот` / `Создать ручной снапшот` / `Метка (опционально)` / `напр., перед-очисткой` / `Создать`

- [ ] **Step 9: Wire SnapshotCard**

Replace `frontend/src/components/widgets/SnapshotCard.tsx`:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { RotateCcw, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { KindBadge, type KindTone } from "./KindBadge";
import { ConfirmDialog } from "./ConfirmDialog";
import { TypedConfirmDialog } from "./TypedConfirmDialog";
import { useSnapshotDelete } from "@/hooks/useSnapshotDelete";
import { useSnapshotRestore } from "@/hooks/useSnapshotRestore";
import type { SnapshotInfo, SnapshotKind } from "@/types/Snapshot";

const KIND_TONE: Record<SnapshotKind, KindTone> = {
  "pre-op": "amber", daily: "blue", manual: "emerald",
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function SnapshotCard({ snapshot: s }: { snapshot: SnapshotInfo }) {
  const { t } = useTranslation();
  const { name: project } = useParams<{ name: string }>();
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const restore = useSnapshotRestore(project ?? "");
  const remove = useSnapshotDelete(project ?? "");

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <span className="break-all font-mono text-xs">{s.name}</span>
            <KindBadge label={t(`snapshots.kind.${s.kind}`)} tone={KIND_TONE[s.kind]} />
          </div>
        </CardHeader>
        <CardContent className="space-y-1 text-xs">
          <div className="text-[hsl(var(--muted-foreground))]">{s.timestamp}</div>
          {s.label && <div><span className="text-[hsl(var(--muted-foreground))]">{t("snapshots.label")}: </span><span>{s.label}</span></div>}
          {s.op_id && (
            <div className="text-[hsl(var(--muted-foreground))]">
              {t("snapshots.op_id")}: <code>{s.op_id}</code>
              {s.op_type && (<>{" · "}{t("snapshots.op_type")}: <code>{s.op_type}</code></>)}
            </div>
          )}
          <div className="text-[hsl(var(--muted-foreground))]">{t("snapshots.size")}: {formatBytes(s.size_bytes)}</div>
          <div className="flex items-center gap-2 pt-2">
            <Button size="sm" variant="outline" disabled={restore.isPending} onClick={() => setRestoreOpen(true)} title={t("snapshots.restore_button")}>
              <RotateCcw className="mr-1 h-3 w-3" />
              {t("snapshots.restore_button")}
            </Button>
            <Button size="sm" variant="outline" disabled={remove.isPending} onClick={() => setDeleteOpen(true)} title={t("snapshots.delete_button")}>
              <Trash2 className="mr-1 h-3 w-3" />
              {t("snapshots.delete_button")}
            </Button>
          </div>
        </CardContent>
      </Card>

      <TypedConfirmDialog
        open={restoreOpen}
        onOpenChange={setRestoreOpen}
        title={t("snapshots.restore_modal_title")}
        description={t("snapshots.restore_modal_desc")}
        expectedPhrase={s.name}
        phraseLabel={t("snapshots.restore_typed_label")}
        confirmLabel={t("snapshots.restore_button")}
        onConfirm={() => {
          restore.mutate(s.name, { onSettled: () => setRestoreOpen(false) });
        }}
        isPending={restore.isPending}
      />

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("snapshots.delete_modal_title")}
        description={t("snapshots.delete_modal_desc")}
        confirmLabel={t("snapshots.delete_button")}
        destructive
        onConfirm={() => {
          remove.mutate(s.name, { onSettled: () => setDeleteOpen(false) });
        }}
        isPending={remove.isPending}
      />
    </>
  );
}
```

- [ ] **Step 10: Wire Create button on Snapshots page**

Modify `frontend/src/pages/Snapshots.tsx` — add a Create button + dialog. Replace the page body (preserve filter/list logic):

```tsx
import { useState, useMemo } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import { useSnapshots } from "@/hooks/useSnapshots";
import { useSnapshotCreate } from "@/hooks/useSnapshotCreate";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { SnapshotCard } from "@/components/widgets/SnapshotCard";
import { SnapshotFilters, type KindFilter } from "@/components/filters/SnapshotFilters";
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from "@/components/ui/alert-dialog";

export function Snapshots() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const [kind, setKind] = useState<KindFilter>("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [label, setLabel] = useState("");
  const snapshotsQuery = useSnapshots(project);
  const create = useSnapshotCreate(project ?? "");

  const filtered = useMemo(() => {
    const all = snapshotsQuery.data ?? [];
    if (kind === "all") return all;
    return all.filter((s) => s.kind === kind);
  }, [snapshotsQuery.data, kind]);

  if (!project) return null;

  const headerControls = (
    <div className="flex items-center gap-3">
      <SnapshotFilters value={kind} onChange={setKind} />
      <Button size="sm" variant="outline" onClick={() => setCreateOpen(true)} disabled={create.isPending}>
        <Plus className="mr-1 h-3 w-3" />
        {t("snapshots.create_button")}
      </Button>
    </div>
  );

  if (snapshotsQuery.isLoading) {
    return (
      <div className="space-y-3">
        {headerControls}
        <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}
        </div>
      </div>
    );
  }

  const empty = (snapshotsQuery.data ?? []).length === 0;

  return (
    <div className="space-y-3">
      {headerControls}
      {empty ? (
        <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
          {t("snapshots.no_snapshots")}
        </div>
      ) : (
        <>
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("snapshots.showing_n", { count: filtered.length })}
          </div>
          <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {filtered.map((s) => <SnapshotCard key={s.name} snapshot={s} />)}
          </div>
        </>
      )}

      <AlertDialog open={createOpen} onOpenChange={(next) => { if (!next) setLabel(""); setCreateOpen(next); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("snapshots.create_modal_title")}</AlertDialogTitle>
            <AlertDialogDescription>&nbsp;</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2">
            <label className="text-sm font-medium">{t("snapshots.create_label_label")}</label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              maxLength={128}
              disabled={create.isPending}
              className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
              placeholder={t("snapshots.create_label_placeholder")}
              autoFocus
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={create.isPending}>
              {t("confirm.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => create.mutate(label || undefined, { onSettled: () => { setCreateOpen(false); setLabel(""); } })}
              disabled={create.isPending}
            >
              {create.isPending ? t("confirm.working") : t("snapshots.create_submit")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
```

- [ ] **Step 11: Update Snapshots.test.tsx**

Add the new keys to the bundle in `frontend/src/__tests__/Snapshots.test.tsx`'s `beforeAll` block (`created_toast`, `restore_modal_title` etc.) so tests don't warn.

- [ ] **Step 12: Run tests + tsc**

```bash
cd frontend && pnpm test && pnpm typecheck
```

- [ ] **Step 13: Commit**

```bash
git add frontend/src/api/snapshots.api.ts frontend/src/hooks/useSnapshotCreate.ts frontend/src/hooks/useSnapshotDelete.ts frontend/src/hooks/useSnapshotRestore.ts frontend/src/__tests__/api-snapshots-mutations.test.ts frontend/src/__tests__/Snapshots.test.tsx frontend/src/components/widgets/SnapshotCard.tsx frontend/src/pages/Snapshots.tsx frontend/public/locales/
git commit -m "feat(frontend): wire Snapshot Create/Delete (Tier 2)/Restore (Tier 3) mutations"
```

---

## Task 5: Suggestions mutations + wire SuggestionCard

**Files:**
- Modify: `frontend/src/api/suggestions.api.ts` (add `approveSuggestion`, `rejectSuggestion`, `deferSuggestion`)
- Create: `frontend/src/hooks/useSuggestionApprove.ts`, `useSuggestionReject.ts`, `useSuggestionDefer.ts`
- Create: `frontend/src/__tests__/api-suggestions-mutations.test.ts`
- Modify: `frontend/src/components/widgets/SuggestionCard.tsx`
- Modify: locales

- [ ] **Step 1: Failing test for api functions**

`frontend/src/__tests__/api-suggestions-mutations.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { approveSuggestion, rejectSuggestion, deferSuggestion } from "../api/suggestions.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("suggestions mutations", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("approveSuggestion POSTs to .../approve", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, operation: "merge_entities", suggestion_id: "ont-1", activity_id: "a", target_path: "x", affected_pages: ["x.md"], wikilinks_rewritten: 0 },
    });
    const out = await approveSuggestion("alpha", "ont-1");
    expect(apiClient.post).toHaveBeenCalledWith("/ontology/alpha/suggestions/ont-1/approve");
    expect(out.success).toBe(true);
  });

  it("rejectSuggestion POSTs to .../reject", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, suggestion_id: "ont-1", status: "rejected" },
    });
    await rejectSuggestion("alpha", "ont-1");
    expect(apiClient.post).toHaveBeenCalledWith("/ontology/alpha/suggestions/ont-1/reject");
  });

  it("deferSuggestion POSTs to .../defer", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, suggestion_id: "ont-1", status: "deferred" },
    });
    await deferSuggestion("alpha", "ont-1");
    expect(apiClient.post).toHaveBeenCalledWith("/ontology/alpha/suggestions/ont-1/defer");
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Append to `frontend/src/api/suggestions.api.ts`**

```ts
export interface ApproveResult {
  success: boolean;
  operation: string;
  suggestion_id: string;
  activity_id: string;
  target_path: string;
  affected_pages: string[];
  wikilinks_rewritten: number;
}

export interface RejectResult {
  success: boolean;
  suggestion_id: string;
  status: string;
}

export async function approveSuggestion(
  project: string, id: string,
): Promise<ApproveResult> {
  const r = await apiClient.post(
    `/ontology/${encodeURIComponent(project)}/suggestions/${encodeURIComponent(id)}/approve`,
  );
  return r.data as ApproveResult;
}

export async function rejectSuggestion(
  project: string, id: string,
): Promise<RejectResult> {
  const r = await apiClient.post(
    `/ontology/${encodeURIComponent(project)}/suggestions/${encodeURIComponent(id)}/reject`,
  );
  return r.data as RejectResult;
}

export async function deferSuggestion(
  project: string, id: string,
): Promise<RejectResult> {
  const r = await apiClient.post(
    `/ontology/${encodeURIComponent(project)}/suggestions/${encodeURIComponent(id)}/defer`,
  );
  return r.data as RejectResult;
}
```

- [ ] **Step 4: Implement hooks**

`frontend/src/hooks/useSuggestionApprove.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { approveSuggestion } from "@/api/suggestions.api";
import { extractApiError } from "@/lib/error";

export function useSuggestionApprove(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (id: string) => approveSuggestion(project, id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["suggestions", project] });
      void qc.invalidateQueries({ queryKey: ["pages", project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("suggestions.approved_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

`frontend/src/hooks/useSuggestionReject.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { rejectSuggestion } from "@/api/suggestions.api";
import { extractApiError } from "@/lib/error";

export function useSuggestionReject(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (id: string) => rejectSuggestion(project, id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["suggestions", project] });
      toast.success(t("suggestions.rejected_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

`frontend/src/hooks/useSuggestionDefer.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { deferSuggestion } from "@/api/suggestions.api";
import { extractApiError } from "@/lib/error";

export function useSuggestionDefer(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (id: string) => deferSuggestion(project, id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["suggestions", project] });
      toast.success(t("suggestions.deferred_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 5: Run api test** → PASS.

- [ ] **Step 6: Add locale keys**

Append to each `suggestions` block:

```json
"approved_toast": "...",
"rejected_toast": "...",
"deferred_toast": "...",
"approve_button": "...",
"reject_button": "...",
"defer_button": "...",
"approve_modal_title": "...",
"approve_modal_desc": "...",
"approve_delete_modal_title": "...",
"approve_delete_modal_desc": "...",
"approve_delete_typed_label": "..."
```

- en: `Suggestion approved` / `Suggestion rejected` / `Suggestion deferred` / `Approve` / `Reject` / `Defer` / `Apply suggestion?` / `This will execute the {{operation}} operation on {{count}} affected pages.` / `Apply delete-page suggestion?` / `This will permanently delete the page from the vault. Type the page name to confirm.` / `Type the page name`
- uk: `Пропозицію затверджено` / `Пропозицію відхилено` / `Пропозицію відкладено` / `Затвердити` / `Відхилити` / `Відкласти` / `Застосувати пропозицію?` / `Виконає операцію {{operation}} над {{count}} сторінками.` / `Застосувати видалення сторінки?` / `Сторінка буде видалена з vault. Введіть назву сторінки для підтвердження.` / `Введіть назву сторінки`
- ru: `Предложение одобрено` / `Предложение отклонено` / `Предложение отложено` / `Одобрить` / `Отклонить` / `Отложить` / `Применить предложение?` / `Выполнит операцию {{operation}} над {{count}} страницами.` / `Применить удаление страницы?` / `Страница будет удалена из vault. Введите имя страницы для подтверждения.` / `Введите имя страницы`

- [ ] **Step 7: Wire SuggestionCard**

Replace `frontend/src/components/widgets/SuggestionCard.tsx` to add dialogs + onClick handlers. The conditional Tier-3 for `delete_page` operation. Full file:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Check, X, Clock } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ConfidenceBar } from "./ConfidenceBar";
import { KindBadge, type KindTone } from "./KindBadge";
import { ConfirmDialog } from "./ConfirmDialog";
import { TypedConfirmDialog } from "./TypedConfirmDialog";
import { MarkdownView } from "@/components/markdown/MarkdownView";
import { pageHref } from "@/lib/pageHref";
import { pageBasename } from "@/lib/pageBasename";
import { useSuggestionApprove } from "@/hooks/useSuggestionApprove";
import { useSuggestionReject } from "@/hooks/useSuggestionReject";
import { useSuggestionDefer } from "@/hooks/useSuggestionDefer";
import type { Suggestion, SuggestionOperation, SuggestionStatus } from "@/types/Suggestion";

const OP_TONE: Record<SuggestionOperation, KindTone> = {
  merge_entities: "blue", rename_entity: "amber", delete_page: "rose",
};
const STATUS_TONE: Record<SuggestionStatus, KindTone> = {
  pending: "amber", approved: "emerald", rejected: "rose", deferred: "zinc",
};

interface Props {
  project: string;
  suggestion: Suggestion;
}

export function SuggestionCard({ project, suggestion: s }: Props) {
  const { t } = useTranslation();
  const fm = s.frontmatter;
  const [approveOpen, setApproveOpen] = useState(false);
  const approve = useSuggestionApprove(project);
  const reject = useSuggestionReject(project);
  const defer = useSuggestionDefer(project);

  const isDelete = fm.operation === "delete_page";
  const targetBasename = isDelete && fm.affected_pages[0]
    ? pageBasename(fm.affected_pages[0])
    : "";

  const isPendingAny = approve.isPending || reject.isPending || defer.isPending;

  return (
    <>
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
            <span className="text-xs text-[hsl(var(--muted-foreground))]">{t("suggestions.confidence")}:</span>
            <ConfidenceBar value={fm.confidence} />
          </div>

          <div>
            <div className="text-xs text-[hsl(var(--muted-foreground))]">{t("suggestions.affected_pages")}:</div>
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
              <span className="text-[hsl(var(--muted-foreground))]">{t("suggestions.proposed_target")}:</span>{" "}
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
              <div className="mt-2"><MarkdownView body={s.body} /></div>
            </details>
          )}

          {fm.status === "pending" && (
            <div className="flex items-center gap-2 pt-1">
              <Button size="sm" variant="outline" disabled={isPendingAny} onClick={() => setApproveOpen(true)} title={t("suggestions.approve_button")}>
                <Check className="mr-1 h-3 w-3" />
                {t("suggestions.approve_button")}
              </Button>
              <Button size="sm" variant="outline" disabled={isPendingAny} onClick={() => reject.mutate(fm.id)} title={t("suggestions.reject_button")}>
                <X className="mr-1 h-3 w-3" />
                {t("suggestions.reject_button")}
              </Button>
              <Button size="sm" variant="outline" disabled={isPendingAny} onClick={() => defer.mutate(fm.id)} title={t("suggestions.defer_button")}>
                <Clock className="mr-1 h-3 w-3" />
                {t("suggestions.defer_button")}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {isDelete ? (
        <TypedConfirmDialog
          open={approveOpen}
          onOpenChange={setApproveOpen}
          title={t("suggestions.approve_delete_modal_title")}
          description={t("suggestions.approve_delete_modal_desc")}
          expectedPhrase={targetBasename}
          phraseLabel={t("suggestions.approve_delete_typed_label")}
          confirmLabel={t("suggestions.approve_button")}
          onConfirm={() => approve.mutate(fm.id, { onSettled: () => setApproveOpen(false) })}
          isPending={approve.isPending}
        />
      ) : (
        <ConfirmDialog
          open={approveOpen}
          onOpenChange={setApproveOpen}
          title={t("suggestions.approve_modal_title")}
          description={t("suggestions.approve_modal_desc", { operation: t(`suggestions.operation.${fm.operation}`), count: fm.affected_pages.length })}
          confirmLabel={t("suggestions.approve_button")}
          onConfirm={() => approve.mutate(fm.id, { onSettled: () => setApproveOpen(false) })}
          isPending={approve.isPending}
        />
      )}
    </>
  );
}
```

- [ ] **Step 8: Update Suggestions.test.tsx**

Add new keys to bundle.

- [ ] **Step 9: Run tests + tsc**

```bash
cd frontend && pnpm test && pnpm typecheck
```

- [ ] **Step 10: Commit**

```bash
git add frontend/src/api/suggestions.api.ts frontend/src/hooks/useSuggestionApprove.ts frontend/src/hooks/useSuggestionReject.ts frontend/src/hooks/useSuggestionDefer.ts frontend/src/__tests__/api-suggestions-mutations.test.ts frontend/src/__tests__/Suggestions.test.tsx frontend/src/components/widgets/SuggestionCard.tsx frontend/public/locales/
git commit -m "feat(frontend): wire Suggestion Approve (Tier 2/3 conditional) + Reject + Defer mutations"
```

---

## Task 6: Dead-Letter mutations + wire DeadLetterRow + DeadLetterDetail

**Files:**
- Modify: `frontend/src/api/dead_letter.api.ts` (add `retryDeadLetter`, `dismissDeadLetter`)
- Create: `frontend/src/hooks/useDeadLetterRetry.ts`, `useDeadLetterDismiss.ts`
- Create: `frontend/src/__tests__/api-dead-letter-mutations.test.ts`
- Modify: `frontend/src/components/widgets/DeadLetterRow.tsx`
- Modify: `frontend/src/pages/DeadLetterDetail.tsx`
- Modify: locales

- [ ] **Step 1: Failing test**

`frontend/src/__tests__/api-dead-letter-mutations.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { retryDeadLetter, dismissDeadLetter } from "../api/dead_letter.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

describe("dead-letter mutations", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });
  afterEach(() => vi.resetAllMocks());

  it("retryDeadLetter POSTs to /dead-letter/{id}/retry", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        id: "j1", kind: "ingest", payload: {}, status: "queued",
        attempt: 0, next_attempt_at: "2026-04-29T12:00:00Z",
        created_at: "2026-04-29T11:00:00Z", started_at: null, finished_at: null,
        error: null, error_traceback: null, project_name: "alpha",
      },
    });
    const out = await retryDeadLetter("j1");
    expect(apiClient.post).toHaveBeenCalledWith("/dead-letter/j1/retry");
    expect(out.id).toBe("j1");
  });

  it("dismissDeadLetter DELETEs /dead-letter/{id}", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: null });
    await dismissDeadLetter("j1");
    expect(apiClient.delete).toHaveBeenCalledWith("/dead-letter/j1");
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Append to `frontend/src/api/dead_letter.api.ts`**

```ts
export async function retryDeadLetter(jobId: string): Promise<Job> {
  const r = await apiClient.post(`/dead-letter/${encodeURIComponent(jobId)}/retry`);
  return r.data as Job;
}

export async function dismissDeadLetter(jobId: string): Promise<void> {
  await apiClient.delete(`/dead-letter/${encodeURIComponent(jobId)}`);
}
```

- [ ] **Step 4: Implement hooks**

`frontend/src/hooks/useDeadLetterRetry.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { retryDeadLetter } from "@/api/dead_letter.api";
import { extractApiError } from "@/lib/error";

export function useDeadLetterRetry() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (jobId: string) => retryDeadLetter(jobId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dead-letter"] });
      void qc.invalidateQueries({ queryKey: ["dead-letter-entry"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
      toast.success(t("dead_letter.retried_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

`frontend/src/hooks/useDeadLetterDismiss.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { dismissDeadLetter } from "@/api/dead_letter.api";
import { extractApiError } from "@/lib/error";

export function useDeadLetterDismiss() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (jobId: string) => dismissDeadLetter(jobId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dead-letter"] });
      void qc.invalidateQueries({ queryKey: ["dead-letter-entry"] });
      toast.success(t("dead_letter.dismissed_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Add locale keys**

Append to each `dead_letter` block:

```json
"retried_toast": "...",
"dismissed_toast": "...",
"retry_button": "...",
"dismiss_button": "...",
"dismiss_modal_title": "...",
"dismiss_modal_desc": "..."
```

- en: `Job re-queued` / `Job dismissed` / `Retry` / `Dismiss` / `Dismiss failed job?` / `This permanently removes the job from the dead-letter queue.`
- uk: `Задачу повторно поставлено в чергу` / `Задачу відхилено` / `Повторити` / `Відхилити` / `Відхилити збійну задачу?` / `Це назавжди видаляє задачу з черги збоїв.`
- ru: `Задача переставлена в очередь` / `Задача отклонена` / `Повторить` / `Отклонить` / `Отклонить сбойную задачу?` / `Это навсегда удаляет задачу из очереди сбоев.`

- [ ] **Step 7: Wire DeadLetterRow**

Replace `frontend/src/components/widgets/DeadLetterRow.tsx`:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { ChevronRight, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectBadge } from "./ProjectBadge";
import { ConfirmDialog } from "./ConfirmDialog";
import { useDeadLetterRetry } from "@/hooks/useDeadLetterRetry";
import { useDeadLetterDismiss } from "@/hooks/useDeadLetterDismiss";
import type { Job } from "@/types/Job";

const MAX_ATTEMPTS = 4;

export function DeadLetterRow({ job: j }: { job: Job }) {
  const { t } = useTranslation();
  const [dismissOpen, setDismissOpen] = useState(false);
  const retry = useDeadLetterRetry();
  const dismiss = useDeadLetterDismiss();

  return (
    <>
      <div className="flex items-center gap-3 rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm">
        <ProjectBadge name={j.project_name} />
        <span className="rounded bg-[hsl(var(--muted))] px-1.5 py-0.5 text-xs">{j.kind}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-xs" title={j.id}>{j.id.slice(0, 8)}…</span>
            <span className="text-xs text-[hsl(var(--muted-foreground))]">
              {t("dead_letter.attempt_n_of_m", { n: j.attempt, max: MAX_ATTEMPTS })}
            </span>
            {j.finished_at && <span className="text-xs text-[hsl(var(--muted-foreground))]">· {j.finished_at}</span>}
          </div>
          {j.error && <div className="truncate text-xs text-red-700 dark:text-red-400" title={j.error}>{j.error}</div>}
        </div>
        <Button asChild size="sm" variant="ghost">
          <Link to={`/dead-letter/${encodeURIComponent(j.id)}`}>
            {t("dead_letter.view_details")}
            <ChevronRight className="ml-1 h-3 w-3" />
          </Link>
        </Button>
        <Button size="sm" variant="outline" disabled={retry.isPending} onClick={() => retry.mutate(j.id)} title={t("dead_letter.retry_button")}>
          <RotateCcw className="mr-1 h-3 w-3" />
          {t("dead_letter.retry_button")}
        </Button>
        <Button size="sm" variant="outline" disabled={dismiss.isPending} onClick={() => setDismissOpen(true)} title={t("dead_letter.dismiss_button")}>
          <X className="mr-1 h-3 w-3" />
          {t("dead_letter.dismiss_button")}
        </Button>
      </div>

      <ConfirmDialog
        open={dismissOpen}
        onOpenChange={setDismissOpen}
        title={t("dead_letter.dismiss_modal_title")}
        description={t("dead_letter.dismiss_modal_desc")}
        confirmLabel={t("dead_letter.dismiss_button")}
        destructive
        onConfirm={() => dismiss.mutate(j.id, { onSettled: () => setDismissOpen(false) })}
        isPending={dismiss.isPending}
      />
    </>
  );
}
```

- [ ] **Step 8: Wire DeadLetterDetail**

Modify `frontend/src/pages/DeadLetterDetail.tsx` — replace the disabled Retry/Dismiss buttons:

```tsx
// at top
import { useState } from "react";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { useDeadLetterRetry } from "@/hooks/useDeadLetterRetry";
import { useDeadLetterDismiss } from "@/hooks/useDeadLetterDismiss";

// inside component
const [dismissOpen, setDismissOpen] = useState(false);
const retry = useDeadLetterRetry();
const dismiss = useDeadLetterDismiss();

// replace the two Buttons in the header div with:
<Button size="sm" variant="outline" disabled={retry.isPending} onClick={() => j && retry.mutate(j.id)} title={t("dead_letter.retry_button")}>
  <RotateCcw className="mr-1 h-3 w-3" />
  {t("dead_letter.retry_button")}
</Button>
<Button size="sm" variant="outline" disabled={dismiss.isPending} onClick={() => setDismissOpen(true)} title={t("dead_letter.dismiss_button")}>
  <X className="mr-1 h-3 w-3" />
  {t("dead_letter.dismiss_button")}
</Button>

// at the end of the article, before the closing </article>:
<ConfirmDialog
  open={dismissOpen}
  onOpenChange={setDismissOpen}
  title={t("dead_letter.dismiss_modal_title")}
  description={t("dead_letter.dismiss_modal_desc")}
  confirmLabel={t("dead_letter.dismiss_button")}
  destructive
  onConfirm={() => j && dismiss.mutate(j.id, { onSettled: () => setDismissOpen(false) })}
  isPending={dismiss.isPending}
/>
```

(Read the current file fully and apply minimally — the rest of the layout stays.)

- [ ] **Step 9: Update DeadLetter.test.tsx + DeadLetterDetail.test.tsx**

Add new keys to both test bundles.

- [ ] **Step 10: Run tests + tsc**

- [ ] **Step 11: Commit**

```bash
git add frontend/src/api/dead_letter.api.ts frontend/src/hooks/useDeadLetterRetry.ts frontend/src/hooks/useDeadLetterDismiss.ts frontend/src/__tests__/api-dead-letter-mutations.test.ts frontend/src/__tests__/DeadLetter.test.tsx frontend/src/__tests__/DeadLetterDetail.test.tsx frontend/src/components/widgets/DeadLetterRow.tsx frontend/src/pages/DeadLetterDetail.tsx frontend/public/locales/
git commit -m "feat(frontend): wire DeadLetter Retry (Tier 1) + Dismiss (Tier 2) mutations"
```

---

## Task 7: Lost-Sessions mutations + wire LostSessionRow

**Files:**
- Modify: `frontend/src/api/lost_sessions.api.ts` (add `importLostSession`, `ignoreLostSession`)
- Create: `frontend/src/hooks/useLostSessionImport.ts`, `useLostSessionIgnore.ts`
- Create: `frontend/src/__tests__/api-lost-sessions-mutations.test.ts`
- Modify: `frontend/src/components/widgets/LostSessionRow.tsx`
- Modify: locales

- [ ] **Step 1: Failing test**

`frontend/src/__tests__/api-lost-sessions-mutations.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { importLostSession, ignoreLostSession } from "../api/lost_sessions.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("lost-sessions mutations", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("importLostSession POSTs body with project_name", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        id: "j1", kind: "ingest", payload: {}, status: "queued",
        attempt: 0, next_attempt_at: "t", created_at: "t",
        started_at: null, finished_at: null, error: null, error_traceback: null,
        project_name: "alpha",
      },
    });
    const out = await importLostSession("abc", { project_name: "alpha", transcript_path: "/x.md" });
    expect(apiClient.post).toHaveBeenCalledWith("/lost-sessions/abc/import", {
      project_name: "alpha", transcript_path: "/x.md",
    });
    expect(out.id).toBe("j1");
  });

  it("ignoreLostSession POSTs body with project_name + sha", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { ignored_count: 1 } });
    const out = await ignoreLostSession("abc", { project_name: "alpha", sha: "deadbeef" });
    expect(apiClient.post).toHaveBeenCalledWith("/lost-sessions/abc/ignore", {
      project_name: "alpha", sha: "deadbeef",
    });
    expect(out.ignored_count).toBe(1);
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Append to `frontend/src/api/lost_sessions.api.ts`**

```ts
import type { Job } from "@/types/Job";

export interface ImportLostSessionBody {
  project_name: string;
  transcript_path?: string;
}

export interface IgnoreLostSessionBody {
  project_name: string;
  sha?: string;
}

export async function importLostSession(
  session_id: string,
  body: ImportLostSessionBody,
): Promise<Job> {
  const r = await apiClient.post(
    `/lost-sessions/${encodeURIComponent(session_id)}/import`,
    body,
  );
  return r.data as Job;
}

export async function ignoreLostSession(
  session_id: string,
  body: IgnoreLostSessionBody,
): Promise<{ ignored_count: number }> {
  const r = await apiClient.post(
    `/lost-sessions/${encodeURIComponent(session_id)}/ignore`,
    body,
  );
  return r.data as { ignored_count: number };
}
```

- [ ] **Step 4: Implement hooks**

`frontend/src/hooks/useLostSessionImport.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { importLostSession, type ImportLostSessionBody } from "@/api/lost_sessions.api";
import { extractApiError } from "@/lib/error";

interface ImportArgs {
  session_id: string;
  body: ImportLostSessionBody;
}

export function useLostSessionImport() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ session_id, body }: ImportArgs) => importLostSession(session_id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      void qc.invalidateQueries({ queryKey: ["dead-letter"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
      void qc.invalidateQueries({ queryKey: ["sessions"] });
      toast.success(t("lost_sessions.imported_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

`frontend/src/hooks/useLostSessionIgnore.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ignoreLostSession, type IgnoreLostSessionBody } from "@/api/lost_sessions.api";
import { extractApiError } from "@/lib/error";

interface IgnoreArgs {
  session_id: string;
  body: IgnoreLostSessionBody;
}

export function useLostSessionIgnore() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ session_id, body }: IgnoreArgs) => ignoreLostSession(session_id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      toast.success(t("lost_sessions.ignored_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Add locale keys**

Append to each `lost_sessions` block:

```json
"imported_toast": "...",
"ignored_toast": "...",
"import_button": "...",
"ignore_button": "...",
"ignore_modal_title": "...",
"ignore_modal_desc": "..."
```

- en: `Import queued` / `Marked ignored` / `Import` / `Ignore` / `Mark session as ignored?` / `This will hide the session from the lost-sessions list. The transcript file is not deleted.`
- uk: `Імпорт у черзі` / `Позначено як ігнорувати` / `Імпортувати` / `Ігнорувати` / `Позначити сесію як ігнорувати?` / `Це сховає сесію зі списку загублених. Файл транскрипту не видаляється.`
- ru: `Импорт в очереди` / `Помечено как игнорировать` / `Импортировать` / `Игнорировать` / `Пометить сессию как игнорировать?` / `Это скроет сессию из списка потерянных. Файл транскрипта не удаляется.`

- [ ] **Step 7: Wire LostSessionRow**

Replace `frontend/src/components/widgets/LostSessionRow.tsx`:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectBadge } from "./ProjectBadge";
import { ConfirmDialog } from "./ConfirmDialog";
import { useLostSessionImport } from "@/hooks/useLostSessionImport";
import { useLostSessionIgnore } from "@/hooks/useLostSessionIgnore";
import type { LostSession } from "@/types/LostSession";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function LostSessionRow({ session: s }: { session: LostSession }) {
  const { t } = useTranslation();
  const [ignoreOpen, setIgnoreOpen] = useState(false);
  const importMut = useLostSessionImport();
  const ignoreMut = useLostSessionIgnore();

  return (
    <>
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
        <Button
          size="sm" variant="outline"
          disabled={importMut.isPending}
          onClick={() => importMut.mutate({
            session_id: s.session_id,
            body: { project_name: s.project_name, transcript_path: s.transcript_path },
          })}
          title={t("lost_sessions.import_button")}
        >
          <Download className="mr-1 h-3 w-3" />
          {t("lost_sessions.import_button")}
        </Button>
        <Button
          size="sm" variant="outline"
          disabled={ignoreMut.isPending}
          onClick={() => setIgnoreOpen(true)}
          title={t("lost_sessions.ignore_button")}
        >
          <EyeOff className="mr-1 h-3 w-3" />
          {t("lost_sessions.ignore_button")}
        </Button>
      </div>

      <ConfirmDialog
        open={ignoreOpen}
        onOpenChange={setIgnoreOpen}
        title={t("lost_sessions.ignore_modal_title")}
        description={t("lost_sessions.ignore_modal_desc")}
        confirmLabel={t("lost_sessions.ignore_button")}
        onConfirm={() => ignoreMut.mutate(
          { session_id: s.session_id, body: { project_name: s.project_name, sha: s.sha } },
          { onSettled: () => setIgnoreOpen(false) },
        )}
        isPending={ignoreMut.isPending}
      />
    </>
  );
}
```

- [ ] **Step 8: Update LostSessions.test.tsx**

Add new keys to bundle.

- [ ] **Step 9: Run + commit**

```bash
cd frontend && pnpm test && pnpm typecheck
git add frontend/src/api/lost_sessions.api.ts frontend/src/hooks/useLostSessionImport.ts frontend/src/hooks/useLostSessionIgnore.ts frontend/src/__tests__/api-lost-sessions-mutations.test.ts frontend/src/__tests__/LostSessions.test.tsx frontend/src/components/widgets/LostSessionRow.tsx frontend/public/locales/
git commit -m "feat(frontend): wire LostSession Import (Tier 1) + Ignore (Tier 2) mutations"
```

---

## Task 8: Activity Undo + wire ActivityRow + ActivityDetail

**Files:**
- Modify: `frontend/src/api/activity.api.ts` (add `undoOperation`)
- Create: `frontend/src/hooks/useActivityUndo.ts`
- Create: `frontend/src/__tests__/api-activity-mutations.test.ts`
- Modify: `frontend/src/components/widgets/ActivityRow.tsx`
- Modify: `frontend/src/pages/ActivityDetail.tsx`
- Modify: locales

- [ ] **Step 1: Failing test**

`frontend/src/__tests__/api-activity-mutations.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { undoOperation } from "../api/activity.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("activity mutations", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("undoOperation POSTs to /activity/{p}/{op}/undo", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, op_id: "op1", restored_pages: ["wiki/a.md"], new_entry_id: "op2" },
    });
    const out = await undoOperation("alpha", "op1");
    expect(apiClient.post).toHaveBeenCalledWith("/activity/alpha/op1/undo");
    expect(out.success).toBe(true);
    expect(out.restored_pages).toEqual(["wiki/a.md"]);
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Append to `frontend/src/api/activity.api.ts`**

```ts
export interface UndoApiResult {
  success: boolean;
  op_id: string;
  restored_pages: string[];
  new_entry_id: string;
}

export async function undoOperation(
  project: string, op_id: string,
): Promise<UndoApiResult> {
  const r = await apiClient.post(
    `/activity/${encodeURIComponent(project)}/${encodeURIComponent(op_id)}/undo`,
  );
  return r.data as UndoApiResult;
}
```

- [ ] **Step 4: Implement hook**

`frontend/src/hooks/useActivityUndo.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { undoOperation } from "@/api/activity.api";
import { extractApiError } from "@/lib/error";

interface UndoArgs {
  project: string;
  op_id: string;
}

export function useActivityUndo() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ project, op_id }: UndoArgs) => undoOperation(project, op_id),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["activity"] });
      void qc.invalidateQueries({ queryKey: ["pages", vars.project] });
      void qc.invalidateQueries({ queryKey: ["sessions", vars.project] });
      void qc.invalidateQueries({ queryKey: ["trash", vars.project] });
      toast.success(t("activity.undone_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Add locale keys**

Append to each `activity` block:

```json
"undone_toast": "...",
"undo_button": "...",
"undo_modal_title": "...",
"undo_modal_desc": "..."
```

- en: `Operation undone` / `Undo` / `Undo this operation?` / `This will revert all pages affected by this operation to their state before it ran.`
- uk: `Операцію скасовано` / `Скасувати` / `Скасувати цю операцію?` / `Це поверне усі сторінки, торкнуті цією операцією, до стану до її виконання.`
- ru: `Операция отменена` / `Отменить` / `Отменить эту операцию?` / `Это вернёт все страницы, затронутые операцией, к состоянию до её выполнения.`

- [ ] **Step 7: Wire ActivityRow**

Read existing `frontend/src/components/widgets/ActivityRow.tsx`. Replace the disabled Undo button with:

```tsx
import { useState } from "react";
import { useParams } from "react-router";
import { ConfirmDialog } from "./ConfirmDialog";
import { useActivityUndo } from "@/hooks/useActivityUndo";

// inside component, after destructuring entry:
const { name: project } = useParams<{ name: string }>();
const [undoOpen, setUndoOpen] = useState(false);
const undo = useActivityUndo();
const canUndo = e.can_undo && !e.undone;

// replace Undo button with:
<Button
  size="sm" variant="ghost"
  disabled={!canUndo || undo.isPending}
  onClick={() => setUndoOpen(true)}
  title={canUndo ? t("activity.undo_button") : t("activity.undo_disabled")}
>
  {t("activity.undo_button")}
</Button>

// at end of fragment:
<ConfirmDialog
  open={undoOpen}
  onOpenChange={setUndoOpen}
  title={t("activity.undo_modal_title")}
  description={t("activity.undo_modal_desc")}
  confirmLabel={t("activity.undo_button")}
  destructive
  onConfirm={() => project && undo.mutate(
    { project, op_id: e.op_id },
    { onSettled: () => setUndoOpen(false) },
  )}
  isPending={undo.isPending}
/>
```

(Read current file fully and apply minimally; preserve op-icon, summary, affected pages count, Detail link.)

- [ ] **Step 8: Wire ActivityDetail**

Same pattern in `frontend/src/pages/ActivityDetail.tsx`. Replace the disabled Undo at line ~41:

```tsx
const [undoOpen, setUndoOpen] = useState(false);
const undo = useActivityUndo();
const canUndo = e.can_undo && !e.undone;

// replace button:
<Button
  size="sm" variant="outline"
  disabled={!canUndo || undo.isPending}
  onClick={() => setUndoOpen(true)}
>
  {t("activity.undo_button")}
</Button>

// add at end:
<ConfirmDialog
  open={undoOpen}
  onOpenChange={setUndoOpen}
  title={t("activity.undo_modal_title")}
  description={t("activity.undo_modal_desc")}
  confirmLabel={t("activity.undo_button")}
  destructive
  onConfirm={() => project && undo.mutate(
    { project, op_id: e.op_id },
    { onSettled: () => setUndoOpen(false) },
  )}
  isPending={undo.isPending}
/>
```

(Read full file; `project` likely comes from `useParams` in detail page or from route param.)

- [ ] **Step 9: Update ActivityCenter.test.tsx + ActivityDetail.test.tsx**

Add new keys.

- [ ] **Step 10: Run + commit**

```bash
cd frontend && pnpm test && pnpm typecheck
git add frontend/src/api/activity.api.ts frontend/src/hooks/useActivityUndo.ts frontend/src/__tests__/api-activity-mutations.test.ts frontend/src/__tests__/ActivityCenter.test.tsx frontend/src/__tests__/ActivityDetail.test.tsx frontend/src/components/widgets/ActivityRow.tsx frontend/src/pages/ActivityDetail.tsx frontend/public/locales/
git commit -m "feat(frontend): wire Activity Undo (Tier 2) mutation"
```

---

## Task 9: Sessions Ingest + wire SessionDetail

**Files:**
- Modify: `frontend/src/api/sessions.api.ts` (add `ingestSession`)
- Create: `frontend/src/hooks/useSessionIngest.ts`
- Create: `frontend/src/__tests__/api-sessions-mutations.test.ts`
- Modify: `frontend/src/pages/SessionDetail.tsx`
- Modify: locales

- [ ] **Step 1: Failing test**

`frontend/src/__tests__/api-sessions-mutations.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { ingestSession } from "../api/sessions.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("sessions mutations", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("ingestSession POSTs body with transcript_path", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        id: "j1", kind: "ingest", payload: {}, status: "queued",
        attempt: 0, next_attempt_at: "t", created_at: "t",
        started_at: null, finished_at: null, error: null, error_traceback: null,
        project_name: "alpha",
      },
    });
    const out = await ingestSession("alpha", "abc", "/x.md");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/sessions/alpha/abc/ingest",
      { transcript_path: "/x.md" },
    );
    expect(out.id).toBe("j1");
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Append to `frontend/src/api/sessions.api.ts`**

```ts
import type { Job } from "@/types/Job";

export async function ingestSession(
  project: string,
  session_id: string,
  transcript_path: string,
): Promise<Job> {
  const r = await apiClient.post(
    `/sessions/${encodeURIComponent(project)}/${encodeURIComponent(session_id)}/ingest`,
    { transcript_path },
  );
  return r.data as Job;
}
```

- [ ] **Step 4: Implement hook**

`frontend/src/hooks/useSessionIngest.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ingestSession } from "@/api/sessions.api";
import { extractApiError } from "@/lib/error";

interface IngestArgs {
  project: string;
  session_id: string;
  transcript_path: string;
}

export function useSessionIngest() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ project, session_id, transcript_path }: IngestArgs) =>
      ingestSession(project, session_id, transcript_path),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["session", vars.project, vars.session_id] });
      void qc.invalidateQueries({ queryKey: ["sessions", vars.project] });
      void qc.invalidateQueries({ queryKey: ["pages", vars.project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
      toast.success(t("sessions.ingested_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Add locale keys**

Append to each `sessions` block:

```json
"ingested_toast": "...",
"ingest_button": "..."
```

- en: `Ingest queued` / `Ingest`
- uk: `Інжест у черзі` / `Інжест`
- ru: `Ингест в очереди` / `Ингест`

- [ ] **Step 7: Wire SessionDetail**

Read `frontend/src/pages/SessionDetail.tsx`. Replace disabled Ingest button:

```tsx
import { useSessionIngest } from "@/hooks/useSessionIngest";

// inside component:
const ingest = useSessionIngest();

// replace button:
<Button
  size="sm" variant="outline"
  disabled={ingest.isPending || !session?.transcript_path}
  onClick={() => project && session?.transcript_path && ingest.mutate({
    project, session_id: sid!, transcript_path: session.transcript_path,
  })}
  title={t("sessions.ingest_button")}
>
  {t("sessions.ingest_button")}
</Button>
```

(Adapt to actual prop names — `sid`, `session`, etc. — from current component.)

- [ ] **Step 8: Update SessionDetail.test.tsx**

Add new keys.

- [ ] **Step 9: Run + commit**

```bash
cd frontend && pnpm test && pnpm typecheck
git add frontend/src/api/sessions.api.ts frontend/src/hooks/useSessionIngest.ts frontend/src/__tests__/api-sessions-mutations.test.ts frontend/src/__tests__/SessionDetail.test.tsx frontend/src/pages/SessionDetail.tsx frontend/public/locales/
git commit -m "feat(frontend): wire Session Ingest (Tier 1) mutation"
```

---

## Task 10: Page Verify + Delete + wire PageDetail

**Files:**
- Modify: `frontend/src/api/pages.api.ts` (add `verifyPage`, `deletePage`)
- Create: `frontend/src/hooks/usePageVerify.ts`, `usePageDelete.ts`
- Create: `frontend/src/__tests__/api-pages-mutations.test.ts`
- Modify: `frontend/src/pages/PageDetail.tsx`
- Modify: locales

- [ ] **Step 1: Failing test**

`frontend/src/__tests__/api-pages-mutations.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { verifyPage, deletePage, patchPage } from "../api/pages.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

describe("pages mutations", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.patch).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });
  afterEach(() => vi.resetAllMocks());

  it("verifyPage POSTs to /pages/{p}/{ref}/verify", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { success: true, snapshot_path: "p", activity_id: "a" },
    });
    const out = await verifyPage("alpha", "wiki/foo.md");
    expect(apiClient.post).toHaveBeenCalledWith("/pages/alpha/wiki/foo.md/verify");
    expect(out.success).toBe(true);
  });

  it("deletePage DELETEs and returns trash_id", async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({
      data: { success: true, snapshot_path: "p", activity_id: "a", trash_id: "t1" },
    });
    const out = await deletePage("alpha", "wiki/foo.md");
    expect(apiClient.delete).toHaveBeenCalledWith("/pages/alpha/wiki/foo.md");
    expect(out.trash_id).toBe("t1");
  });

  it("patchPage PATCHes with frontmatter+body", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({
      data: { success: true, snapshot_path: "p", activity_id: "a" },
    });
    const out = await patchPage("alpha", "wiki/foo.md", {
      frontmatter: { status: "verified" },
      body: "## new",
    });
    expect(apiClient.patch).toHaveBeenCalledWith(
      "/pages/alpha/wiki/foo.md",
      { frontmatter: { status: "verified" }, body: "## new" },
    );
    expect(out.success).toBe(true);
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Append to `frontend/src/api/pages.api.ts`**

```ts
export interface PatchResult {
  success: boolean;
  snapshot_path: string | null;
  activity_id: string;
}

export interface DeleteResult {
  success: boolean;
  snapshot_path: string | null;
  activity_id: string;
  trash_id: string;
}

export interface PagePatchBody {
  frontmatter?: Record<string, unknown>;
  body?: string;
}

export async function verifyPage(
  project: string, page_ref: string,
): Promise<PatchResult> {
  const r = await apiClient.post(
    `/pages/${encodeURIComponent(project)}/${page_ref}/verify`,
  );
  return r.data as PatchResult;
}

export async function deletePage(
  project: string, page_ref: string,
): Promise<DeleteResult> {
  const r = await apiClient.delete(
    `/pages/${encodeURIComponent(project)}/${page_ref}`,
  );
  return r.data as DeleteResult;
}

export async function patchPage(
  project: string, page_ref: string, body: PagePatchBody,
): Promise<PatchResult> {
  const r = await apiClient.patch(
    `/pages/${encodeURIComponent(project)}/${page_ref}`,
    body,
  );
  return r.data as PatchResult;
}
```

(Note: `page_ref` is interpolated raw because Trash/Pages use the path-segment encoding helper `pageHref` for URLs going INTO router; the api side calls go directly through axios which forwards the literal path. Existing `getPage` in `pages.api.ts` does the same — match its style.)

Look at the existing `pages.api.ts` to confirm encoding pattern. If existing `getPage(project, page_ref)` uses `encodeURIComponent` on `page_ref`, do the same here. **Read it before writing.**

- [ ] **Step 4: Implement hooks**

`frontend/src/hooks/usePageVerify.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { verifyPage } from "@/api/pages.api";
import { extractApiError } from "@/lib/error";

interface VerifyArgs {
  project: string;
  page_ref: string;
}

export function usePageVerify() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ project, page_ref }: VerifyArgs) => verifyPage(project, page_ref),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["page", vars.project, vars.page_ref] });
      void qc.invalidateQueries({ queryKey: ["pages", vars.project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("pages.verified_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

`frontend/src/hooks/usePageDelete.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { deletePage } from "@/api/pages.api";
import { extractApiError } from "@/lib/error";

interface DeleteArgs {
  project: string;
  page_ref: string;
}

export function usePageDelete() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ project, page_ref }: DeleteArgs) => deletePage(project, page_ref),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["pages", vars.project] });
      void qc.invalidateQueries({ queryKey: ["page", vars.project, vars.page_ref] });
      void qc.invalidateQueries({ queryKey: ["trash", vars.project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("pages.deleted_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Add locale keys**

Append to each `pages` block:

```json
"verified_toast": "...",
"deleted_toast": "...",
"verify_button": "...",
"delete_button": "...",
"edit_button": "...",
"delete_modal_title": "...",
"delete_modal_desc": "..."
```

- en: `Page verified` / `Moved to trash` / `Verify` / `Delete` / `Edit` / `Move to trash?` / `The page is moved to /trash and can be restored from there.`
- uk: `Сторінку перевірено` / `Переміщено до кошика` / `Перевірити` / `Видалити` / `Редагувати` / `Перемістити до кошика?` / `Сторінка переміщується до /trash і її можна відновити звідти.`
- ru: `Страница подтверждена` / `Перемещено в корзину` / `Подтвердить` / `Удалить` / `Редактировать` / `Переместить в корзину?` / `Страница перемещается в /trash и может быть восстановлена оттуда.`

- [ ] **Step 7: Wire PageDetail (Verify Tier 1, Delete Tier 2, Edit navigates)**

Read full `frontend/src/pages/PageDetail.tsx`. Replace the disabled Edit/Verify/Delete buttons with:

```tsx
import { useState } from "react";
import { useNavigate } from "react-router";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { usePageVerify } from "@/hooks/usePageVerify";
import { usePageDelete } from "@/hooks/usePageDelete";

// inside component (assuming `project` and `pagePath` are derived):
const navigate = useNavigate();
const verify = usePageVerify();
const remove = usePageDelete();
const [deleteOpen, setDeleteOpen] = useState(false);

// Edit (navigates to editor)
<Button
  size="sm" variant="outline"
  onClick={() => navigate(`/project/${encodeURIComponent(project)}/pages/${pagePath}/edit`)}
  title={t("pages.edit_button")}
>
  {t("pages.edit_button")}
</Button>

// Verify (Tier 1)
<Button
  size="sm" variant="outline"
  disabled={verify.isPending}
  onClick={() => verify.mutate({ project, page_ref: pagePath })}
  title={t("pages.verify_button")}
>
  {t("pages.verify_button")}
</Button>

// Delete (Tier 2)
<Button
  size="sm" variant="outline"
  disabled={remove.isPending}
  onClick={() => setDeleteOpen(true)}
  title={t("pages.delete_button")}
>
  {t("pages.delete_button")}
</Button>

// at end of component:
<ConfirmDialog
  open={deleteOpen}
  onOpenChange={setDeleteOpen}
  title={t("pages.delete_modal_title")}
  description={t("pages.delete_modal_desc")}
  confirmLabel={t("pages.delete_button")}
  destructive
  onConfirm={() => remove.mutate(
    { project, page_ref: pagePath },
    { onSettled: () => setDeleteOpen(false) },
  )}
  isPending={remove.isPending}
/>
```

(Adapt prop names to actual page; `pagePath` likely from `useParams<{ "*": string }>()`. The `/edit` route is added in Task 11.)

- [ ] **Step 8: Update PageDetail.test.tsx**

Add keys.

- [ ] **Step 9: Run + commit**

```bash
cd frontend && pnpm test && pnpm typecheck
git add frontend/src/api/pages.api.ts frontend/src/hooks/usePageVerify.ts frontend/src/hooks/usePageDelete.ts frontend/src/__tests__/api-pages-mutations.test.ts frontend/src/__tests__/PageDetail.test.tsx frontend/src/pages/PageDetail.tsx frontend/public/locales/
git commit -m "feat(frontend): wire Page Verify (Tier 1) + Delete (Tier 2) + Edit navigation"
```

---

## Task 11: PagePatch + PageEdit page + route wiring

**Files:**
- Create: `frontend/src/hooks/usePagePatch.ts`
- Create: `frontend/src/pages/PageEdit.tsx`
- Create: `frontend/src/__tests__/PageEdit.test.tsx`
- Modify: `frontend/src/App.tsx` (add `/project/:name/pages/*/edit` route)
- Modify: locales

- [ ] **Step 1: Implement `usePagePatch`**

`frontend/src/hooks/usePagePatch.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { patchPage, type PagePatchBody } from "@/api/pages.api";
import { extractApiError } from "@/lib/error";

interface PatchArgs {
  project: string;
  page_ref: string;
  body: PagePatchBody;
}

export function usePagePatch() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ project, page_ref, body }: PatchArgs) => patchPage(project, page_ref, body),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["page", vars.project, vars.page_ref] });
      void qc.invalidateQueries({ queryKey: ["pages", vars.project] });
      void qc.invalidateQueries({ queryKey: ["page-backlinks", vars.project, vars.page_ref] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("pages.editor.saved_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 2: Add locale keys for editor**

Append to each `pages` block:

```json
"editor": {
  "title": "...",
  "title_field": "...",
  "type": "...",
  "status": "...",
  "flavor": "...",
  "confidence": "...",
  "aliases": "...",
  "aliases_hint": "...",
  "body_label": "...",
  "preview": "...",
  "save": "...",
  "cancel": "...",
  "saved_toast": "...",
  "discard_modal_title": "...",
  "discard_modal_desc": "...",
  "discard_button": "...",
  "loading": "..."
}
```

- en: `Edit page` / `Title` / `Type` / `Status` / `Flavor` / `Confidence` / `Aliases` / `Comma-separated` / `Body (markdown)` / `Preview` / `Save` / `Cancel` / `Page saved` / `Discard unsaved changes?` / `Your edits will be lost.` / `Discard` / `Loading…`
- uk: `Редагувати сторінку` / `Заголовок` / `Тип` / `Статус` / `Стиль` / `Впевненість` / `Псевдоніми` / `Через кому` / `Текст (markdown)` / `Перегляд` / `Зберегти` / `Скасувати` / `Сторінку збережено` / `Відкинути незбережені зміни?` / `Ваші зміни будуть втрачені.` / `Відкинути` / `Завантаження…`
- ru: `Редактировать страницу` / `Заголовок` / `Тип` / `Статус` / `Стиль` / `Уверенность` / `Псевдонимы` / `Через запятую` / `Текст (markdown)` / `Превью` / `Сохранить` / `Отмена` / `Страница сохранена` / `Отбросить несохранённые изменения?` / `Ваши изменения будут потеряны.` / `Отбросить` / `Загрузка…`

- [ ] **Step 3: Failing test for PageEdit**

`frontend/src/__tests__/PageEdit.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "../components/ui/sonner";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { PageEdit } from "../pages/PageEdit";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    confirm: { cancel: "Cancel", confirm: "Confirm", working: "Working...", typed_confirm_input_placeholder: "Type {{phrase}}" },
    pages: {
      editor: {
        title: "Edit page",
        title_field: "Title", type: "Type", status: "Status", flavor: "Flavor",
        confidence: "Confidence", aliases: "Aliases", aliases_hint: "csv",
        body_label: "Body", preview: "Preview", save: "Save", cancel: "Cancel",
        saved_toast: "Page saved",
        discard_modal_title: "Discard?", discard_modal_desc: "Lost.",
        discard_button: "Discard", loading: "Loading…",
      },
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
          <Route path="/project/:name/pages/*/edit" element={ui} />
          <Route path="/project/:name/pages/*" element={<div data-testid="page-detail-stub" />} />
        </Routes>
        <Toaster />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const SAMPLE = {
  project: "alpha",
  path: "wiki/concepts/foo.md",
  exists: true,
  frontmatter: {
    title: "Foo", type: "concept", status: "draft", flavor: ["intro"],
    confidence: 0.85, aliases: [],
    created: "2026-04-29T12:00:00Z", updated: "2026-04-29T12:00:00Z",
    extracted_pct: 100, inferred_pct: 0, ambiguous_pct: 0,
  },
  body: "## Hello",
};

describe("PageEdit", () => {
  it("renders form populated from page query", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: SAMPLE });
    render(wrap(<PageEdit />, "/project/alpha/pages/wiki/concepts/foo.md/edit"));
    await waitFor(() => expect(screen.getByDisplayValue("Foo")).toBeInTheDocument());
    expect(screen.getByDisplayValue(/## Hello/)).toBeInTheDocument();
  });

  it("Save calls patch with edited body", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: SAMPLE });
    const patchSpy = vi.spyOn(apiClient, "patch").mockResolvedValue({
      data: { success: true, snapshot_path: "p", activity_id: "a" },
    });
    const user = userEvent.setup();
    render(wrap(<PageEdit />, "/project/alpha/pages/wiki/concepts/foo.md/edit"));
    await waitFor(() => screen.getByDisplayValue("Foo"));
    const textarea = screen.getByLabelText(/body/i);
    await user.clear(textarea);
    await user.type(textarea, "edited");
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
    const [url, payload] = patchSpy.mock.calls[0]!;
    expect(url).toContain("/pages/alpha/");
    expect(payload).toMatchObject({ body: "edited" });
  });
});
```

- [ ] **Step 4: Run** → FAIL.

- [ ] **Step 5: Implement PageEdit**

`frontend/src/pages/PageEdit.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { MarkdownView } from "@/components/markdown/MarkdownView";
import { usePage } from "@/hooks/usePage";
import { usePagePatch } from "@/hooks/usePagePatch";

const PAGE_TYPES = ["concept", "entity", "source", "log", "draft"] as const;
const PAGE_STATUSES = ["draft", "reviewed", "verified", "stale", "archived"] as const;
const PAGE_FLAVORS = ["intro", "deep-dive", "reference", "tutorial", "audit"] as const;

export function PageEdit() {
  const { name: project, "*": pagePath } = useParams<{ name: string; "*": string }>();
  const cleanPath = (pagePath ?? "").replace(/\/edit$/, "");
  const navigate = useNavigate();
  const { t } = useTranslation();

  const pageQuery = usePage(project, cleanPath);
  const patchMut = usePagePatch();

  const [title, setTitle] = useState("");
  const [type, setType] = useState<string>("concept");
  const [status, setStatus] = useState<string>("draft");
  const [flavor, setFlavor] = useState<string[]>([]);
  const [confidence, setConfidence] = useState<number>(0);
  const [aliases, setAliases] = useState<string>("");
  const [body, setBody] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);

  useEffect(() => {
    if (pageQuery.data) {
      const fm = pageQuery.data.frontmatter;
      setTitle(fm.title ?? "");
      setType(fm.type);
      setStatus(fm.status);
      setFlavor(Array.isArray(fm.flavor) ? fm.flavor : []);
      setConfidence(fm.confidence ?? 0);
      setAliases(Array.isArray(fm.aliases) ? fm.aliases.join(", ") : "");
      setBody(pageQuery.data.body ?? "");
      setDirty(false);
    }
  }, [pageQuery.data]);

  if (pageQuery.isLoading) return <Skeleton className="h-64" />;
  if (!project || !pagePath) return null;

  const cancel = () => {
    if (dirty) setDiscardOpen(true);
    else navigate(`/project/${encodeURIComponent(project)}/pages/${cleanPath}`);
  };

  const save = () => {
    patchMut.mutate(
      {
        project,
        page_ref: cleanPath,
        body: {
          frontmatter: {
            title,
            type,
            status,
            flavor: flavor.length > 0 ? flavor : undefined,
            confidence,
            aliases: aliases
              .split(",")
              .map((a) => a.trim())
              .filter(Boolean),
          },
          body,
        },
      },
      {
        onSuccess: () => {
          navigate(`/project/${encodeURIComponent(project)}/pages/${cleanPath}`);
        },
      },
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("pages.editor.title")}</h1>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={cancel} disabled={patchMut.isPending}>
            <X className="mr-1 h-3 w-3" />
            {t("pages.editor.cancel")}
          </Button>
          <Button size="sm" onClick={save} disabled={patchMut.isPending}>
            <Save className="mr-1 h-3 w-3" />
            {patchMut.isPending ? t("confirm.working") : t("pages.editor.save")}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium">{t("pages.editor.title_field")}</label>
            <input
              type="text" value={title}
              onChange={(e) => { setTitle(e.target.value); setDirty(true); }}
              className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
            />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="text-xs font-medium">{t("pages.editor.type")}</label>
              <select
                value={type}
                onChange={(e) => { setType(e.target.value); setDirty(true); }}
                className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1.5 text-sm"
              >
                {PAGE_TYPES.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium">{t("pages.editor.status")}</label>
              <select
                value={status}
                onChange={(e) => { setStatus(e.target.value); setDirty(true); }}
                className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1.5 text-sm"
              >
                {PAGE_STATUSES.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium">{t("pages.editor.confidence")}</label>
              <input
                type="number" step="0.05" min="0" max="1" value={confidence}
                onChange={(e) => {
                  const n = Number(e.target.value);
                  if (!Number.isNaN(n) && n >= 0 && n <= 1) {
                    setConfidence(n); setDirty(true);
                  }
                }}
                className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1.5 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium">{t("pages.editor.flavor")}</label>
            <select
              multiple value={flavor}
              onChange={(e) => {
                const next = Array.from(e.target.selectedOptions).map((o) => o.value);
                setFlavor(next); setDirty(true);
              }}
              className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-2 py-1.5 text-sm"
            >
              {PAGE_FLAVORS.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium">
              {t("pages.editor.aliases")}{" "}
              <span className="text-[hsl(var(--muted-foreground))]">— {t("pages.editor.aliases_hint")}</span>
            </label>
            <input
              type="text" value={aliases}
              onChange={(e) => { setAliases(e.target.value); setDirty(true); }}
              className="mt-1 w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label htmlFor="page-body" className="text-xs font-medium">{t("pages.editor.body_label")}</label>
            <textarea
              id="page-body" value={body}
              onChange={(e) => { setBody(e.target.value); setDirty(true); }}
              className="mt-1 h-96 w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 font-mono text-sm"
            />
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-xs font-medium uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
            {t("pages.editor.preview")}
          </div>
          <div className="rounded-md border bg-[hsl(var(--background))] p-4">
            <MarkdownView body={body} />
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={discardOpen}
        onOpenChange={setDiscardOpen}
        title={t("pages.editor.discard_modal_title")}
        description={t("pages.editor.discard_modal_desc")}
        confirmLabel={t("pages.editor.discard_button")}
        destructive
        onConfirm={() => {
          setDiscardOpen(false);
          navigate(`/project/${encodeURIComponent(project)}/pages/${cleanPath}`);
        }}
      />
    </div>
  );
}
```

- [ ] **Step 6: Run** → PASS.

- [ ] **Step 7: Add route in App.tsx**

Edit `frontend/src/App.tsx`. Add:

```tsx
import { PageEdit } from "./pages/PageEdit";
```

Inside the `/project/:name/` children, add (BEFORE the catch-all `pages/*` route):

```tsx
{ path: "pages/*/edit", element: <PageEdit /> },
```

The order matters — `pages/*/edit` must come before `pages/*` so react-router matches the more-specific route first.

- [ ] **Step 8: Run all tests + build**

```bash
cd frontend && pnpm test && pnpm typecheck && pnpm build
```

- [ ] **Step 9: Commit**

```bash
git add frontend/src/hooks/usePagePatch.ts frontend/src/pages/PageEdit.tsx frontend/src/__tests__/PageEdit.test.tsx frontend/src/App.tsx frontend/public/locales/
git commit -m "feat(frontend): PageEdit page (frontmatter + markdown editor + preview) wired to PATCH"
```

---

## Task 12: Final verification + acceptance walkthrough

- [ ] **Step 1: Production build**

```bash
cd /d/code/claude-mnemos/frontend
pnpm build
```

Expect dist in `../claude_mnemos/daemon/static/`. Bundle ~265-275 KB gzip (alert-dialog + 16 hooks + PageEdit add ~10-15 KB).

- [ ] **Step 2: Full frontend tests + lint + typecheck**

```bash
pnpm test
pnpm lint
pnpm typecheck
```

All clean. 2 pre-existing shadcn warnings allowed. Vitest count grows by ~30-40 tests on top of #14b-2's 118.

- [ ] **Step 3: Backend pytest sanity**

```bash
cd /d/code/claude-mnemos
python -m pytest -q --ignore=tests/daemon/integration -k "not slow" 2>&1 | tail -5
```

Expect 1202 passed + same 12 failed + 16 errors as on main (pre-existing CLI test pollution; zero backend code touched on this branch — confirm via `git diff main..HEAD --stat -- 'claude_mnemos/' 'tests/'` returning empty).

- [ ] **Step 4: Acceptance criteria walk-through (design §8)**

1. ✅ Every formerly-disabled mutation button is now active or navigates (PageDetail Edit).
2. ✅ Tier 2 actions show ConfirmDialog before mutating.
3. ✅ Tier 3 actions require typing expected phrase.
4. ✅ Toast.success on every successful mutation; toast.error on every failure.
5. ✅ invalidateQueries fires; UI reflects the change within poll window.
6. ✅ PageEdit at `/project/:p/pages/*/edit` with frontmatter+body PATCH; preview live; cancel-when-dirty prompts discard.
7. ✅ Snapshots page has Create button.
8. ✅ Toaster mounts once globally in App.tsx.
9. ✅ notifications.store.ts deleted.
10. ✅ Backend pytest unchanged.
11. ✅ Vitest grows ~30-40.
12. ✅ ESLint clean; tsc strict clean.
13. ✅ Bundle ~265-275 KB gzip.
14. ✅ All copy in en/uk/ru.

- [ ] **Step 5: Branch summary**

```bash
git log --oneline main..HEAD
git status
```

~13-15 commits, working tree clean.

- [ ] **Step 6: Optional commit if anything dangling**

If pnpm-lock.yaml updated, commit it. Otherwise verification-only.

---

## Spec coverage map

| Design § | Plan tasks |
|---|---|
| §2.1 Tier system | Task 2 (primitives), used in 3-10 |
| §2.2 Toast | Task 1 (mount + helper), used in all hooks |
| §2.3 Mutation hooks | Tasks 3-10 (one per domain) |
| §2.4 Page editor | Task 11 |
| §2.7 Manual snapshot | Task 4 (Create button) |
| §3 Inventory wiring | Tasks 3-11 |
| §4 Cache invalidation | Per-task in mutation hooks |
| §5 i18n | Each task adds its own block |
| §6 alert-dialog dep | Task 1 |
| §8 ACs | Task 12 |
| §10 Out of scope | Documented in design only — no tasks |
