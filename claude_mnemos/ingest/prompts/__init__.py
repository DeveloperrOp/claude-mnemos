from __future__ import annotations

from functools import lru_cache

from claude_mnemos.runtime import prompts_dir as _runtime_prompts_dir

_PROMPTS_DIR = _runtime_prompts_dir()


@lru_cache(maxsize=1)
def load_system() -> str:
    return (_PROMPTS_DIR / "system.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _load_user_template() -> str:
    return (_PROMPTS_DIR / "extract_user.md").read_text(encoding="utf-8")


def format_user(*, transcript: str, language_hint: str, chunk_note: str = "") -> str:
    template = _load_user_template()
    # When there is no chunk note (the single-chunk case), drop the whole
    # placeholder line so the rendered prompt is identical to the pre-chunking
    # template — zero behaviour change for existing callers.
    if chunk_note:
        template = template.replace("{chunk_note}", chunk_note)
    else:
        template = template.replace("\n{chunk_note}", "").replace("{chunk_note}", "")
    return template.replace("{language_hint}", language_hint).replace("{transcript}", transcript)
