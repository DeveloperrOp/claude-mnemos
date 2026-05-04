# Public-grade Onboarding — Design Spec

**Date:** 2026-05-04
**Status:** Draft, awaiting Yarik approval
**Scope:** Multi-day plan. Full redesign of install + first-run + first-session journey so a non-technical user installs claude-mnemos and reaches a working dashboard with **zero command-line knowledge**.

---

## TL;DR

Public-grade product means installation must look like Slack, not like a Python package. We split the work into 5 phases, smallest-impact first, native installer at peak.

The end state: user double-clicks `claude-mnemos-setup.exe` (or `.dmg`), it installs, opens browser to a Welcome screen that already shows their detected Claude Code projects with one-click "Track this folder" buttons, hooks install themselves, daemon autostarts with the OS, and the first session that comes through triggers a celebration toast. Anywhere something can break, there's a Setup-Checklist widget with a Fix button. Behind the scenes, `mnemos doctor` exposes the same diagnostics for power users.

The estimated scope is **~10–14 days** of work split across 5 independently-shippable phases.

---

## Goals

1. **Zero CLI knowledge required.** A non-technical user (your "ребёнок" yardstick) installs and reaches a working dashboard without ever opening a terminal.
2. **Self-healing.** When a step fails (hooks not installed, Claude Code missing, daemon down), the UI shows the problem with a one-click fix — no log-reading.
3. **Continuous progress signal.** From install through first ingested session, the user never wonders "is this working?". Each milestone is celebrated.
4. **Discoverable diagnostics.** `mnemos doctor` (CLI) and a Diagnostics tab (UI) let any user run a full health-check without external help.

## Non-Goals

- Web-hosted SaaS variant — out of scope, mnemos remains local-only.
- Mobile app — out of scope.
- Auto-update mechanism for native installers — deferred to a future phase (Phase 6+, not in this design).
- Public marketing site / video tutorials — referenced but production lies outside this design.
- Localizing onboarding to >2 languages — UA/RU/EN parity remains; new languages out of scope.
- Telemetry/analytics — explicitly Phase 4 below, opt-in only, gated behind a separate spec sub-review when we get there.

## Success Criteria

A new user, with Claude Code already installed but **never having heard of mnemos**, can:

1. Install in **≤ 60 seconds** (download + run installer + close it).
2. See their first project tracked **without typing any path**.
3. Get a "first session ingested" celebration **within 5 minutes** of opening Claude Code.
4. If something is broken, see a **prominent yellow/red banner with a Fix button**, never a silent failure or a "check the logs" message.

If any of these fail in user testing on a fresh Windows VM, the design has missed.

---

## Current state (baseline 2026-05-04)

### What exists

- **Distribution:** `pipx install claude-mnemos`. Requires user to know about Python + pipx.
- **Hooks install:** `mnemos hooks install` writes SessionStart + SessionEnd to `~/.claude/settings.json`. PreCompact NOT included (regression — bug to fix as part of Phase 1).
- **Tray supervisor:** `mnemos tray start` runs with daemon-as-subprocess + restart-limiter (3 in 5 min). Autostart via Startup-folder `.lnk` (Win) / launchd plist (Mac).
- **Onboarding wizard** (`/`-route when no projects exist): asks for Display Name + Slug + Vault root + (advanced) Cwd patterns. Display name auto-derives slug. Vault picker exists. Tray autostart checkbox present (opt-in, default checked but easy to miss).
- **Settings UI** (Plan B): full project lifecycle through UI — create/edit/delete.
- **Health visibility:** HealthAlertsBar on Overview, Health page, hook_silence detector working.

### What's broken or missing

