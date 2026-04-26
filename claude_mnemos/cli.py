from __future__ import annotations

import argparse
import sys
from pathlib import Path

from claude_mnemos.config import Config, UnknownLanguageHintError
from claude_mnemos.core.atomic import FileBusyError
from claude_mnemos.core.locks import LockTimeoutError
from claude_mnemos.ingest.llm import (
    LLMClient,
    LLMExtractionError,
    MissingApiKeyError,
    TranscriptTooLargeError,
)
from claude_mnemos.ingest.pipeline import ingest
from claude_mnemos.ingest.transcript import EmptyTranscriptError
from claude_mnemos.state.manifest import ManifestCorruptError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude_mnemos")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="Ingest a Claude Code JSONL session into a vault")
    p.add_argument("jsonl", type=Path, help="Path to the session JSONL file")
    p.add_argument("vault", type=Path, help="Path to the vault root")
    p.add_argument("--model", type=str, default=None, help="Model id or alias (sonnet/haiku/opus)")
    p.add_argument(
        "--language-hint",
        type=str,
        default=None,
        choices=["auto", "uk", "ru", "en"],
        help="Language hint for the extraction prompt",
    )
    p.add_argument(
        "--max-input-tokens",
        type=int,
        default=None,
        help="Hard upper bound on prompt tokens",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Run extraction but write nothing to the vault",
    )
    p.add_argument(
        "--no-llm",
        action="store_true",
        help="Write raw/chats only; skip LLM extraction (no API key required)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "ingest":
        parser.error(f"unknown command: {args.command}")
        return 2

    if not args.jsonl.exists():
        print(f"error: jsonl not found: {args.jsonl}", file=sys.stderr)
        return 2

    try:
        cfg = Config.from_env().with_overrides(
            model=args.model,
            language_hint=args.language_hint,
            max_input_tokens=args.max_input_tokens,
        )
    except UnknownLanguageHintError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    extract = not args.no_llm
    llm_client: LLMClient | None = None

    try:
        if extract:
            llm_client = LLMClient(cfg)

        result = ingest(
            args.jsonl,
            args.vault,
            cfg=cfg,
            llm_client=llm_client,
            extract=extract,
            dry_run=args.dry_run,
        )
    except EmptyTranscriptError as exc:
        print(f"error: empty transcript: {exc}", file=sys.stderr)
        return 65
    except MissingApiKeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 66
    except LLMExtractionError as exc:
        print(f"error: LLM extraction failed: {exc}", file=sys.stderr)
        return 70
    except TranscriptTooLargeError as exc:
        print(f"error: transcript too large: {exc}", file=sys.stderr)
        return 71
    except LockTimeoutError as exc:
        print(f"error: another ingest is running: {exc}", file=sys.stderr)
        return 73
    except ManifestCorruptError as exc:
        print(f"error: manifest corrupt: {exc}", file=sys.stderr)
        return 74
    except FileBusyError as exc:
        print(f"error: vault file busy after retries: {exc}", file=sys.stderr)
        return 75
    except FileExistsError as exc:
        print(f"error: source page collision: {exc}", file=sys.stderr)
        return 73  # EX_CANTCREAT — same family as LockTimeoutError

    if result.status == "already_ingested":
        print(f"already_ingested: session_id={result.session_id}")
        return 0
    if result.status == "dry_run":
        print(
            f"dry_run: would write {len(result.created_pages)} pages, "
            f"{len(result.skipped_collisions)} collisions"
        )
        return 0
    if result.status == "raw_only":
        print(f"raw_only: wrote {result.raw_path}")
        return 0
    print(
        f"extracted: session_id={result.session_id} "
        f"pages={len(result.created_pages)} skipped={len(result.skipped_collisions)} "
        f"tokens_in={result.input_tokens} tokens_out={result.output_tokens}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
