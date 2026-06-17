# In-App One-Click Updater (Variant A) — Design + Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** A "Update now" button in the dashboard that downloads the new **portable-zip** build from GitHub Releases, swaps the installed files, and relaunches — automating the manual portable+robocopy flow the user does today, WITHOUT a code-signing certificate.

**Platform scope (v1):** Windows only (the user's platform; the only supervised platform). macOS/Linux keep the existing "open release page" behaviour.

**Core safety invariant:** *Any failure of the swap leaves the prior, working install intact.* The updater backs up the install dir before touching it and restores the backup on any error or if the new build fails to launch. This makes the feature safe to ship even though the real end-to-end swap can only be proven on a live frozen install (dev runs as a venv, `is_frozen()` is False, so the apply endpoint refuses there).

---

## The hard constraint (from architecture map)

All three roles (tray, daemon, launcher) share the two install-dir exes (`claude-mnemos.exe`, `claude-mnemos-cli.exe`) + locked `_internal/*.dll|*.pyd`. A running process cannot overwrite its own exe. Therefore the swap MUST be done by a **separate process that lives OUTSIDE the install dir and survives killing all claude-mnemos processes.** On Windows the always-present standalone tool is **PowerShell** — it has no dependency on the (about-to-be-overwritten) install dir. Writing to `C:\Program Files\claude-mnemos` needs **elevation** (the user's manual robocopy is elevated), so the updater script runs elevated (one UAC prompt per update).

## Flow (Windows)

1. User clicks **Update now** in the Overview update banner.
2. `POST /api/update/apply`:
   - Refuse unless `runtime.is_frozen()` and `platform == Windows` (409 otherwise).
   - Re-check the latest release; resolve the `claude-mnemos-portable-x64.zip` asset's `browser_download_url`.
   - Download it to `~/.claude-mnemos/updates/<latest>/portable.zip`; validate it's a non-trivial, openable zip whose entries include `claude-mnemos.exe`.
   - Render `updater.ps1` from a template into `~/.claude-mnemos/updates/<latest>/` with the resolved install dir + zip path + relaunch command baked in.
   - Spawn it **elevated + hidden + detached**: `powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File updater.ps1` via `Start-Process -Verb RunAs` (UAC). Return `{started: true}` immediately.
3. `updater.ps1` (elevated, hidden, lives in `~/.claude-mnemos/updates/<latest>/` — NOT the install dir):
   1. `taskkill /F /IM claude-mnemos.exe /T` + `/IM claude-mnemos-cli.exe /T`; poll until gone (≤15s).
   2. **Backup** the install dir → `~/.claude-mnemos/updates/<latest>/backup\` via `robocopy /E /NFL /NDL /NJH /NJS`.
   3. Extract `portable.zip` → `...\extract\` (`Expand-Archive`).
   4. **Sanity-gate:** abort+restore if `extract\claude-mnemos.exe` is missing.
   5. Mirror `extract\` → install dir via `robocopy /E` (overwrite; no purge — stale files are harmless, deleting is the risk).
   6. **Relaunch as the interactive user** (not elevated): a one-shot Scheduled Task running `"<install>\claude-mnemos.exe" tray run` as the recorded user, then `schtasks /run` + `/delete`. (Elevated `Start-Process` would run the tray elevated, which then writes admin-owned files into `~/.claude-mnemos` — must avoid.)
   7. **Verify launch:** poll `GET http://127.0.0.1:5757/api/version` for ≤30s; if it never comes up OR any prior step failed → **restore the backup** (robocopy backup → install dir) and relaunch the OLD tray. Write a result line to `~/.claude-mnemos/updates/<latest>/result.txt` either way.
4. The new (or restored) version starts; the banner re-checks and shows `current == latest` (or the old version, with an error surfaced from `result.txt`).

## Why this is safe to ship unproven
Worst case at every step is a restore to the backed-up working install. The only unrecoverable risk is a crash BETWEEN backup and a successful partial overwrite where the backup is also lost — mitigated by doing the backup first and never deleting it until the new version is verified up.

---

### Task 1: Surface the portable-zip asset URL in update-check

**Files:** Modify `claude_mnemos/core/update_check.py`, `claude_mnemos/daemon/routes/update.py`. Test: `tests/core/test_update_check.py` (extend/create), `tests/daemon/test_app_update.py` (if exists; else extend).

- [ ] Add `asset_url: str | None = None` to `UpdateStatus`. In `check_for_update`, after `_fetch_latest_release()`, scan `release.get("assets", [])` for the entry whose `name == "claude-mnemos-portable-x64.zip"` and take its `browser_download_url`; store in the cache + status. Keep `download_url` (release html) unchanged. A helper `def _pick_asset_url(release: dict, asset_name: str) -> str | None`.
- [ ] Surface `asset_url` in `GET /api/update-status`.
- [ ] Tests: a mock release dict with `assets` → `asset_url` populated; no matching asset → None; cache round-trips `asset_url`.

### Task 2: Backend apply endpoint + download/stage + updater.ps1 template

**Files:** Create `claude_mnemos/core/update_apply.py`. Modify `claude_mnemos/daemon/routes/update.py`. Test: `tests/core/test_update_apply.py`, extend `tests/daemon/test_app_update.py`.

- [ ] `update_apply.py`:
  - `WINDOWS_PORTABLE_ASSET = "claude-mnemos-portable-x64.zip"`.
  - `class UpdateApplyError(Exception)`.
  - `def can_apply() -> tuple[bool, str]`: returns `(False, reason)` unless `runtime.is_frozen()` and `sys.platform == "win32"`.
  - `def download_and_stage(asset_url: str, version: str, *, opener=urllib.request.urlopen) -> Path`: download to `~/.claude-mnemos/updates/<version>/portable.zip` (mkdir parents), then validate: `zipfile.is_zipfile(p)` and the namelist contains `claude-mnemos.exe`; raise `UpdateApplyError` otherwise. `opener` injectable for tests.
  - `def render_updater_script(*, install_dir: Path, work_dir: Path, zip_path: Path, username: str, version: str) -> str`: returns the `updater.ps1` text implementing the flow above (taskkill → backup → extract → sanity-gate → robocopy → schtasks relaunch as `username` → verify /api/version → restore-on-fail → result.txt). Use parameterized, quoted paths; `-ErrorAction Stop` + try/catch around the swap with a restore in catch.
  - `def stage_update(asset_url: str, version: str) -> Path`: orchestrates download_and_stage + writes `updater.ps1` (via `render_updater_script`) into the work dir; returns the work dir.
  - `def spawn_updater(work_dir: Path) -> None`: `subprocess.Popen` of `powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Process powershell -Verb RunAs -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','<work>\updater.ps1'"` with `CREATE_NO_WINDOW | DETACHED_PROCESS`. (The outer non-elevated PS triggers the elevation prompt; the inner elevated PS runs the script.)
  - `current_install_dir()` = `runtime.executable_path().parent`; `current_username()` = `os.getlogin()` (fallback `getpass.getuser()`).
- [ ] `POST /api/update/apply` route: `ok, reason = can_apply()`; if not ok → 409 `{error, reason}`. Else `s = check_for_update(force=True)`; if `not s.has_update or not s.asset_url` → 409. Else `work = stage_update(s.asset_url, s.latest)`; `spawn_updater(work)`; return `{started: True, version: s.latest}`. Wrap download/stage errors → 502 `{error}`.
- [ ] Tests (NO real download / NO real spawn — all mocked):
  - `download_and_stage` writes + validates a fake zip (build a real in-memory zip containing `claude-mnemos.exe`); rejects a non-zip and a zip missing the exe.
  - `render_updater_script` output contains the taskkill, robocopy backup, Expand-Archive, the sanity-gate on `claude-mnemos.exe`, the schtasks relaunch with the username + `tray run`, the `/api/version` verify, and the restore-on-fail block; paths are quoted.
  - `can_apply` False in dev (not frozen) with a reason.
  - The route returns 409 in dev (not frozen) — assert it never spawns anything.
  - The route with `can_apply` monkeypatched True + `check_for_update` returning a status with `asset_url` + `stage_update`/`spawn_updater` monkeypatched → 200 `{started: True}`, and `spawn_updater` was called once.

### Task 3: Frontend "Update now" button (Windows) on the update banner

**Files:** Modify the Overview update banner component (find it: grep `update-status` / `update_available` / the banner in `frontend/src`). Add a hook `useApplyUpdate` (POST `/api/update/apply`). Locales uk/ru/en. Test: the banner test.

- [ ] When `/api/update-status` reports `has_update` AND the platform is Windows AND `asset_url` is present, show an **Update now** button next to the existing "Open release"/dismiss. (Platform: read from `/api/version` which returns `platform` — e.g. contains "Windows"; or add a small check. Reuse existing version query.)
- [ ] Clicking it: POST `/api/update/apply`; on success show a "Updating… the app will close and reopen. This needs a Windows permission prompt (UAC)." state and stop polling. On 409/502 show the error (e.g. "Update isn't available for this build — use Open release"). Keep "Open release page" as the always-available fallback.
- [ ] i18n keys `update.apply_button`, `update.applying`, `update.apply_uac_hint`, `update.apply_error`. uk primary.
- [ ] vitest: button shows only when has_update + windows + asset_url; clicking calls the endpoint; non-windows hides it (only the release link shows).

### Task 4: Docs + version

- [ ] No version bump in repo (tag drives it). Add a short note to README/Help if there's an updates section (optional).

## Final verification
- [ ] Full backend pytest 0 failures, mypy clean, ruff `claude_mnemos` clean.
- [ ] Frontend tsc + vitest clean; `npm run build`.
- [ ] Adversarial review of the diff — focus on the updater.ps1 (exe-lock, elevation, relaunch-as-user, rollback completeness, partial-failure recovery, path quoting/injection).
- [ ] **The real swap is NOT auto-testable** (needs a live frozen install). First live run is the user's, with the documented manual rollback (backup at `~/.claude-mnemos/updates/<ver>/backup`).

## Out of scope (v1)
- macOS/Linux auto-apply (keep release-page link).
- Delta updates / background download.
- Code-signing (Variant B / Squirrel-Sparkle) — separate EV-cert track.

---

## POST-REVIEW: v1 is NOT shippable — V2 redesign (pending Yarik's gate)

Adversarial review of v1 (4 lenses + verify) found **16 confirmed issues, 6 HIGH**, including a FATAL one. v1 is held on the branch, NOT merged/released. Build V2 only after Yarik approves the approach (brick-risk feature).

**Showstoppers in v1:**
- **#7 FATAL:** the generated `updater.ps1` does not PARSE — `$TaskRun = "\"{exe}\" tray run"` uses `\"` which is invalid PowerShell (PS uses backtick `` `" ``). The update is dead-on-arrival.
- **#1 brick:** the swap is a per-file `robocopy /E` over the live install incl. `_internal/*.pyd|*.dll`. A hard kill (power loss, AV quarantine of the unsigned exe, laptop sleep) mid-copy leaves a PyInstaller frankenbuild (new exe + old python DLL → "Failed to load Python DLL"). The `catch` never runs (process killed); the intact backup is never read on boot → unrecoverable brick.
- **#10/#2/#8 relaunch:** the schtasks-as-user relaunch is fragile (minute-resolution `/ST`, `/Run` can no-op, `/RU /IT` reliability, exit codes unchecked).
- **#11 restore:** rollback uses `/E` (no `/MIR`) → Frankenstein restore.
- **#12 verify:** can't tell a transient relaunch hiccup from a broken build → rolls back good swaps.
- **#5 verify false-pass; #9 `Get-Process` no wildcard (misses cli.exe); #4 no disk-space check / extract-after-kill; #6/#13/#14 failures invisible + no recovery path; #15/#16 UI no UAC pre-warning + in-memory state.**

**V2 robust design (addresses all of the above):**
1. **Do all the safe work in Python BEFORE anything is killed:** download → validate zip → `extractall` to `updates/<ver>/extract` → assert `claude-mnemos.exe` present → free-disk-space check (≥ install size + extract size on the install volume). Write a `swap.pending` JSON marker (`{version, install_dir, old_dir, started_at}`) BEFORE spawning. A bad download never touches the running app.
2. **Atomic, rename-based swap (no per-file merge):** the elevated inner script does `taskkill /F /IM claude-mnemos.exe /T` + `claude-mnemos-cli.exe /T` → poll `Get-Process claude-mnemos*` (wildcard) until gone → `Rename-Item <install> <install>.old` → `Move-Item <extract> <install>` (same-volume = atomic rename; cross-volume profile = documented manual-recovery case). An interruption leaves whole-old, whole-new, or briefly install-absent — NEVER a frankenbuild. Restore = rename `<install>.old` back (inherently clean, no `/MIR` needed). Keep `.old` until the new build is verified healthy.
3. **Two-process model, no schtasks (reliable relaunch):** the daemon spawns a NON-elevated OUTER powershell (detached, survives `/T`). It does `Start-Process -Verb RunAs -Wait` on the elevated INNER swap script (swap only, writes `result.txt`, NO relaunch). After it returns, the outer (running as the user) does a plain `Start-Process "<install>\claude-mnemos.exe" tray run` (non-elevated, correct user) and polls `/api/version` until the JSON `version == target` (≤60s); on success removes `<install>.old` + clears the marker; on failure leaves the marker for boot recovery.
4. **Resume-on-boot recovery + surfaced outcome:** the frozen entry points scan `swap.pending` on startup — if the running `__version__ == target` → success (clear marker, remove `.old`); else record a "last update failed/incomplete" status. The daemon reads `result.txt`/marker and exposes `last_apply: {version, status, error}` on `/api/update-status`; the banner shows a red "Last update failed — previous version restored: <error>" state. Cleanup keeps only the most recent backup.
5. **UI:** warn BEFORE the click ("this closes the app and asks for a Windows permission (UAC) to write to Program Files; if the dashboard doesn't return in ~1 min, relaunch from Start menu"). Persist the updating intent via the marker so the dead-SPA window is explainable.

**Safety story (V2):** every failure leaves a *recoverable* state — old version running, new version running, a clean restore from `.old`, or (rare hard-kill mid-rename) an install-absent state with an intact `.old` backup + a documented one-line manual restore. Never a silent frankenbuild.
