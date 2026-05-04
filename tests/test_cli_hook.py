import sys
from unittest.mock import MagicMock

import pytest


def test_hook_session_start_calls_session_start_main(monkeypatch):
    captured = {"called": 0}

    def fake_main():
        captured["called"] += 1
        return 0

    monkeypatch.setattr(
        "claude_mnemos.cli_hook._import_session_start",
        lambda: fake_main,
    )

    from claude_mnemos.cli_hook import run

    rc = run(["session-start"], stdin_payload='{"transcript_path":"/tmp/x.jsonl"}')
    assert rc == 0
    assert captured["called"] == 1


def test_hook_invalid_event_returns_2(monkeypatch):
    from claude_mnemos.cli_hook import run
    rc = run(["bogus-event"], stdin_payload="")
    assert rc == 2


def test_hook_passes_stdin_to_underlying_script(monkeypatch):
    seen = {}

    def fake_main():
        seen["stdin"] = sys.stdin.read()
        return 0

    monkeypatch.setattr(
        "claude_mnemos.cli_hook._import_session_end",
        lambda: fake_main,
    )

    from claude_mnemos.cli_hook import run
    rc = run(["session-end"], stdin_payload='{"transcript_path":"/tmp/y.jsonl"}')
    assert rc == 0
    assert "transcript_path" in seen["stdin"]
