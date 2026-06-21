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
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{cmd[0]} failed: {exc}"
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode == 0, out


def git_pull() -> tuple[bool, str]:
    """Fast-forward the checkout. Returns ``(ok, combined_output)``."""
    root = repo_root()
    if root is None:
        return False, "not a git checkout"
    return _run(["git", "pull", "--ff-only"], root, timeout=120)


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
