"""CLI subgroup ``mnemos project`` — project-map CRUD.

Read commands hit the file system directly. Write commands try the
daemon REST first (POST/PATCH/DELETE /projects/...) and fall back to
direct ProjectStore writes when the daemon is offline. Falling back
respects single-user dev convenience until #13b-β makes the daemon
truly multi-vault.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping

import httpx

from claude_mnemos.mapping.resolver import ProjectResolver, ResolverAmbiguityError
from claude_mnemos.state.projects import (
    ProjectMapEntry,
    ProjectNameConflictError,
    ProjectNotFoundError,
    ProjectStore,
)
from claude_mnemos.state.settings import SettingsStore

EXIT_PROJECT_MAP_ERROR = 94
EXIT_RESOLVER_AMBIGUITY = 96
EXIT_PROJECT_NOT_FOUND = 97
EXIT_DAEMON_UNREACHABLE = 84  # reused from jobs


def _daemon_url() -> str:
    return os.environ.get("MNEMOS_DAEMON_URL", "http://127.0.0.1:5757")


def handle(args: argparse.Namespace) -> int:
    cmd = args.project_command
    if cmd == "add":
        return _handle_add(args)
    if cmd == "list":
        return _handle_list(args)
    if cmd == "show":
        return _handle_show(args)
    if cmd == "update":
        return _handle_update(args)
    if cmd == "remove":
        return _handle_remove(args)
    if cmd == "resolve":
        return _handle_resolve(args)
    print(f"unknown project command: {cmd}", file=sys.stderr)
    return 2


def _handle_add(args: argparse.Namespace) -> int:
    body = {
        "name": args.name,
        "vault_root": str(args.vault),
        "cwd_patterns": args.cwd_pattern,
    }
    try:
        r = httpx.post(f"{_daemon_url()}/projects", json=body, timeout=2.0)
        if r.status_code == 201:
            print(f"added project {args.name!r}")
            return 0
        if r.status_code == 409:
            print(f"project {args.name!r} already exists", file=sys.stderr)
            return EXIT_PROJECT_MAP_ERROR
        if r.status_code == 422:
            print(f"validation error: {r.text}", file=sys.stderr)
            return EXIT_PROJECT_MAP_ERROR
        print(f"daemon error {r.status_code}: {r.text}", file=sys.stderr)
        return EXIT_PROJECT_MAP_ERROR
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        try:
            ProjectStore().add(ProjectMapEntry(
                name=args.name,
                vault_root=args.vault,
                cwd_patterns=args.cwd_pattern,
            ))
            print(f"added project {args.name!r} (offline)")
            return 0
        except ProjectNameConflictError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_PROJECT_MAP_ERROR
        except Exception as exc:  # noqa: BLE001
            print(f"add failed: {exc}", file=sys.stderr)
            return EXIT_PROJECT_MAP_ERROR


def _handle_list(args: argparse.Namespace) -> int:
    entries = ProjectStore().list_all()
    if getattr(args, "json", False):
        print(json.dumps([e.model_dump(mode="json") for e in entries], indent=2))
    else:
        if not entries:
            print("(no projects)")
        for e in entries:
            patterns = ",".join(e.cwd_patterns) or "-"
            print(f"{e.name}\t{e.vault_root}\t{patterns}")
    return 0


def _handle_show(args: argparse.Namespace) -> int:
    try:
        entry = ProjectStore().get(args.name)
    except ProjectNotFoundError:
        print(f"project {args.name!r} not found", file=sys.stderr)
        return EXIT_PROJECT_NOT_FOUND
    settings = SettingsStore().get_project(args.name)
    view = {
        "name": entry.name,
        "vault_root": str(entry.vault_root),
        "cwd_patterns": entry.cwd_patterns,
        "settings": settings.model_dump(mode="json"),
    }
    if getattr(args, "json", False):
        print(json.dumps(view, indent=2))
    else:
        print(_pretty(view))
    return 0


def _pretty(view: Mapping[str, object]) -> str:
    cwd_patterns = view["cwd_patterns"]
    assert isinstance(cwd_patterns, list)
    out = [
        f"name:        {view['name']}",
        f"vault_root:  {view['vault_root']}",
        f"cwd_patterns: {', '.join(cwd_patterns) or '-'}",
        "settings:",
        json.dumps(view["settings"], indent=2),
    ]
    return "\n".join(out)


def _handle_update(args: argparse.Namespace) -> int:
    try:
        entry = ProjectStore().get(args.name)
    except ProjectNotFoundError:
        print(f"project {args.name!r} not found", file=sys.stderr)
        return EXIT_PROJECT_NOT_FOUND
    new_patterns = list(entry.cwd_patterns)
    for p in args.add_cwd_pattern:
        if p not in new_patterns:
            new_patterns.append(p)
    new_patterns = [p for p in new_patterns if p not in args.remove_cwd_pattern]
    body: dict[str, object] = {"cwd_patterns": new_patterns}
    if args.vault is not None:
        body["vault_root"] = str(args.vault)
    try:
        r = httpx.patch(f"{_daemon_url()}/projects/{args.name}", json=body, timeout=2.0)
        if r.status_code == 200:
            print(f"updated project {args.name!r}")
            return 0
        print(f"daemon error {r.status_code}: {r.text}", file=sys.stderr)
        return EXIT_PROJECT_MAP_ERROR
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        try:
            ProjectStore().update(
                args.name,
                vault_root=args.vault,
                cwd_patterns=new_patterns,
            )
            print(f"updated project {args.name!r} (offline)")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"update failed: {exc}", file=sys.stderr)
            return EXIT_PROJECT_MAP_ERROR


def _handle_remove(args: argparse.Namespace) -> int:
    if not args.yes:
        print(f"Remove project {args.name!r}? [y/N] ", end="", flush=True)
        ans = sys.stdin.readline().strip().lower()
        if ans not in ("y", "yes"):
            print("aborted")
            return 0
    try:
        r = httpx.delete(f"{_daemon_url()}/projects/{args.name}", timeout=2.0)
        if r.status_code in (200, 204):
            print(f"removed project {args.name!r}")
            return 0
        if r.status_code == 404:
            print(f"project {args.name!r} not found", file=sys.stderr)
            return EXIT_PROJECT_NOT_FOUND
        print(f"daemon error {r.status_code}: {r.text}", file=sys.stderr)
        return EXIT_PROJECT_MAP_ERROR
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        try:
            ProjectStore().remove(args.name)
            print(f"removed project {args.name!r} (offline)")
            return 0
        except ProjectNotFoundError:
            print(f"project {args.name!r} not found", file=sys.stderr)
            return EXIT_PROJECT_NOT_FOUND


def _handle_resolve(args: argparse.Namespace) -> int:
    try:
        entry = ProjectResolver().resolve_by_cwd(args.cwd)
    except ResolverAmbiguityError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_RESOLVER_AMBIGUITY
    if entry is None:
        print(f"no project matches cwd {args.cwd}", file=sys.stderr)
        return EXIT_PROJECT_NOT_FOUND
    if getattr(args, "json", False):
        print(json.dumps(entry.model_dump(mode="json"), indent=2))
    else:
        print(f"{entry.name}\t{entry.vault_root}")
    return 0
