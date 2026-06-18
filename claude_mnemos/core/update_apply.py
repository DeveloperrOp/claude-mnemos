"""One-click self-update for the installed Windows portable-zip build (V2.1).

The daemon (running as the user, non-elevated) downloads + VALIDATES the
portable-zip BEFORE anything is killed, takes a single-flight lock (an
``O_EXCL`` ``swap.pending`` marker), then spawns — via WMI so it is NOT a child
of the daemon and survives the kill below — a non-elevated *outer* PowerShell:

  1. ``Start-Process -Verb RunAs -Wait`` an elevated *inner* swap script, which
     kills the running exes, EXTRACTS the validated zip into ``<install>.new``
     (a same-volume sibling of the install), then does two same-volume RENAMES:
     ``<install>`` -> ``<install>.old`` and ``<install>.new`` -> ``<install>``.
     On any error it renames ``<install>.old`` back. It never relaunches.
  2. Relaunches the tray as the (non-elevated) interactive user via a plain
     ``Start-Process``, then polls ``/api/version`` until the JSON ``version``
     equals the target; on success removes the backup + clears the marker.

SAFETY
------
* **Single-flight:** the ``swap.pending`` marker is created with ``O_EXCL``;
  a second concurrent apply is refused, so two inner scripts can never race and
  destroy each other's backup.
* **Same-volume atomic swap:** the new build is extracted into a sibling of the
  install dir, so BOTH the aside-rename and the swap-rename are metadata-only
  (never a cross-volume copy that could leave a half-built install).
* **Always-recoverable:** the backup ``<install>.old`` is created by rename and
  kept until the outer verifies the target version. Every failure leaves the
  old version, the new version, a clean rename-restore, or (rare hard-kill
  exactly between two renames) an install-absent state with the intact
  ``<install>.old`` recorded in the marker for manual recovery.

The real end-to-end swap cannot be auto-tested (needs a live frozen install;
dev is a venv where :func:`can_apply` refuses). Tests are mocked and assert on
the generated PowerShell TEXT; the scripts are also parse-checked with the real
PowerShell AST parser on Windows.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import re
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

logger = logging.getLogger(__name__)

WINDOWS_PORTABLE_ASSET = "claude-mnemos-portable-x64.zip"
PENDING_MARKER = "swap.pending"
# A marker older than this is treated as a stale leftover from a crashed run and
# may be superseded by a new apply.
STALE_MARKER_SECONDS = 30 * 60

_DEFAULT_DAEMON_URL = "http://127.0.0.1:5757"


class UpdateApplyError(Exception):
    """Raised when staging the update fails (download / validation / in-progress)."""


_VERSION_RE = re.compile(r"^[0-9][0-9A-Za-z.\-]{0,30}$")


def _validate_version(version: str) -> str:
    """Return a filesystem-safe version string or raise UpdateApplyError.

    Strips a leading 'v', then enforces a strict allowlist so a hostile
    release tag can't traverse out of the updates dir or inject into the
    generated PowerShell paths.
    """
    cleaned = version.lstrip("v").strip()
    if not _VERSION_RE.match(cleaned) or ".." in cleaned:
        raise UpdateApplyError(f"unsafe update version: {version!r}")
    return cleaned


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


def update_in_progress() -> bool:
    """True when a FRESH ``swap.pending`` marker exists (a swap is mid-flight).

    A stale marker (older than :data:`STALE_MARKER_SECONDS`, left by a crashed
    run) is not considered in-progress so a retry isn't blocked forever.
    """
    marker = pending_marker_path()
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        started = datetime.fromisoformat(data["started_at"])
    except (OSError, ValueError, KeyError):
        return False
    age = (datetime.now(UTC) - started).total_seconds()
    return age < STALE_MARKER_SECONDS


def download_and_validate(
    asset_url: str,
    version: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Path:
    """Download the portable zip and validate it BEFORE anything is killed.

    Validates it's a real zip containing ``claude-mnemos.exe`` and that the
    install volume has room for the extracted ``.new`` tree. The ELEVATED inner
    script does the actual extraction into ``<install>.new`` (same volume as the
    install, so the swap renames are atomic). Returns the staged zip path.
    """
    work = updates_dir() / version
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / "portable.zip"

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
        uncompressed = sum(i.file_size for i in zf.infolist())

    # The swap extracts a `.new` tree next to the install (~uncompressed) and
    # renames the live install to `.old` (free — a rename). Require headroom on
    # the INSTALL volume, where both siblings live.
    try:
        free = shutil.disk_usage(current_install_dir().anchor).free
    except OSError:
        free = None
    if free is not None and free < uncompressed + (50 << 20):  # + 50 MiB slack
        raise UpdateApplyError(
            f"insufficient free disk space on the install volume: need "
            f"~{uncompressed} bytes, have {free}"
        )
    return zip_path


def write_pending_marker(*, version: str, install_dir: Path, old_dir: Path) -> Path:
    """Atomically claim the single-flight lock + record the in-progress swap.

    Creates the marker with ``O_EXCL`` so a concurrent apply loses the race and
    gets :class:`UpdateApplyError`. A STALE marker (crashed run) is removed
    first so a retry isn't blocked forever.
    """
    marker = pending_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    if marker.exists() and not update_in_progress():
        marker.unlink(missing_ok=True)  # stale leftover — supersede it
    payload = json.dumps(
        {
            "version": version,
            "install_dir": str(install_dir),
            "old_dir": str(old_dir),
            "started_at": datetime.now(UTC).isoformat(),
        },
        indent=2,
    )
    try:
        with open(marker, "x", encoding="utf-8") as fh:  # O_EXCL — single flight
            fh.write(payload)
    except FileExistsError as exc:
        raise UpdateApplyError("an update is already in progress") from exc
    return marker


def render_inner_script(
    *,
    install_dir: Path,
    old_dir: Path,
    new_dir: Path,
    zip_path: Path,
    result_path: Path,
    version: str,
) -> str:
    """The ELEVATED inner script: kill -> extract to .new -> two same-volume
    renames -> restore-on-fail. No relaunch, no scheduled task."""
    inst = str(install_dir)
    old = str(old_dir)
    new = str(new_dir)
    zp = str(zip_path)
    result = str(result_path)
    return f"""\
