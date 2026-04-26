from __future__ import annotations

import argparse
import sys
from pathlib import Path

from claude_mnemos.core.atomic import FileBusyError
from claude_mnemos.core.locks import LockTimeoutError
from claude_mnemos.ingest.pipeline import ingest_minimal
from claude_mnemos.ingest.transcript import EmptyTranscriptError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude_mnemos")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Ingest a Claude Code JSONL session into a vault")
    ingest.add_argument("jsonl", type=Path, help="Path to the session JSONL file")
    ingest.add_argument("vault", type=Path, help="Path to the vault root")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ingest":
        if not args.jsonl.exists():
            print(f"error: jsonl not found: {args.jsonl}", file=sys.stderr)
            return 2
        try:
            result = ingest_minimal(args.jsonl, args.vault)
        except EmptyTranscriptError as exc:
            print(f"error: empty transcript: {exc}", file=sys.stderr)
            return 65  # EX_DATAERR
        except LockTimeoutError as exc:
            print(f"error: another ingest is running: {exc}", file=sys.stderr)
            return 73  # EX_CANTCREAT (already running)
        except FileBusyError as exc:
            print(f"error: vault file busy after retries: {exc}", file=sys.stderr)
            return 75  # EX_TEMPFAIL
        print(f"wrote {result.page_path} ({result.message_count} messages)")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
