"""Rate-limit detection for the CLI provider.

Claude Code CLI surfaces rate-limit errors via non-zero exit code + stderr
text. There's no structured error envelope, so we pattern-match. Heuristics:
- 'rate_limit' / 'rate-limit' / 'rate limit' substring (case-insensitive)
- 'HTTP 429' or '429 Too Many Requests'

When matched, ``parse_rate_limit_from_stderr`` returns a ``RateLimitError``
whose ``reset_at`` is either parsed from the stderr (if present in
ISO-8601 form) or set to ``now + 5h`` (Anthropic Pro window).

``RateLimitError`` is a subclass of ``LLMExtractionError`` so existing
``except LLMExtractionError`` catches still work; the JobStore pause
path uses ``isinstance(exc, RateLimitError)`` to discriminate.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from claude_mnemos.ingest.llm import LLMExtractionError

DEFAULT_PAUSE_HOURS = 5
_RATE_LIMIT_RE = re.compile(r"rate[ _-]?limit|429\b", re.IGNORECASE)
_RESET_AT_RE = re.compile(
    r"reset[_ ]?at[:= ]+(\d{4}-\d{2}-\d{2}T[\d:.+-]+(?:Z|[+-]\d{2}:?\d{2}))",
    re.IGNORECASE,
)


class RateLimitError(LLMExtractionError):
    """LLM call failed because rate limit was hit. Caller should pause queue."""

    def __init__(self, message: str, *, reset_at: datetime) -> None:
        super().__init__(message)
        self.reset_at = reset_at


def parse_rate_limit_from_stderr(stderr: str) -> RateLimitError | None:
    """Inspect *stderr* for rate-limit signal. Return RateLimitError or None."""
    if not stderr or not _RATE_LIMIT_RE.search(stderr):
        return None
    iso_match = _RESET_AT_RE.search(stderr)
    if iso_match:
        try:
            reset = datetime.fromisoformat(iso_match.group(1))
            if reset.tzinfo is None:
                reset = reset.replace(tzinfo=UTC)
        except ValueError:
            reset = datetime.now(UTC) + timedelta(hours=DEFAULT_PAUSE_HOURS)
    else:
        reset = datetime.now(UTC) + timedelta(hours=DEFAULT_PAUSE_HOURS)
    return RateLimitError(stderr.strip(), reset_at=reset)
