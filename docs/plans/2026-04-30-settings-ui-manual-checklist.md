# Settings UI — Manual E2E Checklist

Run by hand on Yarik's Win11 after merge.

## Prerequisites
- [ ] daemon restarted with new code (`mnemos daemon stop && mnemos daemon start`)
- [ ] dashboard reloaded (Ctrl+F5 to clear bundle cache)
- [ ] frontend bundle rebuilt (`pnpm build` from frontend/)

## Project Settings (`/project/<slug>/settings`)

### General section
- [ ] Display name editable; Save persists; sidebar updates with new name
- [ ] Slug shown read-only with Copy button (clipboard test)
- [ ] Vault path shown read-only with Copy button
- [ ] CWD patterns: «Add folder» opens DirectoryPicker, recursive checkbox toggles `\*` suffix
- [ ] Save with empty display_name clears it (sidebar reverts to slug)

### Per-section save (each section: change → Save enables → Save → reload page → persists)
- [ ] Auto-ingest: enabled toggle + mode select
- [ ] Lint: schedule string + autofix toggle
- [ ] Ontology: confidence_min / confidence_auto_apply numeric inputs
- [ ] Watchdog: mode select (strict/merge/open)
- [ ] Snapshots: daily_enabled + retention_days
- [ ] Lifecycle: auto_stale_days + auto_archive
- [ ] Prompts: text inputs (empty → null in JSON)
- [ ] Telemetry: opt_in checkbox
- [ ] Locale: switch between Inherit/uk/ru/en; Inherit shows current global

### Ingest overrides
- [ ] Toggle Override checkbox for model → input appears, set value, Save → PATCH body has model
- [ ] Toggle off again → input hides, Save → PATCH body has `model: null`
- [ ] All 4 override fields work (model/language_hint/max_input_tokens/context_limit)
- [ ] Numeric inputs: clearing field doesn't break (no value-0 silently injected)

### Danger zone (delete project)
- [ ] Delete button red, opens modal
- [ ] Wrong slug typed → Delete button disabled
- [ ] Correct slug typed → Delete button enabled
- [ ] Click Delete with no jobs → 204 → navigated to home, project gone from sidebar
- [ ] Vault folder still on disk (verify in file explorer) — markdown'ы целые
- [ ] `mnemos project add` with same slug + vault restores access
- [ ] If jobs running: 409 → modal shows error message + «Force delete» link
- [ ] Click Force delete → DELETE `?force=true` → success
- [ ] Force delete link does NOT appear on other errors (test with offline daemon — should show plain error)

## Global Settings (`/settings/global`)
- [ ] General section: locale radio + daemon_port number input editable
- [ ] Defaults: model + language_hint + max_input_tokens + retention_days editable
- [ ] All saves persist after page reload
- [ ] Sidebar footer link visible, navigates correctly

## Validation errors
- [ ] retention_days=0 → Save → 422 → inline error message under field
- [ ] daemon_port=99999 → 422 → inline error
- [ ] confidence_min=1.5 → 422 → inline error

## Routing / placeholder
- [ ] `/project/<slug>/settings` no longer shows «Coming in #14c» placeholder
- [ ] `/settings/global` route exists and renders
