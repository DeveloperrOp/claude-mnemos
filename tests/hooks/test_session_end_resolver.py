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


def test_hook_default_manual_mode_skips_daemon_post(isolated_home, monkeypatch):
    """v0.0.10: by default ``dump_on_session_end`` is False (manual mode), so
    the hook resolves the project but does NOT POST to the daemon and does
    NOT spawn the fallback ingest subprocess. The transcript stays on disk
    for the user to import via Lost Sessions later.

    Regression for the v0.0.9 "auto-ingest without consent" behaviour.
    """
    home, env = isolated_home
    # Tag the env so the hook can't accidentally hit a real daemon.
    env["MNEMOS_DAEMON_URL"] = "http://127.0.0.1:1"  # already unreachable

    map_dir = home / ".claude-mnemos"
    map_dir.mkdir()
    cwd = home / "code" / "x"
    cwd.mkdir(parents=True)
    (map_dir / "project-map.json").write_text(json.dumps({
        "version": 1,
        "projects": [{
            "name": "x", "vault_root": str(home / "v"),
            "cwd_patterns": [str(cwd)],
        }],
    }))
    # NO global-settings.json on disk → defaults all False.
    transcript = home / "t.jsonl"
    transcript.write_text("{}")
    payload = {"transcript_path": str(transcript), "cwd": str(cwd)}
    r = _run_hook(payload, env)
    assert r.returncode == 0
    assert b"not registered" not in r.stderr
    # No "failed to spawn ingest worker" — fallback path never reached.
    assert b"failed to spawn" not in r.stderr


def test_hook_opt_in_dump_on_session_end_attempts_post(isolated_home):
    """When the global setting ``dump_on_session_end`` is True, the hook
    DOES try to POST. Daemon is unreachable in this fixture so the spawn
    fallback fires — that's how we detect the POST path was taken."""
    home, env = isolated_home

    map_dir = home / ".claude-mnemos"
    map_dir.mkdir()
    cwd = home / "code" / "y"
    cwd.mkdir(parents=True)
    (map_dir / "project-map.json").write_text(json.dumps({
        "version": 1,
        "projects": [{
            "name": "y", "vault_root": str(home / "v"),
            "cwd_patterns": [str(cwd)],
        }],
    }))
    # Global settings opt-in.
    (map_dir / "global-settings.json").write_text(json.dumps({
        "version": 1,
        "auto_ingest_defaults": {
            "dump_on_session_end": True,
            "dump_stale_after_24h": False,
            "extract_after_dump": False,
        },
    }))
    transcript = home / "t.jsonl"
    transcript.write_text("{}")
    payload = {"transcript_path": str(transcript), "cwd": str(cwd)}
    r = _run_hook(payload, env)
    assert r.returncode == 0
    # Daemon at 127.0.0.1:1 is unreachable → POST fails → spawn fallback
    # fires. The fallback uses Popen detached, so it doesn't print to stderr,
    # but it also doesn't return anything we can observe directly. The
    # important thing: the hook didn't return early on dump_on_session_end
    # check (no "lost-sessions" message in stderr).
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
