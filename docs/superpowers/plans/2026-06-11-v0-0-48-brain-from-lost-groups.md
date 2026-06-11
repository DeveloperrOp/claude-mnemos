# v0.0.48: «Мозг из группы потерянных сессий» + честные галочки + живой счётчик инъекций + уборка — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Пользователь группирует непривязанные потерянные сессии по папкам и в один клик создаёт под группу новый проект («мозг») с автоимпортом; галочка autostart в инсталляторе и настройка window-close-action становятся рабочими; счётчик инъекций перестаёт врать и инъекции возвращаются на raw-only vault'ах; lint/type-долг закрыт и защищён CI-гейтом.

**Architecture:** Фича A собирается из готовых кусков: backend добавляет одно поле `group_root` (git-root или cwd) в ответ `GET /api/lost-sessions`; frontend группирует unassigned-сессии по нему и переиспользует `useProjectCreate` (паттерн из OnboardingWelcome) + `useLostSessionsImportSelection`. Части B/C — точечная проводка существующих механизмов (`tray uninstall` + `autostart_decision`, `install-state.window_close_action`). Часть D — три точечных фикса по диагнозу (период виджета, наблюдаемость хука, seed starvation). Часть E — механическая уборка батчами с полным pytest после каждого батча + новый лёгкий CI-workflow.

**Tech Stack:** Python 3.12 / FastAPI / pydantic / pytest; React 19 / TanStack Query / zod / Vitest; Inno Setup 6.

**Операционные правила (из памяти проекта):**
- Тесты запускать через `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest ...`.
- Frontend: `cd D:\code\claude-mnemos\frontend; npm test -- --run`; типы: `npx tsc --noEmit`.
- Коммит-сообщения ТОЛЬКО через `git commit -F <файл>` (here-string ломается на кавычках/скобках).
- Деструктив — только на claude-mnemos-dev. НЕ запускать второй frozen-демон против реального home.
- Порядок частей: A → B → C → D → E → F. Уборка (E) последней, чтобы массовые правки не конфликтовали с фичей.

---

## Часть A — «Мозг из группы потерянных сессий»

### Task 1: Backend — поле `group_root` в lost-session записи

**Files:**
- Modify: `claude_mnemos/daemon/routes/lost_sessions.py:66-107` (функция `collect_lost_sessions`)
- Test: `tests/daemon/test_routes_lost_sessions_cross_vault.py`

- [ ] **Step 1: Write the failing test**

В конец `tests/daemon/test_routes_lost_sessions_cross_vault.py` добавить (фикстуры `daemon_with_two` и `_make_shared_transcripts` уже есть в файле):

```python
class TestGroupRoot:
    def test_group_root_falls_back_to_cwd_when_not_a_repo(
        self,
        daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """cwd вне git-репозитория → group_root == cwd."""
        _daemon, client, _va, _vb = daemon_with_two
        work = tmp_path / "some" / "workdir"
        work.mkdir(parents=True)
        _make_shared_transcripts(tmp_path, monkeypatch, "sess-gr-1", cwd=str(work))
        # git-фоллбэк выключаем, чтобы тест не зависел от того, лежит ли
        # tmp_path внутри чьего-то репозитория
        monkeypatch.setattr(
            "claude_mnemos.daemon.routes.lost_sessions._git_toplevel",
            lambda _cwd: None,
        )
        client.post("/api/lost-sessions/scan")
        r = client.get("/api/lost-sessions")
        assert r.status_code == 200
        items = [s for s in r.json()["sessions"] if s["session_id"] == "sess-gr-1"]
        assert items, r.json()
        assert items[0]["group_root"] == str(work)

    def test_group_root_uses_git_toplevel_for_subdirs(
        self,
        daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Две сессии в подпапках одного репо → один group_root (корень репо)."""
        _daemon, client, _va, _vb = daemon_with_two
        repo = tmp_path / "myrepo"
        sub_a = repo / "packages" / "a"
        sub_b = repo / "packages" / "b"
        sub_a.mkdir(parents=True)
        sub_b.mkdir(parents=True)
        root = tmp_path / "transcripts"
        root.mkdir(exist_ok=True)
        import json as _json
        (root / "sess-sub-a.jsonl").write_text(
            _json.dumps({"cwd": str(sub_a)}), encoding="utf-8")
        (root / "sess-sub-b.jsonl").write_text(
            _json.dumps({"cwd": str(sub_b)}), encoding="utf-8")
        monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(root))
        monkeypatch.setattr(
            "claude_mnemos.daemon.routes.lost_sessions._git_toplevel",
            lambda cwd: repo if str(cwd).startswith(str(repo)) else None,
        )
        client.post("/api/lost-sessions/scan")
        r = client.get("/api/lost-sessions")
        got = {s["session_id"]: s["group_root"] for s in r.json()["sessions"]}
        assert got.get("sess-sub-a") == str(repo)
        assert got.get("sess-sub-b") == str(repo)

    def test_group_root_is_null_without_cwd(
        self,
        daemon_with_two: tuple[MnemosDaemon, TestClient, Path, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _daemon, client, _va, _vb = daemon_with_two
        _make_shared_transcripts(tmp_path, monkeypatch, "sess-nocwd")  # cwd=None
        client.post("/api/lost-sessions/scan")
        r = client.get("/api/lost-sessions")
        items = [s for s in r.json()["sessions"] if s["session_id"] == "sess-nocwd"]
        assert items
        assert items[0]["group_root"] is None
```

ВАЖНО: в тестах monkeypatch'ится `claude_mnemos.daemon.routes.lost_sessions._git_toplevel` — значит в Step 3 импорт должен быть `from claude_mnemos.mapping.resolver import _git_toplevel` (имя попадает в namespace модуля routes). `_git_toplevel` обёрнут в `lru_cache` — в тестах патчим имя в модуле routes, кэш не мешает.

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/daemon/test_routes_lost_sessions_cross_vault.py::TestGroupRoot -v`
Expected: FAIL — `KeyError: 'group_root'` (или AssertionError: поле отсутствует).

- [ ] **Step 3: Write minimal implementation**

В `claude_mnemos/daemon/routes/lost_sessions.py`:

1) Расширить импорт из resolver (строка 28):
```python
from claude_mnemos.mapping.resolver import (
    ProjectResolver,
    ResolverAmbiguityError,
    _git_toplevel,
)
```

2) В `collect_lost_sessions` заменить хвост цикла (строки 104-106):
```python
            d = item.model_dump(mode="json")
            d["project_name"] = assigned
            # Ключ группировки для UI «создать мозг из папки»: корень
            # git-репозитория схлопывает подпапки одного проекта в одну
            # группу; вне репо группой служит сам cwd.
            group: Path | None = None
            if item.cwd:
                try:
                    group = _git_toplevel(Path(item.cwd))
                except OSError:
                    group = None
            d["group_root"] = str(group) if group else item.cwd
            out.append(d)
```

(`item.cwd is None` → `group_root` остаётся `None`, что и проверяет третий тест.)

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/daemon/test_routes_lost_sessions_cross_vault.py -v`
Expected: все тесты файла PASS (старые тесты не должны сломаться — поле добавлено, ничего не удалено).

- [ ] **Step 5: Run full backend suite for the touched area**

Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/daemon/test_app_lost_sessions.py tests/daemon/test_app_lost_sessions_ignored.py tests/core/test_lost_sessions.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/lost_sessions.py tests/daemon/test_routes_lost_sessions_cross_vault.py
git commit -F .git/COMMIT_MSG_TMP
```
Текст COMMIT_MSG_TMP: `feat: lost-sessions carry group_root (git toplevel or cwd) for folder grouping`

### Task 2: Frontend — `group_root` в zod-схеме + хелперы путей

**Files:**
- Modify: `frontend/src/types/LostSession.ts:3-13`
- Create: `frontend/src/lib/pathDisplay.ts`
- Modify: `frontend/src/pages/OnboardingWelcome.tsx:14-25` (перенести хелперы, DRY)
- Test: `frontend/src/__tests__/pathDisplay.test.ts`

- [ ] **Step 1: Write the failing test**

Создать `frontend/src/__tests__/pathDisplay.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { humanize, lastSegment } from "@/lib/pathDisplay";

