import pytest

from claude_mnemos.config import (
    DEFAULT_MAX_INPUT_TOKENS,
    DEFAULT_MODEL,
    Config,
    UnknownLanguageHintError,
    resolve_model_id,
)


def test_default_config(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MNEMOS_MODEL", raising=False)
    monkeypatch.delenv("MNEMOS_LANGUAGE_HINT", raising=False)
    monkeypatch.delenv("MNEMOS_MAX_INPUT_TOKENS", raising=False)
    monkeypatch.delenv("MNEMOS_LOCK_TIMEOUT", raising=False)

    cfg = Config.from_env()
    assert cfg.api_key is None
    assert cfg.model == DEFAULT_MODEL
    assert cfg.language_hint == "auto"
    assert cfg.max_input_tokens == DEFAULT_MAX_INPUT_TOKENS
    assert cfg.lock_timeout == 60.0


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("MNEMOS_MODEL", "haiku")
    monkeypatch.setenv("MNEMOS_LANGUAGE_HINT", "uk")
    monkeypatch.setenv("MNEMOS_MAX_INPUT_TOKENS", "50000")
    monkeypatch.setenv("MNEMOS_LOCK_TIMEOUT", "10.5")

    cfg = Config.from_env()
    assert cfg.api_key == "sk-test"
    assert cfg.model.startswith("claude-haiku-")
    assert cfg.language_hint == "uk"
    assert cfg.max_input_tokens == 50000
    assert cfg.lock_timeout == 10.5


def test_with_overrides_keeps_unset_from_env(monkeypatch):
    monkeypatch.setenv("MNEMOS_MODEL", "sonnet")
    cfg = Config.from_env().with_overrides(language_hint="en")
    assert cfg.model.startswith("claude-sonnet-")
    assert cfg.language_hint == "en"


def test_with_overrides_explicit_full_id_passes_through():
    cfg = Config.from_env().with_overrides(model="claude-opus-4-7")
    assert cfg.model == "claude-opus-4-7"


def test_resolve_model_id_aliases():
    assert resolve_model_id("sonnet") == "claude-sonnet-4-6"
    assert resolve_model_id("haiku") == "claude-haiku-4-5-20251001"
    assert resolve_model_id("opus") == "claude-opus-4-7"


def test_resolve_model_id_pass_through():
    assert resolve_model_id("claude-something-custom") == "claude-something-custom"


def test_invalid_language_hint_raises(monkeypatch):
    monkeypatch.setenv("MNEMOS_LANGUAGE_HINT", "klingon")
    with pytest.raises(UnknownLanguageHintError):
        Config.from_env()


def test_invalid_max_input_tokens_raises(monkeypatch):
    monkeypatch.setenv("MNEMOS_MAX_INPUT_TOKENS", "not-a-number")
    with pytest.raises(ValueError):
        Config.from_env()


def test_with_overrides_invalid_language_hint_raises():
    cfg = Config(
        api_key=None,
        model="claude-sonnet-4-6",
        language_hint="auto",
        max_input_tokens=150_000,
        lock_timeout=60.0,
    )
    with pytest.raises(UnknownLanguageHintError):
        cfg.with_overrides(language_hint="klingon")  # type: ignore[arg-type]
