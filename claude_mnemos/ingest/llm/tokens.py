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
import logging
import os
from pathlib import Path

import tiktoken

_LOG = logging.getLogger(__name__)

# Frozen builds (PyInstaller exe, py2app .app): tiktoken discovers its
# encodings by scanning the tiktoken_ext namespace package via pkgutil at
# runtime — invisible to both bundlers' static analysis, and py2app cannot
# even list a namespace package in `packages`. A direct import makes the
# plugin module visible to any bundler. Suppressed so an exotic tiktoken
# build without the plugin degrades to the old behaviour instead of
# breaking module import.
with contextlib.suppress(ImportError):
    import tiktoken_ext.openai_public  # type: ignore[import-untyped]  # noqa: F401


def _ensure_cache_dir_env() -> None:
    """Pin tiktoken's BPE download cache to a durable per-user dir.

    tiktoken defaults to %TEMP%/data-gym-cache, which Windows Storage Sense
    purges — every purge costs a 1.7 MB re-download from
    openaipublic.blob.core.windows.net and a hard failure when offline.
    A pre-set TIKTOKEN_CACHE_DIR is respected (user override).
    tiktoken creates the directory itself on first download.
    """
    os.environ.setdefault(
        "TIKTOKEN_CACHE_DIR",
        str(Path.home() / ".claude-mnemos" / "tiktoken-cache"),
    )


# At import time — tiktoken reads the env var on each load, so this only has
# to happen before the first get_encoding() call, which _encoder() guarantees.
_ensure_cache_dir_env()

# Warn-once flag for degraded token counting (see count_tokens_local).
_degrade_warned = False


@functools.lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens_local(text: str) -> int:
    """Return approximate token count for *text* using cl100k_base.

    Empty string returns 0. Never raises: token counts are cosmetic (~approx)
    and this runs AFTER the paid `claude -p` call — a cold BPE cache plus no
    network must degrade to 0, not fail the whole extract. lru_cache only
    memoizes success, so a later call retries once the network is back.
    """
    if not text:
        return 0
    try:
        enc = _encoder()
    except Exception as exc:  # noqa: BLE001 — any tokenizer failure degrades
        global _degrade_warned
        if not _degrade_warned:
            _LOG.warning(
                "tiktoken unavailable (%s: %s) — approximate token counts "
                "degrade to 0 until the BPE table can be loaded",
                type(exc).__name__,
                exc,
            )
            _degrade_warned = True
        return 0
    return len(enc.encode(text))


def probe_tokenizer() -> tuple[bool, str]:
    """Hard tokenizer check for CI smoke / diagnostics — no degrade.

    count_tokens_local masks tokenizer failures by design, so a broken
    frozen bundle (missing tiktoken_ext plugin) would go unnoticed. This
    probe surfaces the failure: returns (ok, human-readable detail).
    """
    try:
        n = len(_encoder().encode("claude-mnemos tokenizer probe"))
    except Exception as exc:  # noqa: BLE001 — diagnostic façade
        return False, f"{type(exc).__name__}: {exc}"
    return True, f"cl100k_base ok ({n} tokens)"