describe("lastSegment", () => {
  it("returns the last path segment for windows paths", () => {
    expect(lastSegment("D:\\code\\my-project")).toBe("my-project");
  });
  it("returns the last segment for posix paths with trailing slash", () => {
    expect(lastSegment("/home/user/proj/")).toBe("proj");
  });
});

describe("humanize", () => {
  it("turns kebab/snake into Title Case words", () => {
    expect(humanize("my-cool_project")).toBe("My Cool Project");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\code\claude-mnemos\frontend; npm test -- --run src/__tests__/pathDisplay.test.ts`
Expected: FAIL — модуль `@/lib/pathDisplay` не существует.

- [ ] **Step 3: Write implementation**

Создать `frontend/src/lib/pathDisplay.ts` (код 1:1 из OnboardingWelcome.tsx:14-25):

```typescript
export function lastSegment(p: string): string {
  return p.replace(/[\\/]+$/, "").split(/[\\/]/).slice(-1)[0] ?? p;
}

export function humanize(name: string): string {
  return name
    .replace(/[-_]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}
```

В `frontend/src/pages/OnboardingWelcome.tsx` удалить локальные `lastSegment`/`humanize` (строки 14-25) и добавить импорт:
```typescript
import { humanize, lastSegment } from "@/lib/pathDisplay";
```

В `frontend/src/types/LostSession.ts` добавить поле в `LostSessionSchema` (после `cwd`):
```typescript
  group_root: z.string().nullable().optional(),
```

- [ ] **Step 4: Run tests + types**

Run: `cd D:\code\claude-mnemos\frontend; npm test -- --run; npx tsc --noEmit`
Expected: все Vitest PASS (включая существующий LostSessions.test.tsx), tsc clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/pathDisplay.ts frontend/src/__tests__/pathDisplay.test.ts frontend/src/types/LostSession.ts frontend/src/pages/OnboardingWelcome.tsx
git commit -F .git/COMMIT_MSG_TMP
```
Текст: `feat: group_root in LostSession schema + shared path display helpers`

### Task 3: Frontend — компонент групп `LostSessionGroups`

**Files:**
- Create: `frontend/src/components/widgets/LostSessionGroups.tsx`
- Test: `frontend/src/__tests__/LostSessionGroups.test.tsx`

Группируются ТОЛЬКО unassigned-сессии с непустым `group_root ?? cwd`. Карточка группы: папка, число сессий, суммарный размер, последний mtime, кнопка «Создать мозг из этой папки». Сессии без cwd остаются только в плоском списке ниже.

- [ ] **Step 1: Write the failing test**

Создать `frontend/src/__tests__/LostSessionGroups.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LostSessionGroups, groupUnassigned } from "@/components/widgets/LostSessionGroups";
import type { LostSession } from "@/types/LostSession";

function mk(over: Partial<LostSession>): LostSession {
  return {
    session_id: "s1",
    transcript_path: "C:/t/s1.jsonl",
    sha: "sha-s1",
    size_bytes: 100,
    mtime: "2026-06-01T00:00:00Z",
    project_name: "__unassigned__",
    cwd: "D:/code/proj",
    group_root: "D:/code/proj",
    preview: null,
    ...over,
  };
}

describe("groupUnassigned", () => {
  it("groups unassigned sessions by group_root", () => {
    const groups = groupUnassigned([
      mk({ session_id: "a", group_root: "D:/code/proj" }),
      mk({ session_id: "b", group_root: "D:/code/proj" }),
      mk({ session_id: "c", group_root: "D:/code/other", cwd: "D:/code/other" }),
    ]);
    expect(groups).toHaveLength(2);
    const proj = groups.find((g) => g.root === "D:/code/proj");
    expect(proj?.sessions.map((s) => s.session_id)).toEqual(["a", "b"]);
  });

  it("falls back to cwd when group_root is missing", () => {
    const groups = groupUnassigned([
      mk({ session_id: "a", group_root: null, cwd: "D:/x" }),
    ]);
    expect(groups[0].root).toBe("D:/x");
  });

  it("skips assigned sessions and sessions without any folder", () => {
    const groups = groupUnassigned([
      mk({ session_id: "a", project_name: "perviy" }),
      mk({ session_id: "b", group_root: null, cwd: null }),
    ]);
    expect(groups).toHaveLength(0);
  });

  it("sorts groups by session count desc", () => {
    const groups = groupUnassigned([
      mk({ session_id: "a", group_root: "D:/one" }),
      mk({ session_id: "b", group_root: "D:/two" }),
      mk({ session_id: "c", group_root: "D:/two" }),
    ]);
    expect(groups[0].root).toBe("D:/two");
  });
});

describe("LostSessionGroups", () => {
  it("renders a card per group with count and create button", () => {
    render(
      <LostSessionGroups
        sessions={[
          mk({ session_id: "a" }),
          mk({ session_id: "b" }),
        ]}
        onCreateBrain={vi.fn()}
      />,
    );
    expect(screen.getByText(/D:\/code\/proj/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /создать мозг/i }),
    ).toBeInTheDocument();
  });

  it("renders nothing when no unassigned groups", () => {
    const { container } = render(
      <LostSessionGroups sessions={[mk({ project_name: "perviy" })]} onCreateBrain={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
```

Примечание: если в test-setup проекта i18n инициализируется иначе — смотри образец в `frontend/src/__tests__/LostSessions.test.tsx` и повтори его обвязку (render-обёртку/QueryClientProvider), кнопку матчить по `name: /создать мозг/i` с ru-локалью либо по `data-testid="create-brain"` — тогда добавь этот testid в компонент.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\code\claude-mnemos\frontend; npm test -- --run src/__tests__/LostSessionGroups.test.tsx`
Expected: FAIL — модуль не существует.

- [ ] **Step 3: Write implementation**

Создать `frontend/src/components/widgets/LostSessionGroups.tsx`:

```tsx
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { FolderPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { isUnassigned } from "@/lib/lostSessionsConst";
import type { LostSession } from "@/types/LostSession";

export interface LostGroup {
  root: string;
  sessions: LostSession[];
  totalBytes: number;
  lastMtime: string;
}

/** Группирует непривязанные сессии по group_root (или cwd). Pure — тестируется отдельно. */
export function groupUnassigned(sessions: LostSession[]): LostGroup[] {
  const m = new Map<string, LostSession[]>();
  for (const s of sessions) {
    if (!isUnassigned(s.project_name)) continue;
    const root = s.group_root ?? s.cwd;
    if (!root) continue;
    const arr = m.get(root) ?? [];
    arr.push(s);
    m.set(root, arr);
  }
  return Array.from(m.entries())
    .map(([root, ss]) => ({
      root,
      sessions: ss,
      totalBytes: ss.reduce((n, s) => n + s.size_bytes, 0),
      lastMtime: ss.reduce((mx, s) => (s.mtime > mx ? s.mtime : mx), ss[0].mtime),
    }))
    .sort((a, b) => b.sessions.length - a.sessions.length);
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

interface Props {
  sessions: LostSession[];
  onCreateBrain: (group: LostGroup) => void;
}

export function LostSessionGroups({ sessions, onCreateBrain }: Props) {
  const { t } = useTranslation();
  const groups = useMemo(() => groupUnassigned(sessions), [sessions]);
  if (groups.length === 0) return null;
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-medium">
        {t("lost_sessions.groups.heading", "Папки без мозга")}
      </h2>
      <p className="text-xs text-muted-foreground">
        {t(
          "lost_sessions.groups.hint",
          "Эти сессии велись в папках, за которыми mnemos не следит. Создай мозг — сессии импортируются в него.",
        )}
      </p>
      <div className="space-y-2">
        {groups.map((g) => (
          <div
            key={g.root}
            className="flex items-center gap-3 rounded-md border border-border/60 bg-card/40 p-3"
          >
            <div className="flex-1 min-w-0">
              <div className="font-mono text-sm truncate" title={g.root}>
                {g.root}
              </div>
              <div className="text-xs text-muted-foreground">
                {t("lost_sessions.groups.stats", {
                  n: g.sessions.length,
                  size: formatBytes(g.totalBytes),
                  defaultValue: "{{n}} сессий · {{size}}",
                })}
              </div>
            </div>
            <Button size="sm" data-testid="create-brain" onClick={() => onCreateBrain(g)}>
              <FolderPlus className="mr-1 h-3 w-3" />
              {t("lost_sessions.groups.create_brain", "Создать мозг из этой папки")}
            </Button>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:\code\claude-mnemos\frontend; npm test -- --run src/__tests__/LostSessionGroups.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/LostSessionGroups.tsx frontend/src/__tests__/LostSessionGroups.test.tsx
git commit -F .git/COMMIT_MSG_TMP
```
Текст: `feat: LostSessionGroups widget — unassigned sessions grouped by folder`

### Task 4: Frontend — диалог «Создать мозг» (create → import chain)

**Files:**
- Create: `frontend/src/components/widgets/CreateBrainDialog.tsx`
- Test: `frontend/src/__tests__/CreateBrainDialog.test.tsx`

Диалог: предзаполненное имя (`humanize(lastSegment(root))`, редактируемое), под ним derived slug; путь vault (`<root>/.mnemos`, редактируемый текстом + кнопка Browse через готовый `DirectoryPicker`); строка «Отслеживаемая папка: <root>/**» (read-only); кнопка «Создать и импортировать N сессий». Цепочка: `createProject` → `importLostSessionsSelection` (sessions группы с `project_name: slug`, `extract: false` — уважаем продуктовое решение «экстракция только вручную/по настройке мозга»). 409 → inline-ошибка «имя занято» (пользователь правит имя). Успех → тост (его даёт сам import-хук) + `onDone()`.

- [ ] **Step 1: Write the failing test**

Создать `frontend/src/__tests__/CreateBrainDialog.test.tsx`. Образец обвязки (QueryClientProvider + мок api) взять из `frontend/src/__tests__/useLostSessionsImportSelection.test.tsx`. Тестируем: (1) предзаполнение имени и vault из root; (2) happy path — по клику зовётся `createProject` с `{name, display_name, vault_root, cwd_patterns}` и затем `importLostSessionsSelection` с session_ids группы; (3) 409 → показывается inline-ошибка, диалог не закрывается.

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CreateBrainDialog } from "@/components/widgets/CreateBrainDialog";
import type { LostGroup } from "@/components/widgets/LostSessionGroups";
import type { LostSession } from "@/types/LostSession";

vi.mock("@/api/projects.api", () => ({
  createProject: vi.fn(),
}));
vi.mock("@/api/lost_sessions.api", async (orig) => ({
  ...(await orig()),
  importLostSessionsSelection: vi.fn(),
}));
import { createProject } from "@/api/projects.api";
import { importLostSessionsSelection } from "@/api/lost_sessions.api";

function mkSession(id: string): LostSession {
  return {
    session_id: id,
    transcript_path: `C:/t/${id}.jsonl`,
    sha: `sha-${id}`,
    size_bytes: 10,
    mtime: "2026-06-01T00:00:00Z",
    project_name: "__unassigned__",
    cwd: "D:/code/my-project",
    group_root: "D:/code/my-project",
    preview: null,
  };
}

const group: LostGroup = {
  root: "D:/code/my-project",
  sessions: [mkSession("a"), mkSession("b")],
  totalBytes: 20,
  lastMtime: "2026-06-01T00:00:00Z",
};

function renderDialog(onDone = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <CreateBrainDialog open group={group} onOpenChange={() => {}} onDone={onDone} />
    </QueryClientProvider>,
  );
  return { onDone };
}

beforeEach(() => {
  vi.mocked(createProject).mockReset();
  vi.mocked(importLostSessionsSelection).mockReset();
});

describe("CreateBrainDialog", () => {
  it("prefills display name and vault from group root", () => {
    renderDialog();
    expect(screen.getByDisplayValue("My Project")).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("D:/code/my-project/.mnemos"),
    ).toBeInTheDocument();
  });

  it("creates project then imports the group's sessions", async () => {
    vi.mocked(createProject).mockResolvedValue({
      name: "my-project",
      display_name: "My Project",
      vault_root: "D:/code/my-project/.mnemos",
      cwd_patterns: ["D:/code/my-project/**"],
    } as never);
    vi.mocked(importLostSessionsSelection).mockResolvedValue({
      queued: 2, skipped: 0, missing: [], session_ids: ["a", "b"],
    } as never);
    const { onDone } = renderDialog();
    fireEvent.click(screen.getByTestId("create-brain-submit"));
    await waitFor(() => expect(createProject).toHaveBeenCalledWith({
      name: "my-project",
      display_name: "My Project",
      vault_root: "D:/code/my-project/.mnemos",
      cwd_patterns: ["D:/code/my-project/**"],
    }));
    await waitFor(() => expect(importLostSessionsSelection).toHaveBeenCalledWith({
      project_name: "my-project",
      session_ids: ["a", "b"],
      extract: false,
    }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("shows inline error on 409 and keeps dialog open", async () => {
    const err = Object.assign(new Error("conflict"), {
      response: { status: 409 },
    });
    vi.mocked(createProject).mockRejectedValue(err);
    renderDialog();
    fireEvent.click(screen.getByTestId("create-brain-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("create-brain-error")).toBeInTheDocument(),
    );
    expect(importLostSessionsSelection).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\code\claude-mnemos\frontend; npm test -- --run src/__tests__/CreateBrainDialog.test.tsx`
Expected: FAIL — компонента нет.

- [ ] **Step 3: Write implementation**

Создать `frontend/src/components/widgets/CreateBrainDialog.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { DirectoryPicker } from "@/components/picker/DirectoryPicker";
import { createProject } from "@/api/projects.api";
import { importLostSessionsSelection } from "@/api/lost_sessions.api";
import { deriveSlug } from "@/lib/slugify";
import { humanize, lastSegment } from "@/lib/pathDisplay";
import { extractApiError } from "@/lib/error";
import type { LostGroup } from "@/components/widgets/LostSessionGroups";

interface Props {
  open: boolean;
  group: LostGroup;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
}

function isConflict(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "response" in err &&
    (err as { response?: { status?: number } }).response?.status === 409
  );
}

export function CreateBrainDialog({ open, group, onOpenChange, onDone }: Props) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [display, setDisplay] = useState("");
  const [vault, setVault] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const base = group.root.replace(/[\\/]+$/, "");
    setDisplay(humanize(lastSegment(base)));
    setVault(`${base}/.mnemos`);
    setError(null);
  }, [open, group.root]);

  const slug = useMemo(() => deriveSlug(display), [display]);
  const patterns = useMemo(
    () => [`${group.root.replace(/[\\/]+$/, "")}/**`],
    [group.root],
  );

  async function submit() {
    if (!slug || !vault || pending) return;
    setPending(true);
    setError(null);
    try {
      await createProject({
        name: slug,
        display_name: display,
        vault_root: vault,
        cwd_patterns: patterns,
      });
    } catch (err) {
      setPending(false);
      setError(
        isConflict(err)
          ? t("lost_sessions.groups.name_taken", "Имя уже занято — поменяй название.")
          : extractApiError(err),
      );
      return;
    }
    try {
      await importLostSessionsSelection({
        project_name: slug,
        session_ids: group.sessions.map((s) => s.session_id),
        extract: false,
      });
    } catch (err) {
      // Проект создан, импорт не прошёл — говорим честно, проект остаётся.
      setPending(false);
      setError(
        t("lost_sessions.groups.import_failed", {
          error: extractApiError(err),
          defaultValue:
            "Мозг создан, но импорт сессий не прошёл: {{error}}. Импортируй их вручную из списка ниже.",
        }),
      );
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      return;
    }
    setPending(false);
    for (const key of ["projects", "lost-sessions", "sessions", "jobs", "health"]) {
      void qc.invalidateQueries({ queryKey: [key] });
    }
    onOpenChange(false);
    onDone();
  }

  return (
    <>
      <ConfirmDialog
        open={open}
        onOpenChange={onOpenChange}
        title={t("lost_sessions.groups.dialog_title", "Создать мозг из папки")}
        description={group.root}
        confirmLabel={t("lost_sessions.groups.dialog_confirm", {
          n: group.sessions.length,
          defaultValue: "Создать и импортировать {{n}} сессий",
        })}
        onConfirm={submit}
        isPending={pending}
        confirmTestId="create-brain-submit"
        extraContent={
          <div className="space-y-3">
            <label className="block text-sm">
              <span className="text-muted-foreground">
                {t("lost_sessions.groups.field_name", "Название мозга")}
              </span>
              <input
                type="text"
                value={display}
                onChange={(e) => setDisplay(e.target.value)}
                className="mt-1 w-full rounded-md border bg-background px-2 py-1.5 text-sm"
              />
            </label>
            <label className="block text-sm">
              <span className="text-muted-foreground">
                {t("lost_sessions.groups.field_vault", "Папка для файлов знаний")}
              </span>
              <div className="mt-1 flex gap-2">
                <input
                  type="text"
                  value={vault}
                  onChange={(e) => setVault(e.target.value)}
                  className="flex-1 rounded-md border bg-background px-2 py-1.5 text-sm font-mono"
                />
                <Button type="button" variant="outline" size="sm" onClick={() => setPickerOpen(true)}>
                  {t("lost_sessions.groups.browse", "Обзор…")}
                </Button>
              </div>
            </label>
            <div className="text-xs text-muted-foreground">
              {t("lost_sessions.groups.watching", "Отслеживается")}: <span className="font-mono">{patterns[0]}</span>
            </div>
            {error && (
              <div data-testid="create-brain-error" className="text-sm text-destructive">
                {error}
              </div>
            )}
          </div>
        }
      />
      <DirectoryPicker
        open={pickerOpen}
        initialPath={vault}
        allowCreate
        onSelect={(p) => {
          setVault(p);
          setPickerOpen(false);
        }}
        onClose={() => setPickerOpen(false)}
      />
    </>
  );
}
```

ВНИМАНИЕ-1: проверь сигнатуру `ConfirmDialog` (`frontend/src/components/widgets/ConfirmDialog.tsx`) — если prop `confirmTestId` не существует, добавь его (прокинуть `data-testid` на confirm-кнопку) либо матчь кнопку в тесте по тексту. Если `extraContent` называется иначе — у `LostSessionsManager.tsx:366` он точно `extraContent`, бери оттуда.
ВНИМАНИЕ-2: проверь точные props `DirectoryPicker` в `frontend/src/components/picker/DirectoryPicker.tsx` (`onSelect`/`onClose`/`allowCreate` — по recon-отчёту такие, но сверь перед использованием).

- [ ] **Step 4: Run tests + types**

Run: `cd D:\code\claude-mnemos\frontend; npm test -- --run; npx tsc --noEmit`
Expected: PASS, tsc clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/widgets/CreateBrainDialog.tsx frontend/src/__tests__/CreateBrainDialog.test.tsx
git commit -F .git/COMMIT_MSG_TMP
```
Текст: `feat: CreateBrainDialog — create project from folder group and import its sessions`

### Task 5: Frontend — врезка групп в страницу LostSessions + локали

**Files:**
- Modify: `frontend/src/pages/LostSessions.tsx`
- Modify: `frontend/public/locales/ru.json`, `frontend/public/locales/uk.json`, `frontend/public/locales/en.json`
- Test: `frontend/src/__tests__/LostSessions.test.tsx` (расширить)

- [ ] **Step 1: Write the failing test**

В `frontend/src/__tests__/LostSessions.test.tsx` добавить тест (используя существующую обвязку файла — мок `getLostSessions` и render-хелпер):

```tsx
it("renders folder groups block when unassigned sessions exist", async () => {
  // в существующем моке списка сессий добавить unassigned-запись c
  // group_root: "D:/code/orphan-proj" и project_name: "__unassigned__"
  renderPage();
  expect(await screen.findByText(/orphan-proj/)).toBeInTheDocument();
  expect(screen.getByTestId("create-brain")).toBeInTheDocument();
});
```

(Точная форма — по образцу соседних тестов файла: тот же QueryClientProvider/Router-враппер.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\code\claude-mnemos\frontend; npm test -- --run src/__tests__/LostSessions.test.tsx`
Expected: новый тест FAIL.

- [ ] **Step 3: Write implementation**

В `frontend/src/pages/LostSessions.tsx`:
1) импорты:
```tsx
import { useState } from "react";
import { LostSessionGroups, type LostGroup } from "@/components/widgets/LostSessionGroups";
import { CreateBrainDialog } from "@/components/widgets/CreateBrainDialog";
```
2) state + рендер над `<LostSessionsManager …>`:
```tsx
const [brainGroup, setBrainGroup] = useState<LostGroup | null>(null);
…
<LostSessionGroups sessions={sessions} onCreateBrain={setBrainGroup} />
{brainGroup && (
  <CreateBrainDialog
    open={brainGroup !== null}
    group={brainGroup}
    onOpenChange={(o) => { if (!o) setBrainGroup(null); }}
    onDone={() => setBrainGroup(null)}
  />
)}
```
(`sessions` — тот же массив, который страница уже передаёт в manager.)

3) Локали — добавить в `frontend/public/locales/ru.json` в объект `lost_sessions` ключ `groups`:
```json
"groups": {
  "heading": "Папки без мозга",
  "hint": "Эти сессии велись в папках, за которыми mnemos не следит. Создай мозг — сессии импортируются в него.",
  "stats": "{{n}} сессий · {{size}}",
  "create_brain": "Создать мозг из этой папки",
  "dialog_title": "Создать мозг из папки",
  "dialog_confirm": "Создать и импортировать {{n}} сессий",
  "field_name": "Название мозга",
  "field_vault": "Папка для файлов знаний",
  "browse": "Обзор…",
  "watching": "Отслеживается",
  "name_taken": "Имя уже занято — поменяй название.",
  "import_failed": "Мозг создан, но импорт сессий не прошёл: {{error}}. Импортируй их вручную из списка ниже.",
  "created_toast": "Мозг «{{name}}» создан"
}
```
Аналогично en (английские строки) и uk (украинские строки) — переводить по смыслу, словарь UI-терминов: «мозг»/“brain”/«мозок», vault = «Папка для файлов знаний».

- [ ] **Step 4: Run tests + types**

Run: `cd D:\code\claude-mnemos\frontend; npm test -- --run; npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/LostSessions.tsx frontend/public/locales/ru.json frontend/public/locales/uk.json frontend/public/locales/en.json frontend/src/__tests__/LostSessions.test.tsx
git commit -F .git/COMMIT_MSG_TMP
```
Текст: `feat: folder groups + create-brain flow on LostSessions page (uk/ru/en locales)`

### Task 6: Живая проверка фичи A на :5757

- [ ] **Step 1:** `cd D:\code\claude-mnemos\frontend; npm run build` (frontend пересобрать, daemon отдаёт SPA из статики).
- [ ] **Step 2:** Перезапустить дев-демон (через кнопку Restart в дашборде или `D:\code\claude-mnemos\.venv\Scripts\python.exe -m claude_mnemos.daemon …` — как в текущем окружении принято; НЕ frozen).
- [ ] **Step 3:** Открыть `http://127.0.0.1:5757/lost-sessions` — убедиться: блок «Папки без мозга» показывает группы из ~90 реальных непривязанных сессий, сгруппированные по папкам.
- [ ] **Step 4:** ДЕСТРУКТИВ ТОЛЬКО НА ТЕСТОВОЙ ПАПКЕ: создать мозг из какой-нибудь мелкой/мусорной группы (согласовать с Яриком выбор группы), проверить: проект появился в списке проектов, сессии группы ушли из lost и появились как ingest-джобы в Queue, экстракция НЕ запустилась (extract=false).
- [ ] **Step 5:** Проверить консоль браузера — 0 errors.

---

## Часть B — честная галочка autostart в инсталляторе

### Task 7: postinstall уважает `autostart_decision == "declined"`

**Files:**
- Modify: `claude_mnemos/postinstall.py:44-58` (`_silent_init`)
- Test: `tests/test_postinstall.py`

- [ ] **Step 1: Write the failing test**

В `tests/test_postinstall.py` добавить (повторив обвязку соседних тестов файла — они мокают `runtime.is_frozen` и используют tmp home):

```python
def test_silent_init_skips_autostart_when_declined(tmp_path, monkeypatch):
    """Если инсталлятор записал autostart_decision='declined' (галочка снята),
    первый запуск НЕ должен ставить автозапуск."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from claude_mnemos.state.install_state import load_install_state
    state = load_install_state()
    state.autostart_decision = "declined"
    state.save()

    calls = []
    monkeypatch.setattr(
        "claude_mnemos.cli_hooks.install", lambda: calls.append("hooks"))
    monkeypatch.setattr(
        "claude_mnemos.tray.__main__._cmd_install",
        lambda spawn_tray: calls.append("tray") or 0)

    from claude_mnemos import postinstall
    errors = postinstall._silent_init()

    assert errors == []
    assert "hooks" in calls          # hooks ставятся всегда
    assert "tray" not in calls       # autostart — нет
    assert load_install_state().autostart_decision == "declined"  # не перезаписан
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/test_postinstall.py -v -k declined`
Expected: FAIL — `"tray" in calls`.

- [ ] **Step 3: Write implementation**

В `claude_mnemos/postinstall.py` обернуть tray-блок (строки 44-54):

```python
    try:
        state = load_install_state()
        if state.autostart_decision == "declined":
            # Инсталлятор (галочка "Start when I sign in" снята) или сам
            # пользователь ранее отключил автозапуск — first-run его не
            # навязывает. Включить можно в Settings → System.
            logger.info("postinstall: autostart declined earlier; skipping")
        else:
            from claude_mnemos.tray.__main__ import _cmd_install as _tray_install_impl
            # spawn_tray=False: this runs DURING app entry (`tray run` itself, or
            # the launcher which spawns its own tray) — a second spawned `tray
            # run` would race the host process for the single-instance mutex.
            rc = _tray_install_impl(spawn_tray=False)
            if rc == 0:
                state = load_install_state()
                if state.autostart_decision is None:
                    state.autostart_decision = "accepted"
                    state.save()
    except Exception as exc:  # noqa: BLE001
        msg = f"tray autostart install failed: {exc!r}"
        logger.exception("postinstall: %s", msg)
        errors.append(msg)
```

- [ ] **Step 4: Run tests**

Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/test_postinstall.py -v`
Expected: все PASS (старые тесты happy-path не трогаем — decision у них None).

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/postinstall.py tests/test_postinstall.py
git commit -F .git/COMMIT_MSG_TMP
```
Текст: `fix: first-run postinstall respects declined autostart decision`

### Task 8: Inno — консьюмим галочку `autostart`

**Files:**
- Modify: `installer/windows/mnemos.iss` ([Run] строка ~73, [Code] строки 212-255)

Механика: галочка снята → инсталлятор запускает `tray uninstall` (удаляет .lnk, пишет `autostart_decision="declined"` — это уже делает `_cmd_uninstall`), и Task 7 не даст first-run переустановить. Галочка стоит → инсталлятор сам пишет свежий .lnk (RewriteAutostartLnk) — теперь и на fresh-install, и на upgrade.

- [ ] **Step 1: Edit [Run]** — добавить ПЕРЕД launcher-строкой (`Filename: "{app}\{#MyAppExeName}"; Parameters: "launcher"; …`):

```ini
; Consume the "autostart" task (v0.0.48): unchecked → remove the Startup
; shortcut AND record autostart_decision="declined" so first-run postinstall
; doesn't re-install it. Checked → RewriteAutostartLnk in [Code] writes the lnk.
Filename: "{app}\{#MyAppExeName}"; Parameters: "tray uninstall"; Tasks: not autostart; Flags: runhidden
```

- [ ] **Step 2: Edit [Code]** — сделать галочку авторитетной:

Заменить
```pascal
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and HadAutostartLnk then
    RewriteAutostartLnk();
end;
```
на
```pascal
procedure CurStepChanged(CurStep: TSetupStep);
begin
  // The "autostart" task is authoritative (v0.0.48): checked → write a fresh
  // shortcut pointing at the just-installed exe (covers both fresh installs
  // and upgrades, and repairs stale dev-venv shortcuts); unchecked → the
  // [Run] "tray uninstall" entry removes it and records the decline.
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('autostart') then
    RewriteAutostartLnk();
end;
```

Удалить переменную `HadAutostartLnk` (var-блок) и строку `HadAutostartLnk := FileExists(AutostartLnkPath());` из `InitializeSetup` (вместе с комментарием «Snapshot BEFORE…»). Комментарий-простыню над `RewriteAutostartLnk` (строки 195-210) обновить: стратегия теперь «галочка авторитетна», а не «восстанавливаем если было».

- [ ] **Step 3: Verify**

Run: `Select-String -Path D:\code\claude-mnemos\installer\windows\mnemos.iss -Pattern 'autostart'`
Expected: Task объявлен (строка 55), консьюмится в [Run] (`Tasks: not autostart`) и в [Code] (`WizardIsTaskSelected('autostart')`). `HadAutostartLnk` в файле больше не встречается.
Полная живая проверка инсталлятора — в Task 18 (релизный прогон).

- [ ] **Step 4: Commit**

```bash
git add installer/windows/mnemos.iss
git commit -F .git/COMMIT_MSG_TMP
```
Текст: `fix: installer autostart checkbox is now honored (was placebo since v0.0.5)`

---

## Часть C — настройка «закрытие окна» в Settings

### Task 9: Backend — GET /system/window-close-action

**Files:**
- Modify: `claude_mnemos/daemon/routes/system.py`
- Test: `tests/daemon/test_app_system.py`

- [ ] **Step 1: Write the failing test**

В `tests/daemon/test_app_system.py` добавить (обвязка/клиент-фикстура — как у существующих window-close-тестов на строках 73-89 того же файла):

```python
def test_get_window_close_action_defaults_to_hide(client):
    r = client.get("/api/system/window-close-action")
    assert r.status_code == 200
    assert r.json() == {"action": "hide"}


def test_get_window_close_action_roundtrip(client):
    r = client.post("/api/system/window-close-action", json={"action": "quit"})
    assert r.status_code == 200
    r = client.get("/api/system/window-close-action")
    assert r.json() == {"action": "quit"}
```

(Если фикстура клиента в файле называется иначе — использовать её имя.)

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/daemon/test_app_system.py -v -k window_close`
Expected: новые тесты FAIL — 405/404 на GET.

- [ ] **Step 3: Write implementation**

В `claude_mnemos/daemon/routes/system.py` перед POST-эндпойнтом добавить:

```python
@router.get("/system/window-close-action")
def get_window_close_action() -> dict[str, Any]:
    state = load_install_state()
    return {"action": state.window_close_action or "hide"}
```

Заодно поправить docstring `claude_mnemos/launcher.py:82`: обещанный тумблер теперь существует — «Settings → System → "Closing the window quits the app"».

- [ ] **Step 4: Run tests**

Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/daemon/test_app_system.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/system.py claude_mnemos/launcher.py tests/daemon/test_app_system.py
git commit -F .git/COMMIT_MSG_TMP
```
Текст: `feat: GET /system/window-close-action (read side for the settings toggle)`

### Task 10: Frontend — чекбокс «Закрытие окна = выход» в GlobalSettings

**Files:**
- Modify: `frontend/src/api/system.api.ts`
- Create: `frontend/src/hooks/useWindowCloseAction.ts`
- Modify: `frontend/src/pages/GlobalSettings.tsx:8-39` (`AutostartToggleSection` → секция System с двумя чекбоксами)
- Modify: локали ru/uk/en
- Test: `frontend/src/__tests__/GlobalSettings.test.tsx` (расширить)

- [ ] **Step 1: Write the failing test**

В `frontend/src/__tests__/GlobalSettings.test.tsx` добавить тест по образцу соседних (мокая api):

```tsx
it("renders window-close toggle and posts quit on check", async () => {
  // mock getWindowCloseAction -> {action: "hide"}; setWindowCloseAction spy
  renderPage();
  const cb = await screen.findByLabelText(/закрытие окна/i);
  fireEvent.click(cb);
  await waitFor(() =>
    expect(setWindowCloseAction).toHaveBeenCalledWith("quit"),
  );
});
```

(Матчинг по aria-label — добавить `aria-label` на input в реализации; точную обвязку взять из существующих тестов файла.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd D:\code\claude-mnemos\frontend; npm test -- --run src/__tests__/GlobalSettings.test.tsx`
Expected: новый тест FAIL.

- [ ] **Step 3: Write implementation**

`frontend/src/api/system.api.ts` — добавить:
```typescript
export interface WindowCloseAction {
  action: "hide" | "quit";
}

export async function getWindowCloseAction(): Promise<WindowCloseAction> {
  const r = await apiClient.get<WindowCloseAction>("/system/window-close-action");
  return r.data;
}

export async function setWindowCloseAction(action: "hide" | "quit"): Promise<void> {
  await apiClient.post("/system/window-close-action", { action });
}
```

Создать `frontend/src/hooks/useWindowCloseAction.ts` (калька с useAutostart.ts):
```typescript
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { getWindowCloseAction, setWindowCloseAction } from "@/api/system.api";

export function useWindowCloseActionStatus() {
  return useQuery({ queryKey: ["window-close-action"], queryFn: getWindowCloseAction });
}

export function useSetWindowCloseAction() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: setWindowCloseAction,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["window-close-action"] });
      toast.success(t("settings.system.window_close_saved", "Сохранено"));
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });
}
```

В `frontend/src/pages/GlobalSettings.tsx` внутри `AutostartToggleSection` (после autostart-label, в той же `<section>`):
```tsx
function WindowCloseToggle() {
  const { t } = useTranslation();
  const q = useWindowCloseActionStatus();
  const m = useSetWindowCloseAction();
  if (q.isLoading || !q.data) return null;
  return (
    <label className="flex items-start gap-3 py-2 cursor-pointer">
      <input
        type="checkbox"
        aria-label={t("settings.system.window_close_label", "Закрытие окна полностью выключает программу")}
        checked={q.data.action === "quit"}
        onChange={(e) => m.mutate(e.target.checked ? "quit" : "hide")}
        disabled={m.isPending}
        className="mt-1"
      />
      <div>
        <div className="text-sm font-medium">
          {t("settings.system.window_close_label", "Закрытие окна полностью выключает программу")}
        </div>
        <div className="text-xs text-muted-foreground">
          {t(
            "settings.system.window_close_hint",
            "Выключено: окно сворачивается в трей, запись сессий продолжается.",
          )}
        </div>
      </div>
    </label>
  );
}
```
и отрендерить `<WindowCloseToggle />` после autostart-`<label>` внутри секции System. Локали ru/uk/en: ключи `settings.system.window_close_label`, `window_close_hint`, `window_close_saved`.

- [ ] **Step 4: Run tests + types**

Run: `cd D:\code\claude-mnemos\frontend; npm test -- --run; npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/system.api.ts frontend/src/hooks/useWindowCloseAction.ts frontend/src/pages/GlobalSettings.tsx frontend/public/locales/ru.json frontend/public/locales/uk.json frontend/public/locales/en.json frontend/src/__tests__/GlobalSettings.test.tsx
git commit -F .git/COMMIT_MSG_TMP
```
Текст: `feat: window-close-action toggle in Settings → System (consumes the dead endpoint)`

---

## Часть D — «0 инъекций»: правда в виджете и возврат инъекций

### Task 11: UsageWidget — период 30d (tooltip перестаёт врать)

**Files:**
- Modify: `frontend/src/components/widgets/UsageWidget.tsx:38`
- Test: `frontend/src/__tests__/UsageWidget.test.tsx`

- [ ] **Step 1:** В `UsageWidget.test.tsx` найти место, где мокается `useUsage`/`getUsage`, и добавить/поправить assert: виджет запрашивает `"30d"`. Запустить — FAIL.
- [ ] **Step 2:** В `UsageWidget.tsx:38` заменить `useUsage("1d")` → `useUsage("30d")`. Tooltip `usage_widget.tooltip_inject_events` («за последние 30 дней») теперь правдив; проверить, что и `tooltip_tokens` в локалях не говорит «за сутки» (если говорит — поправить на «за 30 дней» в ru/uk/en).
- [ ] **Step 3:** `cd D:\code\claude-mnemos\frontend; npm test -- --run src/__tests__/UsageWidget.test.tsx` → PASS.
- [ ] **Step 4:** Commit: `fix: UsageWidget queries 30d to match its own tooltip (was 1d)`.

### Task 12: Хук session_start — наблюдаемость (empty-события + лог несматченного cwd)

**Files:**
- Modify: `hooks/session_start.py:104-150`
- Test: `tests/test_session_start_hook.py`

- [ ] **Step 1: Write the failing tests**

В `tests/test_session_start_hook.py` (обвязка — как у соседних тестов файла: stdin-payload + monkeypatch resolver/builder):

```python
def test_empty_context_still_writes_metric_event(...):
    """Контекст пуст → stdout пуст, но событие mode='empty' записано в
    .inject-metrics.json (раньше: никакого следа)."""

def test_unmatched_cwd_logs_to_inject_log(...):
    """resolve_by_cwd -> None → строка 'cwd not in any project' появляется
    в ~/.claude-mnemos/inject.log (раньше: молчаливый return)."""
```

Полные тела написать по образцу существующих тестов файла (там уже есть фикстуры для payload/vault). Ассерты: первый — после `main()` файл `<vault>/.inject-metrics.json` существует и последнее событие имеет `mode == "empty"`, stdout пуст; второй — inject.log содержит подстроку `cwd not in any project`.

- [ ] **Step 2:** Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/test_session_start_hook.py -v` → новые FAIL.

- [ ] **Step 3: Write implementation** — в `hooks/session_start.py`:

1) строки 112-113, добавить лог:
```python
    if project is None:
        _log(f"cwd not in any project: {cwd}")
        return 0
```

2) Перенести метрик-блок ПЕРЕД `if not context: return 0` (сейчас блок на строках 128-150 стоит после). Итоговый порядок после вызова `build_adaptive_context_with_stats`:
```python
    # Best-effort metric write — failure does not block the inject. Writes
    # ALSO when context is empty (mode="empty"): без этого «0 инъекций» в
    # дашборде неотличим от «хук вообще не звался».
    try:
        from datetime import UTC, datetime
        from uuid import uuid4

        from claude_mnemos.state.inject_metrics import (
            InjectMetricEvent,
            InjectMetricsLog,
        )
        event = InjectMetricEvent(
            id=uuid4().hex,
            timestamp=datetime.now(UTC),
            session_id=payload.get("session_id"),
            operation="session_start",
            mode=stats.mode,
            tokens_full=stats.tokens_full,
            tokens_actual=stats.tokens_actual,
            candidates_total=stats.candidates_total,
            candidates_packed=stats.candidates_packed,
        )
        InjectMetricsLog.append_to_vault(Path(project.vault_root), event)
    except Exception as exc:  # noqa: BLE001
        _log(f"metric write failed: {exc}")

    if not context:
        return 0
```

ПРОВЕРИТЬ перед реализацией: что `stats.mode == "empty"` когда `build_adaptive_context_with_stats` возвращает пустую строку (см. `claude_mnemos/core/session_start.py`, `InjectStats`/`InjectMode`). Если пустые пути возвращают другой mode — нормализовать в hook'е: `mode = stats.mode if context else "empty"`.
ПРОВЕРИТЬ: `compression_summary` в `claude_mnemos/core/metrics.py` фильтрует empty-события из `valid_events_count`, но считает в `events_count` — значит топбар начнёт показывать ЧИСЛО ПОПЫТОК. Это осознанное решение (наблюдаемость > косметика); avg_compression уже взвешен по `valid_events_count` и не испортится (проверить тестом `tests/core/test_metrics.py`, что avg не учитывает empty).

- [ ] **Step 4:** Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/test_session_start_hook.py tests/test_inject_metrics.py tests/core/test_metrics.py -v` → PASS.
- [ ] **Step 5:** Commit: `fix: session_start hook records empty injects + logs unmatched cwd (closes hook_silence blindspot)`.

### Task 13: Seed starvation — raw-only ингесты больше не глушат инъекции

**Files:**
- Modify: `claude_mnemos/core/session_start.py:183-204` (`_seeds_from_manifest`)
- Test: `tests/test_session_start.py`

Сейчас seeds берутся из `created_pages` ПОСЛЕДНИХ `recent` (10) ингест-записей. При manual-default (extract=off, v0.0.10+) свежие записи содержат только `raw/chats/*.md` → все seeds мёртвые (не wiki-слаги) → контекст пуст навсегда, пока юзер не экстрактит. Фикс: считать «свежими» последние `recent` записей, у которых ЕСТЬ wiki-страницы, и брать слаги только из них.

- [ ] **Step 1: Write the failing test**

В `tests/test_session_start.py` (по образцу существующих тестов `_seeds_from_manifest` / manifest-фикстур этого файла):

```python
def test_seeds_skip_raw_only_records_and_reach_older_wiki_records(...):
    """10 свежих raw-only записей + старая запись с wiki/concepts/foo.md →
    seeds == {"concepts/foo"} (раньше: пустые seeds, инъекции мертвы)."""
```

Тело: собрать manifest с 10 записями, у которых `created_pages=["raw/chats/x.md"]` и более старой записью с `created_pages=["wiki/concepts/foo.md"]`; вызвать `_seeds_from_manifest(vault, recent=10)`; assert `"concepts/foo" in seeds` и ни один `raw/...` не попал.

- [ ] **Step 2:** Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/test_session_start.py -v -k seeds` → FAIL.

- [ ] **Step 3: Write implementation** — заменить тело цикла в `_seeds_from_manifest`:

```python
    records = list(manifest.ingested.values())
    records.sort(key=lambda r: r.ingested_at, reverse=True)
    seeds: set[str] = set()
    # raw-only записи (manual-default ингест без экстракции) не дают wiki-слагов;
    # пропускаем их, не расходуя бюджет recent — иначе 10 raw-ингестов подряд
    # навсегда глушат инъекции (seed starvation, найдено в v0.0.48).
    wiki_records = 0
    for rec in records:
        if wiki_records >= recent:
            break
        slugs: set[str] = set()
        for page_ref in rec.created_pages:
            ref = page_ref.replace("\\", "/")
            if not ref.startswith("wiki/"):
                continue
            ref = ref[len("wiki/"):]
            if ref.endswith(".md"):
                ref = ref[:-3]
            slugs.add(ref)
        if not slugs:
            continue
        wiki_records += 1
        seeds.update(slugs)
    return seeds
```

- [ ] **Step 4:** Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/test_session_start.py -v` → PASS (старые тесты тоже: для записей с wiki-страницами поведение идентично).
- [ ] **Step 5:** Commit: `fix: seed starvation — raw-only ingests no longer exhaust the recent-records budget for inject seeds`.

### Task 14: Stale-lock в inject-metrics не дропает события молча

**Files:**
- Modify: `claude_mnemos/state/inject_metrics.py:142-151` (`append_to_vault`)
- Test: `tests/test_inject_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
def test_append_breaks_stale_lock(tmp_path):
    """Лок-файл старше 60s (упавший писатель) ломается, событие пишется."""
    vault = tmp_path
    lock = vault / ".inject-metrics.lock"   # сверить точное имя в inject_metrics.py
    lock.write_text("dead-writer")
    old = time.time() - 120
    os.utime(lock, (old, old))
    InjectMetricsLog.append_to_vault(vault, _mk_event())  # _mk_event — хелпер по образцу соседних тестов
    events = InjectMetricsLog.load(vault).events           # сверить API чтения по соседним тестам
    assert len(events) == 1
```

(Имена `lock`-файла и API чтения сверить с `claude_mnemos/state/inject_metrics.py` и существующими тестами `tests/test_inject_metrics.py` — взять оттуда хелперы.)

- [ ] **Step 2:** Run → FAIL (timeout-ветка молча дропает).
- [ ] **Step 3:** В `append_to_vault` перед poll-циклом: если lock существует и `time.time() - lock.stat().st_mtime > 60` → `lock.unlink(missing_ok=True)` (best-effort, в try/except OSError). Константа `STALE_LOCK_SEC = 60` рядом с существующими константами модуля.
- [ ] **Step 4:** Run: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest tests/test_inject_metrics.py -v` → PASS.
- [ ] **Step 5:** Commit: `fix: break stale .inject-metrics.lock instead of silently dropping events`.

---

## Часть E — уборка lint/type + CI-гейт

Снимок долга (2026-06-11): ruff 77 (32 автофиксабельных: UP037×16, I001×5, F401×2, UP035×6, UP041×2, UP017×1; вручную: E402×12, SIM105×11, E501×10, B904×5, B008×3, SIM102×3, UP046×1), mypy 67 в 22 файлах (type-arg×22, no-any-return×15, no-untyped-def×7, assignment×5, unused-ignore×5, attr-defined×5, no-untyped-call×4, прочее×4).

### Task 15: ruff → 0

- [ ] **Step 1:** `D:\code\claude-mnemos\.venv\Scripts\python.exe -m ruff check claude_mnemos --fix` (только safe-фиксы). Затем ПОЛНЫЙ прогон: `...\python.exe -m pytest -q` → exit 0 (известные pre-existing env-фейлы Windows PID — сверить, что их число не выросло).
- [ ] **Step 2:** Commit: `chore: ruff safe autofixes (quoted annotations, imports, deprecated aliases)`.
- [ ] **Step 3:** Ручной батч с ПРАВИЛАМИ ОСТОРОЖНОСТИ:
  - **E402 (12)** — почти все это НАМЕРЕННЫЕ lazy/post-path-setup импорты (hooks/*, postinstall, cli): НЕ переносить наверх, ставить `# noqa: E402` с однострочным обоснованием. Переносить только если импорт явно случайно оказался не наверху.
  - **B008 (3)** — это FastAPI-идиома `Body(...)` в дефолтах аргументов: НЕ менять код, добавить в `pyproject.toml` ruff per-file-ignores: `"claude_mnemos/daemon/routes/*" = ["B008"]`.
  - **SIM105 (11)** — заменить `try/except: pass` на `contextlib.suppress(...)` ТОЛЬКО там, где except-тело действительно пустое; если там лог — оставить и `# noqa: SIM105` не нужен (ruff не флагует непустые).
  - **B904 (5)** — добавить `from exc` / `from None` осознанно (в HTTPException-цепочках обычно `from None` нежелателен — брать `from exc`).
  - **E501 (10)** — переносы строк, не трогая смысл; в строках-URL → `# noqa: E501`.
  - **SIM102 (3)** — схлопнуть вложенные if только если читабельность не падает, иначе noqa.
  - **UP046 (1)** — generic-класс на PEP 695 синтаксис, если Python-таргет позволяет (3.12 — позволяет).
- [ ] **Step 4:** После КАЖДОЙ группы файлов: `...\python.exe -m pytest -q` → exit 0. `...\python.exe -m ruff check claude_mnemos` → `All checks passed!`.
- [ ] **Step 5:** Commit: `chore: ruff clean — manual fixes (E402 noqa-intentional, SIM105, B904, E501) + B008 per-file-ignore`.

### Task 16: mypy → 0

- [ ] **Step 1:** `D:\code\claude-mnemos\.venv\Scripts\python.exe -m mypy claude_mnemos` — взять полный список, сгруппировать по файлам.
- [ ] **Step 2:** Чинить ПО ФАЙЛАМ (22 файла, батчами по 4-6 файлов), правила:
  - `type-arg` — дописать параметры дженериков (`dict[str, Any]`, `list[str]`, `Callable[..., None]`); НЕ менять рантайм-поведение.
  - `no-any-return` — аннотировать промежуточные значения или `cast(...)`; запрещено «лечить» через `-> Any`.
  - `unused-ignore` — просто удалить устаревшие `# type: ignore`.
  - `attr-defined`/`assignment` — смотреть индивидуально; если это pydantic/динамика — точечный `# type: ignore[attr-defined]` с комментарием-причиной.
  - После каждого батча: `pytest -q` exit 0 + `mypy` count уменьшился.
- [ ] **Step 3:** Финал: `mypy claude_mnemos` → `Success: no issues found in 163 source files`.
- [ ] **Step 4:** Commit (по батчу на коммит): `chore: mypy clean batch N/4 — <files>`.

### Task 17: CI-гейт (lint + types, лёгкий)

**Files:**
- Create: `.github/workflows/ci.yml`

Полный pytest в CI НЕ гоняем (бюджет Actions — известный инцидент v0.0.39); гейт держит только статику: ruff + mypy + tsc + vitest. Релизный workflow (release.yml) уже гоняет smoke-pytest.

- [ ] **Step 1:** Создать `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    name: Lint & Types
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e . ruff mypy
      - name: ruff
        run: python -m ruff check claude_mnemos
      - name: mypy
        run: python -m mypy claude_mnemos

  frontend:
    name: Frontend types & tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v6
        with:
          node-version: "20"
      - name: Install
        working-directory: frontend
        run: npm ci
      - name: tsc
        working-directory: frontend
        run: npx tsc --noEmit
      - name: vitest
        working-directory: frontend
        run: npm test -- --run
```

ПРОВЕРИТЬ перед коммитом: установлены ли ruff/mypy как extras в pyproject (`[project.optional-dependencies]`) — если есть dev-extra, ставить `pip install -e .[dev]` вместо ручного списка; версии ruff/mypy желательно зафиксировать теми же, что в локальном .venv (`ruff --version`, `mypy --version`), чтобы CI не разъезжался с локалью.

- [ ] **Step 2:** Commit: `ci: lint/type gate (ruff + mypy + tsc + vitest) on push/PR`.
- [ ] **Step 3:** Push в main, убедиться что workflow запустился и зелёный: `gh run list --workflow=ci.yml --limit 1`.

---

## Часть F — релиз v0.0.48

### Task 18: Adversarial-review + релиз + живое доказательство

- [ ] **Step 1:** Полные прогоны: `pytest -q` (exit 0), `ruff check` (clean), `mypy` (clean), `npm test -- --run` (all pass), `npx tsc --noEmit` (clean), `npm run build` (ok).
- [ ] **Step 2:** Скептик-ревью КРИТИЧНЫХ путей этого релиза (по практике v0.0.43/44 — скептик дважды ловил реальные баги): (а) цепочка create→import в CreateBrainDialog — частичные фейлы, повторный сабмит, пересечение cwd_patterns с существующим проектом; (б) installer-правки .iss — fresh/upgrade/unchecked-сценарии по таблице; (в) перенос метрик-блока в hook — не сломали ли contract инъекции (stdout-формат не менялся).
- [ ] **Step 3:** Релиз: тег `v0.0.48` → push → CI (release.yml) собирает 3 платформы → опубликовать. Версия штампуется из тега автоматически (set_version.py).
- [ ] **Step 4:** Установка у Ярика: WDAC блокирует setup.exe → путь как в v0.0.47: portable zip → elevated robocopy в `C:\Program Files\claude-mnemos`. ВАЖНО: после robocopy-установки Startup-ярлык НЕ переписывается инсталлятором — проверить `Mnemos.lnk` вручную (должен указывать на `C:\Program Files\claude-mnemos\claude-mnemos.exe tray run` — починен 2026-06-11).
- [ ] **Step 5:** Живое доказательство на установленной версии: (1) `/lost-sessions` показывает группы; (2) создать мозг из согласованной с Яриком группы — проект появился, сессии импортировались; (3) Settings → System: оба чекбокса работают (window-close: переключить на quit, закрыть окно лаунчера → процесс завершился; вернуть hide); (4) топбар: счётчик инъекций за 30 дней ненулевой после первой сессии в отслеживаемой папке с wiki-страницами; (5) `~/.claude-mnemos/inject.log` пишет `cwd not in any project` для сессий из неотслеживаемых папок.
- [ ] **Step 6:** Интерактивный разбор оставшихся групп потерянных сессий с Яриком (импорт/игнор/мозг per группа) + 45 битых wikilinks (отдельная сессия, вне этого плана).

---

## Self-review notes

- Решение «extract=false при импорте группы» — соответствует продуктовому решению Ярика (2026-06-11): автоэкстракция выключена по умолчанию, включается per-мозг в настройках.
- `group_root` считается и для assigned-сессий (лишняя работа ~0: lru_cache на `_git_toplevel`), зато схема однородная.
- Топбар после Task 12 показывает ПОПЫТКИ инъекций (включая empty) — это осознанно: «0» теперь означает «хук молчит», ненулевое с пустыми контекстами видно в Metrics. Если Ярик захочет «только успешные» — поменять агрегатор на valid_events_count одной строкой (зафиксировать при ревью).
- Конфликт имён в CreateBrainDialog обрабатывается без авто-суффикса (юзер правит имя) — проще и предсказуемее.
- Уборка (E) идёт ПОСЛЕ фич: автофиксы ruff не конфликтуют с диффами A-D.
- Известные pre-existing failing tests (Windows PID + env-зависимые, ~3-5 шт.) — не чинятся этим планом; критерий «exit 0» означает «не хуже базовой линии», зафиксировать их список перед Task 1.
