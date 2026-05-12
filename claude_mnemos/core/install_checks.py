"""Install-level health detectors complementing core/health_checks.py.

These run on demand from `mnemos doctor` and from the Diagnostics
UI page. Same StoredAlert shape as the cron-based detectors so the
UI can render them uniformly.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

from claude_mnemos.core.clock import utcnow
from claude_mnemos.state.alerts_store import StoredAlert

CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
_REQUIRED_HOOK_EVENTS = ("SessionStart", "SessionEnd", "PreCompact")
_MNEMOS_TOKEN = "claude_mnemos"
_MNEMOS_DASHED = "claude-mnemos"


def _which(name: str) -> str | None:
    return shutil.which(name)


def check_claude_cli_installed() -> StoredAlert | None:
    """Critical alert if `claude` is not on PATH."""
    if _which("claude") is not None:
        return None
    now = utcnow()
    return StoredAlert(
        id="claude_cli_not_installed",
        detector="check_claude_cli_installed",
        severity="critical",
        message=(
            "Claude Code CLI is not installed. Install it from "
            "https://docs.anthropic.com/en/docs/claude-code/quickstart "
            "before using mnemos."
        ),
        i18n_key="diagnostics.alert.claude_cli_not_installed",
        context={},
        first_seen=now,
        last_seen=now,
        silenced_until=None,
        dismissed=False,
    )


def _hook_events_installed() -> set[str]:
    if not CLAUDE_SETTINGS.exists():
        return set()
    try:
        data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    hooks = data.get("hooks", {})
    out: set[str] = set()
    for event in _REQUIRED_HOOK_EVENTS:
        blocks = hooks.get(event, [])
        for block in blocks:
            for h in block.get("hooks", []):
                cmd = h.get("command", "")
                if _MNEMOS_TOKEN in cmd or _MNEMOS_DASHED in cmd:
                    out.add(event)
                    break
    return out


def check_hooks_present() -> StoredAlert | None:
    """Critical if no mnemos hooks; warning if partial; None if all 3 present."""
    installed = _hook_events_installed()
    now = utcnow()
    if not installed:
        return StoredAlert(
            id="hooks_not_installed",
            detector="check_hooks_present",
            severity="critical",
            message=(
                "Claude Code hooks are not installed. Run `mnemos hooks "
                "install` so mnemos can capture sessions."
            ),
            i18n_key="diagnostics.alert.hooks_not_installed",
            context={"installed": []},
            first_seen=now,
            last_seen=now,
            silenced_until=None,
            dismissed=False,
        )
    missing = [e for e in _REQUIRED_HOOK_EVENTS if e not in installed]
    if missing:
        return StoredAlert(
            id="hooks_partial",
            detector="check_hooks_present",
            severity="warning",
            message=(
                f"Some Claude Code hooks are missing: {', '.join(missing)}. "
                f"Re-run `mnemos hooks install`."
            ),
            i18n_key="diagnostics.alert.hooks_partial",
            i18n_params={"missing": ", ".join(missing)},
            context={"installed": sorted(installed), "missing": missing},
            first_seen=now,
            last_seen=now,
            silenced_until=None,
            dismissed=False,
        )
    return None


def check_vault_writable(vault_roots: Iterable[Path]) -> StoredAlert | None:
    """Critical if any registered vault_root is not writable."""
    bad: list[str] = []
    for vr in vault_roots:
        try:
            vr.mkdir(parents=True, exist_ok=True)
            probe = vr / ".write_probe.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError:
            bad.append(str(vr))
    if not bad:
        return None
    now = utcnow()
    return StoredAlert(
        id="vault_not_writable",
        detector="check_vault_writable",
        severity="critical",
        message=(
            "These vault roots are not writable: "
            + ", ".join(bad)
            + ". Check permissions."
        ),
        i18n_key="diagnostics.alert.vault_not_writable",
        i18n_params={"paths": ", ".join(bad)},
        context={"unwritable": bad},
        first_seen=now,
        last_seen=now,
        silenced_until=None,
        dismissed=False,
    )
