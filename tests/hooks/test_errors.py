"""Tests for claude_mnemos.hooks.errors logger."""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def errors_module(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMOS_HOOK_ERRORS_FILE", str(tmp_path / "h.jsonl"))
    import importlib
    from claude_mnemos.hooks import errors
    importlib.reload(errors)
    return errors, tmp_path / "h.jsonl"


def test_record_creates_file(errors_module):
    errors, path = errors_module
    errors.record(hook="session_start", kind="info", message="hello")
    assert path.exists()
    line = path.read_text(encoding="utf-8").splitlines()[-1]
    rec = json.loads(line)
    assert rec["hook"] == "session_start"
    assert rec["kind"] == "info"
    assert rec["message"] == "hello"
    assert "ts" in rec


def test_record_caps_at_max_lines(errors_module):
    errors, path = errors_module
    for i in range(errors.MAX_LINES + 50):
        errors.record(hook="h", kind="info", message=str(i))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == errors.MAX_LINES
    # Oldest dropped, newest preserved
    assert json.loads(lines[-1])["message"] == str(errors.MAX_LINES + 50 - 1)


def test_record_exception_captures_traceback(errors_module):
    errors, path = errors_module
    try:
        raise ValueError("test")
    except ValueError as e:
        errors.record_exception(hook="session_start", exc=e, context={"k": "v"})
    line = path.read_text(encoding="utf-8").splitlines()[-1]
    rec = json.loads(line)
    assert rec["kind"] == "exception"
    assert "ValueError: test" in rec["message"]
    assert "ValueError" in rec["traceback"]
    assert rec["context"] == {"k": "v"}


def test_read_recent_newest_first(errors_module):
    errors, _ = errors_module
    errors.record(hook="h", kind="info", message="A")
    errors.record(hook="h", kind="info", message="B")
    errors.record(hook="h", kind="info", message="C")
    out = errors.read_recent()
    assert [e["message"] for e in out] == ["C", "B", "A"]


def test_read_recent_when_missing(errors_module):
    errors, path = errors_module
    assert not path.exists()
    assert errors.read_recent() == []
