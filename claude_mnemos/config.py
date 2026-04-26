from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Literal, cast

LanguageHint = Literal["auto", "uk", "ru", "en"]

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_INPUT_TOKENS = 150_000
DEFAULT_LOCK_TIMEOUT = 60.0
DEFAULT_LANGUAGE_HINT: LanguageHint = "auto"

_MODEL_ALIASES = {
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
    "opus": "claude-opus-4-7",
}

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

        return cls(
            api_key=api_key,
            model=model,
            language_hint=cast(LanguageHint, hint_raw),
            max_input_tokens=max_tokens,
            lock_timeout=lock,
        )

    def with_overrides(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        language_hint: LanguageHint | None = None,
        max_input_tokens: int | None = None,
        lock_timeout: float | None = None,
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
        )
