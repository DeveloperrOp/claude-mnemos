"""Claude CLI binary discovery + auth preflight.

``find_claude_binary()`` is cross-platform: Unix uses ``shutil.which``;
Windows additionally checks ``%APPDATA%/npm/claude.{cmd,bat}`` because
``shutil.which`` may not pick up npm-global wrappers when PATHEXT is
configured unusually.

``check_claude_cli_auth()`` runs two probes:
1. ``claude --version`` — verifies installed binary.
2. ``claude -p "ok"`` — dry test that fails if user is not logged in.

Both calls timeout at 10s. If a corrupt binary hangs longer that's the
caller's problem; preflight is not the place to fight pathological cases.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from claude_mnemos.runtime import windowless_creationflags


@dataclass(frozen=True)
class AuthStatus:
    installed: bool
    authenticated: bool
    binary_path: str | None = None


def find_claude_binary() -> Path | None:
    found = shutil.which("claude")
    if found:
        return Path(found)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            for name in ("claude.cmd", "claude.bat"):
                cand = Path(appdata) / "npm" / name
                if cand.is_file():
                    return cand
    return None


def check_claude_cli_auth() -> AuthStatus:
    binary = find_claude_binary()
    if binary is None:
        return AuthStatus(installed=False, authenticated=False, binary_path=None)

    try:
        version_result = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=windowless_creationflags(),
        )
    except (subprocess.TimeoutExpired, OSError):
        return AuthStatus(installed=False, authenticated=False, binary_path=str(binary))

    if version_result.returncode != 0:
        return AuthStatus(installed=False, authenticated=False, binary_path=str(binary))

    # Dry test — minimal prompt. If authenticated, returns 0 quickly.
    try:
        dry_result = subprocess.run(
            [str(binary), "-p", "ok", "--max-turns", "1"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            input="",  # avoid hang on stdin
            creationflags=windowless_creationflags(),
        )
    except (subprocess.TimeoutExpired, OSError):
        return AuthStatus(installed=True, authenticated=False, binary_path=str(binary))

    authenticated = dry_result.returncode == 0
    return AuthStatus(installed=True, authenticated=authenticated, binary_path=str(binary))
