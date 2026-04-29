from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import anthropic

from claude_mnemos.config import Config

DEFAULT_MAX_TOKENS = 8000
DEFAULT_TIMEOUT_SEC = 120.0


class MissingApiKeyError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is not set and ApiLLMClient is selected."""


class TranscriptTooLargeError(RuntimeError):
    """Raised when prompt token count exceeds configured max_input_tokens."""


class LLMExtractionError(RuntimeError):
    """Raised when LLM call fails to produce a valid tool_use payload after retry."""


@dataclass(frozen=True)
class ExtractionRaw:
    payload: dict[str, Any]
    input_tokens: int
    output_tokens: int


class ApiLLMClient:
    """Thin wrapper around anthropic.Anthropic enforcing single-tool-use extraction.

    Pass `_client` only in tests (DI for mocking).
    """

    def __init__(self, cfg: Config, *, _client: Any | None = None) -> None:
        if _client is None and not cfg.api_key:
            raise MissingApiKeyError(
                "ANTHROPIC_API_KEY is not set. Use --no-llm to skip extraction."
            )
        self.cfg = cfg
        self._client = _client or anthropic.Anthropic(
            api_key=cfg.api_key,
            max_retries=2,
            timeout=DEFAULT_TIMEOUT_SEC,
        )
        self._last_input_tokens: int = 0
        self._last_output_tokens: int = 0

    def extract(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        validate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> ExtractionRaw:
        """Single tool-use call. If `validate` raises, retry once with the error
        appended as a user message; if retry also fails, raise LLMExtractionError.
        """
        system_blocks = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        user_messages: list[dict[str, Any]] = [{"role": "user", "content": user}]

        try:
            tc = self._client.messages.count_tokens(
                model=self.cfg.model,
                system=system_blocks,  # type: ignore[arg-type]
                tools=[tool],  # type: ignore[list-item]
                messages=user_messages,  # type: ignore[arg-type]
            )
            input_tokens = int(tc.input_tokens)
        except (AttributeError, TypeError):
            input_tokens = 0

        if input_tokens > self.cfg.max_input_tokens:
            raise TranscriptTooLargeError(
                f"prompt would be {input_tokens} tokens; "
                f"max_input_tokens={self.cfg.max_input_tokens}"
            )

        payload = self._call_once(system_blocks, user_messages, tool)
        first_validation_error: Exception | None = None
        if validate is not None:
            try:
                validate(payload)
                return self._build_result(payload)
            except Exception as exc:  # noqa: BLE001
                first_validation_error = exc
        else:
            return self._build_result(payload)

        combined_user = (
            user
            + "\n\n---\n\n"
            + f"ATTENTION: A previous attempt to call {tool['name']} failed schema validation: "
            + str(first_validation_error)
            + f". Please call {tool['name']} again with a corrected payload "
            + "that strictly matches the tool's input_schema."
        )
        retry_messages: list[dict[str, Any]] = [{"role": "user", "content": combined_user}]
        try:
            payload2 = self._call_once(system_blocks, retry_messages, tool)
        except LLMExtractionError as exc:
            raise LLMExtractionError(
                f"retry after validation failure also failed: {exc}"
            ) from exc

        try:
            validate(payload2)
        except Exception as exc:  # noqa: BLE001
            raise LLMExtractionError(
                f"LLM tool input failed validation twice: first={first_validation_error}, "
                f"second={exc}"
            ) from exc
        return self._build_result(payload2)

    def _call_once(
        self,
        system_blocks: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tool: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            resp = self._client.messages.create(  # type: ignore[call-overload]
                model=self.cfg.model,
                system=system_blocks,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=messages,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
        except anthropic.APIError as exc:
            raise LLMExtractionError(f"anthropic API error: {exc}") from exc

        self._last_input_tokens = int(getattr(resp.usage, "input_tokens", 0))
        self._last_output_tokens = int(getattr(resp.usage, "output_tokens", 0))

        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise LLMExtractionError(
            "LLM response contained no tool_use block — extraction failed."
        )

    def _build_result(self, payload: dict[str, Any]) -> ExtractionRaw:
        return ExtractionRaw(
            payload=payload,
            input_tokens=self._last_input_tokens,
            output_tokens=self._last_output_tokens,
        )
