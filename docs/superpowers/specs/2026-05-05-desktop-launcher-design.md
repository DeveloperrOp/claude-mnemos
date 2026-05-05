# Desktop Launcher (E1) — Design Spec

**Date:** 2026-05-05
**Status:** Draft, awaiting Yarik approval
**Scope:** Replace «open browser at localhost:5757» UX with a native desktop application window. Fix the tray-supervisor multi-spawn bug. Make autostart at boot a first-class default. Land before public `v0.0.1` release.

---

## TL;DR

claude-mnemos becomes a Discord-/Steam-style desktop application. User clicks one icon → a native window opens with the dashboard inside (`pywebview` + Edge WebView2 on Win, WKWebView on Mac, WebKitGTK on Linux). The tray-supervisor stays as the always-on background entity that owns the daemon-subprocess and `Mnemos.lnk` autostart. Tray icon is visible at all times. Closing the window minimises to tray; full-quit only via tray-menu *Quit*. Daemon stays alive (capturing sessions) regardless of whether the window is open.

The current tray-supervisor PID-file lock has a race condition that allowed 100+ rogue tray instances to spawn during dev. Replace with a **Windows named mutex** (`CreateMutexW` + `ERROR_ALREADY_EXISTS`) on Win and `fcntl.flock` on Mac/Linux — atomic, race-free.

Estimated scope: **~3–4 working days** plus the bundling/CI re-test cycle. Lands before `v0.0.1` (which is already gated on Phase 2 CI passing). Phase numbering: this is **Phase 3** in the public-onboarding redesign series.

---

## Goals

1. **Zero browser involvement** — user never types `localhost:5757` or sees URL bars.
2. **Fix tray multi-spawn** — guarantee single-instance via OS-native mutex / file lock.
3. **Autostart enabled by default** — daemon ingests sessions without user action.
4. **Window lifecycle obvious** — close-to-tray default, with first-time consent dialog.
5. **No regression** — existing CLI subcommands (`mnemos init`, `mnemos doctor`, `mnemos hooks install`, etc) continue to work unchanged.

## Non-Goals

- Replacing the daemon's HTTP transport with IPC. Daemon keeps `:5757` on loopback. Hooks still POST via HTTP. (Discussed and rejected — months of rewrite for no UX gain.)
- Native menu bar / OS-level keyboard shortcuts in the window. Web-based menu is fine.
- Hot-reload of the SPA in the launcher window. Bundle is static; updates ship via auto-update banner (Phase 2 Task 10).
- Cross-launcher message routing (multiple launcher windows on the same daemon). Single-instance only.
- Linux DE integration polish beyond a basic `.desktop` entry.

## Success Criteria

A user on a fresh Win11 VM running the unsigned `claude-mnemos-setup-x64.exe` from `v0.0.1`:

1. Sees a tray icon **immediately after install** without a browser tab opening.
2. Double-clicks the Start Menu shortcut → a native window opens within 3s, dashboard renders.
3. Closes the window via X → window disappears, tray icon stays, daemon stays alive (verified: hooks still capture).
4. Reboots Windows → tray + daemon auto-start; window does NOT auto-open.
5. Right-clicks tray → menu has Open Dashboard / Pause Daemon / Settings / Quit.
6. Runs the installer twice → second install does NOT spawn a second tray (single-instance verified).
7. CLI `mnemos doctor` from a separate terminal still works (no rogue tray spawned).

If any of (1)–(7) fail on user testing, the design has missed.

---

## Current state (baseline 2026-05-05)

- **Daemon:** `claude_mnemos/daemon/process.py::MnemosDaemon` — FastAPI/uvicorn on `:5757`, owns scheduler + watchdogs.
- **Tray supervisor:** `claude_mnemos/tray/__main__.py` (209 LoC) + `supervisor.py` (322 LoC) + `icon.py` (184 LoC) + `platform/{base,windows,macos}.py` (autostart `.lnk` / `launchd` plist).
- **Single-instance lock:** PID file at `~/.claude-mnemos/tray.pid`. `_acquire_tray_lock()` — checks file + `psutil.pid_exists`. **Race-prone**: two processes can both see «no PID, no live tray» and both write their PID, second overwriting first. **Confirmed bug** — caused 9+ live tray instances during 2026-05-05 session.
- **CLI entry:** `mnemos tray run|install|uninstall|status`.
- **Frontend:** React 19 SPA bundled by Vite into `claude_mnemos/daemon/static/`, served by daemon at `/`.
- **No desktop window today** — user opens `http://localhost:5757` in browser.

What's broken:
- Lock race (described above).
- Multi-spawn allowed by Phase 1 + Phase 2 install flows: `mnemos tray install` calls `_cmd_install` which spawns tray IF none alive — but the «alive» check is the racy lock. PyInstaller smoke test runs the bundled exe many times → before fix `c753517`, each run triggered postinstall → spawned tray → another tray accumulated.
- Browser-based UX has no «daemon down» fallback (covered separately — solved by launcher always running its own splash if daemon isn't yet up).

---

## Architecture

### Three-process model

```
                ┌──────────────────────────────┐
   User clicks  │  claude-mnemos-tray.exe      │  ← single mutex-locked supervisor
   tray icon    │  (autostart at boot)         │
   or shortcut  │                              │
                │  • holds Win named mutex     │
                │  • spawns daemon child       │
                │  • spawns launcher child     │
                │  • tray-icon UI              │
                │  • autostart .lnk owner      │
                └──────────────┬───────────────┘
                               │ fork
              ┌────────────────┴───────────────┐
              ▼                                ▼
   ┌─────────────────────┐         ┌──────────────────────┐
   │ claude-mnemos       │ ←HTTP→  │ claude-mnemos        │
   │ daemon              │  loop   │ launcher (window)    │
   │  • FastAPI :5757    │  back   │  • pywebview         │
   │  • scheduler        │         │  • WebView2 / WKWeb  │
   │  • watchdogs        │         │  • points to :5757   │
   └─────────────────────┘         └──────────────────────┘
              ▲                                ▲
              │ HTTP (loopback)                │ menu/window events
              │                                │ via tray IPC
              │
   ┌──────────┴────────────┐
   │ Claude Code hooks     │  ← separate processes, fire on session events
   │ (session-start,       │     POST to daemon :5757
   │  session-end,         │
   │  pre-compact)         │
   └───────────────────────┘
```

- **Tray supervisor** is the single autostart entity. It owns the Windows named mutex. Subprocess of nothing — top-level when launched by autostart `.lnk`.
- **Daemon** is supervisor's subprocess. Survives launcher close. Killed only when supervisor quits (tray-menu Quit) or when supervisor restart-limiter trips.
- **Launcher** is supervisor's subprocess (or sibling, see below). Optional UI. Closing the launcher window minimises to tray (process keeps running, hidden) OR fully exits the launcher process (daemon untouched).
- **Hooks** are independent processes spawned by Claude Code. They POST to daemon over HTTP. No change.

### Single-instance enforcement (the multi-spawn fix)

Replace the PID-file lock with **Windows named mutex** atomic primitive:

```python
# claude_mnemos/tray/single_instance.py (new)
import sys, ctypes
from ctypes import wintypes

_MUTEX_NAME = "Global\\com.yarik.claude-mnemos.tray"

class WindowsSingleInstance:
    _handle = None

    def acquire(self) -> bool:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        self._handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
        ERROR_ALREADY_EXISTS = 183
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            return False
        return self._handle != 0

    def release(self) -> None:
        if self._handle:
            ctypes.WinDLL("kernel32").CloseHandle(self._handle)
            self._handle = None
```

On macOS / Linux: `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on a file at `~/.claude-mnemos/tray.lock` — also atomic, also race-free.

Both interfaces are uniform (`acquire() -> bool`, `release() -> None`). Selected at runtime via `sys.platform`.

If `acquire()` returns False, the second instance:
1. Sends a "show window" message to the existing instance (via a tiny named-pipe IPC on Win, Unix-domain socket on Mac/Linux).
2. Exits cleanly with success code (the user double-clicked, expected behavior is "show the existing window", not «error»).

The IPC channel is a single endpoint: `~/.claude-mnemos/tray.sock` (or `\\.\pipe\claude-mnemos-tray` on Win). Single message: `"show"`. The active instance receives it and unhides/focuses the launcher window.

### Launcher window (pywebview)

`pywebview` library wraps native webview controls — Edge WebView2 on Win 11 (preinstalled), Edge WebView2 Runtime on Win 10 (installer-bootstrapped via Inno Setup), WKWebView on macOS, WebKitGTK on Linux.

```python
# claude_mnemos/launcher.py (new, ~150 LoC)
import threading
import time
import urllib.request
import webview

DAEMON_URL = "http://127.0.0.1:5757"
HEALTH_URL = f"{DAEMON_URL}/api/health"
SPLASH_HTML = """<html>...connecting to daemon...spinner...</html>"""

class Launcher:
    def __init__(self, supervisor):
        self.supervisor = supervisor
        self.window = None

    def start(self):
        self.window = webview.create_window(
            title="claude-mnemos",
            html=SPLASH_HTML,
            width=1280,
            height=800,
            min_size=(900, 600),
        )
        webview.start(self._after_load, self.window)

    def _after_load(self):
        # Poll daemon health, navigate when ready.
        for _ in range(30):
            try:
                with urllib.request.urlopen(HEALTH_URL, timeout=1) as r:
                    if r.status == 200:
                        self.window.load_url(DAEMON_URL)
                        return
            except Exception:
                pass
            time.sleep(0.5)
        # Daemon never came up — keep splash with retry button (not in MVP).
```

The launcher window is a thin wrapper. The dashboard inside is the same React SPA we already ship.

### Window-close behavior

First time the user clicks the X button on the window:
- A native dialog appears: "Close window or quit fully?"
  - **Close window** (default) — window hides, tray + daemon stay alive. App keeps capturing sessions.
  - **Quit fully** — supervisor sends shutdown signal to daemon, releases mutex, exits.
- A "Don't ask again" checkbox persists the choice in `~/.claude-mnemos/install-state.json::window_close_action` (`"hide"` or `"quit"`).
- Subsequent X clicks honor the saved preference; no dialog.

Tray-menu Quit always exits fully (no dialog).

Setting toggle in `/settings/global` page lets user reset the preference.

### Tray menu

Right-click tray icon shows:

- **Open Dashboard** — focuses launcher window if open, spawns it if hidden.
- **Daemon: ●Healthy / ⚠Restarting / ●Stopped** (read-only status).
- **Pause Daemon** / **Resume Daemon** — temporarily stops/starts daemon ingest. Useful during system-heavy work.
- **Settings...** — opens launcher window navigated to `/settings/global`.
- **Quit** — full exit.

Left-click tray = Open Dashboard.

### Autostart by default

Spec section: autostart is mandatory on first install. Inno Setup `[Tasks]` keeps the autostart task `checkedonce` (already there). On Mac the launchd plist is registered by tray supervisor's `_cmd_install`. Mnemos.lnk / plist points to `claude-mnemos-tray.exe run`.

A toggle in `/settings/global` lets advanced users disable autostart. Backend endpoint `POST /api/settings/autostart`:
- body `{"enabled": false}` → tray supervisor calls `mgr.uninstall()` (removes `.lnk`)
- body `{"enabled": true}` → calls `mgr.install()` (recreates `.lnk`)

Default state: enabled. Toggle is in Settings → System → "Запускать с Windows" (i18n).

### Edge WebView2 on Win 10

Win 11 ships Edge WebView2 Runtime preinstalled. Win 10 may not have it. Inno Setup needs to detect-and-install:

```inno
[Files]
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: {tmp}; Flags: deleteafterinstall

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; \
  Check: not WebView2RuntimeInstalled; StatusMsg: "Installing Edge WebView2 Runtime..."

[Code]
function WebView2RuntimeInstalled: Boolean;
var
  V: string;
begin
  Result := RegQueryStringValue(HKLM,
    'Software\Wow6432Node\Microsoft\EdgeUpdate\ClientState\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', V) and (V <> '');
end;
```

Bootstrap installer is ~200KB, downloads runtime if missing.

Mac: WKWebView is part of the OS since 10.10 — no install needed.
Linux: AppImage requires `webkit2gtk-4.0` runtime libs. Document the apt/dnf install in README; AppImage cannot bundle GTK reliably.

### CLI surface (new + changed)

| Command | Behavior |
|---|---|
| `mnemos launcher` | **NEW.** Open launcher window. If tray supervisor not running, spawn it (which spawns daemon). Single-instance guarded. |
| `mnemos tray run` | UNCHANGED. Run as supervisor (foreground). |
| `mnemos tray install` | UNCHANGED. Register autostart + spawn detached supervisor. |
| `mnemos tray uninstall` | UNCHANGED. Remove autostart + stop supervisor. |
| `mnemos init` | CHANGED. After hooks install + autostart register, instead of `webbrowser.open` it calls `mnemos launcher` (which opens the desktop window). |
| `mnemos doctor`, `mnemos hooks ...`, etc. | UNCHANGED. |

The Inno Setup `[Run]` postinstall step is also changed: instead of `tray run`, it calls `claude-mnemos.exe launcher` (which transparently starts tray + daemon + window). Symmetric for Mac DMG and Linux AppImage entry points.

### Process supervision details

Tray supervisor `Supervisor` class extension:

```python
# claude_mnemos/tray/supervisor.py (modified, ~80 LoC added)
class Supervisor:
    def __init__(self, daemon_pid_file, log_path):
        ...
        self.daemon_proc: subprocess.Popen | None = None
        self.launcher_proc: subprocess.Popen | None = None
        self.daemon_paused: bool = False
        self.restart_limiter = RestartLimiter(max_restarts=3, window_s=300)

    def start(self) -> None:
        self._start_daemon()
        # Launcher is NOT auto-started by supervisor — spawned on tray-click
        # OR explicitly by user opening the app. Default first-launch UX
        # (Inno [Run]) calls `mnemos launcher` which routes through here.

    def open_launcher(self) -> None:
        if self.launcher_proc and self.launcher_proc.poll() is None:
            # Send IPC "show" to existing launcher
            self._ipc_send("show")
            return
        self.launcher_proc = subprocess.Popen(
            [sys.executable, "-m", "claude_mnemos.launcher"],
            ...
        )

    def pause_daemon(self) -> None: ...
    def resume_daemon(self) -> None: ...
    def shutdown(self) -> None:
        # Quit menu item: stop launcher, stop daemon, release mutex.
        ...
```

Daemon is given a graceful 5s shutdown window (POST `/api/daemon/shutdown`) before SIGKILL.

---

## Testing

- **Unit:** `tests/test_single_instance.py` (Win mutex acquire/release, double-acquire returns False, IPC roundtrip).
- **Unit:** `tests/test_launcher.py` (splash → daemon URL navigation, daemon-down retry).
- **Unit:** `tests/test_tray_supervisor.py` (existing) + new tests for `open_launcher` IPC, `pause_daemon`, `shutdown`.
- **CI smoke:** `tests/installer/test_pyinstaller_smoke.py` extended with `test_bundle_launcher_spawns_window` (skipped when `DISPLAY` unavailable / on headless runners — for CI it's `skipif(headless)`). May be hard to assert window opened on CI; alternative: test that `mnemos launcher --no-window` exits 0 (a CI-friendly mode that initialises pywebview and exits before showing).
- **Live walk** on a fresh Win11 VM: success criteria 1–7 from above.

## Backwards compatibility

- All existing CLI commands continue to work.
- Existing `mnemos tray run` / `tray install` paths unchanged for power users / CI.
- `~/.claude-mnemos/install-state.json` schema gets a new optional field `window_close_action` (default null → ask first time). Existing files without it work fine.
- Frontend SPA unchanged. The launcher loads the exact same `index.html` from daemon.
- Hooks (`session-start`, `session-end`, `pre-compact`) — no change. They POST to `:5757` regardless of how the daemon was started.

## Risks

| Risk | Mitigation |
|---|---|
| Edge WebView2 Runtime install fails on Win 10 → window can't render | Document fallback: open browser at `:5757` if WebView2 missing. Detect via `pywebview.start()` raising. Show modal: "WebView2 not installed. Open in browser instead?" |
| WebKitGTK not installed on user's Linux distro → AppImage launcher fails | Document apt/dnf install in README. Fallback: `webbrowser.open` to `:5757`. Same logic as Win fallback. |
| pywebview adds ~10MB to bundle | Acceptable. Total bundle stays under 100MB. |
| Single-instance IPC named-pipe permission issues | Use `Local\\` not `Global\\` namespace on Win for per-user mutex (no admin needed). On Mac/Linux use `~/.claude-mnemos/tray.sock` with 0700 permissions. |
| Race between daemon-shutdown and launcher trying to load `:5757` (during quit) | Launcher polls health; on consistent connection-refused for >3s, shows "Daemon offline" splash with Quit/Restart buttons. |
| Tests of pywebview need a display | Headless mode flag `--no-window` initialises pywebview without showing the window — CI uses that. |
| Mnemos.lnk re-creation hammered into Mac/Linux LaunchAgent — drift between platforms | Already abstracted via `tray/platform/{windows,macos}.py`. Add Linux module for `~/.config/autostart/claude-mnemos.desktop`. |

## File structure

| File | Purpose | LoC |
|---|---|---|
| `claude_mnemos/launcher.py` (new) | pywebview window wrapper, splash, daemon-URL navigation, IPC client | ~180 |
| `claude_mnemos/tray/single_instance.py` (new) | Win named mutex / Mac+Linux fcntl flock — uniform interface | ~120 |
| `claude_mnemos/tray/ipc.py` (new) | Named pipe (Win) / Unix socket (Mac+Linux) for "show window" message | ~80 |
| `claude_mnemos/cli_launcher.py` (new) | `mnemos launcher` subcommand | ~50 |
| `claude_mnemos/tray/__main__.py` | Replace `_acquire_tray_lock` + `_release_tray_lock` with single_instance helpers. Add `_cmd_run` IPC server. | mod |
| `claude_mnemos/tray/supervisor.py` | Add `open_launcher`, `pause_daemon`, `resume_daemon`, `shutdown`, IPC server hook. | mod |
| `claude_mnemos/cli.py` | Register `add_launcher_subparser`. | mod |
| `claude_mnemos/cli_init.py` | Replace `webbrowser.open(DASHBOARD_URL)` with `subprocess.Popen([self_exe, "launcher"])`. | mod |
| `claude_mnemos/daemon/routes/settings.py` (or new `routes/system.py`) | New `POST /api/settings/autostart` endpoint. | mod |
| `frontend/src/pages/GlobalSettings.tsx` | Add "Запускать с Windows" toggle. | mod |
| `frontend/src/api/settings.api.ts` | `setAutostartEnabled(enabled: boolean)` mutation. | mod |
| `installer/windows/mnemos.iss` | Add WebView2 bootstrapper detection + install. Change `[Run]` from `tray run` → `launcher`. | mod |
| `installer/macos/setup.py` | Bundle pywebview. Change LaunchServices entry point if needed. | mod |
| `installer/linux/build-appimage.sh` | Document `webkit2gtk` runtime requirement. | mod |
| `installer/pyinstaller/mnemos.spec` | Add pywebview + clr_loader hidden imports; add WebView2 loader bin if Win. | mod |
| `pyproject.toml` | Add `pywebview>=5.4` to runtime dependencies. | mod |
| Tests | `test_single_instance.py`, `test_launcher.py`, supervisor tests | new |

---

## Phasing of the plan

The implementation plan (next step, written via writing-plans) will decompose into ~10–12 tasks:

1. `single_instance.py` (mutex + fcntl uniform interface)
2. `ipc.py` (named pipe / socket "show" message)
3. Replace tray PID lock with `single_instance`, add IPC server in supervisor
4. `launcher.py` (pywebview splash + nav, headless flag)
5. `mnemos launcher` subcommand
6. Window-close-to-tray dialog + state persistence
7. Tray-menu rewrite (Open / Status / Pause / Settings / Quit)
8. Backend `/api/settings/autostart` + frontend toggle
9. PyInstaller spec — pywebview hidden imports
10. Inno Setup WebView2 bootstrapper detection + Run-launcher swap + desktop-icon `checkedonce`
11. Mac DMG + Linux AppImage entry-point swap
12. Live walk + tests + documentation

---

## Out-of-scope (carried over from earlier phases)

- Code signing for installers.
- Sparkle/Squirrel auto-replace updater.
- Mobile app or web SaaS variant.
- Touching the daemon's HTTP transport (it stays as-is).

## Resolved decisions (Yarik 2026-05-05)

- **Tray icon**: required, visible always.
- **Autostart**: enabled by default (toggleable in Settings).
- **Launcher tech**: pywebview (E1), not full Tauri/Electron rewrite.
- **Release timing**: hold `v0.0.1` public release until E1 is shipped (option Y).
- **Interim daemon**: started manually now (option a) until E1 lands.
- **Desktop shortcut on Windows**: mandatory at install time. Inno Setup `[Tasks]` entry `desktopicon` switches from `unchecked` to `checkedonce` (default ON, opt-out checkbox available for power users). Shortcut launches `claude-mnemos.exe launcher`. Mac/Linux do not get desktop shortcuts (Mac uses Launchpad/Dock; Linux uses `.desktop` entry in `~/.local/share/applications/` via AppImage `--integrate`, no separate desktop file needed).

## Self-review notes

- Architecture diagram, file-by-file LoC estimate, and test strategy are concrete — no «TBD».
- Backwards compatibility section explicitly preserves all current CLI behaviour.
- Risks section lists fallback for the two highest-impact failure modes (WebView2 missing, WebKitGTK missing).
- Single-instance fix is named (Win mutex / fcntl flock) — concrete, not handwaved.
- Phasing has 12 tasks; each is self-contained.
- Out-of-scope list catches scope creep targets that have come up across the previous phases.
