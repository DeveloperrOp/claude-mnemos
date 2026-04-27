from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from claude_mnemos.config import Config, UnknownLanguageHintError
from claude_mnemos.core.atomic import FileBusyError
from claude_mnemos.core.locks import LockTimeoutError
from claude_mnemos.core.ontology_apply import OntologyError, apply_suggestion
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
from claude_mnemos.state.ontology import (
    OntologyCorruptError,
    Suggestion,
    SuggestionFrontmatter,
    SuggestionStore,
    generate_suggestion_id,
)


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

    # ── ontology subgroup ─────────────────────────────────────────────────
    ontology_p = sub.add_parser(
        "ontology", help="Manage HITL ontology suggestions (merge/rename/delete)"
    )
    ontology_sub = ontology_p.add_subparsers(dest="ontology_cmd", required=True)

    list_p = ontology_sub.add_parser("list", help="List suggestions (default: pending)")
    list_p.add_argument("--vault", type=Path, default=Path.cwd())
    list_p.add_argument(
        "--all",
        action="store_true",
        help="Include archived (approved/rejected) suggestions",
    )

    for cmd in ("approve", "reject", "defer"):
        sp = ontology_sub.add_parser(cmd)
        sp.add_argument("suggestion_id", type=str)
        sp.add_argument("--vault", type=Path, default=Path.cwd())

    propose_p = ontology_sub.add_parser(
        "propose", help="Create a new suggestion manually"
    )
    propose_sub = propose_p.add_subparsers(dest="propose_op", required=True)

    merge_p = propose_sub.add_parser("merge")
    merge_p.add_argument(
        "--source", action="append", required=True,
        help="Vault-relative source page (specify at least 2 times)",
    )
    merge_p.add_argument("--target", required=True)
    merge_p.add_argument("--reason", default="")
    merge_p.add_argument("--confidence", type=float, default=0.7)
    merge_p.add_argument("--vault", type=Path, default=Path.cwd())

    rename_p = propose_sub.add_parser("rename")
    rename_p.add_argument("--source", required=True)
    rename_p.add_argument("--target", required=True)
    rename_p.add_argument("--reason", default="")
    rename_p.add_argument("--confidence", type=float, default=0.7)
    rename_p.add_argument("--vault", type=Path, default=Path.cwd())

    delete_p = propose_sub.add_parser("delete")
    delete_p.add_argument("--source", required=True)
    delete_p.add_argument("--reason", default="")
    delete_p.add_argument("--confidence", type=float, default=0.7)
    delete_p.add_argument("--vault", type=Path, default=Path.cwd())

    # ─── lint ─────────────────────────────────────────────────────────────
    lint_parser = sub.add_parser("lint", help="Health-check the wiki vault")
    lint_subs = lint_parser.add_subparsers(dest="lint_cmd", required=True)

    lint_run_p = lint_subs.add_parser("run", help="Run all lint rules")
    lint_run_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))

    lint_results_p = lint_subs.add_parser("results", help="Show last cached lint report")
    lint_results_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))
    lint_results_p.add_argument(
        "--severity",
        choices=["error", "warning", "info"],
        default=None,
        help="Filter findings by severity",
    )

    lint_autofix_p = lint_subs.add_parser("autofix", help="Apply safe autofixes")
    lint_autofix_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))
    lint_autofix_p.add_argument(
        "--dry-run", action="store_true", help="Print planned fixes without applying"
    )

    # ─── jobs ─────────────────────────────────────────────────────────────
    jobs_parser = sub.add_parser("jobs", help="Inspect or manage the daemon job queue")
    jobs_subs = jobs_parser.add_subparsers(dest="jobs_cmd", required=True)

    jobs_list_p = jobs_subs.add_parser("list", help="List jobs (filtered by status)")
    jobs_list_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))
    jobs_list_p.add_argument(
        "--status",
        choices=["queued", "running", "succeeded", "failed", "dead_letter"],
        default=None,
    )
    jobs_list_p.add_argument("--limit", type=int, default=50)

    jobs_show_p = jobs_subs.add_parser("show", help="Show one job by id")
    jobs_show_p.add_argument("job_id")
    jobs_show_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))

    jobs_cancel_p = jobs_subs.add_parser("cancel", help="Cancel a queued job")
    jobs_cancel_p.add_argument("job_id")
    jobs_cancel_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))

    jobs_retry_p = jobs_subs.add_parser(
        "retry-dead", help="Restore a dead-letter job to the queue"
    )
    jobs_retry_p.add_argument("job_id")
    jobs_retry_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))

    jobs_dismiss_p = jobs_subs.add_parser(
        "dismiss", help="Permanently delete a dead-letter job"
    )
    jobs_dismiss_p.add_argument("job_id")
    jobs_dismiss_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))

    # ─── page ─────────────────────────────────────────────────────────────
    page_parser = sub.add_parser(
        "page", help="Edit / verify / archive / soft-delete a wiki page"
    )
    page_subs = page_parser.add_subparsers(dest="page_cmd", required=True)

    page_edit_p = page_subs.add_parser(
        "edit", help="Patch frontmatter and/or body of a page (via daemon)"
    )
    page_edit_p.add_argument("page_ref")
    page_edit_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))
    page_edit_p.add_argument(
        "--frontmatter",
        default=None,
        help='JSON object of frontmatter fields to patch, e.g. \'{"status": "verified"}\'',
    )
    page_edit_p.add_argument(
        "--body-file",
        type=Path,
        default=None,
        help="Path to a file whose contents replace the page body",
    )

    for cmd in ("verify", "archive", "delete"):
        sp = page_subs.add_parser(cmd, help=f"{cmd.title()} a page (via daemon)")
        sp.add_argument("page_ref")
        sp.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))

    # ─── trash ────────────────────────────────────────────────────────────
    trash_parser = sub.add_parser(
        "trash", help="Manage the vault's .trash/ (list / restore / dismiss / empty)"
    )
    trash_subs = trash_parser.add_subparsers(dest="trash_cmd", required=True)

    trash_list_p = trash_subs.add_parser("list", help="List trash entries (direct DB read)")
    trash_list_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))

    for cmd in ("restore", "dismiss"):
        sp = trash_subs.add_parser(cmd, help=f"{cmd.title()} a trash entry (via daemon)")
        sp.add_argument("trash_id")
        sp.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))

    trash_empty_p = trash_subs.add_parser(
        "empty", help="Permanently delete all trash entries (via daemon)"
    )
    trash_empty_p.add_argument("--vault", default=os.environ.get("MNEMOS_VAULT_ROOT"))
    trash_empty_p.add_argument(
        "--yes",
        action="store_true",
        help="Skip the typed 'delete' confirmation prompt",
    )

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
    if args.command == "ontology":
        return _cmd_ontology(args)
    if args.command == "lint":
        return _cmd_lint(args)
    if args.command == "jobs":
        return _cmd_jobs(args)
    if args.command == "page":
        return _cmd_page(args)
    if args.command == "trash":
        return _cmd_trash(args)

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


