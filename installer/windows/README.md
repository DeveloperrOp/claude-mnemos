# Windows installer

## Prerequisites

- Python 3.12+ via pipx (for the PyInstaller bundle build)
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) installed at the default path
  (`C:\Program Files (x86)\Inno Setup 6\`)

## Build

From the repo root in PowerShell:

```
.\installer\windows\build.ps1
```

This runs PyInstaller (producing `dist/claude-mnemos/`) then Inno Setup
(producing `installer/windows/dist/claude-mnemos-setup-x64.exe`).

The output is ~70MB compressed. Per-user or system install. Autostart
task is default-on; Start Menu and (optional) desktop shortcuts are
created. Uninstall stops the daemon, removes autostart, and uninstalls
hooks before file deletion.

## CI

The release workflow (`.github/workflows/release.yml`) installs Inno Setup
via Chocolatey on the `windows-latest` runner and runs ISCC there — no
local Inno install is needed for releases.

## Code signing

Initial release ships unsigned. Users will see a SmartScreen warning on
first launch ("Windows protected your PC"). They click *More info →
Run anyway*. We will sign the installer once we have an EV code-signing
certificate (deferred from the initial release).