| Gap | Impact | Phase |
|---|---|---|
| `pipx install` requires Python + terminal knowledge | Blocks "child" yardstick | 2 |
| 3 commands needed before dashboard opens | Each = drop-off chance | 1, 2 |
| Hook install doesn't include PreCompact | Data-loss vector for `/compact` users | 1 |
| Empty-state Onboarding asks for technical terms (vault_root, cwd_patterns) | Cognitive load | 3 |
| User must manually type `cwd_patterns` even though mnemos knows `~/.claude/projects/` | Easily wrong, easily missed | 1 |
| No "first session" celebration → user stares at empty dashboard wondering if it works | Confidence drain | 1 |
| No setup-checklist widget on Overview — user sees broken parts only as red toasts when they fail | No proactive signal | 1 |
| `mnemos doctor` doesn't exist | No self-service diagnostics | 1 |
| Tray icon installs but doesn't introduce itself ("what is this thing in my tray?") | Low feature discovery | 2 |
| No browser auto-open after `tray start` / installer | User has to know `:5757` | 1, 2 |

---

## Target user journey

```
1. Visit mnemos website → click "Download for Windows"
2. Run claude-mnemos-setup.exe → installer ticks "✓ Install Claude Code (if missing)"
   → "✓ Add to startup" → "✓ Open dashboard" → click Install → done
3. Browser auto-opens to http://localhost:5757
4. Welcome screen shows:
   ┌───────────────────────────────────────────┐
   │ Welcome to claude-mnemos                  │
   │                                            │
   │ ✓ Daemon running                          │
   │ ✓ Hooks installed                         │
   │ ✓ Autostart enabled                       │
   │ ⚠ Pick a project to track                 │
   │                                            │
   │ We found these Claude Code workspaces     │
   │ on your computer:                          │
   │                                            │
   │   [ ] D:\code\my-app    (12 sessions)    │
   │   [ ] D:\code\other     (3 sessions)     │
   │   [ ] D:\notes          (8 sessions)     │
   │                                            │
   │ [Track selected ▶]    [Skip for now]     │
   └───────────────────────────────────────────┘
5. User checks "my-app" → click "Track selected"
6. Project created (vault_root auto = D:\code\my-app\.mnemos, cwd_patterns auto)
7. Overview shows "Watching for first session..." with spinner
8. User opens Claude Code in D:\code\my-app, types something, /exit
9. Within 30s — toast: "🎉 First session ingested! 1.2K tokens captured."
10. Setup checklist on Overview shows all ✓
```

The 9 above steps replace the current ~14-step manual journey.

---

## Architecture overview

The redesign is **additive layers on top of existing code**, not a rewrite. The five phases below correspond to five independently-shippable plans. Each phase ends with a working release.

### Layer cake

```
                    ┌─────────────────────────────────┐
   Phase 5         │ Public docs / website / videos  │   ← reference, not built here
                    └─────────────────────────────────┘
                    ┌─────────────────────────────────┐
   Phase 4         │ Opt-in telemetry / error report │
                    └─────────────────────────────────┘
                    ┌─────────────────────────────────┐
   Phase 3         │ Welcome screen + simplified UI  │
                    │ (replaces current Onboarding)   │
                    └─────────────────────────────────┘
                    ┌─────────────────────────────────┐
   Phase 2         │ Native installer (Win MSI / Mac │
                    │ DMG / Linux AppImage)           │
                    └─────────────────────────────────┘
                    ┌─────────────────────────────────┐
   Phase 1         │ Quick wins on current pipx flow │   ← baseline foundations
                    └─────────────────────────────────┘
                    ┌─────────────────────────────────┐
                    │ Existing: tray, daemon, hooks   │
                    │ install, Onboarding wizard,     │
                    │ Settings UI                     │
                    └─────────────────────────────────┘
```

Phases 1 + 3 ship value to existing pipx users. Phase 2 unlocks the public-grade story. Phase 4 is data-collection. Phase 5 is comms.

---

## Phase 1 — Quick wins on existing pipx flow (~3–4 days)

Goal: Halve the friction of the current install path. No installer rebuild yet — these all work for `pipx install` users today.

### 1.1. Fix `mnemos hooks install` to include PreCompact

`cli_hooks.py::install` currently writes only SessionStart + SessionEnd. After PreCompact landed in `hooks/hooks.json`, the CLI was not updated. Add PreCompact installation, regression test, idempotent replacement (same as the other two).

**Files:** `claude_mnemos/cli_hooks.py`, `tests/cli/test_cli_hooks.py`. ~30 LoC.