def _cmd_ontology(args: argparse.Namespace) -> int:
    if args.ontology_cmd == "list":
        return _cmd_ontology_list(args)
    if args.ontology_cmd == "approve":
        return _cmd_ontology_approve(args)
    if args.ontology_cmd == "reject":
        return _cmd_ontology_reject(args)
    if args.ontology_cmd == "defer":
        return _cmd_ontology_defer(args)
    if args.ontology_cmd == "propose":
        return _cmd_ontology_propose(args)
    print(f"unknown ontology subcommand: {args.ontology_cmd}", file=sys.stderr)
    return 2


def _cmd_ontology_list(args: argparse.Namespace) -> int:
    try:
        store = SuggestionStore(args.vault)
        items = store.list(include_archive=args.all)
    except OntologyCorruptError as exc:
        print(f"error: ontology corrupt: {exc}", file=sys.stderr)
        return 74

    if not items:
        print("no suggestions")
        return 0

    for s in items:
        fm = s.frontmatter
        ts = fm.created.strftime("%Y-%m-%d %H:%M")
        target = fm.proposed_target or "—"
        print(
            f"{fm.id}  {ts}  {fm.operation}  status={fm.status}  "
            f"target={target}  conf={fm.confidence:.2f}"
        )
    return 0


def _cmd_ontology_approve(args: argparse.Namespace) -> int:
    try:
        result = apply_suggestion(args.vault, args.suggestion_id)
    except OntologyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 81
    except LockTimeoutError as exc:
        print(f"error: another operation is running: {exc}", file=sys.stderr)
        return 73
    except StagingPromoteError as exc:
        print(f"error: staging promote failed: {exc}", file=sys.stderr)
        return 76

    print(
        f"approved: {result.suggestion_id} via {result.operation}; "
        f"activity={result.activity_id} wikilinks_rewritten={result.wikilinks_rewritten}"
    )
    if result.target_path is not None:
        print(f"target: {result.target_path}")
    return 0


