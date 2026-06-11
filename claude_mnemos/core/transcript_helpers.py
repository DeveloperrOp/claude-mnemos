"""Disk helpers shared by lost_sessions and transcript_scanner.

Extracts transcript helpers (SHA-256, cwd extraction, preview generation)
into a common module to avoid circular import risk when both modules need
to import from each other.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

_SHA_CHUNK_SIZE = 64 * 1024

PREVIEW_MAX_CHARS = 200
PREVIEW_SCAN_LINES = 50  # Read at most N lines per file looking for cwd + first user message.

# System-injected user messages we skip when picking a preview (we want what
# the human actually typed, not IDE/shell metadata wrappers).
_SYSTEM_PREVIEW_PREFIXES = (
    "<ide_opened_file>",
    "<ide_selection>",
    "<ide_diagnostics>",
    "<system-reminder>",
    "<command-message>",
    "<command-name>",
    "<command-args>",
    "<command-stdout>",
    "<command-stderr>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
)


def _resolve_transcripts_root(transcripts_root: Path | None) -> Path:
    if transcripts_root is not None:
        return transcripts_root
    env_value = os.environ.get("MNEMOS_TRANSCRIPTS_ROOT")
    if env_value:
        return Path(env_value)
    return Path.home() / ".claude" / "projects"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_SHA_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _extract_text_from_content(content: object) -> str | None:
    """Pull a text string out of either a raw str content or Anthropic content-block list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str) and t:
                    return t
    return None


def _user_text_from_event(event: dict[str, Any]) -> str | None:
    """Extract user-typed text from a JSONL event, supporting both shapes:

    * ``{"type":"user","content":...}`` (synthetic / generic shape used in our tests
      and possibly by other consumers).
    * ``{"type":"user","message":{"role":"user","content":...}}`` (the real
      Claude Code transcript shape — what `~/.claude/projects/*/*.jsonl` actually
      contains).
    """
    if event.get("type") != "user":
        return None
    text = _extract_text_from_content(event.get("content"))
    if text is not None:
        return text
    message = event.get("message")
    if isinstance(message, dict):
        return _extract_text_from_content(message.get("content"))
    return None


def _extract_cwd_and_preview(path: Path) -> tuple[str | None, str | None]:
    """Read up to PREVIEW_SCAN_LINES JSONL lines, extract cwd + first user message.

    JSONL events vary by Claude Code version. We look for:
    - any event with a top-level "cwd" key (Anthropic CLI puts it on every event;
      Antigravity / other consumers may put it on a single bootstrap event).
    - the first event with type=="user" carrying user-typed text. We skip messages
      whose body starts with an IDE / system / shell wrapper tag (e.g.
      ``<ide_opened_file>...``, ``<command-message>...``) since those are not what
      the human typed and would make every preview look the same.

    Truncates preview to PREVIEW_MAX_CHARS. Tolerates missing fields, malformed
    JSON lines, and OSError on read — degrades to (None, None).
    """
    cwd: str | None = None
    preview: str | None = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= PREVIEW_SCAN_LINES:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if cwd is None:
                    found_cwd = event.get("cwd")
                    if isinstance(found_cwd, str) and found_cwd:
                        cwd = found_cwd
                if preview is None:
                    text = _user_text_from_event(event)
                    if text:
                        stripped = text.lstrip()
                        if not stripped.startswith(_SYSTEM_PREVIEW_PREFIXES):
                            collapsed = " ".join(text.split())
                            preview = collapsed[:PREVIEW_MAX_CHARS]
                            if len(collapsed) > PREVIEW_MAX_CHARS:
                                preview = preview.rstrip() + "…"
                if cwd is not None and preview is not None:
                    break
    except OSError:
        pass
    return cwd, preview