$ErrorActionPreference = "Stop"
try {{
    Start-Sleep 2
    # No /T: kill only the named exes, NOT their child tree — the
    # (interactively-spawned) outer relaunch.ps1 is a child of the daemon, and
    # /T would take it down mid-swap, killing relaunch+verify+cleanup. /IM alone
    # still gets the supervisor + daemon + launcher (all claude-mnemos.exe).
    try {{ taskkill /F /IM claude-mnemos.exe }} catch {{ }}
    try {{ taskkill /F /IM claude-mnemos-cli.exe }} catch {{ }}
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {{
        if (-not (Get-Process claude-mnemos* -ErrorAction SilentlyContinue)) {{ break }}
        Start-Sleep 1
    }}

    # Clean leftovers from a prior aborted run (single-flight guarantees no
    # concurrent run owns these).
    if (Test-Path -LiteralPath "{old}") {{ Remove-Item -LiteralPath "{old}" -Recurse -Force }}
    if (Test-Path -LiteralPath "{new}") {{ Remove-Item -LiteralPath "{new}" -Recurse -Force }}

    # Extract the validated build into a SAME-VOLUME sibling of the install so
    # both swap steps below are metadata-only renames. The install is untouched
    # until both renames; an extract failure here leaves it fully intact.
    Expand-Archive -Path "{zp}" -DestinationPath "{new}" -Force
    if (-not (Test-Path -LiteralPath "{new}\\claude-mnemos.exe")) {{
        throw "extracted build is missing claude-mnemos.exe"
    }}

    # Atomic same-volume renames: aside the live install, then move the new in.
    Move-Item -LiteralPath "{inst}" -Destination "{old}"
    Move-Item -LiteralPath "{new}" -Destination "{inst}"
    if (-not (Test-Path -LiteralPath "{inst}\\claude-mnemos.exe")) {{
        throw "swap left no claude-mnemos.exe at the install path"
    }}
    "OK {version}" | Out-File -FilePath "{result}" -Encoding utf8
}}
catch {{
    $err = $_.Exception.Message
    # Discard a partial .new, then rename the backed-up old tree back into place.
    try {{
        if (Test-Path -LiteralPath "{new}") {{ Remove-Item -LiteralPath "{new}" -Recurse -Force }}
    }} catch {{ }}
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
    relaunch the tray as the user and verify the new build's version."""
    inst = str(install_dir)
    inner = str(inner_path)
    old = str(old_dir)
    marker = str(marker_path)
    result = str(result_path)
    url = daemon_url.rstrip("/")
    exe = f"{inst}\\claude-mnemos.exe"
    return f"""\
$ErrorActionPreference = "Continue"

# 1. Run the elevated swap and WAIT (this raises the single UAC prompt).
try {{
    Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList `
        @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',"{inner}")
}} catch {{ }}

# 2. If the elevated swap never ran (UAC declined / elevation failed) there is
#    no result.txt and the install is UNTOUCHED -> just relaunch the old build
#    and drop the marker; this is not a failed update.
if (-not (Test-Path -LiteralPath "{result}")) {{
    Remove-Item -LiteralPath "{marker}" -Force -ErrorAction SilentlyContinue
    Start-Process -FilePath "{exe}" -ArgumentList 'tray','run'
    return
}}

# 3. Relaunch the tray as THIS (non-elevated) user (array args, no quoting),
#    then verify the NEW build answers with the TARGET version. Retry the
#    launch a few times: the first `tray run` can lose the single-instance
#    race against a not-quite-dead old process and exit silently, which used
#    to leave the daemon down after a successful swap.
$ok = $false
$attempt = 0
while ($attempt -lt 3 -and -not $ok) {{
    $attempt++
    Start-Process -FilePath "{exe}" -ArgumentList 'tray','run'
    $deadline = (Get-Date).AddSeconds(30)
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
}}

if ($ok) {{
    if (Test-Path -LiteralPath "{old}") {{
        Remove-Item -LiteralPath "{old}" -Recurse -Force -ErrorAction SilentlyContinue
    }}
    Remove-Item -LiteralPath "{marker}" -Force -ErrorAction SilentlyContinue
}}
# else: leave the marker + backup for boot-time recovery + the failure banner.
"""


def stage_update(asset_url: str, version: str) -> Path:
    """Single-flight: validate+claim+write the marker + both PS scripts.

    Raises :class:`UpdateApplyError` if a fresh update is already in progress.
    """
    version = _validate_version(version)
    if update_in_progress():
        raise UpdateApplyError("an update is already in progress")

    install_dir = current_install_dir()
    old_dir = install_dir.parent / f"{install_dir.name}.old"
    new_dir = install_dir.parent / f"{install_dir.name}.new"

    # Claim the single-flight lock (O_EXCL) BEFORE the multi-second download so a
    # concurrent apply is refused immediately and can't race into the same dir.
    write_pending_marker(version=version, install_dir=install_dir, old_dir=old_dir)

    try:
        zip_path = download_and_validate(asset_url, version)
    except Exception:
        # Don't leave the lock claimed if we never staged anything.
        pending_marker_path().unlink(missing_ok=True)
        raise

    work = zip_path.parent
    inner_path = work / "swap.ps1"
    outer_path = work / "relaunch.ps1"
    result_path = work / "result.txt"

    inner_path.write_text(
        render_inner_script(
            install_dir=install_dir,
            old_dir=old_dir,
            new_dir=new_dir,
            zip_path=zip_path,
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
    """Launch the outer updater script in the user's INTERACTIVE session.

    A plain child ``Popen`` from the daemon inherits the interactive window
    station, so the outer's ``Start-Process -Verb RunAs`` raises a UAC prompt
    the user actually SEES. (The old WMI ``Win32_Process.Create`` path ran the
    outer under the WMI host's non-interactive station, so the prompt never
    surfaced — and WDAC blocks ``Win32_Process.Create`` outright.)

    The outer is a child of the daemon, but the inner swap kills the daemon
    WITHOUT ``/T``, so this powershell survives to relaunch + verify + cleanup.
    ``DETACHED_PROCESS`` detaches only the console (not the window station), so
    UAC visibility is unaffected; ``CREATE_NO_WINDOW`` keeps a console from
    flashing.
    """
    outer = str(work_dir / "relaunch.ps1")
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
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
    logger.info("[update] outer relaunch.ps1 spawned (interactive)")
