from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Literal, cast

LanguageHint = Literal["auto", "uk", "ru", "en"]
IngestProvider = Literal["cli", "api"]
_VALID_PROVIDERS: set[str] = {"cli", "api"}

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_INPUT_TOKENS = 150_000
DEFAULT_LOCK_TIMEOUT = 60.0
DEFAULT_LANGUAGE_HINT: LanguageHint = "auto"

_MODEL_ALIASES = {
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
    # v0.0.38: "opus" alias points at the newest 4.8. Anthropic typically
    # retires older models 6-12 months after a new tier ships, so we
    # keep the alias on the latest while explicit "claude-opus-4-7"
    # users keep what they asked for.
    "opus": "claude-opus-4-8",
}

# Known-good Claude model IDs as of 2026-05. When the user has configured
# a model that the local CLI rejects ("model not found"), the LLM client
# falls back through this list to keep extraction working until the user
# updates the setting in the UI.
KNOWN_MODELS_NEWEST_FIRST = (
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
)


def fallback_model(requested: str) -> str:
    """Pick the newest known-good model that is *not* the requested one,
    used as a last-resort when the configured model is rejected by the
    local CLI/API. Returns the requested model unchanged if it's not in
    our known set (assume the user knows what they're doing)."""
    if requested not in KNOWN_MODELS_NEWEST_FIRST:
        return requested
    for m in KNOWN_MODELS_NEWEST_FIRST:
        if m != requested:
            return m
    return requested

_VALID_HINTS: set[str] = {"auto", "uk", "ru", "en"}


class UnknownLanguageHintError(ValueError):
    """Raised when MNEMOS_LANGUAGE_HINT is not in {auto, uk, ru, en}."""


def resolve_model_id(model_or_alias: str) -> str:
    """Map sonnet/haiku/opus aliases to full model ids; pass through others."""
    return _MODEL_ALIASES.get(model_or_alias, model_or_alias)


@dataclass(frozen=True)
class Config:
    api_key: str | None
    model: str
    language_hint: LanguageHint
    max_input_tokens: int
    lock_timeout: float
    ingest_provider: IngestProvider | None = None

    @classmethod
    def from_env(cls) -> Config:
        api_key = os.environ.get("ANTHROPIC_API_KEY") or None

        model_raw = os.environ.get("MNEMOS_MODEL", DEFAULT_MODEL)
        model = resolve_model_id(model_raw)

        hint_raw = os.environ.get("MNEMOS_LANGUAGE_HINT", DEFAULT_LANGUAGE_HINT)
        if hint_raw not in _VALID_HINTS:
            raise UnknownLanguageHintError(
                f"MNEMOS_LANGUAGE_HINT={hint_raw!r}; expected one of {sorted(_VALID_HINTS)}"
            )

        max_tokens_raw = os.environ.get("MNEMOS_MAX_INPUT_TOKENS")
        if max_tokens_raw is None:
            max_tokens = DEFAULT_MAX_INPUT_TOKENS
        else:
            try:
                max_tokens = int(max_tokens_raw)
            except ValueError as exc:
                raise ValueError(
                    f"MNEMOS_MAX_INPUT_TOKENS={max_tokens_raw!r}: expected integer"
                ) from exc

        lock_raw = os.environ.get("MNEMOS_LOCK_TIMEOUT")
        if lock_raw is None:
            lock = DEFAULT_LOCK_TIMEOUT
        else:
            try:
                lock = float(lock_raw)
            except ValueError as exc:
                raise ValueError(
                    f"MNEMOS_LOCK_TIMEOUT={lock_raw!r}: expected float"
                ) from exc

        provider_raw = os.environ.get("MNEMOS_INGEST_PROVIDER")
        if provider_raw is not None and provider_raw not in _VALID_PROVIDERS:
            raise ValueError(
                f"MNEMOS_INGEST_PROVIDER={provider_raw!r}; "
                f"ingest_provider must be one of {sorted(_VALID_PROVIDERS)}"
            )

        return cls(
            api_key=api_key,
            model=model,
            language_hint=cast(LanguageHint, hint_raw),
            max_input_tokens=max_tokens,
            lock_timeout=lock,
            ingest_provider=cast("IngestProvider | None", provider_raw),
        )

    def with_overrides(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        language_hint: LanguageHint | None = None,
        max_input_tokens: int | None = None,
        lock_timeout: float | None = None,
        ingest_provider: IngestProvider | None = None,
    ) -> Config:
        if language_hint is not None and language_hint not in _VALID_HINTS:
            raise UnknownLanguageHintError(
                f"language_hint={language_hint!r}; expected one of {sorted(_VALID_HINTS)}"
            )
        return replace(
            self,
            api_key=api_key if api_key is not None else self.api_key,
            model=resolve_model_id(model) if model is not None else self.model,
            language_hint=language_hint if language_hint is not None else self.language_hint,
            max_input_tokens=(
                max_input_tokens if max_input_tokens is not None else self.max_input_tokens
            ),
            lock_timeout=lock_timeout if lock_timeout is not None else self.lock_timeout,
            ingest_provider=(
                ingest_provider if ingest_provider is not None else self.ingest_provider
            ),
        )
