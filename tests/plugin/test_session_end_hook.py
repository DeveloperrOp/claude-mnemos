"""Unit tests for hooks/session_end.py — exercise via importlib."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / "hooks" / "session_end.py"


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
