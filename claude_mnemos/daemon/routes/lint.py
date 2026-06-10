"""REST routes for lint run / results / autofix.

Per-project routes resolve the target VaultRuntime via
``get_runtime(request, project)`` (404 on unknown project) and use
``runtime.vault_root`` for filesystem operations and ``runtime.tracker``
for our-writes registration.

URL structure::

    POST   /lint/{project}/run       — run lint across the vault
    GET    /lint/{project}/results   — retrieve last lint report
    POST   /lint/{project}/autofix   — apply autofix from cached report
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.daemon.routes._helpers import get_runtime
from claude_mnemos.lint.autofix import apply_autofix
from claude_mnemos.lint.models import LintReport
from claude_mnemos.lint.runner import LintRunner
from claude_mnemos.lint.state import load_last_report, save_report

router = APIRouter()


@router.post("/lint/{project}/run")
async def lint_run(project: str, request: Request) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    enabled = runtime.settings.lint.enabled_rules
    tracker = runtime.tracker

    # LintRunner walks the whole vault + parses YAML; save_report writes to
    # disk. Both are blocking — offload off the event loop so a large vault
    # doesn't freeze every other request for the duration of the lint.
    def _run() -> LintReport:
        report = LintRunner(vault, enabled).run()
        save_report(vault, report, tracker=tracker)
        return report

    report = await asyncio.to_thread(_run)
    return report.model_dump(mode="json")


@router.get("/lint/{project}/results")
async def lint_results(project: str, request: Request) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    report = load_last_report(vault)
    if report is None:
        raise HTTPException(status_code=404, detail={"error": "no_lint_run_yet"})
    return report.model_dump(mode="json")


@router.post("/lint/{project}/autofix")
async def lint_autofix(project: str, request: Request) -> dict[str, Any]:
    runtime = get_runtime(request, project)
    vault = runtime.vault_root
    report = load_last_report(vault)
    if report is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "no_cached_report",
                "hint": "POST /lint/{project}/run first, then call /lint/{project}/autofix",
            },
        )
    # apply_autofix mutates files through a staging transaction — blocking.
    result = await asyncio.to_thread(
        apply_autofix, vault, report, tracker=runtime.tracker
    )
    return {
        "success": result.success,
        "snapshot_path": str(result.snapshot_path) if result.snapshot_path else None,
        "fixed_findings": result.fixed_findings,
        "skipped_findings": result.skipped_findings,
        "activity_id": result.activity_id,
    }
