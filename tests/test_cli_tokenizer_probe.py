"""CLI wiring for `tokenizer-probe` (CI bundle smoke / diagnostics).

The probe itself is tested in tests/ingest/llm/test_tokens.py; here we only
verify the subcommand exists, prints the verdict and maps ok→0 / fail→1.
"""

from __future__ import annotations

import pytest

from claude_mnemos.cli import main


def test_tokenizer_probe_ok_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "claude_mnemos.ingest.llm.tokens.probe_tokenizer",
        lambda: (True, "cl100k_base ok (5 tokens)"),
    )
    rc = main(["tokenizer-probe"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "tokenizer: ok" in out
    assert "cl100k_base" in out


def test_tokenizer_probe_failure_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "claude_mnemos.ingest.llm.tokens.probe_tokenizer",
        lambda: (False, "ValueError: Unknown encoding cl100k_base"),
    )
    rc = main(["tokenizer-probe"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "tokenizer: FAIL" in out
    assert "Unknown encoding" in out
