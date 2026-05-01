"""Integration test: hot-mount a vault at runtime and then post a job to it.

Boots a real daemon with an empty project map, then:
1. POST /projects to hot-mount a new vault.
2. POST /jobs with a valid transcript to that vault.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

PORT = 5761


@pytest.mark.slow
def test_hot_mount_then_post_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    pid_file = home / "d.pid"
    env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
    }
    env.pop("MNEMOS_VAULT_ROOT", None)

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "claude_mnemos.daemon",
            "run",
            "--port",
            str(PORT),
            "--pid-file",
            str(pid_file),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            try:
                if (
                    httpx.get(
                        f"http://127.0.0.1:{PORT}/api/health", timeout=0.5
                    ).status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            pytest.fail(f"daemon on :{PORT} did not respond within timeout")

        base = f"http://127.0.0.1:{PORT}"

        # Hot-mount: POST /projects to register vault at runtime.
        vault = tmp_path / "live"
        vault.mkdir()
        r = httpx.post(
            f"{base}/api/projects",
            json={
                "name": "live",
                "vault_root": str(vault),
                "cwd_patterns": [],
            },
            timeout=10.0,
        )
        assert r.status_code == 201, r.text

        # Verify vault's .jobs.db was created by the mount.
        assert (vault / ".jobs.db").is_file(), "live .jobs.db not created after hot-mount"

        # POST a job to the newly mounted vault.
        transcript = vault / "t.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")
        r = httpx.post(
            f"{base}/api/jobs",
            json={
                "kind": "ingest",
                "payload": {
                    "project_name": "live",
                    "transcript_path": str(transcript),
                },
            },
            timeout=10.0,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "queued"
        assert body["kind"] == "ingest"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)
