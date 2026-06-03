from __future__ import annotations

import logging
from pathlib import Path

from claude_mnemos.lint.runner import LintRunner
from claude_mnemos.lint.state import save_report

logger = logging.getLogger(__name__)


def lint_check_task(vault: Path, enabled_rules: list[str] | None = None) -> None:
    """Run lint across the vault and cache the report.

    Invoked by APScheduler on the project's ``lint.schedule`` cadence — never
    raises (a crashing cron tick would otherwise kill the job). ``enabled_rules``
    mirrors the per-project lint setting; ``None`` runs every rule.
    """
    try:
        report = LintRunner(vault, enabled_rules).run()
        save_report(vault, report)
        logger.info(
            "scheduled lint completed for %s (%d findings)",
            vault,
            report.summary.total,
        )
    except Exception:
        logger.exception("scheduled lint failed for %s", vault)
