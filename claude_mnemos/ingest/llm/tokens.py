"""Local approximate token counter for CLI provider mode.

The Claude Code CLI does not expose exact input/output token counts in its
`--output-format json` envelope. We use ``tiktoken`` (OpenAI's tokenizer
library) as a close proxy: Claude uses a similar BPE algorithm; accuracy
is empirically ~85-95% on typical content.

For ApiLLMClient (anthropic.count_tokens API path) accurate counts remain
available — this module is only used by CliLLMClient.

UI must mark CLI-mode token figures with a ``~`` prefix to signal the
approximation. See docs/plans/2026-04-30-llm-cli-provider-design.md §5.
"""

from __future__ import annotations

import contextlib
import functools

import tiktoken

# Frozen builds (PyInstaller exe, py2app .app): tiktoken discovers its
# encodings by scanning the tiktoken_ext namespace package via pkgutil at
# runtime — invisible to both bundlers' static analysis, and py2app cannot
# even list a namespace package in `packages`. A direct import makes the
# plugin module visible to any bundler. Suppressed so an exotic tiktoken
# build without the plugin degrades to the old behaviour instead of
# breaking module import.
with contextlib.suppress(ImportError):
    import tiktoken_ext.openai_public  # type: ignore[import-untyped]  # noqa: F401


@functools.lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens_local(text: str) -> int:
    """Return approximate token count for *text* using cl100k_base.

    Empty string returns 0. Never raises on valid UTF-8.
    """
    if not text:
        return 0
    return len(_encoder().encode(text))
