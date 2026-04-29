# Onboarding + Help + Metrics + Polish Implementation Plan (Plan #14d)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** Replace last 3 #14a Placeholder routes (`/onboarding`, `/help`, `/metrics`) with working pages — onboarding wizard, 5-section Help, full Metrics charts — and clean up technical debt from #14b/c (datetime localization, MAX_ATTEMPTS const, dismiss redirect, dead locale keys, lazy-load).

**Architecture:** Pure frontend. Adds `recharts` dep + shadcn chart wrapper. New: 1 onboarding page with form + 3 mutation hooks for project creation, 1 metrics page with 3 chart/table widgets + 2 new query hooks, 1 rewritten Help page with 5 sections, 1 datetime helper. Wires `<NoProjectsCallout>` and `<ProjectSwitcher>` to the new wizard. Lazy-loads Metrics + Help.

**Tech Stack:** React 19, TanStack Query 5, react-router 7 (`createBrowserRouter`), zod 3, axios, Tailwind v4, shadcn/ui, **recharts ^2.x (NEW)**, Vitest + Testing Library, i18next.

**Design doc:** `docs/plans/2026-04-29-14d-onboarding-help-metrics-design.md` — read before each task.

---

## Files map

**New:**
- `frontend/src/lib/datetime.ts` — `formatDateTime(iso, locale)`
- `frontend/src/__tests__/datetime.test.ts`
- `frontend/src/api/projects.api.ts` — extend with `createProject`
- `frontend/src/__tests__/api-projects-mutations.test.ts`
- `frontend/src/hooks/useProjectCreate.ts`
- `frontend/src/types/UsageTimeline.ts`
- `frontend/src/types/TopSession.ts`
- `frontend/src/__tests__/api-metrics-extras.test.ts`
- `frontend/src/api/metrics.api.ts` — extend with `getTimeline`, `getTopSessions`
- `frontend/src/hooks/useUsageTimeline.ts`
- `frontend/src/hooks/useTopSessions.ts`
- `frontend/src/components/ui/chart.tsx` — shadcn-pattern recharts wrapper
- `frontend/src/components/widgets/UsageTimelineChart.tsx`
- `frontend/src/components/widgets/UsageByProjectTable.tsx`
- `frontend/src/components/widgets/TopSessionsTable.tsx`
- `frontend/src/__tests__/UsageTimelineChart.test.tsx`
- `frontend/src/__tests__/UsageByProjectTable.test.tsx`
- `frontend/src/__tests__/TopSessionsTable.test.tsx`
- `frontend/src/pages/Onboarding.tsx`
- `frontend/src/__tests__/Onboarding.test.tsx`
- `frontend/src/pages/Metrics.tsx`
- `frontend/src/__tests__/Metrics.test.tsx`
- `frontend/src/__tests__/Help.test.tsx` (smoke test for new sections)

**Modified:**
- `frontend/src/types/Job.ts` — export `JOB_MAX_ATTEMPTS = 4`
- `frontend/src/components/widgets/DeadLetterRow.tsx` — use `JOB_MAX_ATTEMPTS` + `formatDateTime`
- `frontend/src/pages/DeadLetterDetail.tsx` — use `JOB_MAX_ATTEMPTS` + `formatDateTime` + navigate after Dismiss
- `frontend/src/components/widgets/{LostSessionRow,SnapshotCard,TrashRow,SessionCard}.tsx` — apply `formatDateTime`
- `frontend/src/components/widgets/NoProjectsCallout.tsx` — add "Create project" CTA
- `frontend/src/components/layout/ProjectSwitcher.tsx` — add `+ New project` menu item
- `frontend/src/pages/Help.tsx` — full rewrite (5 sections)
- `frontend/src/App.tsx` — wire 3 routes (replace placeholders), lazy-load Metrics + Help
- `frontend/public/locales/{en,uk,ru}.json` — add `onboarding.*`, `help.*`, `metrics.*` blocks; remove dead `*_disabled` keys
- `frontend/package.json` — add `recharts`

---

## Task 1: Datetime helper + JOB_MAX_ATTEMPTS const

**Files:**
- Create: `frontend/src/lib/datetime.ts`, `frontend/src/__tests__/datetime.test.ts`
- Modify: `frontend/src/types/Job.ts`

- [ ] **Step 1: Failing test for `formatDateTime`**

`frontend/src/__tests__/datetime.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { formatDateTime } from "../lib/datetime";

describe("formatDateTime", () => {
  it("formats ISO string with en locale", () => {
    const out = formatDateTime("2026-04-29T12:00:00Z", "en");
    // en-US default short style — accept either AM/PM or 24h depending on Intl impl
    expect(out).toMatch(/2026|04|29/);
  });

  it("returns input unchanged on invalid date", () => {
    expect(formatDateTime("not-a-date", "en")).toBe("not-a-date");
  });

  it("handles null/undefined gracefully", () => {
    expect(formatDateTime(null, "en")).toBe("");
    expect(formatDateTime(undefined, "en")).toBe("");
  });

  it("uk locale produces day-month order", () => {
    const out = formatDateTime("2026-04-29T12:00:00Z", "uk");
    expect(out).toMatch(/29/);
    expect(out).toMatch(/04|кві/);
  });
});
```

- [ ] **Step 2: Run** → FAIL.

```
cd frontend && pnpm test datetime
```

- [ ] **Step 3: Implement `frontend/src/lib/datetime.ts`**

```ts
const FORMATTERS = new Map<string, Intl.DateTimeFormat>();

function getFormatter(locale: string): Intl.DateTimeFormat {
  let fmt = FORMATTERS.get(locale);
  if (!fmt) {
    fmt = new Intl.DateTimeFormat(locale, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
    FORMATTERS.set(locale, fmt);
  }
  return fmt;
}

export function formatDateTime(
  iso: string | null | undefined,
  locale: string,
): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return getFormatter(locale).format(d);
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Modify `frontend/src/types/Job.ts`**

At the top of the file (after existing imports), add:

```ts
export const JOB_MAX_ATTEMPTS = 4;
```

(Preserve all existing schemas + types.)

- [ ] **Step 6: Run all tests + tsc**

```bash
cd frontend && pnpm test && pnpm typecheck
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/datetime.ts frontend/src/__tests__/datetime.test.ts frontend/src/types/Job.ts
git commit -m "feat(frontend): #14d datetime helper + JOB_MAX_ATTEMPTS const"
```

---

## Task 2: Apply datetime + JOB_MAX_ATTEMPTS in widgets

**Files modified:**
- `frontend/src/components/widgets/DeadLetterRow.tsx`
- `frontend/src/components/widgets/LostSessionRow.tsx`
- `frontend/src/components/widgets/SnapshotCard.tsx`
- `frontend/src/components/widgets/TrashRow.tsx`
- `frontend/src/components/widgets/SessionCard.tsx`
- `frontend/src/pages/DeadLetterDetail.tsx`

- [ ] **Step 1: Apply formatDateTime in DeadLetterRow**

Read `frontend/src/components/widgets/DeadLetterRow.tsx`. Add imports at top:

```tsx
import { useTranslation } from "react-i18next";
import { formatDateTime } from "@/lib/datetime";
import { JOB_MAX_ATTEMPTS } from "@/types/Job";
```

(`useTranslation` already imported — keep one.)

Replace local `const MAX_ATTEMPTS = 4;` declaration with `JOB_MAX_ATTEMPTS` reference (delete the local const line).

Inside component, add:

```tsx
const { i18n } = useTranslation();
```

(or extend existing `const { t } = useTranslation();` to `const { t, i18n } = useTranslation();`.)

Replace `{j.finished_at}` (raw ISO render) with `{formatDateTime(j.finished_at, i18n.language)}`.

Replace `MAX_ATTEMPTS` references with `JOB_MAX_ATTEMPTS`.

- [ ] **Step 2: Apply in DeadLetterDetail**

Read `frontend/src/pages/DeadLetterDetail.tsx`. Same pattern: import `formatDateTime`, `JOB_MAX_ATTEMPTS`. Replace local `MAX_ATTEMPTS` const. Replace raw `{j.created_at}`, `{j.started_at}`, `{j.finished_at}` references with `{formatDateTime(j.created_at, i18n.language)}` etc.

- [ ] **Step 3: Apply in LostSessionRow**

Read `frontend/src/components/widgets/LostSessionRow.tsx`. Replace `{s.mtime}` with `{formatDateTime(s.mtime, i18n.language)}`. Add `i18n` from `useTranslation()`.

- [ ] **Step 4: Apply in SnapshotCard**

Read `frontend/src/components/widgets/SnapshotCard.tsx`. Replace `{s.timestamp}` with `{formatDateTime(s.timestamp, i18n.language)}`.

- [ ] **Step 5: Apply in TrashRow**

Read `frontend/src/components/widgets/TrashRow.tsx`. Replace `{e.deleted_at}` with `{formatDateTime(e.deleted_at, i18n.language)}`.

- [ ] **Step 6: Apply in SessionCard**

Read `frontend/src/components/widgets/SessionCard.tsx`. Find any datetime renders (likely `{s.ingested_at}`). Replace with formatted version.

- [ ] **Step 7: Run all tests + tsc**

```bash
cd frontend && pnpm test && pnpm typecheck
```

Existing widget tests should still pass — they test by other markers (status text, project name, etc.), not datetime literals. If any test breaks because of a datetime regex, update the regex to match the localized format (e.g., `/2026/` instead of `/2026-04-29T12:00:00Z/`).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/widgets/DeadLetterRow.tsx frontend/src/components/widgets/LostSessionRow.tsx frontend/src/components/widgets/SnapshotCard.tsx frontend/src/components/widgets/TrashRow.tsx frontend/src/components/widgets/SessionCard.tsx frontend/src/pages/DeadLetterDetail.tsx
git commit -m "feat(frontend): #14d apply formatDateTime + JOB_MAX_ATTEMPTS across widgets"
```

