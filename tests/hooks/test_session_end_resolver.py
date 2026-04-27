"""SessionEnd hook (post-Plan #13b-α): cwd → project-map → POST /jobs.

End-to-end runs of ``hooks/session_end.py`` as a subprocess. Each test isolates
``HOME`` / ``USERPROFILE`` to ``tmp_path`` so reads/writes of
``~/.claude-mnemos/`` stay contained.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "session_end.py"


def _run_hook(payload: dict, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload).encode("utf-8"),
        env=env,
        capture_output=True,
        timeout=10,
    )


@pytest.fixture
def isolated_home(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env.pop("MNEMOS_VAULT_ROOT", None)
    env.pop("MNEMOS_INGEST_RUNNING", None)
    # Point daemon at unreachable port so POST fails fast and we observe
    # subprocess fallback behavior without flakiness from a real daemon.
    env["MNEMOS_DAEMON_URL"] = "http://127.0.0.1:1"
    return tmp_path, env


def test_hook_silent_skip_when_cwd_unmatched(isolated_home):
    home, env = isolated_home
    transcript = home / "x.jsonl"
    transcript.write_text("{}")
    cwd = home / "elsewhere"
    cwd.mkdir()
    payload = {"transcript_path": str(transcript), "cwd": str(cwd)}
    r = _run_hook(payload, env)
    assert r.returncode == 0
    err = r.stderr.decode()
    assert ("not registered" in err) or ("lost-sessions" in err)


def test_hook_silent_skip_on_missing_transcript(isolated_home):
    home, env = isolated_home
    payload: dict = {}  # no transcript_path
    r = _run_hook(payload, env)
    assert r.returncode == 0
    assert b"transcript" in r.stderr or b"missing" in r.stderr


def test_hook_recursion_guard(isolated_home):
    home, env = isolated_home
    env["MNEMOS_INGEST_RUNNING"] = "1"
    payload = {"transcript_path": str(home / "x.jsonl")}
    r = _run_hook(payload, env)
    # Hook returns immediately when guard set; no error output expected.
    assert r.returncode == 0
    assert r.stderr == b""


def test_hook_silent_skip_on_invalid_payload(isolated_home):
    home, env = isolated_home
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=b"{not json",
        env=env,
        capture_output=True,
        timeout=10,
    )
    assert r.returncode == 0
    assert b"invalid hook payload" in r.stderr


def test_hook_resolves_match_and_fallback_subprocess(isolated_home):
    home, env = isolated_home
    # Pre-seed project-map directly on disk (avoid invoking nested CLI).
    map_dir = home / ".claude-mnemos"
    map_dir.mkdir()
    cwd = home / "code" / "x"
    cwd.mkdir(parents=True)
    (map_dir / "project-map.json").write_text(json.dumps({
        "version": 1,
        "projects": [{
            "name": "x",
            "vault_root": str(home / "v"),
            "cwd_patterns": [str(cwd)],
        }],
    }))
    transcript = home / "t.jsonl"
    transcript.write_text("{}")
    payload = {"transcript_path": str(transcript), "cwd": str(cwd)}
    r = _run_hook(payload, env)
    # Hook never blocks: returncode 0 unconditionally.
    assert r.returncode == 0
    # Should NOT print "not registered" — project matched.
    assert b"not registered" not in r.stderr


def test_hook_ambiguous_cwd_silent_skip(isolated_home):
    home, env = isolated_home
    map_dir = home / ".claude-mnemos"
    map_dir.mkdir()
    cwd = home / "code" / "shared"
    cwd.mkdir(parents=True)
    pattern = str(cwd)
    # Two distinct projects with the same pattern → ambiguity.
    (map_dir / "project-map.json").write_text(json.dumps({
        "version": 1,
        "projects": [
            {"name": "a", "vault_root": str(home / "va"),
             "cwd_patterns": [pattern]},
            {"name": "b", "vault_root": str(home / "vb"),
             "cwd_patterns": [pattern]},
        ],
    }))
    transcript = home / "t.jsonl"
    transcript.write_text("{}")
    payload = {"transcript_path": str(transcript), "cwd": str(cwd)}
    r = _run_hook(payload, env)
    assert r.returncode == 0
    assert b"ambiguous" in r.stderr
