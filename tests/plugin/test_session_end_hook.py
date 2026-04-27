"""Unit tests for hooks/session_end.py — exercise via importlib."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / "hooks" / "session_end.py"


def _run_hook(stdin_payload: dict, env: dict) -> subprocess.CompletedProcess:
    """Run the hook as a subprocess (end-to-end), feeding stdin payload."""
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(stdin_payload),
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )


def _load_hook_module():
    spec = importlib.util.spec_from_file_location("mnemos_session_end", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hook():
    return _load_hook_module()


@pytest.fixture
def stdin_payload(monkeypatch):
    def _set(payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        monkeypatch.setattr(sys, "stdin", io.StringIO(text))
    return _set


def _track_spawn(monkeypatch, hook):
    calls = []

    def _fake(transcript_path, vault):
        calls.append((transcript_path, vault))

    monkeypatch.setattr(hook, "_spawn_ingest", _fake)
    return calls


def test_recursion_guard_blocks_spawn(hook, monkeypatch, stdin_payload, tmp_path):
    monkeypatch.setenv(hook.RECURSION_ENV, "1")
    monkeypatch.setenv(hook.VAULT_ENV, str(tmp_path))
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("x", encoding="utf-8")
    stdin_payload({"transcript_path": str(transcript)})
    spawned = _track_spawn(monkeypatch, hook)

    assert hook.main() == 0
    assert spawned == []


def test_missing_vault_env_skips(hook, monkeypatch, stdin_payload, capsys):
    monkeypatch.delenv(hook.VAULT_ENV, raising=False)
    monkeypatch.delenv(hook.RECURSION_ENV, raising=False)
    stdin_payload({})
    spawned = _track_spawn(monkeypatch, hook)

    assert hook.main() == 0
    assert spawned == []
    err = capsys.readouterr().err
    assert "MNEMOS_VAULT_ROOT" in err


def test_invalid_json_payload_skips(hook, monkeypatch, capsys, tmp_path):
    monkeypatch.delenv(hook.RECURSION_ENV, raising=False)
    monkeypatch.setenv(hook.VAULT_ENV, str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
    spawned = _track_spawn(monkeypatch, hook)

    assert hook.main() == 0
    assert spawned == []
    assert "invalid hook payload" in capsys.readouterr().err


def test_missing_transcript_field_skips(
    hook, monkeypatch, stdin_payload, tmp_path, capsys
):
    monkeypatch.delenv(hook.RECURSION_ENV, raising=False)
    monkeypatch.setenv(hook.VAULT_ENV, str(tmp_path))
    stdin_payload({"session_id": "abc"})
    spawned = _track_spawn(monkeypatch, hook)

    assert hook.main() == 0
    assert spawned == []
    assert "no transcript_path" in capsys.readouterr().err


def test_nonexistent_transcript_skips(
    hook, monkeypatch, stdin_payload, tmp_path, capsys
):
    monkeypatch.delenv(hook.RECURSION_ENV, raising=False)
    monkeypatch.setenv(hook.VAULT_ENV, str(tmp_path))
    stdin_payload({"transcript_path": str(tmp_path / "missing.jsonl")})
    spawned = _track_spawn(monkeypatch, hook)

    assert hook.main() == 0
    assert spawned == []
    assert "not found" in capsys.readouterr().err


def test_happy_path_spawns_with_correct_args(
    hook, monkeypatch, stdin_payload, tmp_path
):
    monkeypatch.delenv(hook.RECURSION_ENV, raising=False)
    monkeypatch.setenv(hook.VAULT_ENV, str(tmp_path))
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    stdin_payload({"transcript_path": str(transcript), "session_id": "sess-1"})
    spawned = _track_spawn(monkeypatch, hook)

    assert hook.main() == 0
    assert len(spawned) == 1
    transcript_arg, vault_arg = spawned[0]
    assert transcript_arg == transcript
    assert vault_arg == str(tmp_path)


def test_spawn_oserror_swallowed(hook, monkeypatch, stdin_payload, tmp_path, capsys):
    monkeypatch.delenv(hook.RECURSION_ENV, raising=False)
    monkeypatch.setenv(hook.VAULT_ENV, str(tmp_path))
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    stdin_payload({"transcript_path": str(transcript)})

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(hook, "_spawn_ingest", _boom)

    assert hook.main() == 0
    assert "failed to spawn" in capsys.readouterr().err


def test_spawn_uses_recursion_env_in_subprocess(hook, monkeypatch, tmp_path):
    """_spawn_ingest sets MNEMOS_INGEST_RUNNING=1 in the spawned env."""
    captured = {}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs

    monkeypatch.setattr(hook.subprocess, "Popen", FakePopen)

    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    hook._spawn_ingest(transcript, str(tmp_path))

    assert captured["cmd"][1] == "-m"
    assert captured["cmd"][2] == "claude_mnemos"
    assert captured["cmd"][3] == "ingest"
    assert captured["cmd"][4] == str(transcript)
    assert captured["cmd"][5] == str(tmp_path)
    assert captured["kwargs"]["env"][hook.RECURSION_ENV] == "1"


def test_spawn_platform_specific_kwargs(hook, monkeypatch, tmp_path):
    captured = {}

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["kwargs"] = kwargs

    monkeypatch.setattr(hook.subprocess, "Popen", FakePopen)

    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    hook._spawn_ingest(transcript, str(tmp_path))

    if sys.platform == "win32":
        assert "creationflags" in captured["kwargs"]
        assert captured["kwargs"]["stdout"] is hook.subprocess.DEVNULL
        assert captured["kwargs"]["stderr"] is hook.subprocess.DEVNULL
    else:
        assert captured["kwargs"]["start_new_session"] is True


# ---------------------------------------------------------------------------
# Plan #11 Task 10: daemon POST with subprocess fallback
# ---------------------------------------------------------------------------


def test_daemon_post_success_skips_subprocess_spawn(
    hook, monkeypatch, stdin_payload, tmp_path
):
    """If POST /jobs returns 201, hook returns 0 and does NOT spawn fallback."""
    monkeypatch.delenv(hook.RECURSION_ENV, raising=False)
    monkeypatch.setenv(hook.VAULT_ENV, str(tmp_path))
    monkeypatch.setenv("MNEMOS_DAEMON_URL", "http://127.0.0.1:5757")
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    stdin_payload({"transcript_path": str(transcript)})

    posted = {}

    class FakeResponse:
        status_code = 201

    def fake_post(url, json=None, timeout=None):
        posted["url"] = url
        posted["json"] = json
        posted["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(hook.httpx, "post", fake_post)
    spawned = _track_spawn(monkeypatch, hook)

    assert hook.main() == 0
    assert posted["url"].endswith("/jobs")
    assert posted["json"]["kind"] == "ingest"
    assert posted["json"]["payload"]["transcript_path"] == str(transcript)
    assert spawned == []


def test_daemon_post_200_also_skips_subprocess(
    hook, monkeypatch, stdin_payload, tmp_path
):
    """200 OK should also be treated as success."""
    monkeypatch.delenv(hook.RECURSION_ENV, raising=False)
    monkeypatch.setenv(hook.VAULT_ENV, str(tmp_path))
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    stdin_payload({"transcript_path": str(transcript)})

    class FakeResponse:
        status_code = 200

    monkeypatch.setattr(
        hook.httpx, "post", lambda *a, **kw: FakeResponse()
    )
    spawned = _track_spawn(monkeypatch, hook)

    assert hook.main() == 0
    assert spawned == []


def test_daemon_post_5xx_falls_back_to_subprocess(
    hook, monkeypatch, stdin_payload, tmp_path
):
    """If daemon returns non-2xx, fall back to detached subprocess."""
    monkeypatch.delenv(hook.RECURSION_ENV, raising=False)
    monkeypatch.setenv(hook.VAULT_ENV, str(tmp_path))
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    stdin_payload({"transcript_path": str(transcript)})

    class FakeResponse:
        status_code = 503

    monkeypatch.setattr(
        hook.httpx, "post", lambda *a, **kw: FakeResponse()
    )
    spawned = _track_spawn(monkeypatch, hook)

    assert hook.main() == 0
    assert len(spawned) == 1
    assert spawned[0] == (transcript, str(tmp_path))


def test_daemon_post_connect_error_falls_back_to_subprocess(
    hook, monkeypatch, stdin_payload, tmp_path
):
    """If POST raises (e.g. ConnectError), fall back to detached subprocess."""
    monkeypatch.delenv(hook.RECURSION_ENV, raising=False)
    monkeypatch.setenv(hook.VAULT_ENV, str(tmp_path))
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    stdin_payload({"transcript_path": str(transcript)})

    def boom(*_a, **_kw):
        raise hook.httpx.ConnectError("offline")

    monkeypatch.setattr(hook.httpx, "post", boom)
    spawned = _track_spawn(monkeypatch, hook)

    assert hook.main() == 0
    assert len(spawned) == 1


def test_daemon_post_timeout_uses_short_timeout(
    hook, monkeypatch, stdin_payload, tmp_path
):
    """The hook MUST pass a short timeout (<=2s) so it never blocks session end."""
    monkeypatch.delenv(hook.RECURSION_ENV, raising=False)
    monkeypatch.setenv(hook.VAULT_ENV, str(tmp_path))
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    stdin_payload({"transcript_path": str(transcript)})

    captured = {}

    class FakeResponse:
        status_code = 201

    def fake_post(url, json=None, timeout=None):
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(hook.httpx, "post", fake_post)
    _track_spawn(monkeypatch, hook)

    assert hook.main() == 0
    assert captured["timeout"] is not None
    assert captured["timeout"] <= 2.0


@pytest.mark.slow
def test_hook_uses_daemon_when_available(tmp_path: Path):
    """If MNEMOS_DAEMON_URL responds 201 to POST /jobs, hook posts and exits 0.

    Spinning a real daemon here is complex; rely on Task 12 slow E2E.
    """
    pytest.skip("covered by Task 12 slow E2E")


def test_hook_fallback_subprocess_when_daemon_offline(tmp_path: Path):
    """End-to-end: hook script must exit 0 even when daemon is unreachable.

    The hook spawns a detached fallback subprocess; we don't validate that path
    here (just that the hook script itself returns 0 and doesn't block).
    """
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("[]", encoding="utf-8")

    env = {
        **os.environ,
        "MNEMOS_VAULT_ROOT": str(tmp_path),
        "MNEMOS_DAEMON_URL": "http://127.0.0.1:1",  # unreachable
    }
    env.pop("MNEMOS_INGEST_RUNNING", None)

    result = _run_hook({"transcript_path": str(transcript)}, env=env)
    assert result.returncode == 0
