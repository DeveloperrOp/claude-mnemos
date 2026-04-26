from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from claude_mnemos.config import Config, UnknownLanguageHintError
from claude_mnemos.core.atomic import FileBusyError
from claude_mnemos.core.locks import LockTimeoutError
from claude_mnemos.core.staging import StagingPromoteError
from claude_mnemos.core.undo import UndoError, undo
from claude_mnemos.ingest.llm import (
    LLMClient,
    LLMExtractionError,
    MissingApiKeyError,
    TranscriptTooLargeError,
)
from claude_mnemos.ingest.pipeline import ingest
from claude_mnemos.ingest.transcript import EmptyTranscriptError
from claude_mnemos.state.activity import ActivityCorruptError, ActivityEntry, ActivityLog
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

    activity_p = sub.add_parser(
        "activity",
        help="Show recent activity entries from the vault's activity log",
    )
    activity_p.add_argument(
        "--vault",
        type=Path,
        default=Path.cwd(),
        help="Path to the vault root (default: current directory)",
    )
    activity_p.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Show last N entries (0 means show all)",
    )

    undo_p = sub.add_parser(
        "undo",
        help="Undo a previous operation by its activity entry id",
    )
    undo_p.add_argument(
        "op_id",
        nargs="?",
        default=None,
        help="Activity entry id (full or short prefix)",
    )
    undo_p.add_argument(
        "--last",
        action="store_true",
        help="Undo the most recent undoable operation",
    )
    undo_p.add_argument(
        "--vault",
        type=Path,
        default=Path.cwd(),
        help="Path to the vault root (default: current directory)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "activity":
        return _cmd_activity(args)
    if args.command == "undo":
        return _cmd_undo(args)

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
    except ValueError as exc:
        print(f"error: invalid env config: {exc}", file=sys.stderr)
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
            today=date.today(),
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
    except StagingPromoteError as exc:
        print(f"error: staging promote failed: {exc}", file=sys.stderr)
        return 76

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
        if result.snapshot_path is not None:
            print(f"snapshot: {result.snapshot_path}")
        return 0
    print(
        f"extracted: session_id={result.session_id} "
        f"pages={len(result.created_pages)} skipped={len(result.skipped_collisions)} "
        f"tokens_in={result.input_tokens} tokens_out={result.output_tokens}"
    )
    if result.snapshot_path is not None:
        print(f"snapshot: {result.snapshot_path}")
    return 0


def _cmd_activity(args: argparse.Namespace) -> int:
    try:
        log = ActivityLog.load(args.vault)
    except ActivityCorruptError as exc:
        print(f"error: activity log corrupt: {exc}", file=sys.stderr)
        return 74

    entries = list(reversed(log.entries))  # newest first
    if args.limit and args.limit > 0:
        entries = entries[: args.limit]

    if not entries:
        print("no activity entries")
        return 0

    for e in entries:
        ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        suffix = _activity_suffix(e)
        sid = ""
        if isinstance(e.metadata, dict):
            md_sid = e.metadata.get("session_id")
            if isinstance(md_sid, str):
                sid = md_sid
        sid_part = f"  ({sid})" if sid else ""
        print(f"{ts}  {e.operation_type}{sid_part}  {suffix}")
    return 0


def _activity_suffix(e: ActivityEntry) -> str:
    if e.operation_type == "manual_restore":
        return "[chain]"
    if e.undone:
        ts = e.undone_at.strftime("%H:%M:%S") if e.undone_at else "?"
        return f"[UNDONE {ts}]"
    if not e.can_undo:
        return ""
    if e.snapshot_path is None:
        return "[snapshot missing]"
    return f"[undo: {e.id[:8]}]"


def _cmd_undo(args: argparse.Namespace) -> int:
    if args.last and args.op_id is not None:
        print("error: --last cannot be combined with positional op_id", file=sys.stderr)
        return 2
    if not args.last and args.op_id is None:
        print("error: provide op_id or --last", file=sys.stderr)
        return 2

    try:
        log = ActivityLog.load(args.vault)
    except ActivityCorruptError as exc:
        print(f"error: activity log corrupt: {exc}", file=sys.stderr)
        return 74

    if args.last:
        candidate = log.last_undoable()
        if candidate is None:
            print("error: no undoable operation in activity log", file=sys.stderr)
            return 77
        op_id = candidate.id
    else:
        matches = [e for e in log.entries if e.id.startswith(args.op_id)]
        if not matches:
            print(f"error: activity entry not found: {args.op_id}", file=sys.stderr)
            return 77
        if len(matches) > 1:
            ids = ", ".join(m.id[:12] for m in matches)
            print(
                f"error: ambiguous prefix '{args.op_id}' matches {len(matches)} entries: {ids}",
                file=sys.stderr,
            )
            return 77
        op_id = matches[0].id

    try:
        result = undo(args.vault, op_id)
    except UndoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 77
    except LockTimeoutError as exc:
        print(f"error: another ingest is running: {exc}", file=sys.stderr)
        return 73

    print(f"undone: {op_id} restored {len(result.restored_pages)} pages")
    if result.new_entry_id is not None:
        print(f"new activity entry: {result.new_entry_id} (manual_restore)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
