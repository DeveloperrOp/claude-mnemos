from unittest.mock import MagicMock

import anthropic
import pytest

from claude_mnemos.config import Config, fallback_model
from claude_mnemos.ingest.llm import (
    ApiLLMClient,
    LLMExtractionError,
    MissingApiKeyError,
    ModelNotFoundError,
    TranscriptTooLargeError,
)


class _FakeNotFound(anthropic.APIError):
    """Minimal anthropic.APIError subclass standing in for a 404 model-not-found
    response, without the SDK's required (message, request, body) ctor args."""

    def __init__(self, message: str = 'not_found_error: model not found') -> None:
        self.message = message
        self.status_code = 404

    def __str__(self) -> str:
        return self.message


def _cfg(**overrides) -> Config:
    base = dict(
        api_key="sk-test",
        model="claude-sonnet-4-6",
        language_hint="auto",
        max_input_tokens=10_000,
        lock_timeout=60.0,
    )
    base.update(overrides)
    return Config(**base)


def _make_response_with_tool_use(payload: dict):
    """Construct a minimal anthropic Message-like object with one tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "save_wiki_pages"
    block.input = payload

    resp = MagicMock()
    resp.content = [block]
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    resp.usage = usage
    return resp


def _make_token_count(input_tokens: int):
    tc = MagicMock()
    tc.input_tokens = input_tokens
    return tc


def test_missing_api_key_raises():
    cfg = _cfg(api_key=None)
    with pytest.raises(MissingApiKeyError):
        ApiLLMClient(cfg)


def test_transcript_too_large_raises():
    cfg = _cfg(max_input_tokens=1000)
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(2000)

    client = ApiLLMClient(cfg, _client=inner)
    with pytest.raises(TranscriptTooLargeError):
        client.extract(system="sys", user="usr", tool=_dummy_tool())

    inner.messages.create.assert_not_called()


def test_transcript_too_large_carries_structured_token_counts():
    cfg = _cfg(max_input_tokens=1000)
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(2000)

    client = ApiLLMClient(cfg, _client=inner)
    with pytest.raises(TranscriptTooLargeError) as ei:
        client.extract(system="sys", user="usr", tool=_dummy_tool())

    err = ei.value
    assert err.input_tokens == 2000
    assert err.max_input_tokens == cfg.max_input_tokens == 1000
    assert err.input_tokens > err.max_input_tokens


def test_successful_extract_returns_payload_and_usage():
    cfg = _cfg()
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(500)

    valid_payload = {
        "summary": "ok",
        "skipped_reason": None,
        "pages": [
            {
                "type": "entity",
                "title": "X",
                "slug_hint": None,
                "flavor": [],
                "confidence": 0.7,
                "provenance": {"extracted_pct": 100, "inferred_pct": 0, "ambiguous_pct": 0},
                "related": [],
                "body": "body",
            }
        ],
    }
    inner.messages.create.return_value = _make_response_with_tool_use(valid_payload)

    client = ApiLLMClient(cfg, _client=inner)
    result = client.extract(system="sys", user="usr", tool=_dummy_tool())

    assert result.payload == valid_payload
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    inner.messages.create.assert_called_once()


def test_tool_choice_forces_tool():
    cfg = _cfg()
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(500)
    inner.messages.create.return_value = _make_response_with_tool_use({"summary": "x", "pages": []})

    client = ApiLLMClient(cfg, _client=inner)
    client.extract(system="sys", user="usr", tool=_dummy_tool())

    kwargs = inner.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "save_wiki_pages"}
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_retries_once_on_validation_error_then_succeeds():
    cfg = _cfg()
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(500)

    invalid = {"summary": "x"}  # missing required "pages"
    valid = {"summary": "x", "pages": []}
    inner.messages.create.side_effect = [
        _make_response_with_tool_use(invalid),
        _make_response_with_tool_use(valid),
    ]

    client = ApiLLMClient(cfg, _client=inner)

    def validate_payload(p):
        if "pages" not in p:
            raise ValueError("missing pages")
        return p

    result = client.extract(
        system="sys", user="usr", tool=_dummy_tool(), validate=validate_payload
    )

    assert result.payload == valid
    assert inner.messages.create.call_count == 2

    # After existing assertions, verify the retry sent a single user message (not multi-turn)
    second_call_kwargs = inner.messages.create.call_args_list[1].kwargs
    assert len(second_call_kwargs["messages"]) == 1
    assert second_call_kwargs["messages"][0]["role"] == "user"
    assert "previous attempt" in second_call_kwargs["messages"][0]["content"].lower()
    assert "save_wiki_pages" in second_call_kwargs["messages"][0]["content"]


def test_raises_after_two_validation_failures():
    cfg = _cfg()
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(500)

    bad = {"summary": "x"}
    inner.messages.create.return_value = _make_response_with_tool_use(bad)

    client = ApiLLMClient(cfg, _client=inner)

    def validate_payload(p):
        raise ValueError("always fails")

    with pytest.raises(LLMExtractionError):
        client.extract(
            system="sys", user="usr", tool=_dummy_tool(), validate=validate_payload
        )

    assert inner.messages.create.call_count == 2


def test_falls_back_when_model_rejected():
    """If the API rejects cfg.model as unknown (404), the client retries once
    with fallback_model() and the second create() call uses the fallback id."""
    cfg = _cfg(model="claude-opus-4-8")  # in KNOWN_MODELS → has a fallback
    inner = MagicMock()
    # count_tokens also fails on the bad model — must be swallowed, not fatal.
    inner.messages.count_tokens.side_effect = _FakeNotFound()
    valid = {"summary": "x", "pages": []}
    inner.messages.create.side_effect = [
        _FakeNotFound(),
        _make_response_with_tool_use(valid),
    ]

    client = ApiLLMClient(cfg, _client=inner)
    result = client.extract(system="sys", user="usr", tool=_dummy_tool())

    assert result.payload == valid
    assert inner.messages.create.call_count == 2
    fb = fallback_model("claude-opus-4-8")
    assert fb != "claude-opus-4-8"
    assert inner.messages.create.call_args_list[1].kwargs["model"] == fb


def test_model_not_found_raises_when_no_fallback():
    """An unknown model id outside KNOWN_MODELS has no fallback — the error
    propagates as ModelNotFoundError."""
    cfg = _cfg(model="claude-sonnet-4-5")  # not in KNOWN_MODELS
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(500)
    inner.messages.create.side_effect = _FakeNotFound()

    client = ApiLLMClient(cfg, _client=inner)
    with pytest.raises(ModelNotFoundError):
        client.extract(system="sys", user="usr", tool=_dummy_tool())
    assert inner.messages.create.call_count == 1


def test_response_without_tool_use_block_raises():
    cfg = _cfg()
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(500)

    bad_resp = MagicMock()
    block = MagicMock()
    block.type = "text"
    bad_resp.content = [block]
    inner.messages.create.return_value = bad_resp

    client = ApiLLMClient(cfg, _client=inner)

    with pytest.raises(LLMExtractionError):
        client.extract(system="sys", user="usr", tool=_dummy_tool())


def _dummy_tool() -> dict:
    return {
        "name": "save_wiki_pages",
        "description": "test",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }
