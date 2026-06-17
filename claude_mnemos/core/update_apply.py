"""One-click self-update for the installed Windows portable-zip build (V2).

The daemon (running as the user, non-elevated) downloads + EXTRACTS + validates
the portable-zip BEFORE anything is killed, writes a ``swap.pending`` marker,
then spawns a non-elevated *outer* PowerShell that:

  1. ``Start-Process -Verb RunAs -Wait`` an elevated *inner* swap script, which
     kills the running exes and does an atomic, rename-based swap (move the live
     install aside to ``<install>.old``, move the freshly-extracted build into
     place). On any error it restores ``<install>.old``. It never relaunches.
  2. Relaunches the tray as the (non-elevated) interactive user via a plain
     ``Start-Process`` — no scheduled task, no nested-quote hell.
  3. Polls ``/api/version`` until the JSON ``version`` equals the target; on
     success removes ``<install>.old`` and clears the marker. Otherwise it
     leaves both for boot-time recovery + a failure banner.

SAFETY
------
Every failure leaves a *recoverable* state: the old version running, the new
version running, a clean rename-restore from ``<install>.old``, or (rare
hard-kill exactly between the two renames) an install-absent state with the
intact ``<install>.old`` backup recorded in the marker. The swap is a
directory rename, not a per-file merge, so an interruption never produces a
half-old/half-new PyInstaller "frankenbuild" (which would fail to start).

The real end-to-end swap cannot be auto-tested (needs a live frozen install;
dev is a venv where :func:`can_apply` refuses). Tests are mocked and assert on
the generated PowerShell TEXT.
"""

from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claude_mnemos import runtime

WINDOWS_PORTABLE_ASSET = "claude-mnemos-portable-x64.zip"
PENDING_MARKER = "swap.pending"

_DEFAULT_DAEMON_URL = "http://127.0.0.1:5757"


class UpdateApplyError(Exception):
    """Raised when staging the update fails (download / extract / disk space)."""


def can_apply() -> tuple[bool, str]:
    """``(True, "")`` only on the installed Windows build; else ``(False, reason)``."""
    if not runtime.is_frozen() or sys.platform != "win32":
        return (
            False,
            "in-app update only available on the installed Windows build",
        )
    return (True, "")


def updates_dir() -> Path:
    return Path.home() / ".claude-mnemos" / "updates"


def pending_marker_path() -> Path:
    return updates_dir() / PENDING_MARKER


def current_install_dir() -> Path:
    """The directory holding the running ``claude-mnemos.exe``."""
    return runtime.executable_path().parent


