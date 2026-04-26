from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from claude_mnemos.config import Config
from claude_mnemos.core.models import (
    ExtractedPage,
    ExtractionPayload,
    WikiPage,
    WikiPageFrontmatter,
    save_wiki_pages_tool_schema,
)
from claude_mnemos.core.slug import make_slug
from claude_mnemos.ingest.llm import LLMClient
from claude_mnemos.ingest.prompts import format_user, load_system
from claude_mnemos.ingest.transcript import TranscriptMessage


@dataclass(frozen=True)
class ExtractionResult:
    summary: str
    skipped_reason: str | None
    pages: list[WikiPage]
    input_tokens: int
    output_tokens: int


def extract_wiki_pages(
    *,
    messages: list[TranscriptMessage],
    cfg: Config,
    llm_client: LLMClient,
    today: date,
) -> ExtractionResult:
    """Run the LLM extraction over a parsed transcript and return wiki pages.

    `today` is injected for testability (deterministic created/updated).
    """
    transcript_text = _render_transcript(messages)
    system = load_system()
    user = format_user(transcript=transcript_text, language_hint=cfg.language_hint)

    raw = llm_client.extract(
        system=system,
        user=user,
        tool=save_wiki_pages_tool_schema(),
        validate=_validate_payload,
    )

    payload = ExtractionPayload.model_validate(raw.payload)

    pages = [_render_page(p, today) for p in payload.pages]

    return ExtractionResult(
        summary=payload.summary,
        skipped_reason=payload.skipped_reason,
        pages=pages,
        input_tokens=raw.input_tokens,
        output_tokens=raw.output_tokens,
    )


def _validate_payload(payload: dict[str, object]) -> ExtractionPayload:
    # The tool's input_schema marks `pages` as required; mirror that here so the
    # LLMClient retry path triggers when the model omits the field entirely.
    if "pages" not in payload:
        raise ValueError("payload missing required field: pages")
    return ExtractionPayload.model_validate(payload)


def _render_transcript(messages: list[TranscriptMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        lines.append(f"## {m.role}")
        lines.append("")
        lines.append(m.text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_page(p: ExtractedPage, today: date) -> WikiPage:
    slug = make_slug(p.slug_hint) if p.slug_hint else make_slug(p.title)
    folder = "entities" if p.type == "entity" else "concepts"
    rel = Path(f"wiki/{folder}/{slug}.md")

    fm = WikiPageFrontmatter(
        title=p.title,
        type=p.type,
        confidence=p.confidence,
        flavor=p.flavor,
        related=p.related,
        provenance=p.provenance,
        created=today,
        updated=today,
        agent_written=True,
    )
    return WikiPage(relative_path=rel, frontmatter=fm, body=p.body)
