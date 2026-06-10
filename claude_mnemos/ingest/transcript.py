from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class EmptyTranscriptError(ValueError):
    """Raised when the JSONL file contains no message entries.

    A *legitimate* empty case: valid JSON lines existed but none carried a
    user/assistant text message (e.g. a pure tool_use/tool_result session).
    The ingest handler treats this as a no-op success.
    """


class CorruptTranscriptError(ValueError):
    """Raised when the file yielded NO usable lines AND had JSON-decode errors
    — i.e. it isn't a valid JSONL transcript at all (truncated, binary, wrong
    encoding). Distinct from EmptyTranscriptError so the handler lets it fail
    loudly (dead-letter) instead of marking the job succeeded and hiding data
    loss behind a 'pure-tool session' log line."""


@dataclass(frozen=True)
class TranscriptMessage:
    role: str
    text: str
    session_id: str | None = None


def parse_jsonl(path: Path) -> list[TranscriptMessage]:
    """Parse a Claude Code session JSONL into a flat list of text messages.

    Skips entries whose ``type`` is not ``user`` or ``assistant``, and skips
    malformed JSON lines silently. Also skips user/assistant entries whose
    ``content`` contains no text blocks (e.g. pure ``tool_use``/``tool_result``
    entries). Raises ``EmptyTranscriptError`` when no messages survive these
    filters — which can happen even on a non-empty file.
    """
    messages: list[TranscriptMessage] = []
    decode_errors = 0
    nonblank_lines = 0
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        nonblank_lines += 1
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            decode_errors += 1
            continue
        kind = entry.get("type")
        if kind not in ("user", "assistant"):
            continue
        msg = entry.get("message")
        if not isinstance(msg, dict):
            continue
        text = _extract_text(msg.get("content"))
        if text is None:
            continue
        messages.append(
            TranscriptMessage(
                role=msg.get("role", kind),
                text=text,
                session_id=entry.get("sessionId"),
            )
        )
    if not messages:
        # No usable messages. Distinguish a real transcript with nothing to
        # extract (let it succeed as a no-op) from a file that simply isn't a
        # valid JSONL transcript (every non-blank line failed to parse) — the
        # latter is corruption/data-loss and must fail loudly.
        if nonblank_lines > 0 and decode_errors == nonblank_lines:
            raise CorruptTranscriptError(
                f"no parseable JSON lines in {path} "
                f"({decode_errors}/{nonblank_lines} lines failed to decode)"
            )
        raise EmptyTranscriptError(f"no message entries in {path}")
    return messages


def _extract_text(content: object) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
        if parts:
            return "\n".join(parts)
    return None
