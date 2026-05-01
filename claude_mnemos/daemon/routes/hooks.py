"""REST routes exposing the state of Claude Code's user hooks.

The dashboard calls ``GET /hooks/status`` to render a banner explaining
whether mnemos's SessionStart and SessionEnd hooks are wired into
``~/.claude/settings.json``. The detection heuristic is shared with the
``mnemos hooks status`` CLI subgroup.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from claude_mnemos import cli_hooks

router = APIRouter()


def _summarize_event(event: str, hooks_section: dict) -> dict[str, Any]:
    blocks = hooks_section.get(event, [])
    cmds = [
        h.get("command", "")
        for block in blocks
        for h in block.get("hooks", [])
    ]
    mnemos_cmds = [c for c in cmds if cli_hooks._is_mnemos_command(c)]
    other_cmds = [c for c in cmds if not cli_hooks._is_mnemos_command(c)]
    return {
        "installed": bool(mnemos_cmds),
        "mnemos_commands": mnemos_cmds,
        "other_commands": other_cmds,
    }


@router.get("/hooks/status")
async def hooks_status() -> dict[str, Any]:
    """Return whether mnemos hooks are wired into Claude Code's settings.

    Response shape::

        {
          "settings_path": "C:\\\\Users\\\\u\\\\.claude\\\\settings.json",
          "settings_exists": true,
          "session_start": {"installed": true, "mnemos_commands": [...], "other_commands": [...]},
          "session_end":   {"installed": true, "mnemos_commands": [...], "other_commands": [...]},
          "all_installed": true
        }
    """
    settings = cli_hooks._load_settings()
    hooks_section = settings.get("hooks", {})
    ss = _summarize_event("SessionStart", hooks_section)
    se = _summarize_event("SessionEnd", hooks_section)
    return {
        "settings_path": str(cli_hooks.CLAUDE_SETTINGS),
        "settings_exists": cli_hooks.CLAUDE_SETTINGS.exists(),
        "session_start": ss,
        "session_end": se,
        "all_installed": ss["installed"] and se["installed"],
    }
