from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.lint.exceptions import LintCorruptError
from claude_mnemos.lint.models import (
    LintFinding,
    LintReport,
    LintReportSummary,
    LintSeverity,
)
from claude_mnemos.lint.state import (
    LINT_RESULTS_FILENAME,
    load_last_report,
    save_report,
)


def _make_report() -> LintReport:
    return LintReport(
        run_id="abc",
        started_at=datetime(2026, 4, 27, 14, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 4, 27, 14, 0, 1, tzinfo=UTC),
        vault_root="/x",
        rule_versions={"orphan_pages": "v1"},
        summary=LintReportSummary(
            total=1, by_severity={"warning": 1}, by_rule={"orphan_pages": 1}, fixable_count=0
        ),
        findings=[
            LintFinding(
                id="x:1234",
                rule_id="orphan_pages",
                severity=LintSeverity.WARNING,
                message="m",
                page_path="wiki/entities/x.md",
                fixable=False,
                fix_kind=None,
            )
        ],
    )


def test_load_returns_none_when_missing(tmp_path: Path):
    assert load_last_report(tmp_path) is None


def test_save_then_load_round_trip(tmp_path: Path):
    save_report(tmp_path, _make_report())
    assert (tmp_path / LINT_RESULTS_FILENAME).is_file()
    loaded = load_last_report(tmp_path)
    assert loaded is not None
    assert loaded.run_id == "abc"
    assert len(loaded.findings) == 1


def test_load_corrupt_json_raises(tmp_path: Path):
    (tmp_path / LINT_RESULTS_FILENAME).write_text("not json {", encoding="utf-8")
    with pytest.raises(LintCorruptError):
        load_last_report(tmp_path)


def test_load_invalid_schema_raises(tmp_path: Path):
    (tmp_path / LINT_RESULTS_FILENAME).write_text(
        '{"run_id": "x"}', encoding="utf-8"
    )
    with pytest.raises(LintCorruptError):
        load_last_report(tmp_path)


def test_save_uses_tracker_when_provided(tmp_path: Path):
    """Tracker hook is called both before write (add) and after (remove)."""
    from claude_mnemos.daemon.our_writes import OurWritesTracker

    tracker = OurWritesTracker(ttl_s=60.0)
    add_calls: list[Path] = []
    remove_calls: list[Path] = []

    real_add = tracker.add
    real_remove = tracker.remove

    def add_spy(p: Path, *, ttl_s=None):  # noqa: ANN001
        add_calls.append(p)
        real_add(p, ttl_s=ttl_s)

    def remove_spy(p: Path):
        remove_calls.append(p)
        real_remove(p)

    tracker.add = add_spy  # type: ignore[method-assign]
    tracker.remove = remove_spy  # type: ignore[method-assign]

    save_report(tmp_path, _make_report(), tracker=tracker)

    assert (tmp_path / LINT_RESULTS_FILENAME) in add_calls
    assert (tmp_path / LINT_RESULTS_FILENAME) in remove_calls
