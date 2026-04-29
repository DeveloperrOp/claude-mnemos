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
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from claude_mnemos.ingest.llm.api import (
    ApiLLMClient,
    ExtractionRaw,
    LLMExtractionError,
    MissingApiKeyError,
    TranscriptTooLargeError,
)

if TYPE_CHECKING:
    from claude_mnemos.config import Config


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


def make_llm_client(cfg: Config) -> LLMClient:
    """Resolve the LLMClient implementation based on cfg.ingest_provider.

    Resolution rules:
    - cfg.ingest_provider == "api"  → ApiLLMClient (raises MissingApiKeyError if no key)
    - cfg.ingest_provider == "cli"  → CliLLMClient (no key needed)
    - cfg.ingest_provider is None   → auto-detect:
        - api_key set → ApiLLMClient (preserves existing behaviour)
        - api_key not set → CliLLMClient
    """
    if cfg.ingest_provider == "api":
        return ApiLLMClient(cfg)
    if cfg.ingest_provider == "cli":
        from claude_mnemos.ingest.llm.cli import CliLLMClient
        return CliLLMClient(cfg)
    # auto-detect
    if cfg.api_key:
        return ApiLLMClient(cfg)
    from claude_mnemos.ingest.llm.cli import CliLLMClient
    return CliLLMClient(cfg)


__all__ = [
    "ApiLLMClient",
    "ExtractionRaw",
    "LLMClient",
    "LLMExtractionError",
    "MissingApiKeyError",
    "TranscriptTooLargeError",
    "make_llm_client",
]
