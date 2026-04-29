from __future__ import annotations

from claude_mnemos.config import Config
from claude_mnemos.ingest.llm import (
    ApiLLMClient,
    make_llm_client,
)
from claude_mnemos.ingest.llm.cli import CliLLMClient


def _cfg(*, api_key: str | None = None, provider=None) -> Config:
    return Config(
        api_key=api_key,
        model="claude-sonnet-4-5",
        language_hint="auto",
        max_input_tokens=180000,
        lock_timeout=30.0,
        ingest_provider=provider,
    )


def test_explicit_api_returns_api_client_when_key_present() -> None:
    cfg = _cfg(api_key="sk-test", provider="api")
    client = make_llm_client(cfg)
    assert isinstance(client, ApiLLMClient)


def test_explicit_api_raises_when_key_missing() -> None:
    import pytest

    from claude_mnemos.ingest.llm import MissingApiKeyError

    cfg = _cfg(api_key=None, provider="api")
    with pytest.raises(MissingApiKeyError):
        make_llm_client(cfg)


def test_explicit_cli_returns_cli_client() -> None:
    cfg = _cfg(api_key=None, provider="cli")
    client = make_llm_client(cfg)
    assert isinstance(client, CliLLMClient)


def test_explicit_cli_returns_cli_client_even_when_api_key_present() -> None:
    """If user explicitly opts into CLI, honour that even with key present.
    Subprocess env will strip ANTHROPIC_API_KEY."""
    cfg = _cfg(api_key="sk-test", provider="cli")
    assert isinstance(make_llm_client(cfg), CliLLMClient)


def test_auto_detect_uses_api_when_key_set() -> None:
    cfg = _cfg(api_key="sk-test", provider=None)
    assert isinstance(make_llm_client(cfg), ApiLLMClient)


def test_auto_detect_falls_back_to_cli_when_no_key() -> None:
    cfg = _cfg(api_key=None, provider=None)
    assert isinstance(make_llm_client(cfg), CliLLMClient)
