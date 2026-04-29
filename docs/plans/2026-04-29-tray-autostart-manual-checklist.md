# Tray + Autostart — Manual Integration Checklist

These checks cannot run in CI (require display, real OS autostart, reboot). Run them by hand on Win11 (and macOS if available) after merge.

## Windows 11

- [ ] `pip install -e .` succeeds (run from project root, may require `--user` if system-level Python).
- [ ] `mnemos-tray --help` prints subcommands.
- [ ] `mnemos tray install` creates `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Mnemos.lnk` (verify in File Explorer).
- [ ] Tray icon appears (right of taskbar). Right-click → menu has Open dashboard / Restart daemon / Show logs / Quit.
- [ ] Open Settings → Apps → Startup. "Mnemos" appears in the list, toggle works.
- [ ] Reboot. After login, tray icon appears within ~10s; `curl http://localhost:5757/health` → 200.
- [ ] Open Task Manager → find Python process running daemon. End it forcibly (Stop-Process / End Task) → wait 5s → daemon respawns; `~/.claude-mnemos/supervisor.log` shows the crash + restart entries.
- [ ] Force-stop the daemon 4× rapidly (within ~1min) → tray icon turns red, tooltip says "crashed". Restart from menu works.
- [ ] `mnemos tray uninstall` removes the .lnk. Tray keeps running. `mnemos tray status` reports `autostart_enabled=false`.
- [ ] Reboot. Tray does NOT start. `curl http://localhost:5757/health` fails (no daemon).
- [ ] Onboarding wizard at fresh install: checkbox visible, defaults to checked, on Done invokes `/tray/install`.

## macOS

- [ ] `pip install -e .` succeeds.
- [ ] `mnemos tray install` creates `~/Library/LaunchAgents/com.claude-mnemos.tray.plist`. `launchctl list | grep claude-mnemos` → entry visible.
- [ ] Tray icon appears in menu bar. Menu items match Win.
- [ ] Logout / login. Icon appears, daemon up.
- [ ] `kill -9 <daemon_pid>` → respawn within seconds (visible in `~/.claude-mnemos/supervisor.log`).
- [ ] `mnemos tray uninstall` → `launchctl list | grep claude-mnemos` → empty. Plist deleted.
- [ ] Logout / login. No tray, no daemon.

## Common

- [ ] Onboarding wizard does NOT show autostart checkbox on Linux (test in any Linux env — `/tray/status` returns `platform=linux` and frontend hides the field).
- [ ] `GET /tray/status` returns sane JSON in browser (open dashboard → DevTools).
- [ ] `mnemos tray install` while tray is running: idempotent, prints "Auto-start installed", no second tray spawned (verify `~/.claude-mnemos/tray.pid` unchanged).
- [ ] Adopted daemon protection: launch daemon manually via `mnemos daemon start`, then launch tray separately via `mnemos tray run`. The tray "adopts" the existing daemon (visible in supervisor.log). Quit from tray menu must NOT kill the adopted daemon — verify `mnemos daemon status` still reports it running.

## Restart-loop limiter

- [ ] Crash 3× within 5 minutes — supervisor restarts each time with backoff (1s, 2s, 4s).
- [ ] Crash 4× within 5 minutes — supervisor enters Crashed state. Tray icon turns red. Manual Restart from menu works (clears the counter).
