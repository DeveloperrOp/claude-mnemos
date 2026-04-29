"""LLM provider package — Protocol + adapter classes.

Adapters:
- ``ApiLLMClient`` (claude_mnemos.ingest.llm.api): uses anthropic.Anthropic SDK
  with ANTHROPIC_API_KEY. Existing path, preserved for users with their own
  API key billing.
- ``CliLLMClient`` (claude_mnemos.ingest.llm.cli): uses ``claude -p`` subprocess
  with the user's Claude Code subscription (added in Phase 2).

Selection happens via ``make_llm_client(cfg)`` factory (added in Phase 3).
See docs/plans/2026-04-30-llm-cli-provider-design.md.
"""

from claude_mnemos.ingest.llm.api import (
    ApiLLMClient,
    ExtractionRaw,
    LLMExtractionError,
    MissingApiKeyError,
    TranscriptTooLargeError,
)

# Backward-compatible alias — Phase 1 Task 3 will replace this with a Protocol
# that both ApiLLMClient and CliLLMClient satisfy.
LLMClient = ApiLLMClient

__all__ = [
    "ApiLLMClient",
    "ExtractionRaw",
    "LLMClient",
    "LLMExtractionError",
    "MissingApiKeyError",
    "TranscriptTooLargeError",
]
