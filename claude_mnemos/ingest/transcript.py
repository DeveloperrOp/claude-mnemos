from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class EmptyTranscriptError(ValueError):
    """Raised when the JSONL file contains no message entries."""


@dataclass(frozen=True)
class TranscriptMessage:
    role: str
    text: str
    session_id: str | None = None


def parse_jsonl(path: Path) -> list[TranscriptMessage]:
    """Parse a Claude Code session JSONL into a flat list of text messages.

    Ignores entries whose `type` is not `user` or `assistant`. Extracts text
    from both string content and block-list content (Claude's two formats).
    Raises EmptyTranscriptError if no messages are found.
    """
    messages: list[TranscriptMessage] = []
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
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
