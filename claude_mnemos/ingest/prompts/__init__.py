from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=1)
def load_system() -> str:
    return (_PROMPTS_DIR / "system.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _load_user_template() -> str:
    return (_PROMPTS_DIR / "extract_user.md").read_text(encoding="utf-8")


def format_user(*, transcript: str, language_hint: str) -> str:
    template = _load_user_template()
    return template.replace("{language_hint}", language_hint).replace("{transcript}", transcript)
