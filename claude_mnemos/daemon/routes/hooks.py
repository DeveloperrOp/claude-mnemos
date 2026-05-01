"""REST routes exposing the state of Claude Code's user hooks.

The dashboard calls ``GET /hooks/status`` to render a banner explaining
whether mnemos's SessionStart and SessionEnd hooks are wired into
``~/.claude/settings.json``. The detection heuristic is shared with the
``mnemos hooks status`` CLI subgroup.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from claude_mnemos import cli_hooks
from claude_mnemos.hooks import errors as hook_errors

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


@router.get("/hooks/errors")
async def hooks_errors(limit: int = 50) -> dict[str, Any]:
    """Return recent hook-script errors (newest first).

    ``limit`` cap defaults to 50, max 200 (the file is bounded at 200).
    """
    capped = max(1, min(limit, 200))
    entries = hook_errors.read_recent(capped)
    return {
        "log_path": str(hook_errors._log_path()),
        "count": len(entries),
        "entries": entries,
    }


@router.post("/hooks/install")
async def hooks_install() -> dict[str, Any]:
    """Install (or refresh) mnemos hooks in ~/.claude/settings.json.

    Idempotent — replaces any existing mnemos-tagged blocks; preserves foreign
    hooks. Returns the full install result plus the post-install /hooks/status
    payload so the dashboard can update without a second roundtrip.
    """
    try:
        result = cli_hooks.install()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"settings.json unwritable: {e}")

    settings = cli_hooks._load_settings()
    hooks_section = settings.get("hooks", {})
    ss = _summarize_event("SessionStart", hooks_section)
    se = _summarize_event("SessionEnd", hooks_section)
    return {
        "install_result": result,
        "status": {
            "settings_path": str(cli_hooks.CLAUDE_SETTINGS),
            "settings_exists": cli_hooks.CLAUDE_SETTINGS.exists(),
            "session_start": ss,
            "session_end": se,
            "all_installed": ss["installed"] and se["installed"],
        },
    }
