from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from claude_mnemos.config import Config
from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.models import WikiPage, WikiPageFrontmatter
from claude_mnemos.ingest.extraction import ExtractionResult, extract_wiki_pages
from claude_mnemos.ingest.llm import LLMClient
from claude_mnemos.ingest.transcript import TranscriptMessage, parse_jsonl
from claude_mnemos.state.manifest import IngestRecord, Manifest

IngestStatus = Literal["extracted", "raw_only", "already_ingested", "dry_run"]

Extractor = Callable[..., ExtractionResult]


@dataclass(frozen=True)
class IngestResult:
    status: IngestStatus
    session_id: str
    raw_path: Path | None
    source_path: Path | None = None
    created_pages: list[Path] = field(default_factory=list)
    skipped_collisions: list[str] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None


def ingest(
    jsonl_path: Path,
    vault_root: Path,
    *,
    cfg: Config,
    llm_client: LLMClient | None,
    extractor: Extractor | None = extract_wiki_pages,
    extract: bool = True,
    dry_run: bool = False,
    today: date | None = None,
) -> IngestResult:
    """Full ingest pipeline.

    - Parse JSONL (raises EmptyTranscriptError before any side effects).
    - Acquire pipeline lock.
    - Compute SHA-256, check manifest -> no-op if seen.
    - Write raw/chats/<sid>.md (plain).
    - If `extract` and not dry_run: call extractor (LLM), write wiki pages, source page.
    - Update and save manifest.

    Pass `extractor` to inject a stub in tests; default uses real extract_wiki_pages.
    Pass `llm_client=None` only when `extract=False` (no-llm path).
    """
    messages = parse_jsonl(jsonl_path)  # may raise EmptyTranscriptError
    session_id = _resolve_session_id(messages, jsonl_path)
    today_d = today or date.today()
    raw_bytes = jsonl_path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()

    vault_root.mkdir(parents=True, exist_ok=True)

    with pipeline_lock(vault_root, timeout=cfg.lock_timeout):
        manifest = Manifest.load(vault_root)
        if sha in manifest.ingested:
            existing = manifest.ingested[sha]
            return IngestResult(
                status="already_ingested",
                session_id=existing.session_id,
                raw_path=vault_root / existing.raw_path,
                source_path=(
                    vault_root / existing.source_path if existing.source_path else None
                ),
                created_pages=[vault_root / p for p in existing.created_pages],
                skipped_collisions=existing.skipped_collisions,
                model=existing.model,
                input_tokens=existing.input_tokens,
                output_tokens=existing.output_tokens,
            )

        raw_relative = Path("raw/chats") / f"{session_id}.md"
        raw_target = vault_root / raw_relative
        raw_body = _render_raw_transcript(messages)

        # No-LLM path: plain raw chat + manifest, done.
        if not extract:
            if not dry_run:
                atomic_write(raw_target, raw_body)
                manifest.add(
                    sha,
                    IngestRecord(
                        session_id=session_id,
                        ingested_at=datetime.now(),
                        raw_path=raw_relative.as_posix(),
                        source_path=None,
                        created_pages=[raw_relative.as_posix()],
                        skipped_collisions=[],
                        model=None,
                        input_tokens=None,
                        output_tokens=None,
                    ),
                )
                manifest.save(vault_root)
            return IngestResult(
                status="raw_only" if not dry_run else "dry_run",
                session_id=session_id,
                raw_path=raw_target if not dry_run else None,
            )

        # LLM extraction required from here on.
        if extractor is None:
            raise ValueError("extractor cannot be None when extract=True")
        if llm_client is None:
            raise ValueError("llm_client cannot be None when extract=True")

        extraction = extractor(
            messages=messages,
            cfg=cfg,
            llm_client=llm_client,
            today=today_d,
        )

        # Build the source page (we generate this, not the LLM)
        source_relative = Path("wiki/sources") / f"{today_d.isoformat()}-{session_id}.md"
        source_page = _build_source_page(
            session_id=session_id,
            summary=extraction.summary,
            skipped_reason=extraction.skipped_reason,
            extracted_pages=extraction.pages,
            today=today_d,
            relative_path=source_relative,
        )

        # Detect collisions on extracted pages (LLM-generated; skip-with-warning is correct)
        to_write: list[WikiPage] = []
        skipped: list[str] = []
        for p in extraction.pages:
            if (vault_root / p.relative_path).exists():
                skipped.append(p.relative_path.as_posix())
            else:
                to_write.append(p)

        # Source page collision is a hard fail (we generate it, it's unique per session, manifest
        # dedup should have caught a true repeat; collision means stale/manual file in the way).
        source_target = vault_root / source_relative
        if source_target.exists():
            raise FileExistsError(
                f"source page collision at {source_relative.as_posix()}: a file already exists. "
                "This typically means a stale file from a previous manual edit. "
                "Move or delete it before re-running."
            )
        to_write.append(source_page)

        if dry_run:
            return IngestResult(
                status="dry_run",
                session_id=session_id,
                raw_path=None,
                source_path=None,
                created_pages=[vault_root / p.relative_path for p in to_write],
                skipped_collisions=skipped,
                input_tokens=extraction.input_tokens,
                output_tokens=extraction.output_tokens,
                model=cfg.model,
            )

        # Real writes
        atomic_write(raw_target, raw_body)
        created_paths: list[Path] = []
        for p in to_write:
            target = vault_root / p.relative_path
            atomic_write(target, p.serialize())
            created_paths.append(target)

        manifest.add(
            sha,
            IngestRecord(
                session_id=session_id,
                ingested_at=datetime.now(),
                raw_path=raw_relative.as_posix(),
                source_path=source_relative.as_posix(),
                created_pages=[p.relative_path.as_posix() for p in to_write],
                skipped_collisions=skipped,
                model=cfg.model,
                input_tokens=extraction.input_tokens,
                output_tokens=extraction.output_tokens,
            ),
        )
        manifest.save(vault_root)

        return IngestResult(
            status="extracted",
            session_id=session_id,
            raw_path=raw_target,
            source_path=vault_root / source_relative,
            created_pages=created_paths,
            skipped_collisions=skipped,
            input_tokens=extraction.input_tokens,
            output_tokens=extraction.output_tokens,
            model=cfg.model,
        )


