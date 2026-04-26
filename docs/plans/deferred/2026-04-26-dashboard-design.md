# Design: Frontend Dashboard (DEFERRED to Plan #14)

> **⚠️ DEFERRED 2026-04-26.** Этот design написан как Plan #8, но **отложен до Plan #14**: spec'овский dashboard требует 11 разделов, а 7 из них зависят от backend подсистем (ontology / watchdog / lint / jobs+dead-letter / settings persistence / sessions tracker / trash / metrics / page edit / multi-vault / adaptive context) которых **ещё нет**.
>
> Roadmap пересобран — backend подсистемы делаются Plans #8-#13 первыми, потом Plan #14 = Dashboard поверх готового. Yarik одобрил перенос 2026-04-26: «можешь перенести этапы под которые нету инфраструктуры но только сразу отмечай что ты отложил и куда».
>
> Этот файл сохраняется как референс. При возврате к Plan #14 — обновить дату/статус и проверить актуальность каждого раздела (некоторые решения могут устареть к тому моменту).

---

# Design: Frontend Dashboard (originally Plan #8 — DEFERRED)

**Status:** deferred to Plan #14. Original design preserved below.
**Date:** 2026-04-26
**Author:** Claude (with Yarik approval).
**Predecessor:** `2026-04-26-plugin-hooks-design.md` (Plan #7, merged in `427e377`).
**Successor planned:** Plans #8-#13 (backend подсистемы), затем Plan #14 = Dashboard.

---

## 1. Goal

Поднять **первый рабочий веб-dashboard** для mnemos: React + Vite + TypeScript + shadcn/ui + Tailwind + i18next, по spec §11. Дашбординг живёт в том же FastAPI daemon процессе на `127.0.0.1:5757`, доступен в браузере через `http://127.0.0.1:5757/`.

После Plan #8 пользователь:

```bash
mnemos daemon start --vault $MNEMOS_VAULT_ROOT
# открывает в браузере → http://127.0.0.1:5757/
# видит:
# - Overview: counts + scheduler jobs + recent activity preview
# - Pages Browser: список wiki страниц с фильтрами по type/flavor + просмотр
# - Activity Center: история операций с кнопками undo
# - Snapshots: список бэкапов с create/restore/delete actions
```

### Что НЕ даёт (явно отложено)

Из spec §11.1 (15 страниц) и §12.3 (11 разделов Project View) — **делаем только 4 раздела**, потому что остальные требуют backend-фич которых нет:

| Раздел из spec | Почему НЕ в Plan #8 |
|---|---|
| Sessions | Нет endpoint `GET /sessions/:project` (нет sessions tracker'а) |
| Очередь / Failed Jobs | Нет jobs.json + dead-letter (Plan #11+) |
| Suggestions | Нет ontology suggestions panel (Plan #9) |
| Lost sessions | Нет lost-sessions scanner |
| Trash | Нет soft-delete tracker (Plan #11+) |
| Health | Нет lint + system detectors (Plan #11+) |
| Settings | Нет persistent settings backend (Plan #11+) |
| Onboarding wizard | Single-user dogfooding — не нужен (Plan #11+) |
| Project switcher | Single-vault (Plan #11+ multi-vault) |
| Help (5 sections) | Только About раздел (плейсхолдер) |
| Metrics (token usage) | Нет ingest metrics tracker (Plan #11+) |
| Markdown editor (Page Detail edit) | Read-only в Plan #8 (edit endpoints отсутствуют) |
| Obsidian links / backlinks | Нет backlinks index (Plan #11+) |
| Confidence bar 4-factor breakdown | Frontmatter не обязательно содержит — рендерим только если есть |
| Recharts (Usage Timeline) | Нет metrics — отложено |

### Что точно делаем (4 раздела)

1. **Overview** — главная: vault counts + scheduler jobs status + last 5 activity entries + 4 quick-action cards для остальных разделов
2. **Pages Browser** — список wiki pages (type/flavor filter, list view), клик на страницу → Page Detail (read-only markdown render)
3. **Activity Center** — таблица activity entries (newest first, паджинация), кнопка [Undo] для undoable
4. **Snapshots** — таблица бэкапов, кнопки [Create manual] / [Restore] / [Delete] с confirm dialog

Плюс **layout + nav** (TopBar + Sidebar по spec §12.1, без project switcher).

---

## 2. Scope

### 2.1 In scope

#### Backend extensions

| Что | Где |
|---|---|
| `core/page_reader.py` — выделить shared helper для list_pages/read_page (сейчас живёт в `mcp/read_tools/pages.py`) | `claude_mnemos/core/page_reader.py` |
| `GET /pages?type=&flavor=&limit=&offset=` REST endpoint в daemon | `claude_mnemos/daemon/routes/pages.py` |
| `GET /pages/{path:path}` REST endpoint (read с traversal protection) | то же |
| CORS middleware для dev (Vite на :5173 → daemon на :5757) | `claude_mnemos/daemon/app.py` |
| Static mount: `/` → `frontend/dist/` если существует, fallback `/` → JSON `{message: "frontend not built"}` | `claude_mnemos/daemon/app.py` |
| `mcp/read_tools/pages.py` рефакторится использовать новый shared helper (DRY) | edit |
| Tests: `tests/daemon/test_app_pages.py` для новых endpoints | новый |
| Tests: `tests/test_page_reader.py` для shared helper | новый |

#### Frontend (всё новое в `frontend/`)

```
frontend/
├── package.json
├── pnpm-lock.yaml
├── vite.config.ts                 # Vite + react plugin + proxy
├── tsconfig.json
├── tsconfig.node.json
├── tailwind.config.ts
├── postcss.config.js
├── components.json                # shadcn/ui config
├── index.html
├── public/
│   └── locales/
│       ├── uk.json                # primary
│       ├── ru.json
│       └── en.json                # fallback
└── src/
    ├── main.tsx                   # React entry
    ├── App.tsx                    # Router + QueryClient + i18n providers
    ├── i18n.ts                    # i18next setup
    ├── styles/
    │   └── globals.css            # Tailwind base + shadcn vars
    ├── lib/
    │   ├── api.ts                 # fetch wrapper (relative URLs)
    │   ├── format.ts              # bytes/timestamps formatting
    │   └── utils.ts               # cn() helper для tailwind-merge
    ├── components/
    │   ├── ui/                    # shadcn auto-installed (button, card, table, dialog, badge, ...)
    │   ├── layout/
    │   │   ├── Layout.tsx
    │   │   ├── TopBar.tsx
    │   │   └── Sidebar.tsx
    │   ├── ConfirmDialog.tsx      # generic confirm для destructive actions
    │   └── EmptyState.tsx
    ├── pages/
    │   ├── Overview.tsx
    │   ├── PagesBrowser.tsx
    │   ├── PageDetail.tsx
    │   ├── ActivityCenter.tsx
    │   └── Snapshots.tsx
    ├── hooks/
    │   ├── useStatus.ts           # GET /vault/info + /health
    │   ├── usePages.ts            # GET /pages
    │   ├── usePage.ts             # GET /pages/{path}
    │   ├── useActivity.ts         # GET /activity
    │   ├── useSnapshots.ts        # GET /snapshots
    │   └── mutations/
    │       ├── useUndo.ts
    │       ├── useCreateSnapshot.ts
    │       ├── useRestoreSnapshot.ts
    │       └── useDeleteSnapshot.ts
    └── types/
        ├── vault.ts               # zod schemas + inferred types
        ├── activity.ts
        ├── snapshot.ts
        └── page.ts
```

#### Tooling

- pnpm как пакет-менеджер (быстрее npm, не зашоренный как yarn 1.x)
- Vite 5+, React 19, TypeScript 5+
- Tailwind CSS 3.4 (4.0 ещё в alpha; 3.4 stable, отлично работает с shadcn)
- shadcn/ui (Radix-based, локально генерируем компоненты)
- TanStack Query v5 (data fetching, polling 5s для активных операций)
- Zustand (UI state — sidebar collapsed, locale)
- Zod (runtime валидация)
- i18next + react-i18next + LanguageDetector + HttpBackend
- Lucide React (иконки)
- clsx + tailwind-merge
- dayjs (formatting timestamps)
- react-router 6+ (vs 7 — 6 stable)
- react-markdown + remark-gfm (для Page Detail)

#### Build / distribution

- `pnpm build` → `frontend/dist/` (Vite production bundle)
- FastAPI mount: `app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "frontend" / "dist", html=True))` если папка существует
- В dev: пользователь запускает `pnpm dev` (на :5173) и `mnemos daemon start` (на :5757) параллельно. Vite proxy для всех endpoints
- В prod: `pnpm build` один раз, потом только daemon. Браузер открывает `http://127.0.0.1:5757/`

### 2.2 Out of scope

| Component | Plan |
|---|---|
| 7 spec'овских разделов (Sessions, Queue, Suggestions, Lost, Trash, Health, Settings) | Plans #9-#11+ когда backend появится |
| Onboarding wizard | Plan #11+ |
| Project switcher / multi-vault UI | Plan #11+ |
| Page edit (Markdown editor — Monaco/CodeMirror) | Plan #11+ (нет PATCH endpoint) |
| Verify / Archive / Delete page actions | Plan #11+ (нет endpoints) |
| Backlinks panel | Plan #11+ (нет backlinks index) |
| Open-in-Obsidian link | Plan #11+ |
| Token usage metrics + recharts | Plan #11+ (нет metrics tracker) |
| Failed jobs / Dead-letter UI | Plan #11+ (нет dead-letter queue) |
| Real-time updates (WebSockets / SSE) | Plan #11+ — пока polling каждые 5s |
| Dark mode toggle | Plan #11+ |
| Auth/login | Plan #12+ (localhost trust) |
| Telemetry opt-in | YAGNI |
| Help system (5 разделов) | Plan #11+; пока минимальный About-плейсхолдер |
| Provenance markers / 4-factor confidence breakdown | Render если frontmatter содержит, не делаем UI tooltip |

---

## 3. Architecture

### 3.1 Process model

```
┌──────────────┐
│  Browser     │
│  (Chrome)    │
└──────┬───────┘
       │ HTTP
       ▼
┌──────────────────────────────────────────┐
│  uvicorn :5757                           │
│   ├─ FastAPI app                         │
│   │   ├─ /health, /version               │  (existing)
│   │   ├─ /vault/info                     │  (existing)
│   │   ├─ /activity*                      │  (existing)
│   │   ├─ /snapshots*                     │  (existing)
│   │   ├─ /pages, /pages/{path}           │  (NEW Plan #8)
│   │   └─ /  → StaticFiles(frontend/dist) │  (NEW Plan #8)
│   ├─ APScheduler                         │  (existing Plan #5)
│   └─ Static file serving                 │  (NEW Plan #8)
└──────────────────────────────────────────┘
       │ reads
       ▼
┌──────────────┐
│   vault/     │
└──────────────┘
```

В dev — добавляется отдельный процесс Vite на :5173 с прокси к :5757.

### 3.2 Backend extensions: pages endpoints

`core/page_reader.py` — общий helper, переиспользуемый MCP'ом и daemon'ом:

```python
# claude_mnemos/core/page_reader.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Iterable
import yaml

class PageRefError(ValueError): ...

PageType = str  # "entity" | "concept" | "source"

_TYPE_DIRS: dict[str, str] = {
    "entity": "wiki/entities",
    "concept": "wiki/concepts",
    "source": "wiki/sources",
}

def split_frontmatter(text: str) -> tuple[dict[str, Any], str]: ...

def resolve_page_path(vault: Path, page_ref: str) -> Path:
    """Same logic как в mcp/vault_access.py — переезжает сюда. MCP импортирует
    отсюда (back-compat re-export в mcp/vault_access.py)."""

def list_pages(vault, *, type=None, flavor=None, limit=50, offset=0) -> list[dict[str, Any]]:
    """Same shape как mcp/read_tools/pages.list_pages, но c offset support."""

def read_page(vault, page_ref) -> dict[str, Any]: ...
```

`mcp/vault_access.py` и `mcp/read_tools/pages.py` рефакторятся в re-export'ы. Логика жить в одном месте.

`daemon/routes/pages.py`:

```python
from fastapi import APIRouter, HTTPException, Query, Request
from claude_mnemos.core.page_reader import (
    PageRefError, list_pages, read_page,
)

router = APIRouter()

@router.get("/pages")
def list_pages_endpoint(
    request: Request,
    type: str | None = Query(default=None, regex="^(entity|concept|source)$"),
    flavor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    vault = request.app.state.vault_root
    items = list_pages(vault, type=type, flavor=flavor, limit=limit + offset, offset=0)
    sliced = items[offset : offset + limit]
    return {"pages": sliced, "total": len(items)}

@router.get("/pages/{page_path:path}")
def read_page_endpoint(page_path: str, request: Request) -> dict[str, Any]:
    vault = request.app.state.vault_root
    try:
        return read_page(vault, page_path)
    except PageRefError as exc:
        raise HTTPException(status_code=404, detail={"error": "page_ref", "detail": str(exc)})
```

### 3.3 CORS

Только в dev (когда daemon видит origin `http://localhost:5173`). В prod frontend serve'ится тем же origin'ом — CORS не нужен.

```python
# daemon/app.py
from fastapi.middleware.cors import CORSMiddleware

def create_app(vault_root, daemon=None) -> FastAPI:
    app = FastAPI(...)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    ...
```

Dev-only origins zhardcoded — простая защита от случайного prod misuse.

### 3.4 Static mount

```python
# daemon/app.py
from fastapi.staticfiles import StaticFiles

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

def create_app(vault_root, daemon=None) -> FastAPI:
    app = FastAPI(...)
    # ... routers ...
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    else:
        @app.get("/")
        def _no_frontend():
            return {"message": "frontend not built. run `pnpm build` in frontend/"}
    return app
```

`html=True` — fallback на `index.html` для client-side routing (react-router).

### 3.5 Frontend layout

```
┌─────────────────────────────────────────────────────────┐
│ TopBar:                                                 │
│ [🧠 mnemos]  [vault: /path/to/vault]  [🟢]  [UK ▾]    │
├──────────────┬──────────────────────────────────────────┤
│  Sidebar     │  Main content (route)                   │
│  📊 Overview │                                          │
│  📚 Pages    │                                          │
│  📜 Activity │                                          │
│  💾 Snapshots│                                          │
│  ─────────── │                                          │
│  About       │                                          │
└──────────────┴──────────────────────────────────────────┘
```

- TopBar: logo, vault path (read из `/vault/info`), health pill (🟢 ok / 🔴 down), locale switcher
- Sidebar: 4 active nav items + About + collapsible (Zustand state)
- Main: `<Outlet />` от react-router

### 3.6 Routing

```typescript
const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "/pages", element: <PagesBrowser /> },
      { path: "/pages/*", element: <PageDetail /> },  // wildcard для путей с /
      { path: "/activity", element: <ActivityCenter /> },
      { path: "/snapshots", element: <Snapshots /> },
      { path: "/about", element: <About /> },
    ],
  },
]);
```

### 3.7 Data fetching strategy

**TanStack Query** для всех backend reads:

| Hook | Endpoint | Refetch interval |
|---|---|---|
| `useStatus()` | `/vault/info` + `/health` | 10s |
| `usePages(filters)` | `/pages?...` | nothing (manual refetch on filter change) |
| `usePage(path)` | `/pages/{path}` | nothing |
| `useActivity(limit)` | `/activity?limit=...` | 5s |
| `useSnapshots()` | `/snapshots` | 10s |

**Mutations** (write endpoints):

| Hook | Action | Invalidates |
|---|---|---|
| `useUndo()` | `POST /activity/{id}/undo` | activity, status |
| `useCreateSnapshot(label?)` | `POST /snapshots` | snapshots, status |
| `useRestoreSnapshot(name)` | `POST /snapshots/{name}/restore` | snapshots, activity, status |
| `useDeleteSnapshot(name)` | `DELETE /snapshots/{name}` | snapshots, status |

Все мутации показывают confirmation dialog перед запуском (особенно destructive). Toast notifications для success/error.

### 3.8 Module map

**Backend (новое + правки):**

| Файл | Что |
|---|---|
| `claude_mnemos/core/page_reader.py` | NEW — shared helper |
| `claude_mnemos/daemon/routes/pages.py` | NEW — `/pages` + `/pages/{path}` |
| `claude_mnemos/daemon/app.py` | edit — CORS middleware + static mount + include pages router |
| `claude_mnemos/mcp/vault_access.py` | edit — re-export from core/page_reader |
| `claude_mnemos/mcp/read_tools/pages.py` | edit — re-export / use shared helper |
| `tests/test_page_reader.py` | NEW |
| `tests/daemon/test_app_pages.py` | NEW |

**Frontend (всё новое в `frontend/`):**

См. §2.1. Структура подробно расписана.

### 3.9 i18n

3 локали по spec'у: `uk` (primary) / `ru` / `en` (fallback).

В Plan #8 переводим **только то что используется** в наших 4 разделах: navigation, common (loading/save/cancel/delete), wiki types, status, flavor names, operations, errors. ~50-80 ключей в каждой локали.

Detect order: localStorage → navigator language → fallback `en`.

---

## 4. Pages REST contracts

### 4.1 `GET /pages`

Query params (все optional):
- `type`: `"entity" | "concept" | "source"`
- `flavor`: `"pattern" | "mistake" | "decision" | "lesson" | "reference"`
- `limit`: int 1-500 default 50
- `offset`: int >=0 default 0

Response:
```json
{
  "pages": [
    {
      "path": "wiki/entities/foo.md",
      "title": "Foo",
      "type": "entity",
      "flavor": ["pattern"],
      "modified": 1717000000.123
    }
  ],
  "total": 42
}
```

### 4.2 `GET /pages/{path:path}`

Path traversal-safe (через `resolve_page_path` helper).

Response:
```json
{
  "path": "wiki/entities/foo.md",
  "frontmatter": { "title": "Foo", "type": "entity", ... },
  "body": "# Foo\n\nBody markdown..."
}
```

404 если не найдена / path traversal попытка.

---

## 5. Frontend page contents

### 5.1 Overview

```
┌─ vault status ─────────────────────────────────────────┐
│ Wiki pages: 42      Snapshots: 3      Size: 1.2 MB    │
│ Activity: 17 entries                                  │
└────────────────────────────────────────────────────────┘

┌─ Scheduler ──────────┐ ┌─ Recent activity (5) ────────┐
│ ⏰ daily_snapshot     │ │ 2026-04-26 14:30 ingest_extr │
│    next run: 04:00   │ │ 2026-04-26 13:15 ingest_raw  │
│ ⏰ backups_cleanup    │ │ 2026-04-25 22:00 manual_rest │
│    next run: 05:00   │ │ ...                          │
└──────────────────────┘ └──────────────────────────────┘
```

Loads: `useStatus()` + `useActivity(limit=5)`.

### 5.2 Pages Browser

```
┌─ Filters ──────────────────────┐  ┌─ Pages (42) ───────────────┐
│ Type:                          │  │ □ Title       │ Type │ ... │
│  □ entity ☑ concept □ source  │  │ ─────────────────────────── │
│ Flavor:                        │  │ Foo Pattern   │ enti │ ... │
│  □ pattern ☑ lesson           │  │ Bar Decision  │ conc │ ... │
└────────────────────────────────┘  └────────────────────────────┘
```

Loads: `usePages(filters)`. Click on row → navigate `/pages/wiki/entities/foo.md`.

### 5.3 Page Detail

```
← Back to Pages

┌─ wiki/entities/foo.md ────────────────────────────────┐
│ Type: entity   Status: verified                       │
│ Flavor: pattern, lesson                               │
│ Created: 2026-04-26      Confidence: 0.85             │
├───────────────────────────────────────────────────────┤
│                                                       │
│  # Foo                                                │
│                                                       │
│  Body markdown rendered via react-markdown...         │
│                                                       │
└───────────────────────────────────────────────────────┘
```

Loads: `usePage(path)`. Read-only render.

### 5.4 Activity Center

```
┌─ Activity (17 entries) ──────────────────────────────────┐
│ Time              │ Type            │ Op ID    │ Actions │
│ ───────────────────────────────────────────────────────── │
│ 2026-04-26 14:30  │ ingest_extracted│ a8f2…    │ [Undo]  │
│ 2026-04-26 13:15  │ ingest_raw_only │ 3c91…    │ [Undo]  │
│ 2026-04-25 22:00  │ manual_restore  │ b7e1…    │ chain   │
└──────────────────────────────────────────────────────────┘
```

Loads: `useActivity(limit=50)`. [Undo] → ConfirmDialog → `useUndo()` mutation → toast.

### 5.5 Snapshots

```
┌─ Snapshots (3) ──────────────────────────[Create manual]─┐
│ Name                          │ Kind   │ Size  │ Actions │
│ ───────────────────────────────────────────────────────── │
│ daily-2026-04-26              │ daily  │ 1.2MB │ [R] [D] │
│ pre-op-…ingest_extracted-a8f2 │ pre-op │ 1.1MB │ [R] [D] │
│ manual-2026-04-25-22-00-prod  │ manual │ 1.0MB │ [R] [D] │
└──────────────────────────────────────────────────────────┘
```

`[R]` = Restore (ConfirmDialog → `useRestoreSnapshot(name)`)
`[D]` = Delete (ConfirmDialog с typed confirm для prod safety → `useDeleteSnapshot(name)`)
`[Create manual]` → modal с label input → `useCreateSnapshot(label)`.

---

## 6. Confirmation dialogs

| Action | Confirm tier |
|---|---|
| Undo operation | Tier 1 (simple yes/no) |
| Create manual snapshot | None (idempotent, harmless) |
| Restore snapshot | Tier 2 (type "restore" to confirm) |
| Delete snapshot | Tier 2 (type "delete" to confirm) |

Tier 1 = `<AlertDialog>` (shadcn) с buttons Confirm/Cancel.
Tier 2 = `<Dialog>` с input + button enabled только когда text matches.

Tier 3 (typed project name + cooldown — spec §12.4) **не делаем** — у нас нет project deletion и нет multi-vault. Когда появится, добавим.

---

## 7. Error handling

| Сценарий | UX |
|---|---|
| `useStatus` fetch fails | Red pill в TopBar `🔴 daemon unreachable` |
| `usePages`/`useActivity`/`useSnapshots` fail | EmptyState `Failed to load. Retry.` + retry button |
| `usePage` 404 | EmptyState `Page not found.` + back button |
| Mutation error (4xx/5xx) | Toast с error detail + ссылка на `mnemos activity` если undo failed |
| `restore_failed` 500 | Toast красный с `recovery_hint` из daemon response |
| Network offline | TanStack Query auto-retries. Pill `⚠ offline` |
| Build не сделан | `/` показывает JSON `{message: "frontend not built. run pnpm build"}` |

---

## 8. Concurrency / safety

- Frontend ничего не пишет в vault напрямую — все mutations идут через daemon REST (как и MCP write tools в Plan #6). Daemon серилизует через `pipeline_lock`.
- TanStack Query polling (5-10s) мягко загружает daemon — endpoints read-only, без `pipeline_lock`.
- Если две вкладки открыты одновременно — обе видят один daemon, polling скоординирован per-tab. Race conditions невозможны (server side single lock).

---

## 9. Testing strategy

### 9.1 Backend

1. **Unit `core/page_reader.py`:**
   - `list_pages` empty / 3 pages / type filter / flavor filter / pagination
   - `read_page` known/unknown/traversal — те же тесты что для MCP, переехали
   - `split_frontmatter` valid/invalid/no-frontmatter

2. **HTTP `/pages` endpoint:**
   - Empty vault → `{pages: [], total: 0}`
   - With pages → counts корректные
   - `?type=entity` filter
   - `?flavor=pattern` filter
   - `?limit=2&offset=0` slicing
   - `?type=invalid` → 422 (Pydantic validation)

3. **HTTP `/pages/{path}` endpoint:**
   - Known page → 200 + frontmatter + body
   - Non-existent → 404
   - Traversal → 404 (PageRefError → HTTPException)

4. **CORS middleware:**
   - OPTIONS preflight from `http://localhost:5173` → allowed
   - From other origin → not allowed

5. **Static mount:**
   - `/` if `frontend/dist/` exists → serves index.html
   - `/` if not → fallback JSON
   - SPA routing: `/pages` → fallback to index.html (html=True)

### 9.2 Frontend

Минимальное тестирование в Plan #8 — чтоб не потратить дни на test infrastructure setup:

- **Type checks:** `tsc --noEmit` запускается в CI
- **Build sanity:** `pnpm build` должен пройти без ошибок
- **Manual smoke:** ручной обход всех 4 разделов в браузере с реальным daemon

**Не делаем** в Plan #8: Vitest/Playwright/Storybook. Добавим в Plan #11+ когда frontend подрастёт.

### 9.3 Coverage targets

- 423 текущих pytest + ~25 новых (page_reader + pages endpoint + CORS + static).
- ruff + mypy strict на backend чисто.
- TypeScript strict mode на frontend — без any (или явно `as unknown as ...` где нужно).
- `pnpm build` чистый.

### 9.4 Manual smoke в Task последний

```bash
mnemos daemon start --vault /tmp/test-vault
cd frontend && pnpm install && pnpm build
# Открыть http://127.0.0.1:5757/
# Прокликать: Overview → Pages → click page → Activity → undo → confirm → Snapshots → create → restore → delete
```

---

## 10. Distribution / dev workflow

### 10.1 Dev

```bash
# Terminal 1
mnemos daemon start --vault $MNEMOS_VAULT_ROOT

# Terminal 2
cd frontend
pnpm install      # один раз
pnpm dev          # Vite на :5173 с прокси к :5757

# Open http://localhost:5173 — hot reload работает
```

### 10.2 Prod

```bash
cd frontend
pnpm install
pnpm build          # → frontend/dist/

mnemos daemon start --vault $MNEMOS_VAULT_ROOT
# Open http://127.0.0.1:5757
```

### 10.3 Wheel distribution

`pyproject.toml` `[tool.hatch.build.targets.wheel.force-include]` — добавить `frontend/dist/` если хотим включать в wheel. Решение: **НЕ включаем** в Plan #8. Frontend build = опциональный шаг для пользователя. Plan #11+ автоматизирует через post-install скрипт или CDN bundle.

`.gitignore`: `frontend/node_modules/`, `frontend/dist/`.

---

## 11. Known limitations

1. **4 раздела из 11.** Frontend выглядит "пустоватым" по сравнению со spec'ом. Каждый следующий план добавит свой раздел.
2. **Read-only Page Detail.** Edit отложен до Plan #11+ (нет PATCH endpoints).
3. **Polling, не WebSocket.** Real-time updates через TanStack Query polling (5-10s). Для dogfooding достаточно.
4. **Single-vault.** TopBar показывает один vault path, нет project switcher.
5. **CORS только для dev `:5173` origin.** Если пользователь откроет dashboard с другого origin'а — заблокируется. По дизайну (Plan #5 решение).
6. **i18n переводы минимальные** — только нужные для 4 разделов. Plan #11+ расширит.
7. **Нет dark mode.** Light theme only. Plan #11+.
8. **Frontend build руками.** `pnpm build` пользователь делает сам после установки. Plan #11+ автоматизирует.
9. **Нет confidence/provenance UI.** Если frontmatter содержит — рендерим как plain text, без интерактивных tooltip'ов.
10. **Нет page-level actions** (verify/archive/delete) — нет endpoints. Plan #11+.

---

## 12. What this enables (#9+ onwards)

- **Plan #9 (ontology):** добавится sidebar item `💡 Suggestions`, новая страница `Suggestions.tsx` использует `/suggestions/*` endpoints. Layout/i18n уже есть.
- **Plan #10 (watchdog):** изменения отслеживаются → human-edited badges в Pages Browser.
- **Plan #11 (lint, metrics, edit, multi-vault, hooks adaptive context):** добавится 5+ новых разделов. Project switcher в TopBar.
- **Plan #12 (auth + marketplace + auto-install):** `pnpm build` уйдёт в post-install script + bundle в pip wheel.

---

## 13. Решения, принятые сам (для протокола)

| Решение | Альтернатива | Почему |
|---|---|---|
| **4 раздела (Overview/Pages/Activity/Snapshots), не 11 spec'овских** | Все 11 сразу | 7 разделов требуют backend которого нет. Делать каркас под фичи которых нет — преждевременно. Plans #9-#11+ добавят остальное аддитивно. |
| **Page Detail read-only** | + Markdown editor (Monaco) | Нет PATCH endpoint в daemon. Edit = отдельный кусок (Plan #11+). |
| **TanStack Query polling 5-10s, не WebSocket** | SSE/WS | Polling простой, без addit. infrastructure. Real-time критичен только для multi-user (что не наш случай). |
| **CORS только для `:5173` origin** | `allow_origins=["*"]` | Безопасность. Если пользователь откроет с другого origin — блок. Dev origin узкий и хардкодед. |
| **Static mount fallback на JSON если нет dist/** | Hard-fail при старте daemon | Daemon должен работать и без frontend (для CLI/MCP юзеров). |
| **Tier 2 (typed) confirm только для restore/delete snapshot** | Все actions с typed confirm | UX trade-off. Undo достаточно simple confirm — он сам идемпотентен через restore_from_snapshot. |
| **3 локали uk/ru/en по spec** | Только en | Spec прямо требует UK primary. Ярик в Украине. Минимальные ключи в каждой ~50-80. |
| **react-router 6, не 7** | 7 (latest) | 6 stable. 7 вышла недавно. shadcn templates под 6. |
| **Tailwind 3.4, не 4.0** | 4.0 (alpha/beta) | 3.4 stable. shadcn оптимизирован под 3.4. 4.0 переезд — Plan #11+. |
| **pnpm, не npm/yarn** | npm | pnpm быстрее. Lockfile меньше. Стандарт для shadcn ecosystem. |
| **Vite proxy в dev для всех endpoints** | Frontend знает absolute URL `http://127.0.0.1:5757` | Прозрачный dev/prod parity. Frontend всегда дёргает relative `/health` etc. |
| **Endpoints без `/api/` префикса** | `/api/v1/*` | Consistent с Plan #5/#6 решением. Multi-vault routing через path appendage если понадобится. |
| **`core/page_reader.py` — общий helper для MCP+daemon** | Дублировать код | DRY. MCP уже имеет `mcp/read_tools/pages.py` — рефакторим в re-export, чтобы не разойтись. |
| **`react-markdown` для Page Detail render** | dangerouslySetInnerHTML + sanitizer | XSS-safe из коробки. remark-gfm для таблиц/чек-боксов. |
| **Frontend build руками, не в pip wheel** | Bundle в wheel | Wheel размер не блокер; авто-build = Plan #12 distribution work. Сейчас dogfooding — `pnpm build` делается раз. |
| **Tests на frontend минимум** (только tsc + build) | Vitest + Playwright | Test infrastructure for frontend = 2-3 дня. Plan #8 фокус на работающем UI. Vitest добавим в Plan #11+ когда есть что тестировать. |
| **Без dark mode toggle** | shadcn theming setup | YAGNI для dogfooding. Plan #11+. |
| **Без onboarding wizard** | spec §13 | YAGNI для single-user dogfooding. |

---

## 14. Open questions для имплементации (не блокеры)

- **Vite proxy паттерн:** один proxy entry для каждого endpoint или один общий `^/(health|version|vault|activity|snapshots|pages)`? Решу при коде.
- **`/pages/{path:path}` URL encoding** — `wiki/entities/foo.md` в URL. Браузер encode'ит `/`. Vite proxy и FastAPI должны корректно декодировать. Проверю при коде.
- **`react-markdown` sanitization** — добавлять `rehype-sanitize`? Контент vault — наш, не пользовательский input в SaaS-смысле. Trust + минимум sanitization (no scripts).
- **shadcn auto-install в Vite project** — `npx shadcn@latest add button card table dialog ...`. Решу: прединсталлю минимум при setup'е, добавлю по необходимости.
- **TypeScript path aliases** — `@/components/...` через tsconfig + vite-tsconfig-paths plugin. Стандарт для shadcn.
- **i18n key naming convention** — namespace.section.key, например `nav.pages`, `actions.undo`. Опишу в общем JSON.
- **Default page size** — limit=50 кажется ок для wiki <500 страниц. Виртуализация (react-window) — Plan #11+.
- **Sticky TopBar / Sidebar** — да (Tailwind sticky). Mobile responsiveness — минимум (Plan #8 desktop-first; Plan #11+ адаптация).

---

## 15. Why this scope

Через эту дверь:

1. **Впервые видим vault в браузере.** До Plan #8 mnemos = CLI/REST/MCP. Plan #8 даёт визуальный интерфейс — Activity log как таблица, snapshots с кнопками, Pages Browser с фильтрами, page reader с markdown render.
2. **Полный stack по spec'у заложен.** React + TS + shadcn + Tailwind + i18next + TanStack Query + Zustand + Zod — всё реальное, готово масштабироваться. Plans #9-#11+ просто добавляют разделы и features в готовый каркас.
3. **Backend extensions узкие** — только `/pages` endpoints + CORS + static mount. Не лезем в lint/ontology/jobs/dead-letter.
4. **Распространение остаётся manual** — `pnpm build` руками. Auto-install в pip wheel = Plan #12.
5. **Cycle time:** ~10-12 дней. Самый длинный план до сих пор. Если узким местом окажется shadcn setup — могу разбить в Plan #8a (backend + setup + Overview) и Plan #8b (Pages + Activity + Snapshots).
