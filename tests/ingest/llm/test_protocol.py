from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from claude_mnemos.ingest.llm import (
    ApiLLMClient,
    ExtractionRaw,
    LLMClient,
)


def test_llm_client_is_protocol() -> None:
    """LLMClient must be a runtime-checkable Protocol so duck-typed clients
    pass isinstance() checks (used by factory + tests)."""

    class StubClient:
        def extract(
            self,
            *,
            system: str,
            user: str,
            tool: dict[str, Any],
            validate: Any = None,
        ) -> ExtractionRaw:
            return ExtractionRaw(payload={}, input_tokens=0, output_tokens=0)

    assert isinstance(StubClient(), LLMClient)


def test_api_llm_client_satisfies_protocol() -> None:
    """ApiLLMClient must implement LLMClient Protocol."""
    cfg = MagicMock()
    cfg.api_key = "sk-test"
    cfg.model = "claude-sonnet-4-5"
    inner = MagicMock()
    client = ApiLLMClient(cfg, _client=inner)
    assert isinstance(client, LLMClient)


def test_protocol_rejects_class_without_extract() -> None:
    class BadClient:
        def something_else(self) -> None: ...

    assert not isinstance(BadClient(), LLMClient)
