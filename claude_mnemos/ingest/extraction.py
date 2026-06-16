from __future__ import annotations

import logging
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
from claude_mnemos.core.ontology_similarity import body_hash
from claude_mnemos.core.slug import make_slug
from claude_mnemos.ingest.chunk_cache import ChunkCache, hash_chunk_text
from claude_mnemos.ingest.chunking import split_messages_for_budget
from claude_mnemos.ingest.llm import ExtractionRaw, LLMClient
from claude_mnemos.ingest.llm.tokens import count_tokens_local
from claude_mnemos.ingest.prompts import format_user, load_system
from claude_mnemos.ingest.transcript import TranscriptMessage

logger = logging.getLogger(__name__)

_FOLDER_BY_TYPE = {"entity": "entities", "concept": "concepts"}

# Fraction of ``max_input_tokens`` reserved for the rendered transcript when
# chunking. The remaining ~25% is headroom for the system prompt, user-prompt
# scaffolding and the tool schema. The same fraction decides whether a
# transcript fits in a single call (so a transcript classed as "fits" is exactly
# one that would not be chunked).
_BUDGET_FRACTION = 0.75


def _merge_payloads(payloads: list[ExtractionPayload]) -> ExtractionPayload:
    """Deterministically merge per-chunk extraction payloads into one.

    Pure (no I/O, no LLM). Pages are deduped by their slug
    (``make_slug(slug_hint or title)``). For a slug seen more than once:

    - if the two bodies are identical after normalization
      (``body_hash``) → keep the first occurrence's body, but raise its
      ``confidence`` to ``max(existing, page)`` (identical content found twice
      is more trustworthy);
    - otherwise (different bodies, same slug) → keep the higher-``confidence``
      page as the base and APPEND the lower-confidence page's body to it under a
      separator heading, so no knowledge is silently lost. The post-hoc ontology
      scan can later merge/clean the duplicated section. A warning is logged.

    Regardless of which page is kept, ``related`` links from all occurrences
    are unioned (order-preserving, deduped) onto the kept page.

    ``summary`` is the non-empty per-payload summaries joined by a blank line.
    ``skipped_reason`` is ``None`` when any page survives; otherwise the first
    payload's ``skipped_reason`` (or ``"no pages"`` when there are no payloads).
    """
    by_slug: dict[str, ExtractedPage] = {}
    for payload in payloads:
        for page in payload.pages:
            key = make_slug(page.slug_hint or page.title)
            existing = by_slug.get(key)
            if existing is None:
                by_slug[key] = page
                continue
            related = list(dict.fromkeys([*existing.related, *page.related]))
            if body_hash(existing.body) == body_hash(page.body):
                # Identical content found twice: keep the body, take the higher
                # confidence (Finding 2).
                update = {
                    "related": related,
                    "confidence": max(existing.confidence, page.confidence),
                }
                by_slug[key] = existing.model_copy(update=update)
                continue
            # Different bodies under the same slug: keep the higher-confidence
            # page as the base and append the dropped body so nothing is lost
            # (Finding 1).
            if page.confidence > existing.confidence:
                kept, dropped = page, existing
            else:
                kept, dropped = existing, page
            logger.warning(
                "merge: slug collision %r vs %r -> %s; appended lower-confidence body",
                existing.title,
                page.title,
                key,
            )
            merged_body = (
                kept.body + "\n\n---\n\n## (другой фрагмент)\n\n" + dropped.body
            )
            by_slug[key] = kept.model_copy(
                update={"related": related, "body": merged_body}
            )

    summaries = [p.summary for p in payloads if p.summary]
    has_pages = bool(by_slug)
    if has_pages:
        skipped_reason: str | None = None
    elif payloads:
        skipped_reason = payloads[0].skipped_reason
    else:
        skipped_reason = "no pages"

    return ExtractionPayload(
        summary="\n\n".join(summaries),
        skipped_reason=skipped_reason,
        pages=list(by_slug.values()),
    )


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
    chunk_extract: bool = False,
    chunk_cache: ChunkCache | None = None,
) -> ExtractionResult:
    """Run the LLM extraction over a parsed transcript and return wiki pages.

    `today` is injected for testability (deterministic created/updated).

    When ``chunk_extract`` is true and the rendered transcript would not fit a
    single request (``> max_input_tokens * _BUDGET_FRACTION``), the transcript is
    split on whole-message boundaries, each chunk is extracted independently with
    a "part N of M" note, and the per-chunk payloads are merged deterministically
    (see :func:`_merge_payloads`). Otherwise — including every small transcript —
    the single-call path runs unchanged: exactly one ``llm_client.extract`` call.
    """
    full = _render_transcript(messages)
    budget = int(cfg.max_input_tokens * _BUDGET_FRACTION)

    if chunk_extract and full and count_tokens_local(full) == 0:
        # tiktoken degraded to 0 (cold/offline BPE cache): the fits-check below
        # is always True so chunking silently never triggers even for a huge
        # transcript. Keep control flow unchanged — just surface the blind spot
        # (Finding 3).
        logger.warning(
            "merge/chunk: token estimate degraded to 0; chunking may not "
            "trigger for a large transcript"
        )

    if not chunk_extract or count_tokens_local(full) <= budget:
        raw = _extract_one(llm_client, user=_format_user(cfg, full))
        payload = ExtractionPayload.model_validate(raw.payload)
        pages = [_render_page(p, today) for p in payload.pages]
        return ExtractionResult(
            summary=payload.summary,
            skipped_reason=payload.skipped_reason,
            pages=pages,
            input_tokens=raw.input_tokens,
            output_tokens=raw.output_tokens,
        )

    chunks = split_messages_for_budget(messages, budget_tokens=budget)
    total = len(chunks)
    payloads: list[ExtractionPayload] = []
    sum_in = 0
    sum_out = 0
    for i, chunk in enumerate(chunks, start=1):
        rendered = _render_transcript(chunk)
        # Content-address the chunk so a retry after a rate-limit on a LATER
        # chunk can resume here instead of re-paying for this one.
        h = hash_chunk_text(rendered)
        if chunk_cache is not None:
            cached = chunk_cache.get(h)
            if cached is not None:
                # Served from cache: spent no new tokens this run.
                payloads.append(cached)
                continue
        note = f"(Это часть {i} из {total} большого транскрипта.)"
        raw = _extract_one(
            llm_client,
            user=_format_user(cfg, rendered, chunk_note=note),
        )
        payload = ExtractionPayload.model_validate(raw.payload)
        if chunk_cache is not None:
            # Persist right after a successful extract so a rate-limit on a
            # later chunk leaves this one cached for the retry.
            chunk_cache.put(h, payload)
        payloads.append(payload)
        sum_in += raw.input_tokens
        sum_out += raw.output_tokens

    merged = _merge_payloads(payloads)
    pages = [_render_page(p, today) for p in merged.pages]
    return ExtractionResult(
        summary=merged.summary,
        skipped_reason=merged.skipped_reason,
        pages=pages,
        input_tokens=sum_in,
        output_tokens=sum_out,
    )


def _format_user(cfg: Config, transcript: str, *, chunk_note: str = "") -> str:
    return format_user(
        transcript=transcript,
        language_hint=cfg.language_hint,
        chunk_note=chunk_note,
    )


def _extract_one(llm_client: LLMClient, *, user: str) -> ExtractionRaw:
    return llm_client.extract(
        system=load_system(),
        user=user,
        tool=save_wiki_pages_tool_schema(),
        validate=_validate_payload,
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
    folder = _FOLDER_BY_TYPE[p.type]
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
