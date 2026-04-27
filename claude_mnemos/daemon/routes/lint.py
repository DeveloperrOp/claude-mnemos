from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request

from claude_mnemos.lint.autofix import apply_autofix
from claude_mnemos.lint.runner import LintRunner
from claude_mnemos.lint.state import load_last_report, save_report

if TYPE_CHECKING:
    from claude_mnemos.daemon.our_writes import OurWritesTracker

router = APIRouter()


def _vault(request: Request) -> Path:
    vault = request.app.state.vault_root
    assert isinstance(vault, Path)
    return vault


def _tracker(request: Request) -> OurWritesTracker | None:
    daemon = request.app.state.daemon
    if daemon is None:
        return None
    tracker = getattr(daemon, "tracker", None)
    return tracker


@router.post("/lint/run")
async def lint_run(request: Request) -> dict[str, Any]:
    vault = _vault(request)
    report = LintRunner(vault).run()
    save_report(vault, report, tracker=_tracker(request))
    return report.model_dump(mode="json")


@router.get("/lint/results")
async def lint_results(request: Request) -> dict[str, Any]:
    vault = _vault(request)
    report = load_last_report(vault)
    if report is None:
        raise HTTPException(status_code=404, detail={"error": "no_lint_run_yet"})
    return report.model_dump(mode="json")


@router.post("/lint/autofix")
async def lint_autofix(request: Request) -> dict[str, Any]:
    vault = _vault(request)
    report = load_last_report(vault)
    if report is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "no_cached_report",
                "hint": "POST /lint/run first to produce a report, then call /lint/autofix",
            },
        )
    result = apply_autofix(vault, report, tracker=_tracker(request))
    return {
        "success": result.success,
        "snapshot_path": str(result.snapshot_path) if result.snapshot_path else None,
        "fixed_findings": result.fixed_findings,
        "skipped_findings": result.skipped_findings,
        "activity_id": result.activity_id,
    }
