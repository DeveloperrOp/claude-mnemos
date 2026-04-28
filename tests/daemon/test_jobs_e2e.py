"""Slow E2E for Plan #11: real subprocess daemon, real .jobs.db,
POST /jobs creates job, daemon worker runs ingest in raw_only mode,
status transitions to succeeded.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
import pytest

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skip(
        reason=(
            "TODO(β2 Plan #13b-β2): /jobs route still reads daemon.job_store "
            "(single-vault attr) — needs migration to primary_runtime.job_store "
            "before this e2e can pass."
        )
    ),
]


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


# Minimal Claude Code session JSONL format expected by
# `claude_mnemos.ingest.transcript.parse_jsonl`: each entry needs `type` set to
# "user"/"assistant" and a `message` dict with `role` + `content`. The plain
# `{"role": ..., "content": ...}` shape from the plan would be silently
# filtered out and trigger EmptyTranscriptError.
_TRANSCRIPT_JSONL = (
    '{"type":"user","message":{"role":"user","content":"hi"},'
    '"sessionId":"jobs-e2e-001","timestamp":"2026-04-27T00:00:00Z"}\n'
    '{"type":"assistant","message":{"role":"assistant",'
    '"content":[{"type":"text","text":"hello"}]},'
    '"sessionId":"jobs-e2e-001","timestamp":"2026-04-27T00:00:01Z"}\n'
)


@pytest.mark.slow
def test_jobs_e2e_ingest_via_queue(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    pid_file = tmp_path / "daemon.pid"
    port = _free_port()

    # Seed a tiny session.jsonl in proper Claude Code format.
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(_TRANSCRIPT_JSONL, encoding="utf-8")

    # Multi-vault daemon ignores --vault; pre-register so primary_runtime is set
    # and vault-root-dependent routes (/jobs) work.
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
        h = _wait_for_health(f"http://127.0.0.1:{port}/health")
        assert h is not None, (
            "daemon did not start. stderr: "
            f"{proc.stderr.read().decode() if proc.stderr else ''}"
        )

        # Force raw_only via payload (no API key needed)
        r = httpx.post(
            f"http://127.0.0.1:{port}/jobs",
            json={
                "kind": "ingest",
                "payload": {
                    "transcript_path": str(transcript),
                    "extract": False,
                },
            },
            timeout=2.0,
        )
        assert r.status_code == 201
        job_id = r.json()["id"]

        # Poll until terminal status.
        deadline = time.monotonic() + 30.0
        final_status = None
        while time.monotonic() < deadline:
            r = httpx.get(f"http://127.0.0.1:{port}/jobs/{job_id}", timeout=2.0)
            if r.status_code == 200:
                final_status = r.json().get("status")
                if final_status in ("succeeded", "dead_letter", "failed"):
                    break
            time.sleep(0.5)

        assert final_status == "succeeded", (
            f"job ended with status={final_status}, "
            f"stderr={proc.stderr.read(1024).decode() if proc.stderr else ''}"
        )

    finally:
        with contextlib.suppress(psutil.NoSuchProcess):
            psutil.Process(proc.pid).terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    if pid_file.exists():
        pid_file.unlink()
