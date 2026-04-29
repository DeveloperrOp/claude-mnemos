from __future__ import annotations

from claude_mnemos.ingest.llm.tokens import count_tokens_local


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