---

## Task 3: DeadLetterDetail — navigate after Dismiss

**Files:**
- Modify: `frontend/src/pages/DeadLetterDetail.tsx`

- [ ] **Step 1: Read current file**

Look at the existing `dismiss.mutate(j.id, { onSettled: () => setDismissOpen(false) })` call.

- [ ] **Step 2: Add navigation after success**

Add `import { useNavigate } from "react-router";` if not present. Inside component: `const navigate = useNavigate();`. Modify the dismiss `onConfirm`:

```tsx
onConfirm={() => j && dismiss.mutate(j.id, {
  onSuccess: () => navigate("/dead-letter"),
  onSettled: () => setDismissOpen(false),
})}
```

- [ ] **Step 3: Run tests**

```bash
cd frontend && pnpm test DeadLetterDetail
```

The existing test asserts the dismiss POST is called — still passes. Add no new test here (navigation post-success is a small behavior).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DeadLetterDetail.tsx
git commit -m "fix(frontend): #14d DeadLetterDetail navigate to /dead-letter after Dismiss"
```

---

## Task 4: Project create API + hook + test

**Files:**
- Modify: `frontend/src/api/projects.api.ts`
- Create: `frontend/src/hooks/useProjectCreate.ts`
- Create: `frontend/src/__tests__/api-projects-mutations.test.ts`

- [ ] **Step 1: Failing test**

`frontend/src/__tests__/api-projects-mutations.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { createProject } from "../api/projects.api";

vi.mock("../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

describe("projects mutations", () => {
  beforeEach(() => vi.mocked(apiClient.post).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("createProject POSTs body with name + vault_root + cwd_patterns", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        name: "alpha",
        vault_root: "/tmp/alpha",
        cwd_patterns: ["~/code/alpha"],
      },
    });
    const out = await createProject({
      name: "alpha",
      vault_root: "/tmp/alpha",
      cwd_patterns: ["~/code/alpha"],
    });
    expect(apiClient.post).toHaveBeenCalledWith("/projects", {
      name: "alpha",
      vault_root: "/tmp/alpha",
      cwd_patterns: ["~/code/alpha"],
    });
    expect(out.name).toBe("alpha");
  });

  it("createProject defaults cwd_patterns to empty array", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { name: "beta", vault_root: "/tmp/beta", cwd_patterns: [] },
    });
    await createProject({ name: "beta", vault_root: "/tmp/beta" });
    expect(apiClient.post).toHaveBeenCalledWith("/projects", {
      name: "beta",
      vault_root: "/tmp/beta",
      cwd_patterns: [],
    });
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Append to `frontend/src/api/projects.api.ts`**

```ts
export interface CreateProjectBody {
  name: string;
  vault_root: string;
  cwd_patterns?: string[];
}

export async function createProject(body: CreateProjectBody): Promise<ProjectMapEntry> {
  const r = await apiClient.post("/projects", {
    name: body.name,
    vault_root: body.vault_root,
    cwd_patterns: body.cwd_patterns ?? [],
  });
  return ProjectMapEntrySchema.parse(r.data);
}
```

- [ ] **Step 4: Implement `frontend/src/hooks/useProjectCreate.ts`**

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { createProject, type CreateProjectBody } from "@/api/projects.api";
import { extractApiError } from "@/lib/error";

