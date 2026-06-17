"""One-click self-update for the installed Windows portable-zip build.

This module downloads the portable-zip release asset, stages it under
``~/.claude-mnemos/updates/<version>/`` together with a generated
``updater.ps1`` script, and spawns an elevated PowerShell to perform the swap.

SAFETY INVARIANT
----------------
Any failure of the swap MUST leave the prior working install intact. The
generated updater script backs up the install directory **before** touching
it and restores that backup on ANY error (or if the new build fails to
launch). The backup is kept until the very end of the script -- never deleted
inside it.

The real end-to-end swap cannot be auto-tested: it needs a live frozen
install. On the dev box ``runtime.is_frozen()`` is False, so :func:`can_apply`
refuses and the apply endpoint returns 409. All tests are mocked; the
correctness of the generated PowerShell is verified by asserting on its TEXT.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from claude_mnemos import runtime

WINDOWS_PORTABLE_ASSET = "claude-mnemos-portable-x64.zip"

# The relaunch task name and the daemon URL used by the verify step.
_RELAUNCH_TASK = "ClaudeMnemosRelaunch"
_DEFAULT_DAEMON_URL = "http://127.0.0.1:5757"


class UpdateApplyError(Exception):
    """Raised when staging the update fails (download / validation)."""


def can_apply() -> tuple[bool, str]:
    """Return ``(True, "")`` only on the installed Windows build.

    In-app update swaps a real install directory in place via an elevated
    PowerShell; that only makes sense when running as a frozen exe on Windows.
    In every other context (dev venv, macOS, Linux) we refuse with a
    human-readable reason so the caller can surface it.
    """
    if not runtime.is_frozen() or sys.platform != "win32":
        return (
            False,
            "in-app update only available on the installed Windows build",
        )
    return (True, "")


def updates_dir() -> Path:
    """Directory where downloaded updates are staged."""
    return Path.home() / ".claude-mnemos" / "updates"


def current_install_dir() -> Path:
    """The directory holding the running ``claude-mnemos.exe``."""
    return runtime.executable_path().parent


def current_username() -> str:
    """Best-effort interactive username for the relaunch scheduled task."""
    try:
        return os.getlogin()
    except OSError:
        return getpass.getuser()


def download_and_stage(
    asset_url: str,
    version: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Path:
    """Download ``asset_url`` to ``updates_dir()/<version>/portable.zip``.

    Validates the payload is a real zip containing ``claude-mnemos.exe``;
    raises :class:`UpdateApplyError` otherwise. Returns the staged zip path.
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
        names = {Path(n).name for n in zf.namelist()}
    if "claude-mnemos.exe" not in names:
        raise UpdateApplyError(
            "downloaded zip does not contain claude-mnemos.exe"
        )

    return zip_path


def _ps_quote(value: str) -> str:
    """Quote a value for embedding inside a PowerShell double-quoted string.

    The paths we bake in (install dir, work dir, username) are local
    filesystem strings; escape the double-quote and backtick that would break
    out of the literal. We deliberately keep ``\\`` untouched -- PowerShell
    double-quoted strings treat backslash literally.
    """
    return value.replace("`", "``").replace('"', '`"')


