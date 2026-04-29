"""Round-trip page reader/writer that preserves unknown frontmatter keys.

The canonical `WikiPage` (core/models.py) is strict (`extra="forbid"`) — that
contract holds for ingest writes (LLM never adds extras). But pages roundtripped
through external editors (Obsidian) can pick up extra YAML keys like `cssclass`
or `obsidianUIMode`. The watchdog handler (Plan #9) needs to mutate frontmatter
without losing those extras.

`read_page`/`serialize_page` provide that round-trip path: known fields validate
through Pydantic, unknown keys pass through verbatim in `extra_fm`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from claude_mnemos.core.models import WikiPageFrontmatter


def slug_from_page_path(vault: Path, page_path: Path) -> str:
    """Slug = relative path under ``vault/wiki/`` without ``.md`` suffix.

    Example: ``vault/wiki/concepts/foo.md`` → ``concepts/foo``.
    Always uses forward slashes (Windows-safe).
    """
    rel = page_path.relative_to(vault / "wiki")
    return str(rel.with_suffix("")).replace("\\", "/")


class PageParseError(ValueError):
    """Raised when a markdown page cannot be parsed (missing or invalid frontmatter)."""


@dataclass(frozen=True)
class ParsedPage:
    frontmatter: WikiPageFrontmatter
    extra_fm: dict[str, Any]
    body: str


def read_page(path: Path) -> ParsedPage:
    text = path.read_text(encoding="utf-8")
    fm_dict, body = _split_frontmatter(text)
    known_keys = set(WikiPageFrontmatter.model_fields)
    known = {k: v for k, v in fm_dict.items() if k in known_keys}
    extras = {k: v for k, v in fm_dict.items() if k not in known_keys}
    try:
        fm = WikiPageFrontmatter.model_validate(known)
    except ValidationError as exc:
        raise PageParseError(f"frontmatter invalid: {exc}") from exc
    return ParsedPage(frontmatter=fm, extra_fm=extras, body=body)


def serialize_page(parsed: ParsedPage) -> str:
    fm_dict: dict[str, Any] = {
        **parsed.frontmatter.model_dump(mode="json", exclude_defaults=False),
        **parsed.extra_fm,
    }
    yaml_block = yaml.safe_dump(
        fm_dict,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return f"---\n{yaml_block}---\n{parsed.body.rstrip(chr(10))}\n"


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise PageParseError("page does not start with YAML frontmatter")
    end_marker = text.find("\n---\n", 4)
    if end_marker == -1:
        raise PageParseError("YAML frontmatter is not closed")
    fm_text = text[4:end_marker]
    body = text[end_marker + len("\n---\n") :]
    try:
        fm_dict = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        raise PageParseError(f"YAML parse error: {exc}") from exc
    if not isinstance(fm_dict, dict):
        raise PageParseError("frontmatter is not a YAML mapping")
    return fm_dict, body