export function useProjectCreate() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (body: CreateProjectBody) => createProject(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
      toast.success(t("onboarding.success_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/projects.api.ts frontend/src/hooks/useProjectCreate.ts frontend/src/__tests__/api-projects-mutations.test.ts
git commit -m "feat(frontend): #14d createProject api + useProjectCreate hook"
```

---

## Task 5: Onboarding page

**Files:**
- Create: `frontend/src/pages/Onboarding.tsx`
- Create: `frontend/src/__tests__/Onboarding.test.tsx`
- Modify: `frontend/src/App.tsx` (replace Onboarding placeholder route with real component)
- Modify: `frontend/public/locales/{en,uk,ru}.json` (add `onboarding.*`)

- [ ] **Step 1: Add locale keys**

Append to each locale's top level `onboarding` block:

- en:
```json
"onboarding": {
  "title": "Create new project",
  "subtitle": "Mount a vault directory and start ingesting Claude Code sessions.",
  "name_label": "Project name",
  "name_hint": "Lowercase letters, digits, underscores, hyphens. Max 64 chars.",
  "name_invalid": "Invalid name. Use lowercase a-z, 0-9, underscore, hyphen. Must start with letter or digit.",
  "name_taken": "A project with this name already exists.",
  "vault_label": "Vault path",
  "vault_hint": "Absolute path. The directory will be created if it does not exist.",
  "advanced_toggle": "Advanced — CWD patterns",
  "cwd_label": "CWD patterns (one per line)",
  "cwd_hint": "Glob patterns matching working directories where this project is active.",
  "submit": "Create project",
  "cancel": "Cancel",
  "mount_failed_title": "Mount failed",
  "success_toast": "Project created"
}
```

- uk: name = "Створити новий проєкт" / "Підключіть vault і почніть інжест сесій Claude Code." / "Назва проєкту" / "Малі літери, цифри, підкреслення, дефіс. Макс. 64 символи." / "Некоректна назва. Літери a-z, цифри, _ або -. Має починатися з літери або цифри." / "Проєкт з такою назвою вже існує." / "Шлях до vault" / "Абсолютний шлях. Директорія буде створена, якщо її немає." / "Розширені — CWD патерни" / "CWD патерни (по одному в рядку)" / "Glob-патерни для робочих директорій." / "Створити проєкт" / "Скасувати" / "Помилка монтування" / "Проєкт створено"

- ru: "Создать новый проект" / "Подключите vault и начните ингест сессий Claude Code." / "Имя проекта" / "Строчные буквы, цифры, подчёркивание, дефис. Макс. 64 символа." / "Некорректное имя. Буквы a-z, цифры, _ или -. Должно начинаться с буквы или цифры." / "Проект с таким именем уже существует." / "Путь к vault" / "Абсолютный путь. Директория будет создана, если её нет." / "Расширенные — CWD паттерны" / "CWD паттерны (по одному в строке)" / "Glob-паттерны для рабочих директорий." / "Создать проект" / "Отмена" / "Ошибка монтирования" / "Проект создан"

- [ ] **Step 2: Failing test**

`frontend/src/__tests__/Onboarding.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "../components/ui/sonner";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Onboarding } from "../pages/Onboarding";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    onboarding: {
      title: "Create new project",
      subtitle: "Mount a vault.",
      name_label: "Project name",
      name_hint: "lowercase",
      name_invalid: "Invalid name",
      name_taken: "Already exists",
      vault_label: "Vault path",
      vault_hint: "Absolute",
      advanced_toggle: "Advanced",
      cwd_label: "CWD patterns",
      cwd_hint: "globs",
      submit: "Create project",
      cancel: "Cancel",
      mount_failed_title: "Mount failed",
      success_toast: "Project created",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/onboarding"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/onboarding" element={ui} />
          <Route path="/project/:name" element={<div data-testid="project-view-stub" />} />
        </Routes>
        <Toaster />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Onboarding", () => {
  it("disables submit when name is invalid", async () => {
    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    const submit = screen.getByRole("button", { name: /create project/i });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText(/project name/i), "Bad Name!");
    await user.type(screen.getByLabelText(/vault path/i), "/tmp/x");
    expect(submit).toBeDisabled();
    expect(screen.getByText(/invalid name/i)).toBeInTheDocument();
  });

  it("enables submit on valid input + posts to /projects + navigates", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      data: { name: "alpha", vault_root: "/tmp/alpha", cwd_patterns: [] },
    });
    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    await user.type(screen.getByLabelText(/project name/i), "alpha");
    await user.type(screen.getByLabelText(/vault path/i), "/tmp/alpha");

    const submit = screen.getByRole("button", { name: /create project/i });
    expect(submit).not.toBeDisabled();
    await user.click(submit);
    await waitFor(() => expect(screen.getByTestId("project-view-stub")).toBeInTheDocument());
  });

  it("shows mount_failed callout on 500", async () => {
    const err: any = new Error("Request failed");
    err.isAxiosError = true;
    err.response = { status: 500, data: { error: "mount_failed", detail: "Permission denied: /var/foo" } };
    vi.spyOn(apiClient, "post").mockRejectedValueOnce(err);
    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    await user.type(screen.getByLabelText(/project name/i), "alpha");
    await user.type(screen.getByLabelText(/vault path/i), "/var/foo");
    await user.click(screen.getByRole("button", { name: /create project/i }));
    await waitFor(() => expect(screen.getByText(/mount failed/i)).toBeInTheDocument());
    expect(screen.getByText(/permission denied/i)).toBeInTheDocument();
  });

  it("shows inline name_taken on 409", async () => {
    const err: any = new Error("Request failed");
    err.isAxiosError = true;
    err.response = { status: 409, data: { error: "name_conflict", detail: "Name already exists" } };
    vi.spyOn(apiClient, "post").mockRejectedValueOnce(err);
    const user = userEvent.setup();
    render(wrap(<Onboarding />));
    await user.type(screen.getByLabelText(/project name/i), "alpha");
    await user.type(screen.getByLabelText(/vault path/i), "/tmp/alpha");
    await user.click(screen.getByRole("button", { name: /create project/i }));
    await waitFor(() => expect(screen.getByText(/already exists/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement Onboarding page**

`frontend/src/pages/Onboarding.tsx`:

```tsx
import { useState } from "react";
import { useNavigate, Link } from "react-router";
import { useTranslation } from "react-i18next";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { useProjectCreate } from "@/hooks/useProjectCreate";

const NAME_REGEX = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export function Onboarding() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useProjectCreate();

  const [name, setName] = useState("");
  const [vault, setVault] = useState("");
  const [cwd, setCwd] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [nameTakenError, setNameTakenError] = useState(false);
  const [mountFailedDetail, setMountFailedDetail] = useState<string | null>(null);

  const nameValid = NAME_REGEX.test(name);
  const vaultValid = vault.trim().length > 0;
  const canSubmit = nameValid && vaultValid && !create.isPending;

  const showNameInvalid = name.length > 0 && !nameValid;

  const submit = () => {
    setNameTakenError(false);
    setMountFailedDetail(null);
    const cwd_patterns = cwd
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    create.mutate(
      { name, vault_root: vault.trim(), cwd_patterns },
      {
        onSuccess: (entry) => navigate(`/project/${encodeURIComponent(entry.name)}`),
        onError: (err) => {
          if (axios.isAxiosError(err)) {
            const status = err.response?.status;
            if (status === 409) {
              setNameTakenError(true);
            } else if (status === 500) {
              const detail = err.response?.data?.detail;
              setMountFailedDetail(typeof detail === "string" ? detail : err.message);
            }
          }
        },
      },
    );
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold">{t("onboarding.title")}</h1>
        <p className="mt-1 text-sm text-[hsl(var(--muted-foreground))]">{t("onboarding.subtitle")}</p>
      </div>

      <div className="space-y-2">
        <label htmlFor="onb-name" className="text-sm font-medium">{t("onboarding.name_label")}</label>
        <input
          id="onb-name"
          type="text"
          value={name}
          onChange={(e) => { setName(e.target.value); setNameTakenError(false); }}
          disabled={create.isPending}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
        />
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.name_hint")}</p>
        {showNameInvalid && (
          <p className="text-xs text-red-700 dark:text-red-400">{t("onboarding.name_invalid")}</p>
        )}
        {nameTakenError && (
          <p className="text-xs text-red-700 dark:text-red-400">{t("onboarding.name_taken")}</p>
        )}
      </div>

      <div className="space-y-2">
        <label htmlFor="onb-vault" className="text-sm font-medium">{t("onboarding.vault_label")}</label>
        <input
          id="onb-vault"
          type="text"
          value={vault}
          onChange={(e) => setVault(e.target.value)}
          disabled={create.isPending}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
        />
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.vault_hint")}</p>
      </div>

      <div className="space-y-2">
        <button
          type="button"
          className="text-sm text-[hsl(var(--primary))] underline"
          onClick={() => setAdvancedOpen(!advancedOpen)}
        >
          {t("onboarding.advanced_toggle")}
        </button>
        {advancedOpen && (
          <div className="space-y-1 rounded-md border bg-[hsl(var(--muted))] p-3">
            <label htmlFor="onb-cwd" className="text-sm font-medium">{t("onboarding.cwd_label")}</label>
            <textarea
              id="onb-cwd"
              value={cwd}
              onChange={(e) => setCwd(e.target.value)}
              disabled={create.isPending}
              rows={3}
              className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
            />
            <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.cwd_hint")}</p>
          </div>
        )}
      </div>

      {mountFailedDetail && (
        <div className="rounded-md border-2 border-red-600 bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          <div className="font-semibold">{t("onboarding.mount_failed_title")}</div>
          <div className="mt-1 break-all font-mono text-xs">{mountFailedDetail}</div>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button onClick={submit} disabled={!canSubmit}>
          {create.isPending ? t("confirm.working") : t("onboarding.submit")}
        </Button>
        <Button asChild variant="outline">
          <Link to="/">{t("onboarding.cancel")}</Link>
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Wire route in App.tsx**

In `frontend/src/App.tsx`, add `import { Onboarding } from "./pages/Onboarding";` and replace the route:

```tsx
{ path: "onboarding", element: <Onboarding /> },
```

(Replaces `<Placeholder section="Onboarding" plan="#14d" />`.)

- [ ] **Step 6: Run** → PASS.

```bash
cd frontend && pnpm test Onboarding
```

- [ ] **Step 7: Run all tests + tsc**

```bash
cd frontend && pnpm test && pnpm typecheck
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Onboarding.tsx frontend/src/__tests__/Onboarding.test.tsx frontend/src/App.tsx frontend/public/locales/
git commit -m "feat(frontend): #14d Onboarding wizard (form + project create + error handling)"
```

---

## Task 6: NoProjectsCallout CTA + ProjectSwitcher menu item

**Files:**
- Modify: `frontend/src/components/widgets/NoProjectsCallout.tsx`
- Modify: `frontend/src/components/layout/ProjectSwitcher.tsx`
- Modify: `frontend/public/locales/{en,uk,ru}.json` (add `nav.create_project`, `overview.no_projects_cta`)

- [ ] **Step 1: Add locale keys**

In each locale, append:

- en: `"nav": { ..., "create_project": "+ New project" }`, and inside `overview`: `"no_projects_cta": "Create your first project"`.
- uk: `+ Новий проєкт` / `Створити перший проєкт`
- ru: `+ Новый проект` / `Создать первый проект`

(`nav` block likely doesn't exist; use `navigation` if that's what existing keys live under. Check the file for the existing key prefix used by ProjectSwitcher and Sidebar items.)

- [ ] **Step 2: Update NoProjectsCallout**

Replace `frontend/src/components/widgets/NoProjectsCallout.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";

export function NoProjectsCallout() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-2xl rounded-lg border bg-[hsl(var(--muted))] p-6 text-center">
      <h2 className="mb-3 text-lg font-semibold">
        🧠 {t("overview.no_projects_title")}
      </h2>
      <Button asChild size="lg" className="mb-4">
        <Link to="/onboarding">{t("overview.no_projects_cta")}</Link>
      </Button>
      <p className="mb-2 text-sm">{t("overview.no_projects_hint_cmd")}</p>
      <pre className="rounded bg-[hsl(var(--background))] p-2 text-xs">
        {t("overview.no_projects_hint_command")}
      </pre>
    </div>
  );
}
```

- [ ] **Step 3: Update ProjectSwitcher**

Read `frontend/src/components/layout/ProjectSwitcher.tsx`. Find the dropdown menu items list. Add a divider + a "+ New project" entry that navigates to `/onboarding`. The exact wiring depends on existing structure (likely `<DropdownMenuItem>` with `<Link to="/onboarding">` or `useNavigate`). Match existing pattern.

- [ ] **Step 4: Run all tests + tsc**

```bash
cd frontend && pnpm test && pnpm typecheck
```

Existing NoProjectsCallout / ProjectSwitcher tests (if any) may need bundle key additions. Update test bundles to include `overview.no_projects_cta` + the navigation key.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/NoProjectsCallout.tsx frontend/src/components/layout/ProjectSwitcher.tsx frontend/public/locales/
git commit -m "feat(frontend): #14d wire NoProjectsCallout + ProjectSwitcher to /onboarding"
```

---

## Task 7: Metrics types + API + hooks

**Files:**
- Create: `frontend/src/types/UsageTimeline.ts`, `frontend/src/types/TopSession.ts`
- Modify: `frontend/src/api/metrics.api.ts`
- Create: `frontend/src/hooks/useUsageTimeline.ts`, `frontend/src/hooks/useTopSessions.ts`
- Create: `frontend/src/__tests__/api-metrics-extras.test.ts`

- [ ] **Step 1: Failing test for new api functions**

`frontend/src/__tests__/api-metrics-extras.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { getTimeline, getTopSessions } from "../api/metrics.api";

vi.mock("../api/client", () => ({ apiClient: { get: vi.fn() } }));

describe("metrics extras", () => {
  beforeEach(() => vi.mocked(apiClient.get).mockReset());
  afterEach(() => vi.resetAllMocks());

  it("getTimeline parses points array", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        points: [
          { date: "2026-04-29", sessions: 3, tokens_input: 100, tokens_output: 200 },
          { date: "2026-04-30", sessions: 5, tokens_input: 150, tokens_output: 250 },
        ],
      },
    });
    const out = await getTimeline("30d");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/metrics/usage/timeline",
      expect.objectContaining({ params: { period: "30d" } }),
    );
    expect(out).toHaveLength(2);
    expect(out[0]?.sessions).toBe(3);
  });

  it("getTimeline rejects malformed points", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { points: [{ date: "x", sessions: "abc" }] },
    });
    await expect(getTimeline("30d")).rejects.toThrow();
  });

  it("getTopSessions parses sessions array", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        sessions: [
          {
            project: "alpha", session_id: "s1",
            ingested_at: "2026-04-29T12:00:00Z",
            tokens_input: 100, tokens_output: 200,
            tokens_total: 300, raw_bytes: 1024,
          },
        ],
      },
    });
    const out = await getTopSessions(10);
    expect(apiClient.get).toHaveBeenCalledWith(
      "/metrics/usage/top-sessions",
      expect.objectContaining({ params: { limit: 10 } }),
    );
    expect(out[0]?.tokens_total).toBe(300);
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement types**

`frontend/src/types/UsageTimeline.ts`:

```ts
import { z } from "zod";

export const UsageTimelinePointSchema = z.object({
  date: z.string(),
  sessions: z.number().int().nonnegative(),
  tokens_input: z.number().int().nonnegative(),
  tokens_output: z.number().int().nonnegative(),
});
export type UsageTimelinePoint = z.infer<typeof UsageTimelinePointSchema>;

export const UsageTimelineResponseSchema = z.object({
  points: z.array(UsageTimelinePointSchema),
});
```

`frontend/src/types/TopSession.ts`:

```ts
import { z } from "zod";

export const TopSessionSchema = z.object({
  project: z.string(),
  session_id: z.string(),
  ingested_at: z.string(),
  tokens_input: z.number().int().nonnegative(),
  tokens_output: z.number().int().nonnegative(),
  tokens_total: z.number().int().nonnegative(),
  raw_bytes: z.number().int().nonnegative(),
});
export type TopSession = z.infer<typeof TopSessionSchema>;

export const TopSessionsResponseSchema = z.object({
  sessions: z.array(TopSessionSchema),
});
```

- [ ] **Step 4: Append to `frontend/src/api/metrics.api.ts`**

```ts
import {
  UsageTimelineResponseSchema,
  type UsageTimelinePoint,
} from "@/types/UsageTimeline";
import {
  TopSessionsResponseSchema,
  type TopSession,
} from "@/types/TopSession";

export async function getTimeline(period = "30d"): Promise<UsageTimelinePoint[]> {
  const r = await apiClient.get("/metrics/usage/timeline", { params: { period } });
  return UsageTimelineResponseSchema.parse(r.data).points;
}

export async function getTopSessions(limit = 10): Promise<TopSession[]> {
  const r = await apiClient.get("/metrics/usage/top-sessions", { params: { limit } });
  return TopSessionsResponseSchema.parse(r.data).sessions;
}
```

(Preserve existing imports of `UsageSummarySchema` etc.)

- [ ] **Step 5: Implement hooks**

`frontend/src/hooks/useUsageTimeline.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { getTimeline } from "@/api/metrics.api";

export function useUsageTimeline(period = "30d") {
  return useQuery({
    queryKey: ["usage-timeline", period],
    queryFn: () => getTimeline(period),
    refetchInterval: 60_000,
  });
}
```

`frontend/src/hooks/useTopSessions.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { getTopSessions } from "@/api/metrics.api";

export function useTopSessions(limit = 10) {
  return useQuery({
    queryKey: ["top-sessions", limit],
    queryFn: () => getTopSessions(limit),
    refetchInterval: 60_000,
  });
}
```

- [ ] **Step 6: Run** → PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/UsageTimeline.ts frontend/src/types/TopSession.ts frontend/src/api/metrics.api.ts frontend/src/hooks/useUsageTimeline.ts frontend/src/hooks/useTopSessions.ts frontend/src/__tests__/api-metrics-extras.test.ts
git commit -m "feat(frontend): #14d Metrics timeline + top-sessions types + api + hooks"
```

---

## Task 8: Install recharts + chart shadcn primitive

**Files:**
- Modify: `frontend/package.json` (add recharts)
- Create: `frontend/src/components/ui/chart.tsx`

- [ ] **Step 1: Install recharts**

```bash
cd /d/code/claude-mnemos/frontend
pnpm add recharts
```

Confirm `recharts` appears in `package.json` dependencies.

- [ ] **Step 2: Create chart wrapper**

`frontend/src/components/ui/chart.tsx`:

```tsx
import * as React from "react";
import {
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  type TooltipProps,
} from "recharts";
import { cn } from "@/lib/utils";

interface ChartContainerProps extends React.HTMLAttributes<HTMLDivElement> {
  height?: number;
}

export function ChartContainer({
  className, children, height = 280, ...props
}: ChartContainerProps) {
  return (
    <div className={cn("w-full", className)} style={{ height }} {...props}>
      <ResponsiveContainer width="100%" height="100%">
        {children as React.ReactElement}
      </ResponsiveContainer>
    </div>
  );
}

export function ChartTooltipContent({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-xs shadow-md">
      {label && <div className="mb-1 font-medium">{String(label)}</div>}
      {payload.map((entry) => (
        <div key={String(entry.dataKey)} className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-[hsl(var(--muted-foreground))]">{entry.name}:</span>
          <span className="font-mono">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

export const ChartTooltip = RechartsTooltip;
```

- [ ] **Step 3: Run typecheck**

```bash
cd frontend && pnpm typecheck
```

Should be clean. recharts ships its own `.d.ts` files so types resolve.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/components/ui/chart.tsx
git commit -m "feat(frontend): #14d add recharts + chart shadcn-style wrapper"
```

---

## Task 9: UsageTimelineChart widget

**Files:**
- Create: `frontend/src/components/widgets/UsageTimelineChart.tsx`
- Create: `frontend/src/__tests__/UsageTimelineChart.test.tsx`

- [ ] **Step 1: Failing test**

`frontend/src/__tests__/UsageTimelineChart.test.tsx`:

```tsx
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import i18n from "../i18n";
import { UsageTimelineChart } from "../components/widgets/UsageTimelineChart";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    metrics: {
      timeline_legend_input: "Input tokens",
      timeline_legend_output: "Output tokens",
      timeline_legend_sessions: "Sessions",
      timeline_empty: "No data in this period",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

const POINTS = [
  { date: "2026-04-29", sessions: 3, tokens_input: 100, tokens_output: 200 },
  { date: "2026-04-30", sessions: 5, tokens_input: 150, tokens_output: 250 },
];

describe("UsageTimelineChart", () => {
  it("renders legend labels with non-empty data", () => {
    render(<UsageTimelineChart points={POINTS} />);
    expect(screen.getByText("Input tokens")).toBeInTheDocument();
    expect(screen.getByText("Output tokens")).toBeInTheDocument();
    expect(screen.getByText("Sessions")).toBeInTheDocument();
  });

  it("renders empty state when all points are zero", () => {
    const empty = POINTS.map((p) => ({ ...p, sessions: 0, tokens_input: 0, tokens_output: 0 }));
    render(<UsageTimelineChart points={empty} />);
    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });

  it("renders empty state when points array is empty", () => {
    render(<UsageTimelineChart points={[]} />);
    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement widget**

`frontend/src/components/widgets/UsageTimelineChart.tsx`:

```tsx
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, Legend, CartesianGrid,
} from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import type { UsageTimelinePoint } from "@/types/UsageTimeline";

interface Props {
  points: UsageTimelinePoint[];
}

export function UsageTimelineChart({ points }: Props) {
  const { t } = useTranslation();

  const isEmpty = useMemo(() => {
    if (points.length === 0) return true;
    return points.every(
      (p) => p.sessions === 0 && p.tokens_input === 0 && p.tokens_output === 0,
    );
  }, [points]);

  if (isEmpty) {
    return (
      <div className="flex h-72 items-center justify-center rounded-md border bg-[hsl(var(--muted))] text-sm text-[hsl(var(--muted-foreground))]">
        {t("metrics.timeline_empty")}
      </div>
    );
  }

  return (
    <ChartContainer height={320}>
      <ComposedChart data={points} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis dataKey="date" fontSize={11} />
        <YAxis yAxisId="tokens" fontSize={11} />
        <YAxis yAxisId="sessions" orientation="right" fontSize={11} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar yAxisId="tokens" dataKey="tokens_input" stackId="t" name={t("metrics.timeline_legend_input")} fill="#3b82f6" />
        <Bar yAxisId="tokens" dataKey="tokens_output" stackId="t" name={t("metrics.timeline_legend_output")} fill="#10b981" />
        <Line yAxisId="sessions" type="monotone" dataKey="sessions" name={t("metrics.timeline_legend_sessions")} stroke="#f59e0b" strokeWidth={2} />
      </ComposedChart>
    </ChartContainer>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/UsageTimelineChart.tsx frontend/src/__tests__/UsageTimelineChart.test.tsx
git commit -m "feat(frontend): #14d UsageTimelineChart widget (composed bar+line)"
```

---

## Task 10: UsageByProjectTable + TopSessionsTable widgets

**Files:**
- Create: `frontend/src/components/widgets/UsageByProjectTable.tsx`
- Create: `frontend/src/components/widgets/TopSessionsTable.tsx`
- Create: `frontend/src/__tests__/UsageByProjectTable.test.tsx`
- Create: `frontend/src/__tests__/TopSessionsTable.test.tsx`

- [ ] **Step 1: Failing test for UsageByProjectTable**

`frontend/src/__tests__/UsageByProjectTable.test.tsx`:

```tsx
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import { UsageByProjectTable } from "../components/widgets/UsageByProjectTable";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    metrics: {
      by_project_title: "Per project",
      col_project: "Project",
      col_sessions: "Sessions",
      col_tokens_input: "Input",
      col_tokens_output: "Output",
      col_tokens_per_byte: "tok/B",
      empty: "No data",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

const ROWS = [
  {
    project: "alpha", period_days: 30, sessions_covered: 12,
    tokens_input: 100, tokens_output: 200, tokens_injected: 50,
    raw_bytes_total: 1024, tokens_per_byte: 0.293,
  },
];

describe("UsageByProjectTable", () => {
  it("renders header + row", () => {
    render(<MemoryRouter><UsageByProjectTable rows={ROWS} /></MemoryRouter>);
    expect(screen.getByText("Per project")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
  });

  it("renders empty state", () => {
    render(<MemoryRouter><UsageByProjectTable rows={[]} /></MemoryRouter>);
    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement UsageByProjectTable**

`frontend/src/components/widgets/UsageByProjectTable.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProjectBadge } from "./ProjectBadge";
import type { UsageByProjectEntry } from "@/types/UsageSummary";

interface Props {
  rows: UsageByProjectEntry[];
}

export function UsageByProjectTable({ rows }: Props) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("metrics.by_project_title")}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <div className="py-6 text-center text-sm text-[hsl(var(--muted-foreground))]">
            {t("metrics.empty")}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-1 font-medium">{t("metrics.col_project")}</th>
                <th className="py-1 text-right font-medium">{t("metrics.col_sessions")}</th>
                <th className="py-1 text-right font-medium">{t("metrics.col_tokens_input")}</th>
                <th className="py-1 text-right font-medium">{t("metrics.col_tokens_output")}</th>
                <th className="py-1 text-right font-medium">{t("metrics.col_tokens_per_byte")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.project} className="border-b last:border-0">
                  <td className="py-1.5"><ProjectBadge name={r.project} /></td>
                  <td className="py-1.5 text-right font-mono text-xs">{r.sessions_covered}</td>
                  <td className="py-1.5 text-right font-mono text-xs">{r.tokens_input}</td>
                  <td className="py-1.5 text-right font-mono text-xs">{r.tokens_output}</td>
                  <td className="py-1.5 text-right font-mono text-xs">{r.tokens_per_byte.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Failing test for TopSessionsTable**

`frontend/src/__tests__/TopSessionsTable.test.tsx`:

```tsx
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import { TopSessionsTable } from "../components/widgets/TopSessionsTable";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    metrics: {
      top_sessions_title: "Top sessions",
      top_sessions_subtitle: "All-time top by tokens",
      col_project: "Project",
      col_session: "Session",
      col_ingested_at: "Ingested",
      col_tokens_total: "Tokens",
      empty: "No data",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

const ROWS = [
  {
    project: "alpha", session_id: "abc-very-long",
    ingested_at: "2026-04-29T12:00:00Z",
    tokens_input: 100, tokens_output: 200, tokens_total: 300, raw_bytes: 1024,
  },
];

describe("TopSessionsTable", () => {
  it("renders subtitle + row", () => {
    render(<MemoryRouter><TopSessionsTable rows={ROWS} /></MemoryRouter>);
    expect(screen.getByText("Top sessions")).toBeInTheDocument();
    expect(screen.getByText(/all-time/i)).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("300")).toBeInTheDocument();
  });

  it("renders empty state", () => {
    render(<MemoryRouter><TopSessionsTable rows={[]} /></MemoryRouter>);
    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run** → FAIL.

- [ ] **Step 7: Implement TopSessionsTable**

`frontend/src/components/widgets/TopSessionsTable.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProjectBadge } from "./ProjectBadge";
import { formatDateTime } from "@/lib/datetime";
import type { TopSession } from "@/types/TopSession";

interface Props {
  rows: TopSession[];
}

export function TopSessionsTable({ rows }: Props) {
  const { t, i18n } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("metrics.top_sessions_title")}</CardTitle>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("metrics.top_sessions_subtitle")}</p>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <div className="py-6 text-center text-sm text-[hsl(var(--muted-foreground))]">
            {t("metrics.empty")}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-1 font-medium">{t("metrics.col_project")}</th>
                <th className="py-1 font-medium">{t("metrics.col_session")}</th>
                <th className="py-1 font-medium">{t("metrics.col_ingested_at")}</th>
                <th className="py-1 text-right font-medium">{t("metrics.col_tokens_total")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.project}:${r.session_id}`} className="border-b last:border-0">
                  <td className="py-1.5"><ProjectBadge name={r.project} /></td>
                  <td className="py-1.5 font-mono text-xs" title={r.session_id}>
                    {r.session_id.slice(0, 12)}…
                  </td>
                  <td className="py-1.5 text-xs">{formatDateTime(r.ingested_at, i18n.language)}</td>
                  <td className="py-1.5 text-right font-mono text-xs">{r.tokens_total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 8: Run** → PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/widgets/UsageByProjectTable.tsx frontend/src/components/widgets/TopSessionsTable.tsx frontend/src/__tests__/UsageByProjectTable.test.tsx frontend/src/__tests__/TopSessionsTable.test.tsx
git commit -m "feat(frontend): #14d UsageByProjectTable + TopSessionsTable widgets"
```

---

## Task 11: Metrics page

**Files:**
- Create: `frontend/src/pages/Metrics.tsx`
- Create: `frontend/src/__tests__/Metrics.test.tsx`
- Modify: `frontend/public/locales/{en,uk,ru}.json` (add `metrics.*` complete block)

- [ ] **Step 1: Add locale keys**

Append to each locale's `metrics` block (preserve existing keys from earlier tasks):

- en:
```json
"metrics": {
  "title": "Metrics",
  "period_filter_label": "Period",
  "period_7d": "7 days",
  "period_30d": "30 days",
  "period_90d": "90 days",
  "timeline_title": "Token usage timeline",
  "timeline_legend_input": "Input tokens",
  "timeline_legend_output": "Output tokens",
  "timeline_legend_sessions": "Sessions",
  "timeline_empty": "No data in this period",
  "by_project_title": "Per project",
  "top_sessions_title": "Top sessions",
  "top_sessions_subtitle": "All-time top by tokens",
  "col_project": "Project",
  "col_sessions": "Sessions",
  "col_tokens_input": "Input",
  "col_tokens_output": "Output",
  "col_tokens_per_byte": "tok/B",
  "col_session": "Session",
  "col_ingested_at": "Ingested",
  "col_tokens_total": "Tokens",
  "empty": "No data"
}
```

- uk: equivalents (`Метрики` / `Період` / `7 днів` / `30 днів` / `90 днів` / `Часова шкала використання токенів` / `Вхідні токени` / `Вихідні токени` / `Сесії` / `Немає даних за цей період` / `За проєктами` / `Топ сесій` / `Топ за весь час` / `Проєкт` / `Сесії` / `Вхід` / `Вихід` / `ток/Б` / `Сесія` / `Інжест` / `Токени` / `Немає даних`).
- ru: equivalents (`Метрики` / `Период` / `7 дней` / `30 дней` / `90 дней` / `Временная шкала использования токенов` / `Входящие токены` / `Исходящие токены` / `Сессии` / `Нет данных за этот период` / `По проектам` / `Топ сессий` / `Топ за всё время` / `Проект` / `Сессии` / `Вход` / `Выход` / `ток/Б` / `Сессия` / `Ингест` / `Токены` / `Нет данных`).

- [ ] **Step 2: Failing test**

`frontend/src/__tests__/Metrics.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Metrics } from "../pages/Metrics";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    metrics: {
      title: "Metrics",
      period_filter_label: "Period",
      period_7d: "7 days",
      period_30d: "30 days",
      period_90d: "90 days",
      timeline_title: "Token usage timeline",
      timeline_legend_input: "Input tokens",
      timeline_legend_output: "Output tokens",
      timeline_legend_sessions: "Sessions",
      timeline_empty: "No data",
      by_project_title: "Per project",
      top_sessions_title: "Top sessions",
      top_sessions_subtitle: "All-time top",
      col_project: "Project", col_sessions: "Sessions",
      col_tokens_input: "Input", col_tokens_output: "Output",
      col_tokens_per_byte: "tok/B", col_session: "Session",
      col_ingested_at: "Ingested", col_tokens_total: "Tokens",
      empty: "No data",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <MemoryRouter><QueryClientProvider client={qc}>{ui}</QueryClientProvider></MemoryRouter>;
}

describe("Metrics", () => {
  it("renders title + period filter + 3 blocks", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url.endsWith("/timeline")) {
        return { data: { points: [
          { date: "2026-04-29", sessions: 1, tokens_input: 10, tokens_output: 20 },
        ] } };
      }
      if (url.endsWith("/by-project")) {
        return { data: { projects: [{
          project: "alpha", period_days: 30, sessions_covered: 1,
          tokens_input: 10, tokens_output: 20, tokens_injected: 5,
          raw_bytes_total: 100, tokens_per_byte: 0.2,
        }] } };
      }
      if (url.endsWith("/top-sessions")) {
        return { data: { sessions: [{
          project: "alpha", session_id: "s1",
          ingested_at: "2026-04-29T12:00:00Z",
          tokens_input: 10, tokens_output: 20, tokens_total: 30, raw_bytes: 100,
        }] } };
      }
      return { data: {} };
    });
    render(wrap(<Metrics />));
    await waitFor(() => expect(screen.getByText("Metrics")).toBeInTheDocument());
    expect(screen.getByText("Token usage timeline")).toBeInTheDocument();
    expect(screen.getByText("Per project")).toBeInTheDocument();
    expect(screen.getByText("Top sessions")).toBeInTheDocument();
  });

  it("clicking period pill changes timeline query", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { points: [], projects: [], sessions: [] },
    });
    const user = userEvent.setup();
    render(wrap(<Metrics />));
    await waitFor(() => screen.getByText("Metrics"));
    getSpy.mockClear();
    await user.click(screen.getByRole("button", { name: "7 days" }));
    await waitFor(() => {
      const timelineCall = getSpy.mock.calls.find(([url]) => url === "/metrics/usage/timeline");
      expect(timelineCall?.[1]).toEqual({ params: { period: "7d" } });
    });
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement Metrics page**

`frontend/src/pages/Metrics.tsx`:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useUsageTimeline } from "@/hooks/useUsageTimeline";
import { useUsageByProject } from "@/hooks/useUsageByProject";
import { useTopSessions } from "@/hooks/useTopSessions";
import { UsageTimelineChart } from "@/components/widgets/UsageTimelineChart";
import { UsageByProjectTable } from "@/components/widgets/UsageByProjectTable";
import { TopSessionsTable } from "@/components/widgets/TopSessionsTable";
import { cn } from "@/lib/utils";

const PERIODS = ["7d", "30d", "90d"] as const;
type Period = (typeof PERIODS)[number];

export default function Metrics() {
  const { t } = useTranslation();
  const [period, setPeriod] = useState<Period>("30d");
  const timeline = useUsageTimeline(period);
  const byProject = useUsageByProject(period);
  const top = useTopSessions(10);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("metrics.title")}</h1>
        <div className="flex items-center gap-2">
          <span className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("metrics.period_filter_label")}:
          </span>
          {PERIODS.map((p) => (
            <Button
              key={p}
              size="sm"
              variant={period === p ? "default" : "outline"}
              onClick={() => setPeriod(p)}
            >
              {t(`metrics.period_${p}`)}
            </Button>
          ))}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("metrics.timeline_title")}</CardTitle>
        </CardHeader>
        <CardContent>
          {timeline.isLoading ? (
            <Skeleton className="h-72" />
          ) : (
            <UsageTimelineChart points={timeline.data ?? []} />
          )}
        </CardContent>
      </Card>

      <div className={cn("grid gap-4", "xl:grid-cols-2")}>
        {byProject.isLoading ? (
          <Skeleton className="h-48" />
        ) : (
          <UsageByProjectTable rows={byProject.data ?? []} />
        )}
        {top.isLoading ? (
          <Skeleton className="h-48" />
        ) : (
          <TopSessionsTable rows={top.data ?? []} />
        )}
      </div>
    </div>
  );
}

export { Metrics };
```

(Default export is needed for `React.lazy` in Task 13. Named export preserves `import { Metrics }` patterns.)

- [ ] **Step 5: Wire route in App.tsx (temporarily as direct import — Task 13 will lazy-load)**

In `frontend/src/App.tsx`, add `import { Metrics } from "./pages/Metrics";` and replace the route:

```tsx
{ path: "metrics", element: <Metrics /> },
```

- [ ] **Step 6: Run** → PASS.

```bash
cd frontend && pnpm test Metrics
```

- [ ] **Step 7: Run all tests + tsc**

```bash
cd frontend && pnpm test && pnpm typecheck
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Metrics.tsx frontend/src/__tests__/Metrics.test.tsx frontend/src/App.tsx frontend/public/locales/
git commit -m "feat(frontend): #14d Metrics page (timeline + by-project + top-sessions + period filter)"
```

---

## Task 12: Help page rewrite

**Files:**
- Modify: `frontend/src/pages/Help.tsx` (full rewrite)
- Create: `frontend/src/__tests__/Help.test.tsx`
- Modify: `frontend/public/locales/{en,uk,ru}.json` (add `help.*` block)

- [ ] **Step 1: Add locale keys**

Append to each locale's top-level `help` block (5 sections × 3 cards each, plus headings — short copy):

- en:
```json
"help": {
  "title": "Help",
  "nav": {
    "quickstart": "Quickstart",
    "concepts": "Concepts",
    "workflows": "Workflows",
    "troubleshooting": "Troubleshooting",
    "about": "About"
  },
  "quickstart": {
    "heading": "Quickstart",
    "intro": "Get up and running in three steps.",
    "step1_title": "1. Create a project",
    "step1_body": "Click \"+ New project\" or run mnemos project add <name> <vault-path>.",
    "step2_title": "2. Start the daemon",
    "step2_body": "Run mnemos daemon start. The dashboard listens on port 5757.",
    "step3_title": "3. Use Claude Code",
    "step3_body": "Sessions in matched CWDs are auto-ingested into the vault as markdown wiki pages."
  },
  "concepts": {
    "heading": "Concepts",
    "intro": "Core ideas in claude-mnemos.",
    "projects_title": "Projects",
    "projects_body": "A project is a named vault — a directory of markdown files. Each project has its own CWD patterns.",
    "sessions_title": "Sessions",
    "sessions_body": "A session is one Claude Code conversation. Each session is ingested into the vault as one or more wiki pages.",
    "pages_title": "Pages",
    "pages_body": "A wiki page has frontmatter (type, status, flavor, confidence) and a body. Pages link via [[wikilinks]].",
    "suggestions_title": "Suggestions",
    "suggestions_body": "The ontology engine proposes merges, renames, and deletions. Approve, reject, or defer them.",
    "snapshots_title": "Snapshots",
    "snapshots_body": "Pre-op snapshots are taken before risky operations. Daily snapshots run on schedule. Manual snapshots on demand.",
    "deadletter_title": "Failed jobs",
    "deadletter_body": "Jobs that failed after retries land in the dead-letter queue. Retry or dismiss from /dead-letter."
  },
  "workflows": {
    "heading": "Common workflows",
    "intro": "Typical day-to-day operations.",
    "ingest_title": "Daily ingest",
    "ingest_body": "Sessions auto-ingest. Manually ingest from a session detail page if needed.",
    "snapshot_title": "Snapshot before risky op",
    "snapshot_body": "Click Create snapshot on the Snapshots page before any vault-wide change.",
    "restore_title": "Restore from trash",
    "restore_body": "Open /trash for the project, click Restore. The page returns to its original path."
  },
  "troubleshooting": {
    "heading": "Troubleshooting",
    "intro": "Common problems and fixes.",
    "daemon_down_title": "Daemon down",
    "daemon_down_body": "Run mnemos daemon status. Restart with mnemos daemon start.",
    "ingest_failing_title": "Ingest failing",
    "ingest_failing_body": "Check /dead-letter for the job's traceback. Most failures are rate limits or disk full.",
    "mount_failed_title": "Project mount failed",
    "mount_failed_body": "Verify the vault path exists and is writable. Check mnemos doctor."
  },
  "about": {
    "heading": "About",
    "version_label": "Version",
    "links": "Links",
    "github": "GitHub",
    "spec": "Spec",
    "issues": "Report an issue"
  }
}
```

- uk: equivalents (translate naturally; keep `mnemos` commands literal).
- ru: equivalents.

For brevity here: the test below only asserts on heading text from each section, so locale completeness is checked by the test suite. Full UK/RU prose can mirror EN structurally.

- [ ] **Step 2: Failing test**

`frontend/src/__tests__/Help.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { Help } from "../pages/Help";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    help: {
      title: "Help",
      nav: { quickstart: "Quickstart", concepts: "Concepts", workflows: "Workflows", troubleshooting: "Troubleshooting", about: "About" },
      quickstart: { heading: "Quickstart", intro: "go", step1_title: "1.", step1_body: "a", step2_title: "2.", step2_body: "b", step3_title: "3.", step3_body: "c" },
      concepts: { heading: "Concepts", intro: "i",
        projects_title: "Projects", projects_body: "p",
        sessions_title: "Sessions", sessions_body: "s",
        pages_title: "Pages", pages_body: "pg",
        suggestions_title: "Suggestions", suggestions_body: "sg",
        snapshots_title: "Snapshots", snapshots_body: "sn",
        deadletter_title: "Failed jobs", deadletter_body: "dl" },
      workflows: { heading: "Common workflows", intro: "i",
        ingest_title: "Daily ingest", ingest_body: "x",
        snapshot_title: "Snap", snapshot_body: "y",
        restore_title: "Restore", restore_body: "z" },
      troubleshooting: { heading: "Troubleshooting", intro: "i",
        daemon_down_title: "Daemon down", daemon_down_body: "x",
        ingest_failing_title: "Ingest failing", ingest_failing_body: "y",
        mount_failed_title: "Mount", mount_failed_body: "z" },
      about: { heading: "About", version_label: "Version", links: "Links", github: "GitHub", spec: "Spec", issues: "Report" },
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <MemoryRouter><QueryClientProvider client={qc}>{ui}</QueryClientProvider></MemoryRouter>;
}

describe("Help", () => {
  it("renders all 5 section headings", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { status: "ok", version: "0.1.0", uptime_s: 0, scheduler_jobs: [], alerts_count: 0, vaults: {}, jobs_alert: false },
    });
    render(wrap(<Help />));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Help" })).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Quickstart" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Concepts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Common workflows" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Troubleshooting" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "About" })).toBeInTheDocument();
  });

  it("displays version from useHealth", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { status: "ok", version: "1.2.3", uptime_s: 0, scheduler_jobs: [], alerts_count: 0, vaults: {}, jobs_alert: false },
    });
    render(wrap(<Help />));
    await waitFor(() => expect(screen.getByText(/1\.2\.3/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement Help page**

Replace `frontend/src/pages/Help.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useHealth } from "@/hooks/useHealth";

const SECTIONS = ["quickstart", "concepts", "workflows", "troubleshooting", "about"] as const;

export default function Help() {
  const { t } = useTranslation();
  const health = useHealth();
  const version = health.data?.version ?? "—";

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[180px_1fr]">
      <nav className="sticky top-4 hidden self-start lg:block">
        <ul className="space-y-1 text-sm">
          {SECTIONS.map((s) => (
            <li key={s}>
              <a href={`#${s}`} className="text-[hsl(var(--primary))] hover:underline">
                {t(`help.nav.${s}`)}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="space-y-8">
        <h1 className="text-2xl font-semibold">{t("help.title")}</h1>

        <section id="quickstart" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.quickstart.heading")}</h2>
          <p className="text-sm">{t("help.quickstart.intro")}</p>
          {(["step1", "step2", "step3"] as const).map((k) => (
            <Card key={k}>
              <CardHeader><CardTitle className="text-base">{t(`help.quickstart.${k}_title`)}</CardTitle></CardHeader>
              <CardContent className="text-sm">{t(`help.quickstart.${k}_body`)}</CardContent>
            </Card>
          ))}
        </section>

        <section id="concepts" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.concepts.heading")}</h2>
          <p className="text-sm">{t("help.concepts.intro")}</p>
          {(["projects", "sessions", "pages", "suggestions", "snapshots", "deadletter"] as const).map((k) => (
            <Card key={k}>
              <CardHeader><CardTitle className="text-base">{t(`help.concepts.${k}_title`)}</CardTitle></CardHeader>
              <CardContent className="text-sm">{t(`help.concepts.${k}_body`)}</CardContent>
            </Card>
          ))}
        </section>

        <section id="workflows" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.workflows.heading")}</h2>
          <p className="text-sm">{t("help.workflows.intro")}</p>
          {(["ingest", "snapshot", "restore"] as const).map((k) => (
            <Card key={k}>
              <CardHeader><CardTitle className="text-base">{t(`help.workflows.${k}_title`)}</CardTitle></CardHeader>
              <CardContent className="text-sm">{t(`help.workflows.${k}_body`)}</CardContent>
            </Card>
          ))}
        </section>

        <section id="troubleshooting" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.troubleshooting.heading")}</h2>
          <p className="text-sm">{t("help.troubleshooting.intro")}</p>
          {(["daemon_down", "ingest_failing", "mount_failed"] as const).map((k) => (
            <Card key={k}>
              <CardHeader><CardTitle className="text-base">{t(`help.troubleshooting.${k}_title`)}</CardTitle></CardHeader>
              <CardContent className="text-sm">{t(`help.troubleshooting.${k}_body`)}</CardContent>
            </Card>
          ))}
        </section>

        <section id="about" className="space-y-3">
          <h2 className="text-xl font-semibold">{t("help.about.heading")}</h2>
          <Card>
            <CardContent className="space-y-2 text-sm">
              <div>
                <span className="text-[hsl(var(--muted-foreground))]">{t("help.about.version_label")}: </span>
                <code>{version}</code>
              </div>
              <div className="space-x-3">
                <span className="text-[hsl(var(--muted-foreground))]">{t("help.about.links")}:</span>
                <a href="https://github.com/" className="text-[hsl(var(--primary))] hover:underline">{t("help.about.github")}</a>
                <a href="https://github.com/" className="text-[hsl(var(--primary))] hover:underline">{t("help.about.spec")}</a>
                <a href="https://github.com/" className="text-[hsl(var(--primary))] hover:underline">{t("help.about.issues")}</a>
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  );
}

export { Help };
```

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Run all tests + tsc**

```bash
cd frontend && pnpm test && pnpm typecheck
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Help.tsx frontend/src/__tests__/Help.test.tsx frontend/public/locales/
git commit -m "feat(frontend): #14d Help page (5 sections + sticky nav + version)"
```

---

## Task 13: Lazy-load Metrics + Help

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Convert imports to lazy**

In `frontend/src/App.tsx`, replace:

```tsx
import { Help } from "./pages/Help";
import { Metrics } from "./pages/Metrics";
```

with:

```tsx
import { lazy, Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";

const Help = lazy(() => import("./pages/Help"));
const Metrics = lazy(() => import("./pages/Metrics"));
```

Wrap the two route elements in `<Suspense>`:

```tsx
{ path: "help", element: <Suspense fallback={<Skeleton className="h-64" />}><Help /></Suspense> },
{ path: "metrics", element: <Suspense fallback={<Skeleton className="h-64" />}><Metrics /></Suspense> },
```

- [ ] **Step 2: Build to verify chunking**

```bash
cd frontend && pnpm build
```

Vite should now produce a separate chunk for Metrics + Help (look for new `*.js` files alongside `index.js`). Initial bundle should drop noticeably (recharts moves out of the main chunk).

- [ ] **Step 3: Run all tests**

```bash
pnpm test && pnpm typecheck
```

Lazy components hydrate inside `<Suspense>`. Existing tests render `<Help />` and `<Metrics />` directly (not via routing), so they don't go through the lazy boundary — should still pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "perf(frontend): #14d lazy-load Metrics + Help routes"
```

---

## Task 14: Dead `*_disabled` locale key sweep

**Files:**
- Modify: `frontend/public/locales/{en,uk,ru}.json`

- [ ] **Step 1: Find all `*_disabled` keys**

```bash
cd /d/code/claude-mnemos/frontend
node -e "
const fs = require('fs');
const en = JSON.parse(fs.readFileSync('public/locales/en.json', 'utf-8'));
function walk(obj, prefix) {
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? prefix + '.' + k : k;
    if (typeof v === 'string' && k.endsWith('_disabled')) console.log(path);
    else if (typeof v === 'object') walk(v, path);
  }
}
walk(en, '');
"
```

This lists every `*_disabled` key.

- [ ] **Step 2: For each candidate key, check if any code references it**

For a key like `pages.edit_disabled`, run:

```bash
grep -rn "edit_disabled" src/
```

If grep returns ONLY hits in test bundle definitions (which override keys for tests but don't depend on the production locale value), the key is dead — safe to delete.

If grep returns hits in actual src code (`title={t("pages.edit_disabled")}`, etc.), keep the key.

Likely candidates for deletion: keys whose corresponding buttons are now active and use `*_button` keys instead. For example: `pages.edit_disabled`, `pages.verify_disabled`, `pages.delete_disabled`, `sessions.ingest_disabled`, all `*.approve_disabled` / `*.reject_disabled` / `*.defer_disabled`, `dead_letter.retry_disabled` / `dead_letter.dismiss_disabled`, `lost_sessions.import_disabled` / `lost_sessions.ignore_disabled`, `trash.restore_disabled` / `trash.delete_permanently_disabled`, `snapshots.restore_disabled` / `snapshots.delete_disabled`, `activity.undo_disabled` (if widgets no longer reference it).

- [ ] **Step 3: Delete confirmed-dead keys**

For each confirmed-dead key, delete the line from all three locale JSONs (en/uk/ru). Keep keys that test bundles still reference — but those should be added to test bundles directly via `addResourceBundle` rather than relied on from locale files.

If a test bundle references a now-dead key, update the test bundle to define just the key it uses (don't keep dead production keys).

- [ ] **Step 4: Run all tests + JSON validity check**

```bash
node -e "JSON.parse(require('fs').readFileSync('public/locales/en.json', 'utf-8'))"
node -e "JSON.parse(require('fs').readFileSync('public/locales/uk.json', 'utf-8'))"
node -e "JSON.parse(require('fs').readFileSync('public/locales/ru.json', 'utf-8'))"
pnpm test
pnpm typecheck
pnpm lint
```

All clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/public/locales/
git commit -m "chore(frontend): #14d remove dead *_disabled locale keys (post-#14c wiring)"
```

---

## Task 15: Final verification + acceptance walkthrough

- [ ] **Step 1: Production build**

```bash
cd /d/code/claude-mnemos/frontend
pnpm build
```

Confirm:
- Build succeeds.
- Multiple chunks now exist (Metrics + Help split out from index).
- Initial chunk gzip size <= 285 KB.

- [ ] **Step 2: Full frontend tests + lint + typecheck**

```bash
pnpm test
pnpm typecheck
pnpm lint
```

All green. Vitest count grows by ~30-40 vs #14c (~150 → ~180-190).

- [ ] **Step 3: Backend pytest sanity**

```bash
cd /d/code/claude-mnemos
python -m pytest -q --ignore=tests/daemon/integration -k "not slow" 2>&1 | tail -5
```

Expect 1202 passed + 12 failed + 16 errors (same pre-existing CLI-pollution as on main).

```bash
git diff main..HEAD --stat -- 'claude_mnemos/' 'tests/'
```

Expect empty (no backend code touched).

- [ ] **Step 4: Acceptance criteria walk-through (design §8)**

1. ✅ `/onboarding` renders wizard. Form validates name regex, hints vault path, creates+mounts on submit.
2. ✅ Wizard surfaces 409/500 errors actionably (inline + callout); generic via toast.
3. ✅ Successful creation invalidates projects + navigates to `/project/{name}`.
4. ✅ `<NoProjectsCallout>` and `<ProjectSwitcher>` link to `/onboarding`.
5. ✅ `/help` renders 5 sections with sticky nav. Version from `useHealth()`.
6. ✅ `/metrics` renders period filter + timeline + by-project + top sessions.
7. ✅ Empty-data state on chart when 0 vaults / 0 days.
8. ✅ Top sessions labeled as window-agnostic.
9. ✅ Datetimes locale-aware via `formatDateTime`.
10. ✅ `JOB_MAX_ATTEMPTS` constant; no duplicates.
11. ✅ DeadLetterDetail navigates back after Dismiss.
12. ✅ Dead `*_disabled` keys removed.
13. ✅ Metrics + Help lazy-loaded.
14. ✅ Vitest grew ~30-40.
15. ✅ ESLint + tsc clean; backend pytest unchanged.

- [ ] **Step 5: Branch summary**

```bash
git log --oneline main..HEAD
git status
```

~16-17 commits, working tree clean.

- [ ] **Step 6: Optional commit if anything dangling**

If `pnpm-lock.yaml` updated, commit it. Otherwise verification-only.

---

## Spec coverage map

| Design § | Plan tasks |
|---|---|
| §2.1 Onboarding wizard | 4, 5, 6 |
| §2.2 Help page | 12 |
| §2.3 Metrics page | 7, 8, 9, 10, 11 |
| §2.4 Polish (datetime / max-attempts / dismiss / dead keys / lazy) | 1, 2, 3, 13, 14 |
| §3 Data flow | distributed in tasks 4-11 |
| §5 i18n | each task adds keys |
| §6 deps (recharts) | 8 |
| §7 testing | each task ships TDD tests |
| §8 ACs | 15 |
| §10 Out of scope | n/a |
