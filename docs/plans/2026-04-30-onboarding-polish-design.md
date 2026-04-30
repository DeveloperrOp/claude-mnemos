# Onboarding Polish — Design (Plan A)

**Date:** 2026-04-30
**Status:** Approved by Yarik (autonomous brainstorm)
**Goal:** Закрыть 3 из 4 UX pain points project management при создании проекта: display_name (русские имена), file picker для vault path, CWD mini-builder. Plan B (Settings UI) — отдельный план.

---

## 1. Why

После создания первого проекта `test-cli` через Onboarding wizard вылезли pain points:
- Имя проекта принимает только slug-формат (`a-z0-9_-`) — русские/UTF-8 имена не работают.
- Vault path надо вписывать руками — нет file picker'а (browser sandbox не даёт нативный диалог).
- CWD patterns — textarea с glob syntax, юзер должен знать `\*` чтобы paticipate auto-routing.
- Settings UI page — placeholder («З'явиться в плані #14c»).

Plan A закрывает первые три. Settings UI — Plan B.

## 2. Scope

### Включено

- **Backend:**
  - `display_name: str | None` field в `ProjectMapEntry` (nullable, no migration)
  - `/fs/browse?path=<absolute>` endpoint — list subdirectories
  - `/fs/mkdir {"path": ...}` endpoint — create new folder
  - `/fs/home` endpoint — return user home as default starting point
- **Frontend:**
  - `<DirectoryPicker>` reusable modal (browse, breadcrumbs, path input, filter, recent, new folder)
  - `slugify()` lib (display_name → slug auto-derivation, через `@sindresorhus/slugify`)
  - CWD mini-builder с list+add patterns через picker
  - Onboarding wizard form: display_name + slug (linked) + vault path + Browse + CWD builder
  - Везде в UI fallback `display_name ?? name`

### Не включено (Plan B)

- Settings UI page (rename, change CWD existing projects, settings groups editing)
- File picker за пределами Onboarding (можно переиспользовать в Plan B)
- Auto-suggest CWD из vault path (heuristic — слишком рискованный)
- Migration существующих проектов (display_name остаётся None — UI показывает name как fallback)

## 3. Architecture

### Backend additions

```
GET /fs/browse?path=<absolute_path>
  → 200 {
      "cwd": "D:\\code",
      "parent": "D:\\",
      "entries": [
        {"name": "claude-mnemos", "path": "D:\\code\\claude-mnemos"},
        ...
      ],
      "truncated": false
    }
  → 400 path not absolute / not exists / not directory
  → 403 no read permission

POST /fs/mkdir
  body: {"path": "<absolute_path>"}
  → 200 {"path": "<created_path>"}
  → 400 path exists / parent missing / invalid
  → 403 no write permission

GET /fs/home
  → 200 {"home": "C:\\Users\\68664"}
  (cross-platform: os.path.expanduser("~"))
```

`ProjectMapEntry` schema:
```python
class ProjectMapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=PROJECT_NAME_PATTERN)  # slug, unchanged
    display_name: str | None = None                   # NEW — UTF-8, optional
    vault_root: Path
    cwd_patterns: list[str] = Field(default_factory=list)
```

`extra="forbid"` НЕ ломает existing files — отсутствующее поле не есть extra; Pydantic применит default `None`.

### Frontend modules

```
frontend/src/components/picker/
├── DirectoryPicker.tsx          # main modal — props { open, onSelect(path), onClose, initialPath?, allowCreate? }
├── DirectoryList.tsx             # listing folder rows
├── Breadcrumbs.tsx               # D:\ > Обсидиан > OBSIDIAN
├── PathInput.tsx                 # type/paste path, Enter→validate→navigate
├── RecentList.tsx                # last 5 paths from localStorage
├── FilterInput.tsx               # name filter (case-insensitive substring)
└── NewFolderDialog.tsx           # input + Create button

frontend/src/components/onboarding/
└── CwdBuilder.tsx                # list + add via picker; recursive checkbox

frontend/src/api/fs.api.ts        # browse / mkdir / home (zod)
frontend/src/types/Fs.ts          # zod schemas

frontend/src/hooks/useDirectoryPicker.ts
frontend/src/hooks/useRecentPaths.ts

frontend/src/lib/slugify.ts       # display_name → slug

frontend/src/pages/Onboarding.tsx # rewritten to use new components
```

## 4. Behavior

### Slug auto-derivation

`@sindresorhus/slugify` (npm) — has decent Cyrillic→Latin transliteration.

```typescript
import slugify from "@sindresorhus/slugify";

export function deriveSlug(display: string): string {
  const slug = slugify(display, {
    lowercase: true,
    separator: "-",
    decamelize: false,
  });
  // PROJECT_NAME_PATTERN: ^[a-z0-9][a-z0-9_-]{0,63}$
  // Truncate to 64; if doesn't start with [a-z0-9] (extreme case), prepend "p-"
  let s = slug.slice(0, 64);
  if (s && !/^[a-z0-9]/.test(s)) s = "p-" + s;
  return s;
}
```

Form behavior:
- User types in **Display name** → **Slug** auto-updates live
- User clicks **«Edit slug»** → slug field unlocks, auto-derivation pauses
- User clears slug → auto-derivation resumes from current display_name
- Submit validates slug against `PROJECT_NAME_PATTERN`; if invalid (rare with library) → form error

### DirectoryPicker modal

- Triggered by **«📁 Browse»** button rendered next to vault path / CWD inputs
- Opens at `initialPath` (if provided + exists) or `/fs/home` response
- Layout (single modal):
  ```
  ┌─────────────────────────────────────────────────┐
  │  Choose folder                              [×] │
  │ ─────────────────────────────────────────────── │
  │  [path input: D:\code\claude-mnemos      ]      │
  │  D: > code > claude-mnemos                      │
  │  [filter: search this folder...           ]     │
  │ ─────────────────────────────────────────────── │
  │  Recent:                                        │
  │  ▸ D:\Obsidian\test                             │
  │  ▸ D:\code\test-2                               │
  │ ─────────────────────────────────────────────── │
  │  📁 docs                                        │
  │  📁 frontend                                    │
  │  📁 tests                                       │
  │  ...                                            │
  │ ─────────────────────────────────────────────── │
  │  [+ New folder]   [Cancel]   [Select this folder]│
  └─────────────────────────────────────────────────┘
  ```
- Click folder row → navigate inside (path input + breadcrumbs update, list refetches)
- Click breadcrumb segment → navigate to that ancestor
- PathInput: type/paste full path → Enter → if valid directory, navigate; else show inline error
- Filter: instant client-side filter on current listing
- Recent shows up to 5 paths from `localStorage["mnemos_recent_paths"]`; clicking navigates there
- New folder: dialog → input → POST /fs/mkdir → navigate inside on success
- Select this folder: `onSelect(currentPath)`, close modal, push currentPath to Recent (deduped, capped at 5)

### CWD mini-builder

- List of currently added patterns:
  ```
  📁 D:\code\claude-mnemos      [✓ recursive]   [×]
  📁 D:\code\test               [☐ recursive]   [×]
  ```
- recursive checkbox toggles `\*` suffix in stored pattern (and rendering)
- × removes the pattern
- **[+ Add folder]** button opens DirectoryPicker → on select adds pattern with `recursive=true` default
- Empty state: «Не добавлено — без авто-привязки сессии надо ингестить вручную»

### Display_name fallback in UI

Везде где сейчас отображается project name — sidebar list, breadcrumbs, page headers, project switcher dropdown — заменить:
```typescript
const displayName = project.display_name ?? project.name;
```

Сделаем helper `getProjectDisplayName(project)` чтобы не разбрасывать `??` по 10+ компонентам.

## 5. API specifics

### `/fs/browse`

- `path` query param (required, string, absolute)
- Validate: `Path(path).is_absolute() and Path(path).is_dir()`
- List `iterdir()`, filter `is_dir()`
- Sort case-insensitive
- Cap at 100 entries; if more — set `truncated=true`, take first 100
- Return shape:
  ```json
  {
    "cwd": "<resolved absolute>",
    "parent": "<parent or null if drive root>",
    "entries": [{"name": ..., "path": ...}],
    "truncated": false
  }
  ```
- Errors:
  - 400 `{"detail": "path must be absolute"}` / `"path does not exist"` / `"path is not a directory"`
  - 403 `{"detail": "permission denied: <path>"}`

### `/fs/mkdir`

- Body: `{"path": "<absolute>"}`
- Validate: parent exists, target doesn't exist, no path-traversal (`..` segments after resolve)
- `Path(path).mkdir(parents=False, exist_ok=False)`
- Return: `{"path": "<resolved>"}`
- Errors:
  - 400 path exists / parent missing / invalid
  - 403 permission denied

### `/fs/home`

- `os.path.expanduser("~")` → resolve → return
- On Windows multi-drive systems, `home` is single user dir; for browsing other drives, юзер набирает в PathInput.

### Security note

Daemon binds 127.0.0.1 by default — никакой external network. Endpoints без auth. На localhost юзер уже control'ирует свой компьютер; читать/создавать папки — не повышение privileges. Path traversal не proteckt'им specially (юзер может всё), но валидируем normalized abs paths чтоб не падать на trash input.

## 6. Tests

### Unit (backend)

- `tests/state/test_projects_display_name.py`:
  - `ProjectMapEntry(name="x", vault_root=P)` ⇒ `display_name=None`
  - Load from JSON without `display_name` key ⇒ `display_name=None`
  - Load from JSON with `display_name="Foo"` ⇒ `display_name="Foo"`
  - Existing tests in `tests/test_projects.py` continue passing
- `tests/daemon/routes/test_fs.py`:
  - GET /fs/browse — happy path (lists subdirs), missing path → 400, file path → 400, non-absolute → 400
  - GET /fs/browse with truncation (100+ subdirs)
  - POST /fs/mkdir — happy path, conflict 400, parent missing 400
  - GET /fs/home — returns absolute path
- `tests/test_cli_project.py` — extend with `--display-name` flag for `mnemos project add`

### Unit (frontend)

- `tests/lib/slugify.test.ts` — пары display→slug:
  - `"Конструктор сайтов"` → `"konstruktor-saytov"` (or similar — pin actual library output)
  - `"My Project!"` → `"my-project"`
  - `"123-test"` → `"123-test"`
  - `""` → `""`
  - 100-char input → ≤64 char output
- `tests/components/DirectoryPicker.test.tsx`:
  - Opens, fetches initial path, lists folders
  - Click folder navigates, breadcrumbs update
  - PathInput Enter triggers navigation
  - Filter narrows visible folders
  - Recent shows entries from localStorage
  - New folder opens dialog → POST /fs/mkdir → navigates
  - Select this folder calls onSelect with current path
  - Cancel calls onClose
- `tests/components/CwdBuilder.test.tsx`:
  - Add via picker
  - Toggle recursive (pattern updates)
  - Remove pattern
- `tests/pages/Onboarding.test.tsx` extends:
  - Display name → slug auto-derivation
  - Edit slug button unlocks
  - Browse button opens picker, select fills vault path
  - CWD builder integration
  - Submit sends display_name + slug + vault + cwd_patterns to /projects

### Integration / manual

- Yarik creates project «Конструктор сайтов» via wizard → sees slug «konstruktor-sajtov» (or similar) → Browse vault → CWD via mini-builder → Submit → sidebar shows «Конструктор сайтов» (display_name).

## 7. Phase rollout

| Phase | Scope | Tests | Behavior change |
|---|---|---|---|
| 1 | Backend: `display_name` field + `/fs/{browse,mkdir,home}` + tests | +backend | None for existing users |
| 2 | Frontend: slugify lib + Onboarding two-field UI (display_name + slug) | +frontend | Onboarding form layout changes |
| 3 | Frontend: `<DirectoryPicker>` modal component + tests | +frontend | New reusable component |
| 4 | Frontend: CWD mini-builder + Onboarding integration (Browse buttons wired) | +frontend | Onboarding form completed |
| 5 | Final: full test run, manual checklist, memory update, merge | manual | — |

Each phase ends with green test suite. Behavior in production not affected until Phase 4 user-facing changes ship together.

## 8. Risks / edge cases

| Риск | Mitigation |
|---|---|
| `@sindresorhus/slugify` транслитерация плохо ложится на длинные русские | Snapshot tests на Yarik's типичных кейсах; fallback на manual edit slug |
| Slug collision (юзер ввёл уже занятое имя) | Backend POST /projects → 409 → toast «Slug already taken» |
| `/fs/browse` slow на сетевых дисках | 5s axios timeout client-side, spinner + cancel |
| Юзер в picker'е заходит в защищённую папку (Win System32) | 403 from backend, frontend shows inline error «Permission denied» |
| Recent в localStorage stale (папка удалена) | Lazy validate via /fs/browse; show stale entries grayed |
| `display_name = ""` (пустая строка) vs `None` | Frontend trims; if result empty → store None; backend allows both (None or non-empty) |
| Юзер создал проект через CLI без display_name | UI показывает slug — это OK fallback. После Plan B можно отредактировать. |

## 9. Backwards compatibility

- Existing project-map.json: `display_name` отсутствует → loads as None. Pydantic OK.
- Existing CLI commands: `mnemos project add` принимает новый optional флаг `--display-name`; без него — None.
- Existing 4 проекта (test-cli + 3 phantom): UI показывает их через `name` (fallback). Plan B даёт переименование.
- Existing tests in tests/state/test_projects.py / test_cli_project.py: no breaking changes — new field optional.

## 10. Размер

~12 новых файлов frontend (picker pieces + slugify + CwdBuilder + hooks + types/api), 2-3 файла backend (fs router, schemas, registration), ~600-800 LOC + tests. **5-7 рабочих дней** разбито на 5 фаз.

## 11. Success criteria

1. Юзер создаёт проект «Конструктор сайтов» через Onboarding — slug auto-derives, проект появляется в sidebar с display_name.
2. Vault path выбирается через picker (без вписывания руками или копи-пейста).
3. CWD patterns добавляются через mini-builder с file picker (без знания glob syntax).
4. Existing 4 проекта продолжают работать без миграции (display_name = None, UI fallback на slug).
5. Все pre-existing tests passing (1465 backend / 196 frontend); новые tests все зелёные.
6. ruff/tsc/ESLint clean (только pre-existing button.tsx warning).

## 12. Future work (Plan B + beyond)

- Settings UI page (rename existing projects, edit CWD, edit 8 settings groups)
- DirectoryPicker reuse в Settings UI
- File picker «New folder» → optional checkbox «open in Obsidian after»
- Auto-suggest CWD pattern from vault parent (smart heuristic)
- Drag&drop folder из проводника в Onboarding form
