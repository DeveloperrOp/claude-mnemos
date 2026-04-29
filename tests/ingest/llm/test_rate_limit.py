from __future__ import annotations

from datetime import UTC, datetime, timedelta

from claude_mnemos.ingest.llm import LLMExtractionError
from claude_mnemos.ingest.llm.rate_limit import (
    RateLimitError,
    parse_rate_limit_from_stderr,
)


def test_rate_limit_error_is_llm_extraction_error_subclass() -> None:
    """JobStore catches LLMExtractionError; RateLimitError must propagate
    through that catch path while remaining distinguishable via isinstance."""
    err = RateLimitError("rate limited", reset_at=datetime.now(UTC))
    assert isinstance(err, LLMExtractionError)


def test_rate_limit_error_carries_reset_at() -> None:
    when = datetime(2026, 4, 30, 14, 0, tzinfo=UTC)
    err = RateLimitError("limit hit", reset_at=when)
    assert err.reset_at == when


def test_parse_returns_none_for_non_rate_limit_stderr() -> None:
    assert parse_rate_limit_from_stderr("network error: timeout") is None
    assert parse_rate_limit_from_stderr("") is None
    assert parse_rate_limit_from_stderr("auth failed") is None


def test_parse_detects_rate_limit_keyword() -> None:
    err = parse_rate_limit_from_stderr("Error: rate_limit_exceeded — try later")
    assert isinstance(err, RateLimitError)
    assert err.reset_at > datetime.now(UTC)


def test_parse_detects_http_429() -> None:
    err = parse_rate_limit_from_stderr("HTTP 429 Too Many Requests")
    assert isinstance(err, RateLimitError)


def test_parse_default_reset_is_5_hours_ahead() -> None:
    err = parse_rate_limit_from_stderr("rate_limit reached")
    assert err is not None
    delta = err.reset_at - datetime.now(UTC)
    # Allow ±1 minute slop for test execution time
    assert timedelta(hours=4, minutes=59) < delta < timedelta(hours=5, minutes=1)


def test_parse_iso_timestamp_in_stderr_used_when_present() -> None:
    """If stderr contains 'reset_at: <ISO>' or 'retry after: <unix-ts>',
    parser should use that instead of default 5h."""
    when = datetime(2026, 4, 30, 16, 30, tzinfo=UTC)
    err = parse_rate_limit_from_stderr(f"rate_limit_exceeded; reset_at: {when.isoformat()}")
    assert err is not None
    # ISO timestamp parsed back
    assert err.reset_at == when