def _cmd_ontology_reject(args: argparse.Namespace) -> int:
    try:
        store = SuggestionStore(args.vault)
        existing = store.get(args.suggestion_id)
        if existing is None:
            print(f"error: suggestion not found: {args.suggestion_id}", file=sys.stderr)
            return 81
        if existing.frontmatter.status != "pending":
            print(
                f"error: suggestion already {existing.frontmatter.status}",
                file=sys.stderr,
            )
            return 81
        store.update_status(args.suggestion_id, "rejected")
        store.archive_suggestion(args.suggestion_id)
    except OntologyCorruptError as exc:
        print(f"error: ontology corrupt: {exc}", file=sys.stderr)
        return 74

    print(f"rejected: {args.suggestion_id}")
    return 0


def _cmd_ontology_defer(args: argparse.Namespace) -> int:
    try:
        store = SuggestionStore(args.vault)
        existing = store.get(args.suggestion_id)
        if existing is None:
            print(f"error: suggestion not found: {args.suggestion_id}", file=sys.stderr)
            return 81
        if existing.frontmatter.status != "pending":
            print(
                f"error: suggestion already {existing.frontmatter.status}",
                file=sys.stderr,
            )
            return 81
        store.update_status(args.suggestion_id, "deferred")
    except OntologyCorruptError as exc:
        print(f"error: ontology corrupt: {exc}", file=sys.stderr)
        return 74

    print(f"deferred: {args.suggestion_id}")
    return 0


def _cmd_ontology_propose(args: argparse.Namespace) -> int:
    op = args.propose_op
    if op == "merge":
        if len(args.source) < 2:
            print("error: merge requires at least 2 --source", file=sys.stderr)
            return 2
        affected = list(args.source)
        target = args.target
    elif op == "rename":
        affected = [args.source]
        target = args.target
    elif op == "delete":
        affected = [args.source]
        target = None
    else:
        print(f"unknown propose operation: {op}", file=sys.stderr)
        return 2

    operation_map = {
        "merge": "merge_entities",
        "rename": "rename_entity",
        "delete": "delete_page",
    }
    operation = operation_map[op]

    # Validate sources exist
    for src in affected:
        if not (args.vault / src).is_file():
            print(f"error: source page missing: {src}", file=sys.stderr)
            return 81
    if target is not None and (args.vault / target).exists():
        print(f"error: target already exists: {target}", file=sys.stderr)
        return 81

    now = datetime.now(UTC)
    sid = generate_suggestion_id(now)
    suggestion = Suggestion(
        frontmatter=SuggestionFrontmatter(
            id=sid,
            created=now,
            operation=operation,  # type: ignore[arg-type]
            affected_pages=affected,
            proposed_target=target,
            reason=args.reason,
            confidence=args.confidence,
        ),
        body=args.reason,
    )
    store = SuggestionStore(args.vault)
    try:
        store.create(suggestion)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 81
    print(f"created: {sid}  {operation}  affected={','.join(affected)}")
    if target is not None:
        print(f"target: {target}")
    return 0


# ─── lint ──────────────────────────────────────────────────────────────


def _cmd_lint(args: argparse.Namespace) -> int:
    if args.lint_cmd == "run":
        return _cmd_lint_run(args)
    if args.lint_cmd == "results":
        return _cmd_lint_results(args)
    if args.lint_cmd == "autofix":
        return _cmd_lint_autofix(args)
    print(f"unknown lint subcommand: {args.lint_cmd}", file=sys.stderr)
    return 82


def _cmd_lint_run(args: argparse.Namespace) -> int:
    from claude_mnemos.lint.exceptions import LintError
    from claude_mnemos.lint.runner import LintRunner
    from claude_mnemos.lint.state import save_report

    vault = _resolve_vault(args)
    if vault is None:
        return 1
    try:
        report = LintRunner(vault).run()
        save_report(vault, report)
    except LintError as exc:
        print(f"lint failed: {exc}", file=sys.stderr)
        return 82

    print(f"findings: {report.summary.total}")
    print(f"  by severity: {report.summary.by_severity}")
    print(f"  by rule: {report.summary.by_rule}")
    print(f"  fixable: {report.summary.fixable_count}")
    return 0


