"""LLM provider package — Protocol + adapter classes.

Adapters:
- ``ApiLLMClient`` (claude_mnemos.ingest.llm.api): uses anthropic.Anthropic SDK
  with ANTHROPIC_API_KEY.
- ``CliLLMClient`` (claude_mnemos.ingest.llm.cli): uses ``claude -p`` subprocess
  with the user's Claude Code subscription (added in Phase 2).

Selection happens via ``make_llm_client(cfg)`` factory (added in Phase 3).
See docs/plans/2026-04-30-llm-cli-provider-design.md.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from claude_mnemos.ingest.llm.api import (
    ApiLLMClient,
    ExtractionRaw,
    LLMExtractionError,
    MissingApiKeyError,
    TranscriptTooLargeError,
)


@runtime_checkable
class LLMClient(Protocol):
    """Common contract for all LLM extraction backends (API SDK or CLI subprocess).

    Implementations MUST honour the same retry-on-validation-error semantics:
    if ``validate(payload)`` raises, call the model again once with the error
    appended to the user prompt. If the second attempt also fails validation,
    raise ``LLMExtractionError``.
    """

    def extract(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        validate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> ExtractionRaw: ...


__all__ = [
    "ApiLLMClient",
    "ExtractionRaw",
    "LLMClient",
    "LLMExtractionError",
    "MissingApiKeyError",
    "TranscriptTooLargeError",
]
