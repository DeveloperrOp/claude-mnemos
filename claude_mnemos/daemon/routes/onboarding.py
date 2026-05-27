"""REST endpoints powering the Welcome screen + Setup-Checklist widget.

GET /api/onboarding/detected-cwds  → suggested workspaces from ~/.claude/projects/
GET /api/onboarding/setup-status   → 4-row install/operational health summary
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from claude_mnemos.core.cwd_detection import detect_cwds
from claude_mnemos.core.install_checks import (
    check_claude_cli_installed,
    check_hooks_present,
    check_vault_writable,
)

router = APIRouter()


def _registered_cwds(request: Request) -> set[str]:
    daemon = request.app.state.daemon
    if daemon is None:
        return set()
    out: set[str] = set()
    # VaultRuntime stores its ProjectMapEntry as `.project`, not `.entry`.
    # The previous code did `rt.entry.cwd_patterns` inside a bare-except
    # which swallowed the AttributeError silently — the result was that
    # this filter always returned an empty set in production, so the
    # Onboarding wizard re-offered already-tracked workspaces.
    for rt in daemon.runtimes.values():
        for pat in (rt.project.cwd_patterns or []):
            out.add(
                pat.replace("\\**", "").replace("\\*", "").rstrip("\\/").rstrip("/"),
            )
    return out


def _project_count(request: Request) -> int:
    daemon = request.app.state.daemon
    if daemon is None:
        return 0
    return len(daemon.runtimes)


def _vault_roots(request: Request) -> list:
    daemon = request.app.state.daemon
    if daemon is None:
        return []
    return [rt.vault_root for rt in daemon.runtimes.values()]


@router.get("/onboarding/detected-cwds")
def detected_cwds_route(request: Request) -> dict[str, Any]:
    excluded = _registered_cwds(request)
    items = detect_cwds(exclude_cwds=excluded)
    return {"cwds": [d.model_dump(mode="json") for d in items]}


def _row(
    alert: Any | None,
    ok_message: str,
    ok_i18n_key: str,
    ok_i18n_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a setup-status row.

    v0.0.17: each row carries `i18n_key` + `i18n_params` alongside the
    legacy `message` string. Frontend prefers the i18n payload (rendered
    via `t(key, params)`) and falls back to `message` for old clients.
    """
    if alert is None:
        return {
            "status": "ok",
            "message": ok_message,
            "i18n_key": ok_i18n_key,
            "i18n_params": ok_i18n_params or {},
        }
    return {
        "status": alert.severity,
        "message": alert.message,
        "i18n_key": alert.i18n_key,
        "i18n_params": alert.i18n_params or {},
        "id": alert.id,
    }


@router.get("/onboarding/setup-status")
def setup_status_route(request: Request) -> dict[str, Any]:
    cli_alert = check_claude_cli_installed()
    hooks_alert = check_hooks_present()
    vaults_alert = check_vault_writable(_vault_roots(request))
    project_count = _project_count(request)

    rows = {
        "claude_cli": _row(
            cli_alert,
            "Claude Code CLI is installed.",
            "diagnostics.row.claude_cli_ok",
        ),
        "hooks": _row(
            hooks_alert,
            "All Claude Code hooks are installed.",
            "diagnostics.row.hooks_ok",
        ),
        "vaults": _row(
            vaults_alert,
            "All vault roots are writable.",
            "diagnostics.row.vaults_ok",
        ),
        "projects": (
            {
                "status": "ok",
                "message": f"{project_count} project(s) tracked.",
                "i18n_key": "diagnostics.row.projects_tracked",
                "i18n_params": {"count": project_count},
                "count": project_count,
            }
            if project_count > 0
            else {
                "status": "warning",
                "message": "No projects tracked yet.",
                "i18n_key": "diagnostics.row.projects_none",
                "i18n_params": {},
                "count": 0,
            }
        ),
    }
    all_ok = all(r["status"] == "ok" for r in rows.values())
    return {"all_ok": all_ok, **rows}
