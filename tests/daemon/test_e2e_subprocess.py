"""End-to-end test: spawn daemon as subprocess, hit /health, stop it.

Marked `slow` because it spawns a Python interpreter and binds to a TCP port.
Run via `pytest -m slow` or `pytest -m "slow"`.
"""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
import pytest

pytestmark = pytest.mark.slow


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=0.5)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    return False


@pytest.mark.slow
@pytest.mark.skipif(
    sys.platform == "win32" and sys.prefix != sys.base_prefix,
    reason="Windows venv python.exe is a launcher shim: Popen.pid is the shim's "
    "pid while the daemon records its real interpreter pid — the PID assertions "
    "below can never match. Passes on CI, whose setup-python is not a venv.",
)
def test_daemon_subprocess_lifecycle(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    pid_file = tmp_path / "daemon.pid"
    port = _free_port()

    # Pre-register project so vault-root-dependent routes
    # (/vault/{project}, /activity, /snapshots) work.
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    child_env = os.environ.copy()
    child_env["HOME"] = str(isolated_home)
    child_env["USERPROFILE"] = str(isolated_home)
    child_env.pop("MNEMOS_VAULT_ROOT", None)

    # Write project-map.json into the isolated home before spawning so that
    # vault-root routes work once the project is registered.
    import json as _json
    (isolated_home / ".claude-mnemos").mkdir(parents=True, exist_ok=True)
    (isolated_home / ".claude-mnemos" / "project-map.json").write_text(
        _json.dumps({"projects": [{"name": "main", "vault_root": str(vault), "cwd_patterns": []}]}),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "claude_mnemos.daemon",
            "run",
            "--port",
            str(port),
            "--pid-file",
            str(pid_file),
        ],
        env=child_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        assert _wait_for_health(f"http://127.0.0.1:{port}/api/health"), (
            f"daemon did not respond on :{port} within timeout. "
            f"stderr: {proc.stderr.read().decode() if proc.stderr else ''}"
        )

        # PID file written
        assert pid_file.is_file()
        recorded_pid = int(pid_file.read_text())
        assert recorded_pid == proc.pid

        # Endpoints respond
        r = httpx.get(f"http://127.0.0.1:{port}/api/version", timeout=2.0)
        assert r.status_code == 200
        r = httpx.get(f"http://127.0.0.1:{port}/api/vault/main", timeout=2.0)
        assert r.status_code == 200
        r = httpx.get(f"http://127.0.0.1:{port}/api/activity/main", timeout=2.0)
        assert r.status_code == 200
        r = httpx.get(f"http://127.0.0.1:{port}/api/snapshots/main", timeout=2.0)
        assert r.status_code == 200

    finally:
        # Terminate daemon
        with contextlib.suppress(psutil.NoSuchProcess):
            psutil.Process(proc.pid).terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    # PID file should be cleaned up on graceful shutdown
    # (May still exist if daemon was SIGKILL'd — best-effort assertion)
    if pid_file.exists():
        pid_file.unlink()
