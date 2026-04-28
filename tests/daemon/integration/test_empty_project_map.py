"""Integration test: daemon with empty project map.

Boots a real daemon with no pre-registered projects, then asserts:
- GET /projects returns 200 with an empty list
- GET /snapshots returns 503 with no_vault_registered error
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

PORT = 5762


@pytest.mark.slow
def test_empty_bootstrap_serves_projects_and_503_for_vault_routes(
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
                        f"http://127.0.0.1:{PORT}/health", timeout=0.5
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

        # Empty project map → GET /projects returns 200 with an empty list.
        r = httpx.get(f"{base}/projects", timeout=5.0)
        assert r.status_code == 200, r.text
        assert r.json() == [], f"expected empty list, got: {r.json()}"

        # GET /snapshots should 503 because no primary vault is registered.
        r = httpx.get(f"{base}/snapshots", timeout=5.0)
        assert r.status_code == 503, r.text
        body = r.json()
        assert body.get("detail", {}).get("error") == "no_vault_registered", body
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)
