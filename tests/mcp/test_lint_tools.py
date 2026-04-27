import json
from pathlib import Path

from claude_mnemos.lint.models import (
    LintFinding,
    LintReport,
    LintReportSummary,
    LintSeverity,
)
from claude_mnemos.lint.state import save_report
from claude_mnemos.mcp.read_tools.lint import get_lint_results
from claude_mnemos.mcp.write_tools.lint import run_lint


def _make_report() -> LintReport:
    from datetime import UTC, datetime

    return LintReport(
        run_id="r1",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        vault_root="/x",
        rule_versions={},
        findings=[
            LintFinding(
                id="x:1",
                rule_id="orphan_pages",
                severity=LintSeverity.WARNING,
                message="m",
                page_path="wiki/entities/x.md",
                fixable=False,
                fix_kind=None,
            )
        ],
        summary=LintReportSummary(
            total=1,
            by_severity={"warning": 1},
            by_rule={"orphan_pages": 1},
            fixable_count=0,
        ),
    )


async def test_get_lint_results_no_file(tmp_path: Path) -> None:
    out = await get_lint_results(tmp_path)
    assert "no lint run yet" in out[0].text.lower()


async def test_get_lint_results_with_file(tmp_path: Path) -> None:
    save_report(tmp_path, _make_report())
    out = await get_lint_results(tmp_path)
    parsed = json.loads(out[0].text)
    assert parsed["run_id"] == "r1"


async def test_run_lint_daemon_unreachable() -> None:
    out = await run_lint("http://127.0.0.1:1", timeout_s=0.5)
    assert "daemon" in out[0].text.lower()