def _cmd_lint_results(args: argparse.Namespace) -> int:
    from claude_mnemos.lint.exceptions import LintCorruptError
    from claude_mnemos.lint.state import load_last_report

    vault = _resolve_vault(args)
    if vault is None:
        return 1
    try:
        report = load_last_report(vault)
    except LintCorruptError as exc:
        print(f"lint results corrupt: {exc}", file=sys.stderr)
        return 83

    if report is None:
        print("no lint run yet — run `mnemos lint run` first")
        return 0

    findings = report.findings
    if args.severity:
        findings = [f for f in findings if f.severity.value == args.severity]
    print(f"run_id: {report.run_id}  total: {len(findings)}")
    for f in findings:
        print(f"  [{f.severity.value}] {f.rule_id}  {f.page_path}  {f.message}")
    return 0


def _cmd_lint_autofix(args: argparse.Namespace) -> int:
    from claude_mnemos.lint.autofix import SAFE_FIX_KINDS, apply_autofix
    from claude_mnemos.lint.exceptions import LintError
    from claude_mnemos.lint.state import load_last_report

    vault = _resolve_vault(args)
    if vault is None:
        return 1
    report = load_last_report(vault)
    if report is None:
        print("no lint run yet — run `mnemos lint run` first", file=sys.stderr)
        return 82

    applicable = [
        f for f in report.findings
        if f.fixable and f.fix_kind is not None and f.fix_kind in SAFE_FIX_KINDS
    ]

    if args.dry_run:
        print(f"would fix {len(applicable)} findings:")
        for f in applicable:
            print(f"  {f.id}  {f.page_path}  {f.message}")
        return 0

    try:
        result = apply_autofix(vault, report)
    except LintError as exc:
        print(f"autofix failed: {exc}", file=sys.stderr)
        return 82

    print(
        f"fixed {len(result.fixed_findings)} findings; "
        f"skipped {len(result.skipped_findings)}; "
        f"snapshot: {result.snapshot_path}; "
        f"activity: {result.activity_id}"
    )
    return 0


def _resolve_vault(args: argparse.Namespace) -> Path | None:
    """Resolve --vault arg or MNEMOS_VAULT_ROOT env. Mirrors existing cli helpers."""
    raw = getattr(args, "vault", None)
    if not raw:
        print(
            "vault not provided (--vault or MNEMOS_VAULT_ROOT)", file=sys.stderr
        )
        return None
    return Path(raw)


# ─── jobs ──────────────────────────────────────────────────────────────


def _cmd_jobs(args: argparse.Namespace) -> int:
    if args.jobs_cmd == "list":
        return _cmd_jobs_list(args)
    if args.jobs_cmd == "show":
        return _cmd_jobs_show(args)
    if args.jobs_cmd == "cancel":
        return _cmd_jobs_cancel(args)
    if args.jobs_cmd == "retry-dead":
        return _cmd_jobs_retry_dead(args)
    if args.jobs_cmd == "dismiss":
        return _cmd_jobs_dismiss(args)
    print(f"unknown jobs subcommand: {args.jobs_cmd}", file=sys.stderr)
    return 86


def _cmd_jobs_list(args: argparse.Namespace) -> int:
    from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobsCorruptError, JobStore

    vault = _resolve_vault(args)
    if vault is None:
        return 1
    try:
        with JobStore(vault / JOBS_DB_FILENAME) as store:
            jobs = store.list_by_status(args.status, limit=args.limit)
            counts = store.count_by_status()
    except JobsCorruptError as exc:
        print(f"jobs DB corrupt: {exc}", file=sys.stderr)
        return 85

    print(f"{len(jobs)} jobs (counts: {counts})")
    for j in jobs:
        line = (
            f"  {j.id[:8]}  {j.status:<12}  attempt={j.attempt}  "
            f"{j.kind}  {j.created_at.isoformat(timespec='seconds')}"
        )
        if j.error:
            line += f"  err={j.error[:60]}"
        print(line)
    return 0


def _cmd_jobs_show(args: argparse.Namespace) -> int:
    from claude_mnemos.state.jobs import JOBS_DB_FILENAME, JobsCorruptError, JobStore

    vault = _resolve_vault(args)
    if vault is None:
        return 1
    try:
        with JobStore(vault / JOBS_DB_FILENAME) as store:
            job = store.get_by_id(args.job_id)
    except JobsCorruptError as exc:
        print(f"jobs DB corrupt: {exc}", file=sys.stderr)
        return 85
    if job is None:
        print(f"job not found: {args.job_id}", file=sys.stderr)
        return 86
    print(json.dumps(job.model_dump(mode="json"), indent=2, ensure_ascii=False))
    return 0


