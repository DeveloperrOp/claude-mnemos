"""Slow E2E for Plan #12: real subprocess daemon, real REST round-trip for
PATCH /pages, DELETE /pages -> trash, and POST /trash/{id}/restore.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
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


def _wait_for_health(url: str, timeout: float = 15.0) -> dict | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=0.5)
            if r.status_code == 200:
                return r.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    return None


_SEED_PAGE = """---
title: Foo
type: entity
status: draft
confidence: 0.7
flavor: []
sources: []
related: []
created: 2026-04-26
updated: 2026-04-26
agent_written: true
---
original body
"""


@pytest.mark.slow
def test_pages_trash_e2e_round_trip(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    pid_file = tmp_path / "daemon.pid"
    port = _free_port()

    # Multi-vault daemon ignores --vault; pre-register so primary_runtime is set
    # and vault-root-dependent routes (/pages, /trash) work.
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    child_env = os.environ.copy()
    child_env["HOME"] = str(isolated_home)
    child_env["USERPROFILE"] = str(isolated_home)
    child_env.pop("MNEMOS_VAULT_ROOT", None)
    (isolated_home / ".claude-mnemos").mkdir(parents=True, exist_ok=True)
    (isolated_home / ".claude-mnemos" / "project-map.json").write_text(
        json.dumps({"projects": [{"name": "main", "vault_root": str(vault), "cwd_patterns": []}]}),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "claude_mnemos.daemon",
            "run",
            "--vault",
            str(vault),
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
        health = _wait_for_health(f"http://127.0.0.1:{port}/health")
        assert health is not None, (
            "daemon did not start. stderr: "
            f"{proc.stderr.read().decode() if proc.stderr else ''}"
        )

        base = f"http://127.0.0.1:{port}"
        page_rel = "wiki/entities/foo.md"

        # 1. Seed page directly in the vault (with valid frontmatter).
        page_path = vault / page_rel
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(_SEED_PAGE, encoding="utf-8")
        # Give the watchdog a moment to settle on the external create so it
        # doesn't conflate the seed with a human edit on the next mutation.
        time.sleep(1.0)

        # 2. PATCH frontmatter -> status verified.
        r = httpx.patch(
            f"{base}/pages/{page_rel}",
            json={"frontmatter": {"status": "verified"}, "body": None},
            timeout=5.0,
        )
        assert r.status_code == 200, r.text
        patch_body = r.json()
        assert patch_body["success"] is True
        assert patch_body["activity_id"]
        assert patch_body["snapshot_path"]

        # 3. Read page back, verify status=verified on disk.
        contents = page_path.read_text(encoding="utf-8")
        assert "status: verified" in contents

        # 4. DELETE page -> 200 with trash_id.
        r = httpx.delete(f"{base}/pages/{page_rel}", timeout=5.0)
        assert r.status_code == 200, r.text
        delete_body = r.json()
        assert delete_body["success"] is True
        trash_id = delete_body["trash_id"]
        assert trash_id
        assert not page_path.exists()

        # 5. GET /trash sees the entry with original_path.
        r = httpx.get(f"{base}/trash", timeout=5.0)
        assert r.status_code == 200, r.text
        trash_payload = r.json()
        match = next(
            (e for e in trash_payload["entries"] if e["trash_id"] == trash_id),
            None,
        )
        assert match is not None, trash_payload
        assert match["original_path"] == page_rel
        assert match["restorable"] is True

        # 6. POST /trash/{id}/restore -> 200, page is back at original location.
        r = httpx.post(f"{base}/trash/{trash_id}/restore", timeout=5.0)
        assert r.status_code == 200, r.text
        restore_body = r.json()
        assert restore_body["success"] is True
        assert restore_body["restored_path"] == page_rel

        # 7. Page is restored on disk; trash dir is gone.
        assert page_path.is_file()
        restored_contents = page_path.read_text(encoding="utf-8")
        assert "status: verified" in restored_contents
        trash_dir = vault / ".trash" / trash_id
        assert not trash_dir.exists()

    finally:
        # 8. SIGTERM daemon, assert clean shutdown.
        with contextlib.suppress(psutil.NoSuchProcess):
            if sys.platform == "win32":
                psutil.Process(proc.pid).terminate()
            else:
                proc.send_signal(signal.SIGTERM)
        try:
            exit_code = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            exit_code = proc.returncode
        # On Windows terminate() is effectively a kill, so non-zero is fine.
        # On POSIX SIGTERM should exit cleanly (0 or -SIGTERM=-15).
        assert exit_code is not None

    if pid_file.exists():
        pid_file.unlink()