### 1.2. `mnemos init` — single command bootstrap

A new top-level command that does the work that takes 3 commands today:

```
mnemos init
  → Run hooks install (verbose output, skip if already done)
  → Register tray autostart (skip if already registered)
  → Start tray (with daemon as subprocess)
  → Wait for daemon health
  → Open browser to http://localhost:5757
```

Idempotent. If user re-runs after a crash, picks up where it left off. Each step prints a single ✓/✗ line.

**Files:** `claude_mnemos/cli_init.py` (new ~120 LoC), `claude_mnemos/cli.py` (subparser registration).

### 1.3. Cwd auto-detection from `~/.claude/projects/`

mnemos already has the data — every JSONL transcript records its cwd. We aggregate by directory, count sessions in last 30 days, and surface a list ranked by activity.

New endpoint: `GET /api/onboarding/detected-cwds` → `[{cwd: str, session_count: int, last_seen: ISO datetime}]`. Cap at 10 entries. Skip directories that already match a registered `cwd_patterns`.

**Files:** `claude_mnemos/daemon/routes/onboarding.py` (new), `claude_mnemos/core/cwd_detection.py` (new), tests.

### 1.4. Welcome screen replaces empty-state Onboarding

When zero projects exist, instead of the current technical wizard, render a Welcome screen:

- Setup status block: 4 ✓/⚠ rows (Daemon, Hooks, Autostart, First Project)
- Detected workspaces list (from 1.3) — checkboxes, "Track selected" button
- Each tracked checkbox auto-fills:
  - `display_name` = derived from cwd folder name (`my-app` → "My App")
  - `slug` = derived (existing logic)
  - `vault_root` = `<cwd>/.mnemos`
  - `cwd_patterns` = `[<cwd>, <cwd>/*, <cwd>/**]`
- "Skip for now" → falls back to the current technical wizard (kept unchanged for power users).
- "Show advanced" toggle → reveals current technical wizard inline for users who want full control.

Existing `Onboarding.tsx` becomes `OnboardingAdvanced.tsx`. New `OnboardingWelcome.tsx` is the default.

**Files:** `frontend/src/pages/OnboardingWelcome.tsx` (new ~250 LoC), rename existing, route swap, i18n keys, tests.

### 1.5. Setup-Checklist widget on Overview (collapsing)

Persistent widget on Overview that always shows current setup state:

```
┌─ SETUP STATUS ───────────────────────────┐
│ ✓ Daemon running                          │
│ ✓ Hooks installed                         │
│ ✓ 1 project tracked                       │
│ ⚠ No sessions captured yet — try Claude  │
│   Code in D:\code\my-app                  │
└───────────────────────────────────────────┘
```

When all green for 24h, widget auto-collapses to a single ✓ chip in the page header. Expandable on click. When anything goes ⚠/✗, auto-expands and shows Fix button per row.

**Files:** `frontend/src/components/widgets/dashboard/SetupChecklist.tsx`, `useSetupStatus.ts` hook (aggregates 4 existing API endpoints), tests. Mounted on Overview between `HealthAlertsBar` and Projects grid.

### 1.6. First-session celebration

