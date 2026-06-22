"""Source-mode (git checkout) self-update: ``git pull`` + frontend rebuild.

The frozen-exe updater (:mod:`claude_mnemos.core.update_apply`) swaps in a new
binary, which Smart App Control blocks on locked-down machines. When the daemon
runs from a git checkout under a signed Python, updating is just ``git pull`` +
``npm run build``; the daemon then restarts (the tray respawns it) to load the
new code. No new unsigned binary, so nothing for SAC to block.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from claude_mnemos import runtime


def repo_root() -> Path | None:
    """The git checkout root when running from source, else ``None``."""
    if runtime.is_frozen():
        return None
    root = runtime.bundle_root()
    return root if (root / ".git").exists() else None


def can_git_pull() -> bool:
    """True when an in-place ``git pull`` update is possible (source checkout)."""
    return repo_root() is not None


def _run(cmd: list[str], cwd: Path, timeout: float) -> tuple[bool, str]:
    # The daemon runs windowless (pythonw); spawning a console exe (git) without
    # CREATE_NO_WINDOW can fail to allocate a console and exit non-zero with no
    # captured output. The flag runs it cleanly without a console.
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=creationflags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{cmd[0]} failed to start: {exc}"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0 and not out:
        out = f"{cmd[0]} exited with code {proc.returncode}"
    return proc.returncode == 0, out


def display_version() -> str:
    """A meaningful version string for a source checkout: ``git describe`` (e.g.
    ``v0.0.70-6-gabc123``). Falls back to ``__version__`` (frozen builds rewrite
    it from the tag at build time; source keeps the placeholder ``0.0.1``)."""
    from claude_mnemos import __version__

    root = repo_root()
    if root is None:
        return __version__
    ok, out = _run(
        ["git", "describe", "--tags", "--always", "--dirty"], root, timeout=15
    )
    out = out.strip()
    return out if ok and out else __version__


def current_branch(root: Path) -> str:
    """The checked-out branch name, or ``main`` if detached/unknown."""
    ok, name = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root, timeout=15)
    name = name.strip()
    return name if ok and name and name != "HEAD" else "main"


def git_pull() -> tuple[bool, str]:
    """Fast-forward the checkout. Returns ``(ok, combined_output)``.

    Pulls ``origin <branch>`` explicitly so it works even when the branch has no
    upstream configured (a re-inited .git frequently has none)."""
    root = repo_root()
    if root is None:
        return False, "not a git checkout"
    branch = current_branch(root)
    return _run(["git", "pull", "--ff-only", "origin", branch], root, timeout=120)


def restart_daemon_detached() -> None:
    """Restart the daemon without relying on a supervisor (tray-less Python run).

    A detached helper waits for the response to flush, kills EVERY running
    claude_mnemos daemon (the environment can spawn a duplicate that would keep
    the port held), then ``daemon start`` brings a fresh one up on the new code.
    Windows-only: the source/Python install is the Smart-App-Control workaround
    there, and the dashboard polls /api/version until the new daemon answers.
    """
    if sys.platform != "win32":
        return
    root = repo_root()
    if root is None:
        return
    python = sys.executable
    ps = (
        "Start-Sleep -Seconds 2; "
        "Get-CimInstance Win32_Process | Where-Object { "
        "($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') "
        "-and $_.CommandLine -match 'claude_mnemos.daemon' } | "
        "ForEach-Object { taskkill /F /PID $_.ProcessId 2>$null }; "
        "Start-Sleep -Seconds 2; "
        f"& '{python}' -m claude_mnemos daemon start"
    )
    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NO_WINDOW", 0
    )
    subprocess.Popen(  # noqa: S603 — fixed argv, no shell injection (python is ours)
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )


def frontend_build() -> tuple[bool, str]:
    """Rebuild the dashboard into ``daemon/static``. Returns ``(ok, output)``."""
    root = repo_root()
    if root is None:
        return False, "not a git checkout"
    frontend = root / "frontend"
    if not frontend.exists():
        return True, "no frontend to build"
    # cmd.exe so npm.cmd resolves on PATH under Windows; plain npm elsewhere.
    cmd = ["cmd", "/c", "npm", "run", "build"] if sys.platform == "win32" else [
        "npm",
        "run",
        "build",
    ]
    return _run(cmd, frontend, timeout=300)
