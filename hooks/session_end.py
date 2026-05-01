"""SessionEnd hook for claude-mnemos plugin.

Resolves the project for the current cwd via ``ProjectResolver`` (project-map
lives in ``~/.claude-mnemos/project-map.json``). On match, POSTs the ingest
job to the local mnemos daemon (port read from ``GlobalSettings``); on daemon
failure falls back to a detached ``mnemos ingest <t> --project NAME``
subprocess. Hook never blocks: returns 0 unconditionally.

Skip conditions (silent, stderr message, returncode 0):
- Recursion guard (``MNEMOS_INGEST_RUNNING=1``)
- Invalid stdin payload / missing transcript_path
- Resolver ambiguity (config bug — surfaces in stderr)
- cwd not in project-map (Plan #13a's lost-sessions scanner picks it up later)
- Daemon offline AND subprocess fallback OSError
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Hook lives outside the package; allow it to import claude_mnemos.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from claude_mnemos.hooks.errors import (  # noqa: E402
    install_excepthook,
    record_exception,
)

install_excepthook("session_end")

from claude_mnemos.mapping.resolver import (  # noqa: E402
    ProjectResolver,
    ResolverAmbiguityError,
)
from claude_mnemos.state.settings import SettingsStore  # noqa: E402

RECURSION_ENV = "MNEMOS_INGEST_RUNNING"
DAEMON_URL_ENV = "MNEMOS_DAEMON_URL"
DEFAULT_DAEMON_PORT = 5757
DAEMON_POST_TIMEOUT_S = 2.0


def _eprint(msg: str) -> None:
    print(f"mnemos: {msg}", file=sys.stderr)


def _daemon_port() -> int:
    try:
        return SettingsStore().get_global().daemon_port
    except Exception:  # noqa: BLE001
        return DEFAULT_DAEMON_PORT


def _try_post_to_daemon(
    daemon_url: str, transcript_path: str, project_name: str
) -> bool:
    """POST the ingest job to the daemon. Return True iff queued (2xx)."""
    try:
        import httpx
    except ImportError:
        return False
    try:
        response = httpx.post(
            f"{daemon_url.rstrip('/')}/jobs",
            json={
                "kind": "ingest",
                "payload": {
                    "transcript_path": transcript_path,
                    "project_name": project_name,
                },
            },
            timeout=DAEMON_POST_TIMEOUT_S,
        )
    except Exception:  # noqa: BLE001
        return False
    return 200 <= response.status_code < 300


def _spawn_ingest(transcript_path: str, project_name: str) -> None:
    cmd = [
        sys.executable,
        "-m",
        "claude_mnemos",
        "ingest",
        transcript_path,
        "--project",
        project_name,
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

    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _eprint(f"invalid hook payload ({exc}); skipping")
        return 0

    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        _eprint("missing transcript_path in payload; skipping")
        return 0

    cwd_raw = payload.get("cwd") or os.getcwd()
    cwd = Path(cwd_raw)

    try:
        entry = ProjectResolver().resolve_by_cwd(cwd)
    except ResolverAmbiguityError as exc:
        _eprint(f"ambiguous project for cwd {cwd}: {exc}; skipping")
        return 0
    except Exception as exc:  # noqa: BLE001
        _eprint(f"resolver failed: {exc}; skipping")
        return 0

    if entry is None:
        _eprint(
            f"cwd {cwd} not registered in project-map; "
            "transcript остаётся в lost-sessions"
        )
        return 0

    port = _daemon_port()
    daemon_url = os.environ.get(
        DAEMON_URL_ENV, f"http://127.0.0.1:{port}"
    )
    if _try_post_to_daemon(daemon_url, transcript, entry.name):
        return 0

    try:
        _spawn_ingest(transcript, entry.name)
    except OSError as exc:
        _eprint(f"failed to spawn ingest worker: {exc}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        record_exception(hook="session_end", exc=e, context={"argv": sys.argv})
        # Exit 0 anyway — never block Claude Code.
        sys.exit(0)
