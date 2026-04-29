from __future__ import annotations

import os
from unittest.mock import patch

from claude_mnemos.config import Config


def _base_env() -> dict[str, str]:
    return {
        "ANTHROPIC_API_KEY": "",
        "MNEMOS_MODEL": "sonnet",
        "MNEMOS_LANGUAGE_HINT": "auto",
    }


def test_default_ingest_provider_is_none() -> None:
    with patch.dict(os.environ, _base_env(), clear=True):
        cfg = Config.from_env()
    assert cfg.ingest_provider is None


def test_explicit_cli_via_env() -> None:
    env = _base_env() | {"MNEMOS_INGEST_PROVIDER": "cli"}
    with patch.dict(os.environ, env, clear=True):
        cfg = Config.from_env()
    assert cfg.ingest_provider == "cli"


def test_explicit_api_via_env() -> None:
    env = _base_env() | {"MNEMOS_INGEST_PROVIDER": "api"}
    with patch.dict(os.environ, env, clear=True):
        cfg = Config.from_env()
    assert cfg.ingest_provider == "api"


def test_invalid_ingest_provider_raises() -> None:
    import pytest

    env = _base_env() | {"MNEMOS_INGEST_PROVIDER": "openai"}
    with patch.dict(os.environ, env, clear=True), \
         pytest.raises(ValueError, match="ingest_provider"):
        Config.from_env()


def test_with_overrides_preserves_ingest_provider() -> None:
    with patch.dict(os.environ, _base_env(), clear=True):
        base = Config.from_env()
    overridden = base.with_overrides(ingest_provider="cli")
    assert overridden.ingest_provider == "cli"
    # Original untouched (frozen dataclass)
    assert base.ingest_provider is None
