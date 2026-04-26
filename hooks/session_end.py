"""SessionEnd hook for claude-mnemos plugin.

Spawns a detached `mnemos ingest <transcript> <vault>` after every Claude Code
session, then exits immediately. Soft-skips on every error so the user is
never blocked.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

VAULT_ENV = "MNEMOS_VAULT_ROOT"
RECURSION_ENV = "MNEMOS_INGEST_RUNNING"


def _eprint(msg: str) -> None:
    print(f"mnemos: {msg}", file=sys.stderr)


def _spawn_ingest(transcript_path: Path, vault: str) -> None:
    cmd = [
        sys.executable,
        "-m",
        "claude_mnemos",
        "ingest",
        str(transcript_path),
        vault,
    ]
    env = {**os.environ, RECURSION_ENV: "1"}
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            creationflags=flags,
        )
    else:
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )


def main() -> int:
    if os.environ.get(RECURSION_ENV) == "1":
        return 0

    vault = os.environ.get(VAULT_ENV)
    if not vault:
        _eprint(f"{VAULT_ENV} not set; skipping auto-ingest")
        return 0

    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _eprint(f"invalid hook payload ({exc}); skipping")
        return 0

    transcript = payload.get("transcript_path")
    if not transcript or not isinstance(transcript, str):
        _eprint("no transcript_path in payload; skipping")
        return 0

    transcript_path = Path(transcript)
    if not transcript_path.is_file():
        _eprint(f"transcript {transcript} not found; skipping")
        return 0

    try:
        _spawn_ingest(transcript_path, vault)
    except OSError as exc:
        _eprint(f"failed to spawn ingest worker: {exc}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