def _resolve_session_id(messages: list[TranscriptMessage], jsonl_path: Path) -> str:
    for m in messages:
        if m.session_id:
            return m.session_id
    return jsonl_path.stem


def _render_raw_transcript(messages: list[TranscriptMessage]) -> str:
    lines = ["# Transcript", ""]
    for m in messages:
        lines.append(f"## {m.role}")
        lines.append("")
        lines.append(m.text)
        lines.append("")
    return "\n".join(lines)


def _build_source_page(
    *,
    session_id: str,
    summary: str,
    skipped_reason: str | None,
    extracted_pages: list[WikiPage],
    today: date,
    relative_path: Path,
) -> WikiPage:
    title = f"Session {session_id} ({today.isoformat()})"
    related = [_to_wikilink(p.relative_path) for p in extracted_pages]
    body_lines = ["## Summary", "", summary, ""]
    if skipped_reason:
        body_lines.extend(["## Skipped", "", skipped_reason, ""])
    if extracted_pages:
        body_lines.append("## Extracted pages")
        body_lines.append("")
        for p in extracted_pages:
            body_lines.append(f"- {_to_wikilink(p.relative_path)}")
        body_lines.append("")
    body_lines.extend(["## Original", "", f"[[raw/chats/{session_id}|Open transcript]]"])
    body = "\n".join(body_lines)

    fm = WikiPageFrontmatter(
        title=title,
        type="source",
        sources=[f"raw/chats/{session_id}.md"],
        related=related,
        created=today,
        updated=today,
        agent_written=True,
    )
    return WikiPage(relative_path=relative_path, frontmatter=fm, body=body)


def _to_wikilink(rel: Path) -> str:
    return f"[[{rel.with_suffix('').as_posix()}]]"
