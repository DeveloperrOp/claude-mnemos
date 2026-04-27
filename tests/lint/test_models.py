from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from claude_mnemos.lint.models import (
    LintFinding,
    LintFixKind,
    LintReport,
    LintReportSummary,
    LintSeverity,
)


def test_severity_values():
    assert LintSeverity.ERROR.value == "error"
    assert LintSeverity.WARNING.value == "warning"
    assert LintSeverity.INFO.value == "info"


def test_fix_kind_values():
    assert LintFixKind.STRIP_TRAILING_WS.value == "strip_trailing_ws"
    assert LintFixKind.FIX_WIKILINK_TYPO.value == "fix_wikilink_typo"
    assert LintFixKind.ADD_DEFAULT_FRONTMATTER_FIELD.value == "add_default_frontmatter_field"


def test_finding_minimal():
    f = LintFinding(
        id="orphan_pages:abcd1234",
        rule_id="orphan_pages",
        severity=LintSeverity.WARNING,
        message="page has no incoming wikilinks",
        page_path="wiki/entities/foo.md",
        fixable=False,
        fix_kind=None,
    )
    assert f.metadata == {}


def test_finding_rejects_extra_fields():
    with pytest.raises(ValidationError):
        LintFinding(
            id="x",
            rule_id="x",
            severity=LintSeverity.INFO,
            message="m",
            page_path="p.md",
            fixable=False,
            fix_kind=None,
            unknown_field="oops",
        )


def test_finding_fix_kind_consistency():
    f = LintFinding(
        id="trailing_whitespace:abcd",
        rule_id="trailing_whitespace",
        severity=LintSeverity.INFO,
        message="trailing whitespace on lines 3,5",
        page_path="wiki/entities/foo.md",
        fixable=True,
        fix_kind=LintFixKind.STRIP_TRAILING_WS,
        metadata={"lines": [3, 5]},
    )
    assert f.fix_kind == LintFixKind.STRIP_TRAILING_WS


def test_report_round_trip_json():
    finding = LintFinding(
        id="orphan_pages:abcd1234",
        rule_id="orphan_pages",
        severity=LintSeverity.WARNING,
        message="orphan",
        page_path="wiki/entities/foo.md",
        fixable=False,
        fix_kind=None,
    )
    summary = LintReportSummary(
        total=1,
        by_severity={"warning": 1},
        by_rule={"orphan_pages": 1},
        fixable_count=0,
    )
    report = LintReport(
        run_id="abc123",
        started_at=datetime(2026, 4, 27, 14, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 4, 27, 14, 0, 1, tzinfo=UTC),
        vault_root="/path/to/vault",
        rule_versions={"orphan_pages": "v1"},
        findings=[finding],
        summary=summary,
    )
    raw = report.model_dump_json()
    reloaded = LintReport.model_validate_json(raw)
    assert reloaded.run_id == "abc123"
    assert reloaded.findings[0].rule_id == "orphan_pages"