def _cmd_jobs_cancel(args: argparse.Namespace) -> int:
    return _post_or_delete_to_daemon(
        args, method="DELETE", path=f"/jobs/{args.job_id}"
    )


def _cmd_jobs_retry_dead(args: argparse.Namespace) -> int:
    return _post_or_delete_to_daemon(
        args, method="POST", path=f"/dead-letter/{args.job_id}/retry"
    )


def _cmd_jobs_dismiss(args: argparse.Namespace) -> int:
    return _post_or_delete_to_daemon(
        args, method="DELETE", path=f"/dead-letter/{args.job_id}"
    )


def _post_or_delete_to_daemon(
    args: argparse.Namespace, *, method: str, path: str
) -> int:
    daemon_url = os.environ.get("MNEMOS_DAEMON_URL", "http://127.0.0.1:5757")
    try:
        r = httpx.request(method, f"{daemon_url}{path}", timeout=5.0)
    except httpx.HTTPError as exc:
        print(f"daemon unreachable at {daemon_url}: {exc}", file=sys.stderr)
        return 84
    if r.status_code in (200, 201, 204):
        if r.status_code != 204:
            print(r.text)
        return 0
    if r.status_code == 404:
        print(f"job not found: {args.job_id}", file=sys.stderr)
        return 86
    if r.status_code == 409:
        print(f"invalid state: {r.text}", file=sys.stderr)
        return 86
    print(f"daemon HTTP {r.status_code}: {r.text}", file=sys.stderr)
    return 86


# ─── page / trash ──────────────────────────────────────────────────────────


# Exit codes per design §3.6
_EXIT_DAEMON_OFFLINE = 87
_EXIT_REF_NOT_FOUND = 88
_EXIT_COLLISION = 89
_EXIT_VALIDATION = 90


def _daemon_url() -> str:
    return os.environ.get("MNEMOS_DAEMON_URL", "http://127.0.0.1:5757")


def _http_request_to_daemon(
    method: str,
    path: str,
    *,
    json_body: Mapping[str, object] | None = None,
    timeout: float = 10.0,
) -> tuple[httpx.Response | None, int | None]:
    """Send a request to the daemon. Returns (response, None) on success
    or (None, exit_code) on transport failure."""
    url = f"{_daemon_url()}{path}"
    try:
        r = httpx.request(method, url, json=json_body, timeout=timeout)
    except httpx.HTTPError as exc:
        print(f"daemon unreachable at {_daemon_url()}: {exc}", file=sys.stderr)
        return None, _EXIT_DAEMON_OFFLINE
    return r, None


def _map_daemon_status_to_exit(status_code: int, body_text: str) -> int:
    if status_code in (200, 201, 204):
        return 0
    if status_code == 404:
        print(f"not found: {body_text}", file=sys.stderr)
        return _EXIT_REF_NOT_FOUND
    if status_code == 409:
        print(f"conflict: {body_text}", file=sys.stderr)
        return _EXIT_COLLISION
    if status_code == 422:
        print(f"validation error: {body_text}", file=sys.stderr)
        return _EXIT_VALIDATION
    print(f"daemon HTTP {status_code}: {body_text}", file=sys.stderr)
    return 1


def _cmd_page(args: argparse.Namespace) -> int:
    if args.page_cmd == "edit":
        return _cmd_page_edit(args)
    if args.page_cmd == "verify":
        return _cmd_page_verify(args)
    if args.page_cmd == "archive":
        return _cmd_page_archive(args)
    if args.page_cmd == "delete":
        return _cmd_page_delete(args)
    print(f"unknown page subcommand: {args.page_cmd}", file=sys.stderr)
    return 2


def _cmd_page_edit(args: argparse.Namespace) -> int:
    if _resolve_vault(args) is None:
        return 1

    fm_patch: dict[str, object] | None = None
    if args.frontmatter is not None:
        try:
            parsed = json.loads(args.frontmatter)
        except json.JSONDecodeError as exc:
            print(f"error: --frontmatter is not valid JSON: {exc}", file=sys.stderr)
            return _EXIT_VALIDATION
        if not isinstance(parsed, dict):
            print(
                "error: --frontmatter must be a JSON object", file=sys.stderr
            )
            return _EXIT_VALIDATION
        fm_patch = parsed

    body_text: str | None = None
    if args.body_file is not None:
        body_path = Path(args.body_file)
        if not body_path.is_file():
            print(f"error: --body-file not found: {body_path}", file=sys.stderr)
            return _EXIT_VALIDATION
        body_text = body_path.read_text(encoding="utf-8")

    payload = {"frontmatter": fm_patch, "body": body_text}
    response, err = _http_request_to_daemon(
        "PATCH", f"/pages/{args.page_ref}", json_body=payload
    )
    if response is None:
        return err or 1
    rc = _map_daemon_status_to_exit(response.status_code, response.text)
    if rc == 0:
        print(response.text)
    return rc


