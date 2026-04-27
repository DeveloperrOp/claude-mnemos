"""SessionEnd hook for claude-mnemos plugin.

Tries POST /jobs to the local mnemos daemon first (queue mode, Plan #11). If
the daemon is offline or returns non-2xx, falls back to spawning a detached
``mnemos ingest <transcript> <vault>`` subprocess (Plan #7 behavior). Either
way the hook soft-skips on every error and exits 0 so the user is never
blocked.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

VAULT_ENV = "MNEMOS_VAULT_ROOT"
RECURSION_ENV = "MNEMOS_INGEST_RUNNING"
DAEMON_URL_ENV = "MNEMOS_DAEMON_URL"
DEFAULT_DAEMON_URL = "http://127.0.0.1:5757"
DAEMON_POST_TIMEOUT_S = 2.0


def _eprint(msg: str) -> None:
    print(f"mnemos: {msg}", file=sys.stderr)


def _try_post_to_daemon(daemon_url: str, transcript_path: Path) -> bool:
    """POST the ingest job to the daemon. Return True iff queued (2xx)."""
    try:
        response = httpx.post(
            f"{daemon_url.rstrip('/')}/jobs",
            json={
                "kind": "ingest",
                "payload": {"transcript_path": str(transcript_path)},
            },
            timeout=DAEMON_POST_TIMEOUT_S,
        )
    except Exception:
        return False
    return 200 <= response.status_code < 300


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

    daemon_url = os.environ.get(DAEMON_URL_ENV, DEFAULT_DAEMON_URL)
    if _try_post_to_daemon(daemon_url, transcript_path):
        return 0

    try:
        _spawn_ingest(transcript_path, vault)
    except OSError as exc:
        _eprint(f"failed to spawn ingest worker: {exc}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