def current_username() -> str:
    try:
        return os.getlogin()
    except OSError:
        return getpass.getuser()


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def download_and_extract(
    asset_url: str,
    version: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Path:
    """Download + validate + EXTRACT the portable zip BEFORE anything is killed.

    Returns the work dir ``updates_dir()/<version>/`` containing ``portable.zip``
    and an ``extract/`` tree validated to hold ``claude-mnemos.exe``. Raises
    :class:`UpdateApplyError` on a bad download / invalid zip / missing exe /
    insufficient free disk space. Doing all this in Python (not the elevated
    PowerShell) means a bad download never touches the running install.
    """
    work = updates_dir() / version
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / "portable.zip"
    extract_dir = work / "extract"

    req = urllib.request.Request(  # noqa: S310 — URL comes from our own release feed
        asset_url,
        headers={"User-Agent": "claude-mnemos"},
    )
    try:
        with opener(req) as resp, zip_path.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
    except OSError as exc:
        raise UpdateApplyError(f"download failed: {exc}") from exc

    if not zipfile.is_zipfile(zip_path):
        raise UpdateApplyError("downloaded asset is not a valid zip")
    with zipfile.ZipFile(zip_path) as zf:
        if "claude-mnemos.exe" not in {Path(n).name for n in zf.namelist()}:
            raise UpdateApplyError("downloaded zip does not contain claude-mnemos.exe")
        # Free-space precheck: the swap needs room for the extracted tree plus a
        # rename-aside of the live install. Require ~2x the uncompressed size
        # free on the install volume before we extract or touch anything.
        uncompressed = sum(i.file_size for i in zf.infolist())
        try:
            free = shutil.disk_usage(current_install_dir().anchor).free
        except OSError:
            free = None
        if free is not None and free < uncompressed * 2:
            raise UpdateApplyError(
                f"insufficient free disk space: need ~{uncompressed * 2} bytes, "
                f"have {free}"
            )
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
        zf.extractall(extract_dir)

    if not (extract_dir / "claude-mnemos.exe").is_file():
        raise UpdateApplyError("extracted build is missing claude-mnemos.exe")
    return work


def write_pending_marker(*, version: str, install_dir: Path, old_dir: Path) -> Path:
    """Record an in-progress swap so a boot after an interruption can reconcile."""
    marker = pending_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "version": version,
                "install_dir": str(install_dir),
                "old_dir": str(old_dir),
                "started_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return marker


def render_inner_script(
    *,
    install_dir: Path,
    old_dir: Path,
    extract_dir: Path,
    result_path: Path,
    version: str,
) -> str:
    """The ELEVATED inner swap script: kill -> rename-swap -> restore-on-fail.

    No relaunch (the outer script does that, non-elevated). No scheduled task,
    no nested quoting. Paths are baked into PowerShell double-quoted literals;
    the only metacharacters in real install paths are spaces, which are fine
    inside double quotes.
    """
    inst = str(install_dir)
    old = str(old_dir)
    extract = str(extract_dir)
    result = str(result_path)
    return f"""\
$ErrorActionPreference = "Stop"
try {{
    # Give the daemon that spawned this a moment, then kill all roles. The
    # wildcard matches BOTH claude-mnemos.exe and claude-mnemos-cli.exe.
    Start-Sleep 2
    try {{ taskkill /F /IM claude-mnemos.exe /T }} catch {{ }}
    try {{ taskkill /F /IM claude-mnemos-cli.exe /T }} catch {{ }}
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {{
        if (-not (Get-Process claude-mnemos* -ErrorAction SilentlyContinue)) {{ break }}
        Start-Sleep 1
    }}

    # Clean any stale aside-dir from a previous aborted run.
    if (Test-Path -LiteralPath "{old}") {{ Remove-Item -LiteralPath "{old}" -Recurse -Force }}

    # Atomic, rename-based swap. On the same volume these are metadata-only
    # renames, so an interruption leaves the whole old tree, the whole new tree,
    # or (briefly) no install dir -- never a half-old/half-new frankenbuild.
    Move-Item -LiteralPath "{inst}" -Destination "{old}"
    Move-Item -LiteralPath "{extract}" -Destination "{inst}"
    if (-not (Test-Path -LiteralPath "{inst}\\claude-mnemos.exe")) {{
        throw "swap left no claude-mnemos.exe at the install path"
    }}
    "OK {version}" | Out-File -FilePath "{result}" -Encoding utf8
}}
catch {{
    $err = $_.Exception.Message
    # RESTORE: whatever partial state the install is in, replace it with the
    # backed-up old tree (a clean rename-back -- never a merge).
    try {{
        if (Test-Path -LiteralPath "{old}") {{
            if (Test-Path -LiteralPath "{inst}") {{
                Remove-Item -LiteralPath "{inst}" -Recurse -Force
            }}
            Move-Item -LiteralPath "{old}" -Destination "{inst}"
        }}
    }} catch {{ }}
    "FAILED: $err" | Out-File -FilePath "{result}" -Encoding utf8
}}
"""


def render_outer_script(
    *,
    install_dir: Path,
    inner_path: Path,
    old_dir: Path,
    marker_path: Path,
    result_path: Path,
    version: str,
    daemon_url: str = _DEFAULT_DAEMON_URL,
) -> str:
    """The NON-elevated outer script run as the user: elevate-and-wait, then
    relaunch the tray as the user and verify the new build reports the target
    version. On success it removes the backup + clears the marker.
    """
    inst = str(install_dir)
    inner = str(inner_path)
    old = str(old_dir)
    marker = str(marker_path)
    result = str(result_path)
    url = daemon_url.rstrip("/")
    exe = f"{inst}\\claude-mnemos.exe"
    return f"""\
$ErrorActionPreference = "Continue"

# 1. Run the elevated swap and WAIT for it (this raises the single UAC prompt).
Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList `
    @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',"{inner}")

# 2. Relaunch the tray as THIS (non-elevated) interactive user. ArgumentList is
#    an array, so the spaced exe path needs no manual quoting.
Start-Process -FilePath "{exe}" -ArgumentList 'tray','run'

# 3. Verify the NEW build answers with the target version (not just any 200 --
#    a lingering old process must not false-pass).
$ok = $false
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {{
    try {{
        $r = Invoke-WebRequest "{url}/api/version" -UseBasicParsing -TimeoutSec 5
        if ($r.StatusCode -eq 200) {{
            $v = ($r.Content | ConvertFrom-Json).version
            if ($v -eq "{version}") {{ $ok = $true; break }}
        }}
    }} catch {{ }}
    Start-Sleep 2
}}

if ($ok) {{
    # Success: drop the backup + clear the pending marker.
    if (Test-Path -LiteralPath "{old}") {{
        Remove-Item -LiteralPath "{old}" -Recurse -Force -ErrorAction SilentlyContinue
    }}
    Remove-Item -LiteralPath "{marker}" -Force -ErrorAction SilentlyContinue
}}
# else: leave the marker + backup for boot-time recovery + the failure banner.
# The result.txt the inner script wrote records OK/FAILED either way.
$null = "{result}"
"""


def stage_update(asset_url: str, version: str) -> Path:
    """Download+extract+validate, write the marker + both PS scripts. Returns work dir."""
    work = download_and_extract(asset_url, version)
    install_dir = current_install_dir()
    old_dir = install_dir.parent / f"{install_dir.name}.old"
    extract_dir = work / "extract"
    inner_path = work / "swap.ps1"
    outer_path = work / "relaunch.ps1"
    result_path = work / "result.txt"

    write_pending_marker(version=version, install_dir=install_dir, old_dir=old_dir)

    inner_path.write_text(
        render_inner_script(
            install_dir=install_dir,
            old_dir=old_dir,
            extract_dir=extract_dir,
            result_path=result_path,
            version=version,
        ),
        encoding="utf-8",
    )
    outer_path.write_text(
        render_outer_script(
            install_dir=install_dir,
            inner_path=inner_path,
            old_dir=old_dir,
            marker_path=pending_marker_path(),
            result_path=result_path,
            version=version,
        ),
        encoding="utf-8",
    )
    return work


def spawn_updater(work_dir: Path) -> None:
    """Spawn the NON-elevated outer script, detached so it survives the daemon's
    death (the inner script taskkills claude-mnemos.exe; the outer is
    powershell.exe and DETACHED, so neither ``/IM`` nor ``/T`` reaches it)."""
    outer = str(work_dir / "relaunch.ps1")
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    subprocess.Popen(  # noqa: S603 — fixed argv, no shell
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            outer,
        ],
        creationflags=creationflags,
    )