def _cmd_page_verify(args: argparse.Namespace) -> int:
    if _resolve_vault(args) is None:
        return 1
    response, err = _http_request_to_daemon(
        "POST", f"/pages/{args.page_ref}/verify"
    )
    if response is None:
        return err or 1
    rc = _map_daemon_status_to_exit(response.status_code, response.text)
    if rc == 0:
        print(response.text)
    return rc


def _cmd_page_archive(args: argparse.Namespace) -> int:
    if _resolve_vault(args) is None:
        return 1
    response, err = _http_request_to_daemon(
        "POST", f"/pages/{args.page_ref}/archive"
    )
    if response is None:
        return err or 1
    rc = _map_daemon_status_to_exit(response.status_code, response.text)
    if rc == 0:
        print(response.text)
    return rc


def _cmd_page_delete(args: argparse.Namespace) -> int:
    if _resolve_vault(args) is None:
        return 1
    response, err = _http_request_to_daemon(
        "DELETE", f"/pages/{args.page_ref}"
    )
    if response is None:
        return err or 1
    rc = _map_daemon_status_to_exit(response.status_code, response.text)
    if rc == 0:
        print(response.text)
    return rc


# ─── trash ────────────────────────────────────────────────────────────────


def _cmd_trash(args: argparse.Namespace) -> int:
    if args.trash_cmd == "list":
        return _cmd_trash_list(args)
    if args.trash_cmd == "restore":
        return _cmd_trash_restore(args)
    if args.trash_cmd == "dismiss":
        return _cmd_trash_dismiss(args)
    if args.trash_cmd == "empty":
        return _cmd_trash_empty(args)
    print(f"unknown trash subcommand: {args.trash_cmd}", file=sys.stderr)
    return 2


def _cmd_trash_list(args: argparse.Namespace) -> int:
    from claude_mnemos.core.trash import list_trash

    vault = _resolve_vault(args)
    if vault is None:
        return 1

    entries = list_trash(vault)
    if not entries:
        print("no trash entries")
        return 0

    print(f"{len(entries)} trash entries")
    for e in entries:
        ts = e.deleted_at.strftime("%Y-%m-%d %H:%M:%S")
        flag = "restorable" if e.restorable else "blocked"
        orig = e.original_path or "—"
        line = f"  {e.trash_id}  {ts}  {flag}  orig={orig}"
        if e.restore_blocked_reason:
            line += f"  ({e.restore_blocked_reason})"
        print(line)
    return 0


def _cmd_trash_restore(args: argparse.Namespace) -> int:
    if _resolve_vault(args) is None:
        return 1
    response, err = _http_request_to_daemon(
        "POST", f"/trash/{args.trash_id}/restore"
    )
    if response is None:
        return err or 1
    rc = _map_daemon_status_to_exit(response.status_code, response.text)
    if rc == 0:
        print(response.text)
    return rc


def _cmd_trash_dismiss(args: argparse.Namespace) -> int:
    if _resolve_vault(args) is None:
        return 1
    response, err = _http_request_to_daemon(
        "DELETE", f"/trash/{args.trash_id}"
    )
    if response is None:
        return err or 1
    rc = _map_daemon_status_to_exit(response.status_code, response.text)
    if rc == 0:
        print(f"dismissed: {args.trash_id}")
    return rc


def _cmd_trash_empty(args: argparse.Namespace) -> int:
    if _resolve_vault(args) is None:
        return 1

    if not args.yes:
        print("Type 'delete' to confirm: ", end="", flush=True)
        line = sys.stdin.readline().strip()
        if line != "delete":
            print("aborted: confirmation not received", file=sys.stderr)
            return 1

    response, err = _http_request_to_daemon("DELETE", "/trash")
    if response is None:
        return err or 1
    rc = _map_daemon_status_to_exit(response.status_code, response.text)
    if rc == 0:
        print(response.text)
    return rc


if __name__ == "__main__":
    sys.exit(main())
