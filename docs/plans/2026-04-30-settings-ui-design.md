# Settings UI — Design (Plan B)

**Date:** 2026-04-30
**Status:** Approved by Yarik (autonomous brainstorm)
**Goal:** Реализовать страницу Settings (сейчас placeholder с «#14c»). Editing existing проектов: rename (display_name), CWD patterns, 8 settings groups + locale + ingest overrides, delete project. Plus отдельная Global Settings page. Plan A (Onboarding polish, display_name + DirectoryPicker + CwdBuilder) — предшественник, переиспользуем `<CwdBuilder>` и `<DirectoryPicker>`.

---

## 1. Why

После Plan A создание проекта работает хорошо, но **редактирование existing проектов** возможно только через CLI (`mnemos project update`, `mnemos settings set/get`). Settings UI page — placeholder. Это последний значимый pain point из «недоделок» которые Yarik нашёл при клацании дашборда. Plan B закрывает.

## 2. Scope

### Включено

- **Project Settings page** (`/project/<slug>/settings`) — accordion с 12 секциями:
  - **General** — display_name (rename), slug (read-only, copyable), vault_root (read-only, copyable), CWD patterns через `<CwdBuilder>`
  - **Locale** — uk/ru/en/null (null = inherit from global)
  - **Auto-ingest** — enabled (bool), mode (auto/hybrid/manual)
  - **Lint** — schedule (cron string | null), enabled_rules (list of rule names | null), autofix_on_save (bool)
  - **Ontology** — auto_mode (bool), confidence_min (0..1), confidence_auto_apply (0..1)
  - **Watchdog** — mode (strict/merge/open)
  - **Snapshots** — daily_enabled (bool), retention_days (int >= 1)
  - **Lifecycle** — auto_stale_days (int >= 1), auto_archive (bool)
  - **Prompts** — custom_system_path (string | null), custom_extract_user_path (string | null)
  - **Telemetry** — opt_in (bool)
  - **Ingest overrides** — model, language_hint, max_input_tokens, context_limit (each null | value)
  - **Danger zone** — Delete project (typed-confirm modal)
- **Global Settings page** (`/settings/global`) — accordion: locale, daemon_port, default_model, default_language_hint, default_max_input_tokens, default_retention_days
- Save button per section (explicit save)
- Backend validation propagated as inline errors (Pydantic 422 → field-level)
- Reuse `<CwdBuilder>` and `<DirectoryPicker>` from Plan A
- Reuse `<TypedConfirmDialog>` pattern from Plan #14c (mutations)

### Не включено (out of MVP)

- Slug rename (immutable per Q1 decision)
- Vault path rename (immutable — создаёшь новый проект, переносишь данные руками)
- Vault folder delete via UI (только project entry удаляется; markdown'ы остаются)
- Settings export/import / config-as-code
- Bulk edit across multiple projects
- Custom prompt path file picker (юзер вводит вручную; UI hint для shape)
- Per-section permissions / RBAC

## 3. Architecture

```
/project/<slug>/settings (Project Settings page)
   ├── General Section          ← display_name, slug, vault, CWD (CwdBuilder)
   ├── Locale Section
   ├── Auto-ingest Section
   ├── Lint Section
   ├── Ontology Section
   ├── Watchdog Section
   ├── Snapshots Section
   ├── Lifecycle Section
   ├── Prompts Section
   ├── Telemetry Section
   ├── Ingest Overrides Section
   └── Danger Zone Section      ← Delete project

/settings/global (Global Settings page)
   ├── General Section          ← locale, daemon_port
   └── Defaults Section         ← default_model, default_language_hint, default_max_input_tokens, default_retention_days
```

### API mapping

| Section | Endpoint(s) | Notes |
|---|---|---|
| General → display_name | PATCH `/projects/{slug}` body `{display_name}` | empty string clears (Plan A pre-merge fix) |
| General → CWD patterns | PATCH `/projects/{slug}` body `{cwd_patterns: [...]}` | full replace via array |
| Locale … Telemetry, Ingest overrides | PATCH `/settings/{slug}` body `{<section_name>: {...}}` | Pydantic deep_merge на backend |
| Global all sections | PATCH `/settings/global` body | same merge pattern |
| Delete project | DELETE `/projects/{slug}` | new endpoint; unmount + remove |

## 4. Components

### New frontend files

```
frontend/src/pages/
├── ProjectSettings.tsx              # main page composing sections, fetches /projects/{slug} + /settings/{slug}
└── GlobalSettings.tsx                # отдельная страница, fetches /settings/global

frontend/src/components/settings/
├── SettingsAccordion.tsx             # reusable collapsible wrapper, takes title + saving state
├── sections/
│   ├── GeneralSection.tsx
│   ├── LocaleSection.tsx
│   ├── AutoIngestSection.tsx
│   ├── LintSection.tsx
│   ├── OntologySection.tsx
│   ├── WatchdogSection.tsx
│   ├── SnapshotsSection.tsx
│   ├── LifecycleSection.tsx
│   ├── PromptsSection.tsx
│   ├── TelemetrySection.tsx
│   ├── IngestOverridesSection.tsx
│   └── DangerZoneSection.tsx
└── globals/
    ├── GlobalGeneralSection.tsx
    └── GlobalDefaultsSection.tsx

frontend/src/api/settings.api.ts      # GET/PATCH /settings/{slug} + global
frontend/src/types/Settings.ts         # zod schemas mirroring Pydantic
frontend/src/hooks/
├── useProjectSettings.ts              # query + mutate hooks
└── useGlobalSettings.ts
```

### Modified

```
frontend/src/pages/ProjectView.tsx      # remove Settings placeholder, route to ProjectSettings
frontend/src/components/layout/Sidebar.tsx  # +Global settings link in footer
frontend/src/App.tsx (or router config) # add /settings/global route
frontend/public/locales/{en,ru,uk}.json # ~80 new keys (12 sections × ~7 fields × 3 langs)

claude_mnemos/daemon/routes/projects.py  # +DELETE endpoint
claude_mnemos/state/projects.py          # ProjectStore.remove already exists; verify
claude_mnemos/state/settings.py          # SettingsStore.delete_project helper if missing
tests/daemon/test_routes_projects.py     # +DELETE tests
tests/state/test_settings*.py            # +delete_project tests if added helper
```

### Untouched (zero-diff)

```
claude_mnemos/ingest/
claude_mnemos/state/manifest.py
claude_mnemos/core/metrics.py
claude_mnemos/hooks/
claude_mnemos/state/jobs.py
claude_mnemos/daemon/jobs/
claude_mnemos/state/settings.py (Pydantic schemas — final, used as-is)
```

## 5. Detailed behavior

### Settings save model

Each section имеет:
- Form fields с локальным state
- «Save» button disabled пока local state == server data
- При жатии Save → PATCH соответствующего endpoint'а с **только** этой секцией
- Backend применяет deep_merge → новое полное состояние → возвращает
- Frontend обновляет TanStack Query cache; кнопка Save снова disabled

Это per-section save, не auto-save.

### General section (special)

`display_name` и `cwd_patterns` живут в `project-map.json` (Project entry), не в `settings/<slug>.json`. Поэтому General section вызывает **PATCH /projects/{slug}**, а остальные — **PATCH /settings/{slug}**.

`slug` и `vault_root` — read-only text fields с кнопкой «Copy» (clipboard.writeText).

### Locale / inherit-from-global pattern

Project locale = `null | "uk" | "ru" | "en"`. UI:
```
Locale:
   ( ) Inherit from global  (currently: uk)
   ( ) uk
   ( ) ru
   ( ) en
```
Radio buttons. «Inherit» означает `null` в payload. Backend resolves to global при render.

То же для ingest overrides:
```
Override default model:
   [☐] Override   model: [_____________]   (default: claude-sonnet-4-6)
```
Чекбокс controls whether field renders + sends value or sends null.

### Validation strategy

- Frontend: basic UI hints — `type=number` для numeric, range `min`/`max` для bounded floats, `<select>` для enums
- Backend: Pydantic strict validation
- 422 response → parse errors → display inline под полем (e.g., `confidence_min: must be between 0 and 1`)

Не зеркалим Pydantic schema целиком — frontend zod schemas только для парсинга responses, не для validation user input. Это снижает coupling.

### Delete project flow

```
[Danger zone] section внизу:
   Permanent actions
   [Delete project]   ← красная кнопка
        ↓ click
   Modal:
   ┌────────────────────────────────────────┐
   │  Delete project «My Project»?          │
   │                                        │
   │  This unmounts the project and removes │
   │  it from the registry. The vault       │
   │  folder at <path> will NOT be deleted; │
   │  re-add it later with the same slug    │
   │  and vault path to restore.            │
   │                                        │
   │  Type «my-project» to confirm:         │
   │  [_________________]                   │
   │                                        │
   │  [ Cancel ]   [ Delete project ]       │
   └────────────────────────────────────────┘
```

При confirm → DELETE `/projects/{slug}` → 200 → navigate to `/` (home).

### Backend DELETE /projects/{slug}

Сейчас в `routes/projects.py` есть GET/POST/PATCH. Нужен **DELETE**:

```python
@router.delete("/projects/{slug}")
async def delete_project(slug: str, force: bool = False, daemon: ...):
    # 1. Check project exists → 404
    # 2. Check no running jobs (unless force=True) → 409 with detail
    # 3. await daemon.unmount_project(slug)  # stops watchdog, drains jobs
    # 4. ProjectStore.remove(slug)
    # 5. SettingsStore.delete_project(slug) — removes ~/.claude-mnemos/settings/<slug>.json
    # 6. Return 204 No Content
```

Force flag: query param `?force=true` — для override 409. UI default = no force; если 409 — show warning «N jobs running, retry once they finish».

### Sidebar / routing

- Project Settings: уже в sidebar (Plan A не трогал — был placeholder). Заменяем placeholder на real page in router config.
- Global Settings: новая ссылка в Sidebar footer (например, после Help). Иконка ⚙ или 🌐.

### i18n

Locale keys structure:
```
"settings.title": "Settings",
"settings.save": "Save",
"settings.saving": "Saving...",
"settings.saved": "Saved",
"settings.error": "Error: {{msg}}",

"settings.section.general.title": "General",
"settings.section.general.display_name": "Display name",
"settings.section.general.slug": "Slug",
"settings.section.general.slug_hint": "Read-only — fixed at creation",
"settings.section.general.vault": "Vault path",
"settings.section.general.vault_hint": "Read-only — to move, create new project",
"settings.section.general.cwd": "Project folders (auto-routing)",
"settings.section.general.copy": "Copy",

"settings.section.auto_ingest.title": "Auto-ingest",
... (and so on for each section)

"settings.danger.title": "Danger zone",
"settings.danger.delete_button": "Delete project",
"settings.danger.delete_modal_title": "Delete project «{{name}}»?",
"settings.danger.delete_modal_body": "...",
"settings.danger.confirm_label": "Type «{{slug}}» to confirm:",
"settings.danger.cancel": "Cancel",
"settings.danger.confirm": "Delete project",

"settings.global.title": "Global settings",
"settings.global.daemon_port": "Daemon port",
... (etc)
```

~80 keys × 3 languages = 240 strings. Repetitive but not creative.

## 6. Tests

### Unit (backend)

- DELETE /projects/{slug}: happy path → 204, 404 missing, 409 with running jobs, 200 with `?force=true`
- ProjectStore.remove already covered by existing tests; add settings-cleanup assertion
- SettingsStore.delete_project helper если добавляем — unit tests

### Unit (frontend) — most repetitive

For each section component:
- Render → fields show server values
- Change field → Save button enables
- Save click → API call assertion
- 422 response → inline error displayed
- 200 response → Save disables, success indicator

Pages:
- ProjectSettings: fetches both `/projects/{slug}` + `/settings/{slug}`, renders accordion
- GlobalSettings: fetches `/settings/global`
- DangerZone: typed-confirm validation (wrong slug → Delete disabled; correct → enabled), DELETE call, navigate on success

## 7. Risks / edge cases

| Риск | Mitigation |
|---|---|
| User changes 5 sections at once → 5 separate PATCHes | Per-section save isolates concerns; UI shows pending Save buttons clearly |
| Concurrent edits (two tabs) | Last-write-wins; Pydantic не block. OK для solo-user app. |
| Locale changes — i18next реагирует? | Use `i18n.changeLanguage()` after PATCH; if not — page reload. |
| `prompts.custom_system_path` указывает на несуществующий файл | Backend Pydantic accepts (string only), ingest fails later with clear error. UI hint: «file path; validated when used» |
| Delete project while jobs running | DELETE 409, UI shows «N jobs in flight — wait or use ?force=true» |
| Slug shown as readonly но пустой буфер при copy | clipboard.writeText with toast «Copied» |
| Long form tall — collapse/expand | Accordion sections collapsed by default; click to open. |
| Validation errors from PATCH 422 в TanStack Query | onError parses Axios error.response.data.detail (Pydantic shape) → display inline |
| User deletes project then immediately re-adds with same slug | Works — vault data still there, settings file recreated default. |

## 8. Phase rollout

Each phase ends with green test suite + zero-diff guarantee.

| Phase | Scope | Tests |
|---|---|---|
| 1 | Backend: DELETE /projects/{slug} + force flag + SettingsStore.delete_project helper if missing | +backend ~5 |
| 2 | Frontend: api/settings.api.ts + types/Settings.ts (zod) + useProjectSettings + useGlobalSettings hooks | +frontend ~6 |
| 3 | SettingsAccordion wrapper + General + Locale + Auto-ingest + Lint + Ontology sections (5 sections) | +section tests ~15 |
| 4 | Watchdog + Snapshots + Lifecycle + Prompts + Telemetry + IngestOverrides + DangerZone (7 sections) | +section tests ~20 |
| 5 | ProjectSettings page composition + GlobalSettings page + sidebar wiring + locale keys | +page tests ~5 |
| 6 | Final verification, manual checklist, memory update, merge | manual |

## 9. Размер

~16 новых файлов frontend (~1500 LOC + tests), 1 backend endpoint addition (~80 LOC + tests). **6-8 рабочих дней** (Phase 3 + 4 — самые объёмные но repetitive).

## 10. Success criteria

1. ProjectSettings page открывается, все 12 секций аккордеона работают (load → edit → save → reload shows persisted)
2. Можно переименовать display_name через General section, sidebar обновляется (через TanStack Query invalidation)
3. CWD patterns можно менять через CwdBuilder (reuse Plan A)
4. Delete project с typed-confirm удаляет из registry, vault folder остаётся на диске
5. GlobalSettings page работает, locale change применяется (page reload acceptable для MVP)
6. Validation errors (Pydantic 422) показываются inline под соответствующим полем
7. All existing tests passing (1490 backend / 238 frontend); новые tests все зелёные
8. ruff/tsc/ESLint clean
9. Zero diff в untouchable: `extraction.py`, `parser.py`, `metrics.py`, `hooks/`, `jobs/`, `manifest.py`, `state/settings.py` (Pydantic schemas — frozen)

## 11. Future work

- Slug rename via migration tool (CLI: `mnemos project rename old new --migrate`)
- Vault path rename + move data
- Settings export/import as YAML
- Bulk edit (apply same setting to multiple projects)
- File picker для prompts.custom_*_path (reuse DirectoryPicker, but for files not folders — needs `/fs/browse` extension)
