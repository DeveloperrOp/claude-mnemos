from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from claude_mnemos.config import Config
from claude_mnemos.core.locks import pipeline_lock

if TYPE_CHECKING:
    from claude_mnemos.daemon.our_writes import OurWritesTracker
from claude_mnemos.core.models import WikiPage, WikiPageFrontmatter
from claude_mnemos.core.staging import StagingTransaction
from claude_mnemos.ingest.chunk_cache import ChunkCache
from claude_mnemos.ingest.extraction import ExtractionResult, extract_wiki_pages
from claude_mnemos.ingest.llm import LLMClient
from claude_mnemos.ingest.transcript import TranscriptMessage, parse_jsonl
from claude_mnemos.state.activity import (
    ACTIVITY_FILENAME,
    ActivityEntry,
    ActivityLog,
    ActivityOperationType,
)
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
    snapshot_path: Path | None = None
    activity_id: str | None = None


def ingest(
    jsonl_path: Path,
    vault_root: Path,
    *,
    cfg: Config,
    llm_client: LLMClient | None,
    extractor: Extractor | None = extract_wiki_pages,
    extract: bool = True,
    dry_run: bool = False,
    today: date,
    raw_filename_suffix: str = "",
    chunk_extract: bool = False,
    tracker: OurWritesTracker | None = None,
) -> IngestResult:
    """Full ingest pipeline. All vault writes go through StagingTransaction.

    On success: snapshot created, files atomically moved into vault, manifest updated.
    On failure mid-promote: vault restored from snapshot via StagingTransaction.
    On dry_run or exception in `with` block: staging moved to .trash/rejected-...
    """
    messages = parse_jsonl(jsonl_path)
    session_id = _resolve_session_id(messages, jsonl_path)
    raw_bytes = jsonl_path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()

    vault_root.mkdir(parents=True, exist_ok=True)

    with pipeline_lock(vault_root, timeout=cfg.lock_timeout):
        manifest = Manifest.load(vault_root)
        if sha in manifest.ingested:
            existing = manifest.ingested[sha]
            # If we already have real knowledge pages — or the caller didn't
            # ask for extract this run — the previous result is final.
            # Otherwise this is the "first run was raw-only, user clicked
            # Extract knowledge" case: drop the manifest entry so the
            # extract path below runs from scratch. Without this the
            # session reports success and stays raw-only forever, which
            # was reported as "Извлечь знания → очередь сразу завершено,
            # ничего не появилось в мозге".
            already_extracted = any(
                not (p.startswith("raw/chats/") or p.startswith("raw\\chats\\"))
                for p in existing.created_pages
            )
            if already_extracted or not extract:
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
                    snapshot_path=None,
                    activity_id=None,
                )
            # Fall through: re-run extract on top of the existing raw dump.
            manifest.ingested.pop(sha, None)

        activity = ActivityLog.load(vault_root)

        # Build raw filename with optional suffix (e.g., "-precompact")
        raw_filename = f"{session_id}{raw_filename_suffix}.md"
        raw_relative = Path("raw/chats") / raw_filename
        raw_body = _render_raw_transcript(messages)

        with StagingTransaction(vault_root, operation_id=session_id) as txn:
            txn.write(raw_relative, raw_body)

            if not extract:
                # No-LLM path
                manifest.add(
                    sha,
                    IngestRecord(
                        session_id=session_id,
                        ingested_at=datetime.now(UTC),
                        raw_path=raw_relative.as_posix(),
                        source_path=None,
                        created_pages=[raw_relative.as_posix()],
                        skipped_collisions=[],
                        model=None,
                        input_tokens=None,
                        output_tokens=None,
                        transcript_path=str(jsonl_path.resolve()),
                        raw_transcript_bytes=len(raw_bytes),
                    ),
                )
                txn.write(Path(".manifest.json"), manifest.serialize_to_string())

                snapshot_target = txn.pre_promote_snapshot_path()
                activity_id = uuid4().hex
                activity.append(
                    _build_activity_entry(
                        op_type="ingest_raw_only",
                        snapshot_target=snapshot_target,
                        vault_root=vault_root,
                        affected=[raw_relative.as_posix()],
                        metadata={"session_id": session_id},
                        entry_id=activity_id,
                    )
                )
                txn.write(Path(ACTIVITY_FILENAME), activity.serialize_to_string())

                if dry_run:
                    txn.reject("dry-run (--no-llm)")
                    return IngestResult(
                        status="dry_run",
                        session_id=session_id,
                        raw_path=None,
                        snapshot_path=None,
                        activity_id=None,
                    )

                promote = txn.promote_to_vault(tracker=tracker)
                return IngestResult(
                    status="raw_only",
                    session_id=session_id,
                    raw_path=vault_root / raw_relative,
                    snapshot_path=promote.snapshot,
                    activity_id=activity_id,
                )

            # LLM-extract path
            if extractor is None:
                raise ValueError("extractor cannot be None when extract=True")
            if llm_client is None:
                raise ValueError("llm_client cannot be None when extract=True")

            # Chunk-extract owns a per-session payload cache so a rate-limit on
            # a later chunk doesn't re-pay for the earlier ones on retry. Built
            # only for the chunked path; cleared on success, kept on failure.
            chunk_cache = ChunkCache(vault_root, session_id) if chunk_extract else None

            extraction = extractor(
                messages=messages,
                cfg=cfg,
                llm_client=llm_client,
                today=today,
                chunk_extract=chunk_extract,
                chunk_cache=chunk_cache,
            )

            if not extraction.pages:
                # Zero-knowledge extraction (LLM skipped this session or found
                # nothing for this vault). Keep the raw transcript but write NO
                # wiki/sources page: an empty knowledge node whose
                # [[<id>|Open transcript]] backlink + sources:[raw/chats/<id>.md]
                # pointer become broken links once the raw is cleaned up. Record
                # as raw_only instead.
                manifest.add(
                    sha,
                    IngestRecord(
                        session_id=session_id,
                        ingested_at=datetime.now(UTC),
                        raw_path=raw_relative.as_posix(),
                        source_path=None,
                        created_pages=[raw_relative.as_posix()],
                        skipped_collisions=[],
                        model=cfg.model,
                        input_tokens=extraction.input_tokens,
                        output_tokens=extraction.output_tokens,
                        transcript_path=str(jsonl_path.resolve()),
                        raw_transcript_bytes=len(raw_bytes),
                    ),
                )
                txn.write(Path(".manifest.json"), manifest.serialize_to_string())
                snapshot_target = txn.pre_promote_snapshot_path()
                activity_id = uuid4().hex
                activity.append(
                    _build_activity_entry(
                        op_type="ingest_raw_only",
                        snapshot_target=snapshot_target,
                        vault_root=vault_root,
                        affected=[raw_relative.as_posix()],
                        metadata={
                            "session_id": session_id,
                            "skipped_reason": extraction.skipped_reason,
                            "model": cfg.model,
                            "input_tokens": extraction.input_tokens,
                            "output_tokens": extraction.output_tokens,
                        },
                        entry_id=activity_id,
                    )
                )
                txn.write(Path(ACTIVITY_FILENAME), activity.serialize_to_string())
                if dry_run:
                    txn.reject("dry-run (--extract, no knowledge)")
                    if chunk_cache is not None:
                        chunk_cache.clear()
                    return IngestResult(
                        status="dry_run",
                        session_id=session_id,
                        raw_path=None,
                        snapshot_path=None,
                        activity_id=None,
                    )
                promote = txn.promote_to_vault(tracker=tracker)
                if chunk_cache is not None:
                    chunk_cache.clear()
                return IngestResult(
                    status="raw_only",
                    session_id=session_id,
                    raw_path=vault_root / raw_relative,
                    input_tokens=extraction.input_tokens,
                    output_tokens=extraction.output_tokens,
                    model=cfg.model,
                    snapshot_path=promote.snapshot,
                    activity_id=activity_id,
                )

            source_relative = Path("wiki/sources") / f"{today.isoformat()}-{session_id}.md"
            source_page = _build_source_page(
                session_id=session_id,
                summary=extraction.summary,
                skipped_reason=extraction.skipped_reason,
                extracted_pages=extraction.pages,
                today=today,
                relative_path=source_relative,
            )

            # Source-page collision is HARD FAIL (per Plan #2 design)
            source_target_in_vault = vault_root / source_relative
            if source_target_in_vault.exists():
                raise FileExistsError(
                    f"source page collision at {source_relative.as_posix()}: "
                    "a file already exists. This typically means a stale file from a "
                    "previous manual edit. Move or delete it before re-running."
                )

            # Extracted pages: skip-with-warning on collision
            to_write: list[WikiPage] = []
            skipped: list[str] = []
            for p in extraction.pages:
                if (vault_root / p.relative_path).exists():
                    skipped.append(p.relative_path.as_posix())
                else:
                    to_write.append(p)
            to_write.append(source_page)

            for p in to_write:
                txn.write(p.relative_path, p.serialize())

            manifest.add(
                sha,
                IngestRecord(
                    session_id=session_id,
                    ingested_at=datetime.now(UTC),
                    raw_path=raw_relative.as_posix(),
                    source_path=source_relative.as_posix(),
                    created_pages=[p.relative_path.as_posix() for p in to_write],
                    skipped_collisions=skipped,
                    model=cfg.model,
                    input_tokens=extraction.input_tokens,
                    output_tokens=extraction.output_tokens,
                    transcript_path=str(jsonl_path.resolve()),
                    raw_transcript_bytes=len(raw_bytes),
                ),
            )
            txn.write(Path(".manifest.json"), manifest.serialize_to_string())

            snapshot_target = txn.pre_promote_snapshot_path()
            activity_id = uuid4().hex
            affected_paths = [p.relative_path.as_posix() for p in to_write]
            affected_paths.append(raw_relative.as_posix())
            activity.append(
                _build_activity_entry(
                    op_type="ingest_extracted",
                    snapshot_target=snapshot_target,
                    vault_root=vault_root,
                    affected=affected_paths,
                    metadata={
                        "session_id": session_id,
                        "model": cfg.model,
                        "input_tokens": extraction.input_tokens,
                        "output_tokens": extraction.output_tokens,
                        "skipped_collisions": skipped,
                    },
                    entry_id=activity_id,
                )
            )
            txn.write(Path(ACTIVITY_FILENAME), activity.serialize_to_string())

            if dry_run:
                txn.reject("dry-run (--extract)")
                # Extract succeeded — the chunk cache is no longer needed.
                # (Only ever cleared on a successful extract; a rate-limit
                # leaves it so the retry can resume.)
                if chunk_cache is not None:
                    chunk_cache.clear()
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
                    snapshot_path=None,
                    activity_id=None,
                )

            promote = txn.promote_to_vault(tracker=tracker)

            # Extract succeeded and was promoted — drop the chunk cache.
            if chunk_cache is not None:
                chunk_cache.clear()

            return IngestResult(
                status="extracted",
                session_id=session_id,
                raw_path=vault_root / raw_relative,
                source_path=vault_root / source_relative,
                created_pages=[vault_root / p.relative_path for p in to_write],
                skipped_collisions=skipped,
                input_tokens=extraction.input_tokens,
                output_tokens=extraction.output_tokens,
                model=cfg.model,
                snapshot_path=promote.snapshot,
                activity_id=activity_id,
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
    body_lines.extend(["## Original", "", f"[[{session_id}|Open transcript]]"])
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
    return f"[[{rel.stem}]]"


def _build_activity_entry(
    *,
    op_type: ActivityOperationType,
    snapshot_target: Path,
    vault_root: Path,
    affected: list[str],
    metadata: dict[str, object],
    entry_id: str,
) -> ActivityEntry:
    snapshot_relative = snapshot_target.relative_to(vault_root).as_posix()
    return ActivityEntry(
        id=entry_id,
        timestamp=datetime.now(UTC),
        operation_type=op_type,
        status="success",
        snapshot_path=snapshot_relative,
        can_undo=True,
        affected_pages=affected,
        metadata=metadata,
    )
