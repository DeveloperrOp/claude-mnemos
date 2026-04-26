from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import httpx

from claude_mnemos.config import Config, UnknownLanguageHintError
from claude_mnemos.core.atomic import FileBusyError
from claude_mnemos.core.locks import LockTimeoutError
from claude_mnemos.core.staging import StagingPromoteError
from claude_mnemos.core.undo import UndoError, undo
from claude_mnemos.daemon.config import DaemonConfig, default_pid_file
from claude_mnemos.daemon.lockfile import cleanup_pid_file, is_daemon_running
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.daemon.runtime_state import DaemonRuntimeState
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

    daemon_p = sub.add_parser("daemon", help="Manage the mnemos daemon")
    daemon_sub = daemon_p.add_subparsers(dest="daemon_cmd", required=True)

    for cmd in ("start", "foreground"):
        sp = daemon_sub.add_parser(cmd)
        sp.add_argument("--vault", type=Path, default=Path.cwd())
        sp.add_argument("--host", default=None)
        sp.add_argument("--port", type=int, default=None)
        sp.add_argument("--retention-days", type=int, default=None)
        sp.add_argument(
            "--log-level",
            default=None,
            choices=["debug", "info", "warning", "error"],
        )

    stop_p = daemon_sub.add_parser("stop")
    stop_p.add_argument("--timeout", type=float, default=10.0)

    daemon_sub.add_parser("status")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "activity":
        return _cmd_activity(args)
    if args.command == "undo":
        return _cmd_undo(args)
    if args.command == "daemon":
        return _cmd_daemon(args)

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


def _resolve_daemon_config(args: argparse.Namespace) -> DaemonConfig:
    base = DaemonConfig.from_env(args.vault)
    overrides: dict[str, object] = {}
    if args.host is not None:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    if args.retention_days is not None:
        overrides["retention_days"] = args.retention_days
    if args.log_level is not None:
        overrides["log_level"] = args.log_level
    if overrides:
        return base.model_copy(update=overrides)
    return base


def _cmd_daemon(args: argparse.Namespace) -> int:
    if args.daemon_cmd == "start":
        return _cmd_daemon_start(args)
    if args.daemon_cmd == "foreground":
        return _cmd_daemon_foreground(args)
    if args.daemon_cmd == "stop":
        return _cmd_daemon_stop(args)
    if args.daemon_cmd == "status":
        return _cmd_daemon_status(args)
    print(f"unknown daemon subcommand: {args.daemon_cmd}", file=sys.stderr)
    return 2


def _cmd_daemon_start(args: argparse.Namespace) -> int:
    config = _resolve_daemon_config(args)
    pid = is_daemon_running(config.pid_file)
    if pid is not None:
        print(
            f"daemon already running on :{config.port}, pid={pid}",
            file=sys.stderr,
        )
        return 78

    cmd = [
        sys.executable,
        "-m",
        "claude_mnemos.daemon",
        "run",
        "--vault",
        str(config.vault_root),
        "--host",
        config.host,
        "--port",
        str(config.port),
        "--retention-days",
        str(config.retention_days),
        "--log-level",
        config.log_level,
        "--pid-file",
        str(config.pid_file),
    ]
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    DaemonRuntimeState(
        vault_root=config.vault_root,
        host=config.host,
        port=config.port,
        pid_file=config.pid_file,
    ).save()

    deadline = time.monotonic() + 5.0
    health_url = f"http://{config.host}:{config.port}/health"
    while time.monotonic() < deadline:
        try:
            r = httpx.get(health_url, timeout=0.5)
            if r.status_code == 200:
                print(
                    f"daemon started: pid={proc.pid}, vault={config.vault_root}, "
                    f"http://{config.host}:{config.port}"
                )
                return 0
        except httpx.HTTPError:
            pass
        time.sleep(0.2)

    print("daemon failed to start within 5s", file=sys.stderr)
    return 79


def _cmd_daemon_foreground(args: argparse.Namespace) -> int:
    config = _resolve_daemon_config(args)
    pid = is_daemon_running(config.pid_file)
    if pid is not None:
        print(
            f"daemon already running on :{config.port}, pid={pid}",
            file=sys.stderr,
        )
        return 78
    DaemonRuntimeState(
        vault_root=config.vault_root,
        host=config.host,
        port=config.port,
        pid_file=config.pid_file,
    ).save()
    daemon = MnemosDaemon(config)
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        return 0
    finally:
        DaemonRuntimeState.cleanup()
    return 0


def _cmd_daemon_stop(args: argparse.Namespace) -> int:
    state = DaemonRuntimeState.load()
    pid_file = state.pid_file if state else default_pid_file()
    pid = is_daemon_running(pid_file)
    if pid is None:
        print("daemon not running")
        DaemonRuntimeState.cleanup()
        return 0
    try:
        import psutil

        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=args.timeout)
        except psutil.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5.0)
            except psutil.TimeoutExpired:
                print("daemon process did not die after SIGKILL", file=sys.stderr)
                return 80
    except psutil.NoSuchProcess:
        pass
    cleanup_pid_file(pid_file)
    DaemonRuntimeState.cleanup()
    print(f"daemon stopped: pid={pid}")
    return 0


def _cmd_daemon_status(_args: argparse.Namespace) -> int:
    state = DaemonRuntimeState.load()
    pid_file = state.pid_file if state else default_pid_file()
    pid = is_daemon_running(pid_file)
    if pid is None:
        print("stopped")
        return 1
    if state is None:
        print(json.dumps({"pid": pid, "status": "running"}, indent=2))
        return 0
    health_url = f"http://{state.host}:{state.port}/health"
    try:
        r = httpx.get(health_url, timeout=2.0)
        body = r.json()
        body["pid"] = pid
        print(json.dumps(body, indent=2))
        return 0
    except httpx.HTTPError as exc:
        print(
            f"daemon process alive (pid={pid}) but HTTP unreachable: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
