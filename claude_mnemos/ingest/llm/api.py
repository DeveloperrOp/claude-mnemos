from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import anthropic

from claude_mnemos.config import Config, fallback_model
from claude_mnemos.ingest.llm.model_fallback import looks_like_model_not_found

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 8000
DEFAULT_TIMEOUT_SEC = 120.0


class MissingApiKeyError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is not set and ApiLLMClient is selected."""


class TranscriptTooLargeError(RuntimeError):
    """Raised when prompt token count exceeds configured max_input_tokens.

    Carries the structured counts so callers (CLI exit codes, job handlers,
    the dashboard) can show "~N tokens vs limit M" instead of parsing a string.
    ``input_tokens`` is exact for ApiLLMClient (SDK count_tokens) and
    approximate (cl100k proxy) for CliLLMClient's pre-count guard.
    """

    def __init__(
        self, message: str, *, input_tokens: int, max_input_tokens: int
    ) -> None:
        super().__init__(message)
        self.input_tokens = input_tokens
        self.max_input_tokens = max_input_tokens


class LLMExtractionError(RuntimeError):
    """Raised when LLM call fails to produce a valid tool_use payload after retry."""


class ModelNotFoundError(LLMExtractionError):
    """The configured model id was rejected by the provider (CLI or API).

    Subclasses ``LLMExtractionError`` so existing ``except LLMExtractionError``
    catches still fire if no usable fallback exists. The extract() flow catches
    it internally and retries once with ``config.fallback_model`` before letting
    it propagate.
    """


def _api_error_is_model_not_found(exc: Exception) -> bool:
    """True if an anthropic exception means 'that model id does not exist'."""
    status = getattr(exc, "status_code", None)
    if status == 404:
        return True
    return looks_like_model_not_found(str(exc))


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
        # Effective model for this client. extract() flips it to
        # fallback_model(cfg.model) once if the provider rejects cfg.model,
        # so all subsequent calls (validation retries) reuse the working one.
        self._model = cfg.model
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
                model=self._model,
                system=system_blocks,  # type: ignore[arg-type]
                tools=[tool],  # type: ignore[list-item]
                messages=user_messages,  # type: ignore[arg-type]
            )
            input_tokens = int(tc.input_tokens)
        except (AttributeError, TypeError):
            input_tokens = 0
        except anthropic.APIError:
            # Can't pre-count (e.g. the model id is rejected) — skip the size
            # guard and let _call_once() surface/handle the real error.
            input_tokens = 0

        if input_tokens > self.cfg.max_input_tokens:
            raise TranscriptTooLargeError(
                f"prompt would be {input_tokens} tokens; "
                f"max_input_tokens={self.cfg.max_input_tokens}",
                input_tokens=input_tokens,
                max_input_tokens=self.cfg.max_input_tokens,
            )

        payload = self._call_with_model_fallback(system_blocks, user_messages, tool)
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

    def _call_with_model_fallback(
        self,
        system_blocks: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tool: dict[str, Any],
    ) -> dict[str, Any]:
        """First model call. If the provider rejects ``cfg.model`` as unknown,
        switch ``self._model`` to ``fallback_model(cfg.model)`` once and retry,
        so a retired model id doesn't break every ingest until the user edits
        the setting. Subsequent calls (validation retries) reuse the fallback.
        """
        try:
            return self._call_once(system_blocks, messages, tool)
        except ModelNotFoundError:
            fb = fallback_model(self.cfg.model)
            if fb == self._model:
                raise  # nothing else to try
            logger.warning(
                "model %s rejected by Anthropic API; retrying with fallback %s",
                self._model,
                fb,
            )
            self._model = fb
            return self._call_once(system_blocks, messages, tool)

    def _call_once(
        self,
        system_blocks: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tool: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            resp = self._client.messages.create(  # type: ignore[call-overload]
                model=self._model,
                system=system_blocks,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=messages,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
        except anthropic.APIError as exc:
            if _api_error_is_model_not_found(exc):
                raise ModelNotFoundError(
                    f"model {self._model!r} not available: {exc}"
                ) from exc
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
