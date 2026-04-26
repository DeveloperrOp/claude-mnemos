from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.models import WikiPage, WikiPageFrontmatter
from claude_mnemos.ingest.transcript import TranscriptMessage, parse_jsonl


@dataclass(frozen=True)
class IngestResult:
    page_path: Path
    session_id: str
    message_count: int


def ingest_minimal(
    jsonl_path: Path,
    vault_root: Path,
    *,
    lock_timeout: float = 60.0,
) -> IngestResult:
    """Read one JSONL session and write one source page atomically.

    Spec: minimal e2e of section 8.1 (without LLM extraction, staging,
    snapshots, activity log — those are subsequent plans).
    """
    vault_root.mkdir(parents=True, exist_ok=True)
    with pipeline_lock(vault_root, timeout=lock_timeout):
        messages = parse_jsonl(jsonl_path)
        session_id = _resolve_session_id(messages, jsonl_path)
        page = _build_page(messages, session_id)
        target = vault_root / page.relative_path
        atomic_write(target, page.serialize())
        return IngestResult(
            page_path=target,
            session_id=session_id,
            message_count=len(messages),
        )


def _resolve_session_id(messages: list[TranscriptMessage], jsonl_path: Path) -> str:
    for m in messages:
        if m.session_id:
            return m.session_id
    return jsonl_path.stem


def _build_page(messages: list[TranscriptMessage], session_id: str) -> WikiPage:
    today = date.today()
    first_user = next((m.text for m in messages if m.role == "user"), "")
    title = _make_title(first_user, session_id)
    body = _render_body(messages)
    fm = WikiPageFrontmatter(
        title=title,
        type="source",
        sources=[session_id],
        created=today,
        updated=today,
    )
    return WikiPage(
        relative_path=Path("raw/chats") / f"{session_id}.md",
        frontmatter=fm,
        body=body,
    )


def _make_title(first_user_text: str, session_id: str) -> str:
    snippet = first_user_text.strip().splitlines()[0] if first_user_text.strip() else ""
    if not snippet:
        return f"Session {session_id}"
    if len(snippet) > 80:
        snippet = snippet[:77] + "…"
    return snippet


def _render_body(messages: list[TranscriptMessage]) -> str:
    lines = ["# Transcript", ""]
    for m in messages:
        lines.append(f"## {m.role}")
        lines.append("")
        lines.append(m.text)
        lines.append("")
    return "\n".join(lines)