def render_updater_script(
    *,
    install_dir: Path,
    work_dir: Path,
    zip_path: Path,
    username: str,
    version: str,
    daemon_url: str = _DEFAULT_DAEMON_URL,
) -> str:
    """Return the ``updater.ps1`` TEXT with parameters baked in as literals.

    The script, with a top-level try/catch that RESTORES the backup on any
    failure, performs in order: kill the running exes, back up the install
    dir, extract the new build, sanity-gate, swap, relaunch as the interactive
    user (non-elevated) via a one-shot scheduled task, then verify the daemon
    answers ``/api/version``. The catch restores the backup and relaunches the
    restored build. ``result.txt`` records the outcome.
    """
    inst = _ps_quote(str(install_dir))
    work = _ps_quote(str(work_dir))
    zp = _ps_quote(str(zip_path))
    user = _ps_quote(username)
    ver = _ps_quote(version)
    url = _ps_quote(daemon_url.rstrip("/"))

    backup = f"{work}\\backup"
    extract = f"{work}\\extract"
    result = f"{work}\\result.txt"
    exe = f"{inst}\\claude-mnemos.exe"

    # Every command below bakes the resolved path in as a quoted literal so the
    # generated script is self-contained (and so its safety-critical lines are
    # assertable in tests). Paths are quoted; the username is interpolated into
    # the schtasks /RU literal.
    return f"""\
$ErrorActionPreference = "Stop"

$TaskName = "{_RELAUNCH_TASK}"

$TaskRun  = "\\"{exe}\\" tray run"

function Invoke-Relaunch {{
    # Relaunch the tray as the interactive user (NOT elevated) via a one-shot
    # scheduled task, then delete the task.
    $when = (Get-Date).AddSeconds(15).ToString("HH:mm")
    schtasks /Create /TN "$TaskName" /TR "$TaskRun" /SC ONCE /ST $when /RU "{user}" /IT /F
    schtasks /Run /TN "$TaskName"
    Start-Sleep 5
    schtasks /Delete /TN "$TaskName" /F
}}

try {{
    # 1. Wait for the daemon (which spawned us) to be killable, then kill both
    #    front-end exes. The daemon that launched this updater is one of these
    #    and will die here.
    Start-Sleep 2
    try {{ taskkill /F /IM claude-mnemos.exe /T }} catch {{ }}
    try {{ taskkill /F /IM claude-mnemos-cli.exe /T }} catch {{ }}

    # Poll up to ~15s until no claude-mnemos process remains.
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {{
        $procs = Get-Process claude-mnemos -ErrorAction SilentlyContinue
        if (-not $procs) {{ break }}
        Start-Sleep 1
    }}

    # 2. Backup the CURRENT install BEFORE touching anything (safety invariant).
    robocopy "{inst}" "{backup}" /E /NFL /NDL /NJH /NJS /R:2 /W:1
    if ($LASTEXITCODE -gt 7) {{ throw "backup failed (robocopy exit $LASTEXITCODE)" }}

    # 3. Extract the new build into a staging dir.
    Expand-Archive -Path "{zp}" -DestinationPath "{extract}" -Force

    # 4. Sanity gate: the extracted build must contain the exe.
    if (-not (Test-Path "{extract}\\claude-mnemos.exe")) {{
        throw "extracted build is missing claude-mnemos.exe"
    }}

    # 5. Swap: copy the new build over the install dir. No mirror flag -- the
    #    swap merges files and never purges files absent from the new build.
    robocopy "{extract}" "{inst}" /E /R:2 /W:1
    if ($LASTEXITCODE -gt 7) {{ throw "swap failed (robocopy exit $LASTEXITCODE)" }}

    # 6. Relaunch the freshly-swapped tray as the interactive user.
    Invoke-Relaunch

    # 7. Verify the new daemon answers within ~30s; otherwise treat as failure.
    $ok = $false
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {{
        try {{
            $resp = Invoke-WebRequest "{url}/api/version" -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -eq 200) {{ $ok = $true; break }}
        }} catch {{ }}
        Start-Sleep 2
    }}
    if (-not $ok) {{ throw "new build did not answer {url}/api/version" }}

    # 8. Success.
    "OK {ver}" | Out-File -FilePath "{result}" -Encoding utf8
}}
catch {{
    # RESTORE: copy the backup back over the install dir, then relaunch the
    # restored build so the user is never left without a running app
    # (safety invariant — any failure leaves the prior install intact).
    $err = $_.Exception.Message
    try {{
        if (Test-Path "{backup}") {{
            robocopy "{backup}" "{inst}" /E /R:2 /W:1
        }}
    }} catch {{ }}
    try {{ Invoke-Relaunch }} catch {{ }}
    "FAILED: $err" | Out-File -FilePath "{result}" -Encoding utf8
}}
"""


def stage_update(asset_url: str, version: str) -> Path:
    """Download + validate the asset and write ``updater.ps1`` beside it.

    Returns the work directory (``updates_dir()/<version>/``).
    """
    zip_path = download_and_stage(asset_url, version)
    work = zip_path.parent
    script = render_updater_script(
        install_dir=current_install_dir(),
        work_dir=work,
        zip_path=zip_path,
        username=current_username(),
        version=version,
    )
    (work / "updater.ps1").write_text(script, encoding="utf-8")
    return work


def spawn_updater(work_dir: Path) -> None:
    """Spawn a non-elevated PowerShell that elevates and runs ``updater.ps1``.

    The outer (non-elevated) process uses ``Start-Process -Verb RunAs`` to
    re-launch PowerShell elevated against the staged script. We detach it so
    it survives the death of this daemon (which the script taskkills).
    """
    script_path = str(work_dir / "updater.ps1")
    inner_args = (
        "@('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden',"
        f"'-File','{script_path}')"
    )
    outer_command = (
        "Start-Process powershell -Verb RunAs -WindowStyle Hidden "
        f"-ArgumentList {inner_args}"
    )

    creationflags = 0
    if sys.platform == "win32":
        # Guard the win-only flags so the module imports on non-win for tests.
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )

    subprocess.Popen(  # noqa: S603 — fixed argv, no shell
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            outer_command,
        ],
        creationflags=creationflags,
    )
