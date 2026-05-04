"""CLI subgroup for managing Claude Code hook registration.

`mnemos hooks install`   — register or replace mnemos's SessionStart/SessionEnd hooks
                           in ~/.claude/settings.json (idempotent).
`mnemos hooks uninstall` — remove mnemos's SessionStart/SessionEnd hooks
                           (leaves other event types untouched).
`mnemos hooks status`    — print current SessionStart/SessionEnd configuration
                           and whether it points at mnemos.

Identification heuristic: a hook is "mnemos's" if its command line contains
the literal substring "claude_mnemos" or "claude-mnemos" — this matches both
pipx-venv installs (`...\\pipx\\venvs\\claude-mnemos\\...`) and source-tree
installs (`...\\code\\claude-mnemos\\hooks\\session_start.py`).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from claude_mnemos import runtime

CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
MNEMOS_TOKEN = "claude_mnemos"  # part of import path; matches in pipx-venv command line
MNEMOS_DASHED = "claude-mnemos"  # part of source-tree path


def _detect_python() -> str:
    """Resolve the Python executable that should run mnemos hooks.

    Use sys.executable (the interpreter that imported claude_mnemos right
    now). Quote the path on Windows so spaces survive Claude Code's
    command-line splitting.
    """
    return f'"{sys.executable}"'


def _detect_hook_scripts() -> tuple[str, str, str]:
    """Locate hook command lines for the three events.

    Returns three command strings ready to drop into settings.json.

    In frozen mode the hook target is the bundled exe invoked as
    ``"<exe>" hook <event>``. In source mode it's
    ``"<python>" "<script.py>"`` for each of session_start.py / session_end.py
    / pre_compact.py.
    """
    if runtime.is_frozen():
        exe = runtime.executable_path()
        ss = f'"{exe}" hook session-start'
        se = f'"{exe}" hook session-end'
        pc = f'"{exe}" hook pre-compact'
        return ss, se, pc

    py = _detect_python()
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "hooks",
        here.parent / "hooks",
    ]
    for d in candidates:
        ss = d / "session_start.py"
        se = d / "session_end.py"
        pc = d / "pre_compact.py"
        if ss.exists() and se.exists() and pc.exists():
            return f'{py} "{ss}"', f'{py} "{se}"', f'{py} "{pc}"'
    raise FileNotFoundError(
        f"Could not locate mnemos hook scripts. Tried: {[str(c) for c in candidates]}"
    )


def _load_settings() -> dict:
    if not CLAUDE_SETTINGS.exists():
        return {}
    try:
        return json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"Refusing to touch {CLAUDE_SETTINGS}: invalid JSON ({e}).\n"
            "Repair the file manually first."
        )


def _save_settings(data: dict) -> None:
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_SETTINGS.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _is_mnemos_command(cmd: str) -> bool:
    return MNEMOS_TOKEN in cmd or MNEMOS_DASHED in cmd


def _build_hook_block(command: str) -> dict:
    return {
        "hooks": [
            {"type": "command", "command": command, "timeout": 15}
        ]
    }


def _backup_settings() -> Path | None:
    if not CLAUDE_SETTINGS.exists():
        return None
    backup = CLAUDE_SETTINGS.with_suffix(".json.backup-mnemos-hooks-install")
    shutil.copy2(CLAUDE_SETTINGS, backup)
    return backup


def install(*, dry_run: bool = False) -> dict:
    """Install (or refresh) mnemos hooks in ~/.claude/settings.json.

    Returns a result dict::

        {
          "ok": True,
          "session_start_script": "<full command>",
          "session_end_script": "<full command>",
          "pre_compact_script": "<full command>",
          "backup_path": "<path or None>",
        }

    On error raises FileNotFoundError (hook scripts missing) or OSError
    (settings file unwritable). Caller catches.
    """
    ss_cmd, se_cmd, pc_cmd = _detect_hook_scripts()  # full command lines

    if dry_run:
        return {
            "ok": True,
            "session_start_script": ss_cmd,
            "session_end_script": se_cmd,
            "pre_compact_script": pc_cmd,
            "backup_path": None,
            "dry_run": True,
        }

    backup = _backup_settings()
    settings = _load_settings()
    settings.setdefault("hooks", {})
    hooks = settings["hooks"]

    ss_block = _build_hook_block(ss_cmd)
    se_block = _build_hook_block(se_cmd)
    pc_block = _build_hook_block(pc_cmd)

    # Strategy: replace any existing mnemos-flagged blocks; preserve foreign blocks.
    for event, new_block in (
        ("SessionStart", ss_block),
        ("SessionEnd", se_block),
        ("PreCompact", pc_block),
    ):
        existing = hooks.get(event, [])
        filtered = [
            block for block in existing
            if not any(_is_mnemos_command(h.get("command", "")) for h in block.get("hooks", []))
        ]
        filtered.append(new_block)
        hooks[event] = filtered

    _save_settings(settings)
    return {
        "ok": True,
        "session_start_script": ss_cmd,
        "session_end_script": se_cmd,
        "pre_compact_script": pc_cmd,
        "backup_path": str(backup) if backup else None,
    }


def _cmd_install(_args: argparse.Namespace) -> int:
    """CLI wrapper — calls install() and prints user-facing summary."""
    try:
        result = install()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    if result.get("backup_path"):
        print(f"backup → {result['backup_path']}")
    print("[OK] mnemos hooks installed")
    print(f"  SessionStart: {result['session_start_script']}")
    print(f"  SessionEnd:   {result['session_end_script']}")
    print(f"  PreCompact:   {result['pre_compact_script']}")
    print()
    print("Existing non-mnemos hooks for these events were preserved.")
    return 0


def _cmd_uninstall(_args: argparse.Namespace) -> int:
    if not CLAUDE_SETTINGS.exists():
        print(f"{CLAUDE_SETTINGS} does not exist; nothing to uninstall.")
        return 0

    settings = _load_settings()
    hooks = settings.get("hooks", {})
    removed = 0
    for event in ("SessionStart", "SessionEnd", "PreCompact"):
        existing = hooks.get(event, [])
        before = len(existing)
        filtered = [
            block for block in existing
            if not any(_is_mnemos_command(h.get("command", "")) for h in block.get("hooks", []))
        ]
        if not filtered:
            hooks.pop(event, None)
        else:
            hooks[event] = filtered
        removed += before - len(filtered)

    if removed == 0:
        print("No mnemos hooks found in settings; nothing to remove.")
        return 0

    backup = _backup_settings()
    if backup:
        print(f"backup → {backup}")
    _save_settings(settings)
    print(f"[OK] removed {removed} mnemos hook block(s)")
    return 0


def _cmd_status(_args: argparse.Namespace) -> int:
    if not CLAUDE_SETTINGS.exists():
        print(f"{CLAUDE_SETTINGS} does not exist.")
        print("status: not installed")
        return 1

    settings = _load_settings()
    hooks = settings.get("hooks", {})

    def _summarize(event: str) -> tuple[bool, list[str]]:
        blocks = hooks.get(event, [])
        cmds = [h.get("command", "") for block in blocks for h in block.get("hooks", [])]
        mnemos_cmds = [c for c in cmds if _is_mnemos_command(c)]
        return (bool(mnemos_cmds), cmds)

    ss_installed, ss_cmds = _summarize("SessionStart")
    se_installed, se_cmds = _summarize("SessionEnd")
    pc_installed, pc_cmds = _summarize("PreCompact")

    print(f"settings file: {CLAUDE_SETTINGS}")
    print()
    print(f"SessionStart: {'[OK] mnemos installed' if ss_installed else '[X]  no mnemos hook'}")
    for c in ss_cmds:
        marker = "  [mnemos]" if _is_mnemos_command(c) else "  [other]"
        print(f"{marker} {c}")
    print()
    print(f"SessionEnd:   {'[OK] mnemos installed' if se_installed else '[X]  no mnemos hook'}")
    for c in se_cmds:
        marker = "  [mnemos]" if _is_mnemos_command(c) else "  [other]"
        print(f"{marker} {c}")
    print()
    print(f"PreCompact:   {'[OK] mnemos installed' if pc_installed else '[X]  no mnemos hook'}")
    for c in pc_cmds:
        marker = "  [mnemos]" if _is_mnemos_command(c) else "  [other]"
        print(f"{marker} {c}")

    return 0 if (ss_installed and se_installed and pc_installed) else 1


def add_hooks_subparser(parent: argparse._SubParsersAction) -> None:
    """Register the `hooks` subgroup on the given parser."""
    p = parent.add_parser("hooks", help="Manage Claude Code hook registration")
    sub = p.add_subparsers(dest="hooks_cmd", required=True)

    install_p = sub.add_parser("install", help="Install or refresh mnemos hooks in ~/.claude/settings.json")
    install_p.set_defaults(func=_cmd_install)

    uninstall_p = sub.add_parser("uninstall", help="Remove mnemos hooks from ~/.claude/settings.json")
    uninstall_p.set_defaults(func=_cmd_uninstall)

    status_p = sub.add_parser("status", help="Show current SessionStart/SessionEnd/PreCompact hook configuration")
    status_p.set_defaults(func=_cmd_status)


def handle(args: argparse.Namespace) -> int:
    """Dispatch entry point, matching the cli_project / cli_settings convention."""
    return args.func(args)
