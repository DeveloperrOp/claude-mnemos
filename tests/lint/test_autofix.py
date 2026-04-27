from datetime import UTC, datetime
from pathlib import Path

from claude_mnemos.core.undo import undo
from claude_mnemos.lint.autofix import apply_autofix
from claude_mnemos.lint.models import (
    LintFinding,
    LintFixKind,
    LintReport,
    LintReportSummary,
    LintSeverity,
)
from claude_mnemos.state.activity import ActivityLog


def _seed(vault: Path, rel: str, body: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\n"
        "title: T\n"
        "type: entity\n"
        "created: 2026-04-26\n"
        "updated: 2026-04-26\n"
        "agent_written: true\n"
        "---\n" + body,
        encoding="utf-8",
    )
    return p


def _now() -> datetime:
    return datetime.now(UTC)


def _report_with(findings: list[LintFinding]) -> LintReport:
    return LintReport(
        run_id="r1",
        started_at=_now(),
        finished_at=_now(),
        vault_root="/x",
        rule_versions={},
        summary=LintReportSummary(
            total=len(findings),
            by_severity={"info": len(findings)},
            by_rule={},
            fixable_count=sum(1 for f in findings if f.fixable),
        ),
        findings=findings,
    )


def _ws_finding(rel: str) -> LintFinding:
    return LintFinding(
        id="trailing_whitespace:abcd1234",
        rule_id="trailing_whitespace",
        severity=LintSeverity.INFO,
        message="m",
        page_path=rel,
        fixable=True,
        fix_kind=LintFixKind.STRIP_TRAILING_WS,
        metadata={"lines": [1]},
    )


def _wl_finding(rel: str, target: str, candidate: str) -> LintFinding:
    return LintFinding(
        id="wikilinks_broken:abcd1234",
        rule_id="wikilinks_broken",
        severity=LintSeverity.WARNING,
        message="m",
        page_path=rel,
        fixable=True,
        fix_kind=LintFixKind.FIX_WIKILINK_TYPO,
        metadata={"target": target, "candidate": candidate},
    )


def test_autofix_no_fixable_is_noop(tmp_path: Path) -> None:
    report = LintReport(
        run_id="r",
        started_at=_now(),
        finished_at=_now(),
        vault_root="/x",
        rule_versions={},
        summary=LintReportSummary(total=0, fixable_count=0),
        findings=[],
    )
    result = apply_autofix(tmp_path, report)
    assert result.success is True
    assert result.snapshot_path is None
    assert result.activity_id is None


def test_autofix_strip_trailing_whitespace(tmp_path: Path) -> None:
    rel = "wiki/entities/foo.md"
    _seed(tmp_path, rel, "line one  \nline two\n")
    result = apply_autofix(tmp_path, _report_with([_ws_finding(rel)]))
    assert result.success
    assert result.snapshot_path is not None
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert "line one  " not in text
    assert "line one" in text


def test_autofix_writes_lint_fix_activity(tmp_path: Path) -> None:
    rel = "wiki/entities/foo.md"
    _seed(tmp_path, rel, "x  \n")
    result = apply_autofix(tmp_path, _report_with([_ws_finding(rel)]))
    log = ActivityLog.load(tmp_path)
    assert len(log.entries) == 1
    e = log.entries[0]
    assert e.operation_type == "lint_fix"
    assert e.id == result.activity_id
    assert e.can_undo is True


def test_autofix_undoable(tmp_path: Path) -> None:
    rel = "wiki/entities/foo.md"
    _seed(tmp_path, rel, "line one  \nline two\n")
    result = apply_autofix(tmp_path, _report_with([_ws_finding(rel)]))
    assert result.activity_id

    undo_result = undo(tmp_path, result.activity_id)
    assert undo_result.success is True
    assert "line one  " in (tmp_path / rel).read_text(encoding="utf-8")


def test_autofix_fix_wikilink_typo(tmp_path: Path) -> None:
    rel = "wiki/entities/src.md"
    _seed(tmp_path, "wiki/entities/file-lock-bug.md", "ok\n")
    _seed(tmp_path, rel, "See [[file-lock-bub]]\n")
    result = apply_autofix(
        tmp_path,
        _report_with([_wl_finding(rel, "file-lock-bub", "file-lock-bug")]),
    )
    assert result.success
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert "[[file-lock-bug]]" in text
    assert "[[file-lock-bub]]" not in text