When the first manifest entry lands for any project (detect: project's manifest moves from 0 → 1+ ingested SHAs), fire a one-time toast on Overview:

> 🎉 First session ingested for **My App** — 1,234 tokens captured.

Delivered via existing `useDashboardSnapshot` polling (10s) — comparing previous snapshot's per-project count to current. State stored in localStorage so the toast doesn't fire again across reloads.

**Files:** `frontend/src/hooks/useFirstSessionCelebration.ts` (new ~50 LoC), Overview wires it.

### 1.7. `mnemos doctor` CLI + UI Diagnostics tab

CLI command runs the same checks as the current 7 health detectors plus 4 install-level checks (Claude Code installed? Hooks present? Daemon reachable? Vault writable?). Outputs a colored ✓/⚠/✗ list, exit code 0/1.

UI: `/diagnostics` route renders the same checks as cards with Fix buttons (Re-install hooks, Restart daemon, Open log file, etc).

Reuses existing `core/health_checks.py` detectors. Adds 4 install-level detector functions.

**Files:** `claude_mnemos/cli_doctor.py` (new ~80 LoC), `claude_mnemos/core/install_checks.py` (new ~120 LoC), `frontend/src/pages/Diagnostics.tsx` (new ~200 LoC), tests.

### 1.8. Default tray autostart `on` (instead of `off`)

Onboarding checkbox already exists, currently `defaultChecked=true` — keep. But also make the **fallback case** (when checkbox is missed) default to "register autostart on first daemon health success" — only if no decision has been recorded. Idempotent.

**Files:** `claude_mnemos/daemon/process.py` (one-liner check at startup), `state/install_state.py` (new tiny file storing "user dismissed autostart" bit).

### 1.9. Browser auto-open after `mnemos init` / first daemon ready

When `mnemos init` completes daemon health-check, `webbrowser.open("http://localhost:5757")`. Skip if `--no-browser` flag passed.

**Files:** `cli_init.py` (1.2), one-liner.

---

### Phase 1 deliverable

After Phase 1, the user-facing flow is:

```
pipx install claude-mnemos      ← still requires Python knowledge
mnemos init                      ← one command, browser opens
Welcome screen → check workspace → click Track → done
```

Three terminal lines instead of nine, plus a browser-driven Welcome flow. Already a major UX upgrade for existing users without the installer-build investment.

**Tests target:** backend +25, frontend +15, no TypeScript errors. Live walk: fresh `~/.claude-mnemos/` directory, run `mnemos init`, complete onboarding, expect first-session celebration on next Claude session.

---

## Phase 2 — Native installers (~5–7 days)

Goal: Remove the Python prerequisite. User downloads a single `.exe` (or `.dmg` / `.AppImage`), double-clicks, gets working mnemos.

### 2.1. Build pipeline

Use **PyInstaller** to bundle Python + claude-mnemos into a single directory. Frontend bundle already lives under `claude_mnemos/daemon/static/`. Total size estimate: ~50–80 MB (acceptable for a developer tool — Claude Code itself is bigger).

Per-platform packagers:

- **Windows:** Inno Setup → `claude-mnemos-setup-x64.exe`. NSIS-style installer with progress bar, "Add to Startup" checkbox (default on), "Launch claude-mnemos" finish checkbox (default on).
- **macOS:** `py2app` + `create-dmg` → `claude-mnemos.dmg`. App bundle, drag-to-Applications. LaunchAgent registration on first launch.
- **Linux:** `AppImage` first (most portable). `.deb` follow-up if requested.

### 2.2. Postinstall actions (runs once on first launch)

After install, when the user first runs the app, the bundled `mnemos init` flow runs automatically:

- Check if Claude Code is installed; if not, show a friendly modal with a download link. Do NOT block — user can install Claude Code later and re-run "Setup Hooks" from Settings.
- Install hooks (with all 3 events).
- Register autostart (with OS-native mechanism).
- Start daemon.
- Open browser.

### 2.3. CI/CD

GitHub Actions workflow that on tag push (`v0.1.0` etc) builds all 3 installers and attaches them to a release. Matrix build: `windows-latest`, `macos-latest`, `ubuntu-latest`.

### 2.4. Code signing (deferred to follow-up)

Initial release: unsigned. Users will see "unknown publisher" warnings on Windows and Gatekeeper on Mac. We document the workaround in the download page. Code signing certs are a separate purchase decision (~$200–500/yr for OV/EV); deferred until first 100 users.

### 2.5. Updater (explicitly out-of-scope for Phase 2)

User updates by downloading a new installer. Auto-update mechanism (Sparkle on Mac, Squirrel on Win) is Phase 6+.

---

### Phase 2 deliverable

After Phase 2, the user-facing flow is:

```
Download claude-mnemos-setup.exe from website
Double-click installer → Next → Next → Install → Finish
Browser auto-opens to Welcome screen
```

Zero terminal involvement. Matches the "child" yardstick.

**Risks:** Codesign warnings will hurt conversion until we sign. Bundle size is bigger than stock pipx. Path-handling differences between PyInstaller's `_MEIPASS` and source-tree need careful testing of `cli_hooks.py::_detect_hook_scripts`.

---

## Phase 3 — Wizard simplification (~2–3 days)

Goal: When a user does need to enter a project manually (not detected, or "Show Advanced"), the form speaks human language.

### 3.1. Plain-English labels

Current labels → new labels:

| Current | New |
|---|---|
| Display name | Project name |
| Slug | URL-friendly name (auto-set) |
| Vault root | Where to store memory files (auto-set to `<project>/.mnemos`) |
| Cwd patterns (advanced) | Folders where you use Claude Code (auto-detected) |

`vault_root` field hidden by default — auto-set to `<first cwd_pattern>/.mnemos` or `~/.claude-mnemos/<slug>` if cwd is empty. Revealed only by "Show advanced" toggle.

### 3.2. Inline previews

As user types Project name:
- Slug preview chip (live)
- Vault root preview chip ("memory will live in `D:\code\my-app\.mnemos`")
- Cwd preview ("Will track sessions in `D:\code\my-app`")

Reduces "what's about to happen" anxiety.

### 3.3. Single-screen wizard

Current: header + 3 form sections + advanced + autostart + cli-check + buttons. Total scrolling.

New: collapse to 2 fields visible by default (Project name + folder picker), everything else under "Show advanced" / "Show what mnemos will do" toggles. Submit becomes a single big primary button.

### 3.4. Files

`frontend/src/pages/OnboardingAdvanced.tsx` (renamed from current Onboarding.tsx). Tests updated. i18n keys updated. No backend changes.

---

### Phase 3 deliverable

Manual project creation feels like adding a folder to Dropbox, not configuring a build tool.

---

## Phase 4 — Opt-in telemetry / error reporting (~2–3 days)

Goal: When a public user has a problem, we have signal to improve onboarding.

### 4.1. What we collect (opt-in only)

Anonymous, no PII:

- mnemos version, OS, Python version
- Onboarding step completion timestamps (`welcome_shown`, `cwd_detected`, `project_created`, `first_session`, `hooks_installed_at_step`)
- Error events (detector name, no message contents — message contents may contain paths)

What we do NOT collect:

- Cwd paths, project names, vault contents
- Claude conversation contents
- IPs (server-side aggregation strips them)

### 4.2. Implementation

- New `state/telemetry_consent.py` storing user's choice. Default `null` (not asked).
- On first run, Welcome screen shows a one-paragraph opt-in card with "Allow / No thanks" buttons. Choice is sticky.
- Local event buffer (`~/.claude-mnemos/telemetry-pending.jsonl`). Flushed on daemon shutdown + every 24h to a stub HTTPS endpoint we'll set up (placeholder URL — actual endpoint setup is out of scope, this design just sets up the local pipeline).
- "Diagnostics" tab has an "Opt out / Opt in" toggle and a "Show what we'd send" button revealing the pending buffer in raw JSON.

### 4.3. Sub-design gate

When Phase 4 implementation starts, this sub-section gets a separate design review (we may decide to skip telemetry entirely if posthog/sentry feel too heavy for the user count). Implementation plan deferred until that review.

---

## Phase 5 — Public docs / videos (out-of-scope here, referenced for completeness)

Goal: Marketing site, install videos, FAQ. Not built here. Logged so we don't lose track.

Items: landing page (`mnemos.dev` or similar), 60-second install video, "What is mnemos" 2-min explainer, FAQ page, Discord / GitHub Discussions launch.

---

## Cross-cutting concerns

### Backwards compatibility

- Existing pipx users keep working through Phase 1. Phase 2 adds installers, doesn't replace pipx.
- All existing API contracts preserved. New endpoints are additive (`/api/onboarding/*`).
- Existing Onboarding UI route preserved as `OnboardingAdvanced` reachable from "Show advanced" link.

### State storage

- New `state/install_state.py`: tiny JSON file at `~/.claude-mnemos/install-state.json` storing `{first_run_ts, autostart_decision, first_session_celebrated, telemetry_consent}`. Lock-protected, version-stamped.

### Internationalization

- All new strings go through existing i18n. UA + RU + EN parity for every new key. Translation memory recommended for the `OnboardingWelcome` page (~30 new keys).

### Error handling

Every step in the Welcome flow has explicit success/failure UX:

- "Detect workspaces" fails → shows "We couldn't read `~/.claude/projects/` — that's OK, you can add a project manually" with a button to the manual wizard.
- "Track selected" fails (e.g., directory not writable) → toast + `setup-checklist` row stays ⚠.
- "Install hooks" fails → row stays ⚠ with "Try again" button. The `hook_silence` detector will catch it later anyway.

### Tests

- Backend pytest target after all 5 phases: ~+80 tests.
- Frontend Vitest target: ~+40 tests.
- E2E tests: install fresh on Win/Mac/Linux VM, complete onboarding, verify first session — at least one E2E per phase deliverable.

### Risks summary

| Risk | Mitigation |
|---|---|
| Phase 2 installer build complexity (PyInstaller path quirks) | Build incremental; CI matrix from day 1 |
| Code-sign warnings reduce trust on Win/Mac | Document workaround; budget for cert by Phase 2 release |
| `~/.claude/projects/` cwd detection sees stale data on disk | Filter by `mtime > now - 30d` |
| Welcome screen feels patronizing to power users | "Show advanced" reveals current wizard inline (no hide-and-seek) |
| Translation backlog blocks Phase 1 ship | Ship en-only first, UA/RU follow within 24h |
| Telemetry phase scares users | Default OFF, double-confirm "Allow", easy revoke |

---

## Implementation order

1. **Phase 1 first** (3-4 days). Independent value for current users, validates UX direction without big build investment. Smallest sub-tasks 1.1 → 1.9 ship-able as separate commits.
2. **Phase 3 second** (2-3 days). Wizard simplification benefits both pipx and installer users. Cheap, high-impact.
3. **Phase 2 third** (5-7 days). Largest investment; only justified once we know the UX is right (Phases 1+3 done).
4. **Phase 4 last in this design** (2-3 days). Skip if user-count remains < 50.
5. **Phase 5** (separate spec, separate plan).

Total: ~12–17 working days for Phases 1-4. Phase 1 alone ships in 3-4 days and is the highest-leverage delivery.

---

## Out-of-scope decisions

These are documented so they don't drift into scope:

- **Web/SaaS variant:** mnemos remains local-only.
- **Cloud sync between devices:** out of scope; rsync the vault if needed.
- **Multi-user / team features:** out of scope.
- **Auto-update mechanism:** Phase 6+.
- **Code signing certificates:** budget item, separate decision.
- **Cwd detection from sources other than `~/.claude/projects/`:** out of scope.
- **Welcome screen tutorial video embed:** Phase 5 (marketing).
- **Mobile app companion:** out of scope.
- **Existing `Onboarding.tsx` rewrite from scratch:** out of scope — we wrap and rename, not rewrite.

---

## Open questions for Yarik

1. **Telemetry — go or skip?** Default position: build the local pipeline (Phase 4.1, 4.2) but don't set up the server endpoint yet. Decide on actual server when we have ≥50 users. (Costless to defer.)
2. **Bundled Claude Code install?** Phase 2 currently shows a friendly modal if Claude Code is missing. Alternative: bundle Claude Code installation step into mnemos installer (chains Claude Code installer if not detected). Heavier but smoother. **Default: friendly modal only.**
3. **Branding/website domain** — out of scope here, but Phase 5 needs a domain decision before public launch.

---

## Self-review notes

- All sections have concrete file targets and LoC estimates — no "TBD".
- Phases are explicitly independent; reordering Phase 2 ↔ Phase 3 is documented as fine.
- Goals tested against success criteria in `Success Criteria` section: each goal has a measurable failure mode.
- Out-of-scope list explicitly catches scope creep targets (mobile, SaaS, multi-user).
- Phase 4 (telemetry) gated behind sub-design review — not auto-shipping.
- Existing tests baseline carried forward; no test deletion proposed.
- Error UX is explicitly designed for every Welcome flow step — no silent failures.
