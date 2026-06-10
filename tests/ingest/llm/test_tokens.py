from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos.ingest.llm import tokens
from claude_mnemos.ingest.llm.tokens import (
    count_tokens_local,
    probe_tokenizer,
)


def test_count_tokens_empty_string_returns_zero() -> None:
    assert count_tokens_local("") == 0


def test_count_tokens_short_english_in_reasonable_range() -> None:
    n = count_tokens_local("Hello, world!")
    assert 1 <= n <= 6  # cl100k tokenizer: typically 4 tokens


def test_count_tokens_monotonic_with_length() -> None:
    short = count_tokens_local("foo")
    long = count_tokens_local("foo " * 100)
    assert long > short


def test_count_tokens_handles_russian() -> None:
    """Russian characters take ~2 chars/token typically; just verify > 0."""
    n = count_tokens_local("Привет, мир!")
    assert n > 0


def test_count_tokens_handles_json_like_text() -> None:
    payload = '{"name": "test", "value": 42, "nested": {"a": [1, 2, 3]}}'
    n = count_tokens_local(payload)
    assert n > 5


# --- graceful degrade (v0.0.44) -------------------------------------------
#
# The BPE table downloads from openaipublic.blob.core.windows.net on first
# use. A network failure there must NOT propagate out of count_tokens_local:
# tokens are cosmetic (~approx), and the call happens AFTER the paid
# `claude -p` run — raising would fail the whole extract.


def _boom() -> None:
    raise RuntimeError("BPE download failed (offline)")


def test_count_tokens_degrades_to_zero_when_encoder_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tokens, "_encoder", _boom)
    assert count_tokens_local("Hello, world!") == 0


def test_count_tokens_warns_once_per_process(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(tokens, "_encoder", _boom)
    monkeypatch.setattr(tokens, "_degrade_warned", False)
    with caplog.at_level("WARNING", logger="claude_mnemos.ingest.llm.tokens"):
        count_tokens_local("a")
        count_tokens_local("b")
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1


# --- probe_tokenizer (CI bundle smoke) -------------------------------------


def test_probe_tokenizer_ok_on_working_tokenizer() -> None:
    ok, detail = probe_tokenizer()
    assert ok is True
    assert "cl100k_base" in detail


def test_probe_tokenizer_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tokens, "_encoder", _boom)
    ok, detail = probe_tokenizer()
    assert ok is False
    assert "BPE download failed" in detail


# --- durable BPE cache dir (v0.0.44) ----------------------------------------
#
# tiktoken defaults its download cache to %TEMP%/data-gym-cache, which
# Windows Storage Sense purges — every purge costs a 1.7 MB re-download and
# a hard failure when offline. We pin it to ~/.claude-mnemos/tiktoken-cache.


def test_cache_dir_env_defaulted_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIKTOKEN_CACHE_DIR", raising=False)
    tokens._ensure_cache_dir_env()
    import os

    got = Path(os.environ["TIKTOKEN_CACHE_DIR"])
    assert got == Path.home() / ".claude-mnemos" / "tiktoken-cache"


def test_cache_dir_env_respects_existing_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", r"C:\custom\cache")
    tokens._ensure_cache_dir_env()
    import os

    assert os.environ["TIKTOKEN_CACHE_DIR"] == r"C:\custom\cache"


def test_module_import_sets_cache_dir_env() -> None:
    """The env default is applied at import time — before any encode call."""
    import os

    assert os.environ.get("TIKTOKEN_CACHE_DIR")
