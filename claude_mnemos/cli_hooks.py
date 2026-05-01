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


def _detect_hook_scripts() -> tuple[str, str]:
    """Locate session_start.py and session_end.py.

    They live one level above the claude_mnemos package directory in a
    source-tree install (../hooks/), or under the package itself in some
    pipx setups. Try a couple of candidates and return absolute, quoted paths.
    """
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "hooks",            # source tree: <repo>/hooks/
        here.parent / "hooks",                   # alt layout
    ]
    for d in candidates:
        ss = d / "session_start.py"
        se = d / "session_end.py"
        if ss.exists() and se.exists():
            return f'"{ss}"', f'"{se}"'
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


def _cmd_install(_args: argparse.Namespace) -> int:
    py = _detect_python()
    try:
        ss_script, se_script = _detect_hook_scripts()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    backup = _backup_settings()
    if backup:
        print(f"backup → {backup}")

    settings = _load_settings()
    settings.setdefault("hooks", {})
    hooks = settings["hooks"]

    ss_block = _build_hook_block(f"{py} {ss_script}")
    se_block = _build_hook_block(f"{py} {se_script}")

    # Strategy: replace any existing mnemos-flagged blocks; preserve foreign blocks.
    for event, new_block in (("SessionStart", ss_block), ("SessionEnd", se_block)):
        existing = hooks.get(event, [])
        # Drop any blocks whose any hook command contains mnemos-token.
        filtered = [
            block for block in existing
            if not any(_is_mnemos_command(h.get("command", "")) for h in block.get("hooks", []))
        ]
        filtered.append(new_block)
        hooks[event] = filtered

    _save_settings(settings)
    print("✓ mnemos hooks installed")
    print(f"  SessionStart: {py} {ss_script}")
    print(f"  SessionEnd:   {py} {se_script}")
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
    for event in ("SessionStart", "SessionEnd"):
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
    print(f"✓ removed {removed} mnemos hook block(s)")
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

    print(f"settings file: {CLAUDE_SETTINGS}")
    print()
    print(f"SessionStart: {'✓ mnemos installed' if ss_installed else '✗ no mnemos hook'}")
    for c in ss_cmds:
        marker = "  [mnemos]" if _is_mnemos_command(c) else "  [other]"
        print(f"{marker} {c}")
    print()
    print(f"SessionEnd:   {'✓ mnemos installed' if se_installed else '✗ no mnemos hook'}")
    for c in se_cmds:
        marker = "  [mnemos]" if _is_mnemos_command(c) else "  [other]"
        print(f"{marker} {c}")

    return 0 if (ss_installed and se_installed) else 1


def add_hooks_subparser(parent: argparse._SubParsersAction) -> None:
    """Register the `hooks` subgroup on the given parser."""
    p = parent.add_parser("hooks", help="Manage Claude Code hook registration")
    sub = p.add_subparsers(dest="hooks_cmd", required=True)

    install_p = sub.add_parser("install", help="Install or refresh mnemos hooks in ~/.claude/settings.json")
    install_p.set_defaults(func=_cmd_install)

    uninstall_p = sub.add_parser("uninstall", help="Remove mnemos hooks from ~/.claude/settings.json")
    uninstall_p.set_defaults(func=_cmd_uninstall)

    status_p = sub.add_parser("status", help="Show current SessionStart/SessionEnd hook configuration")
    status_p.set_defaults(func=_cmd_status)


def handle(args: argparse.Namespace) -> int:
    """Dispatch entry point, matching the cli_project / cli_settings convention."""
    return args.func(args)
