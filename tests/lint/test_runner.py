from pathlib import Path

from claude_mnemos.lint.runner import LintRunner


def _seed_valid(vault: Path, rel: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\n"
        "title: T\n"
        "type: entity\n"
        "created: 2026-04-26\n"
        "updated: 2026-04-26\n"
        "agent_written: true\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    return p


def test_runner_empty_vault(tmp_path: Path):
    report = LintRunner(tmp_path).run()
    assert report.findings == []
    assert report.summary.total == 0
    assert report.run_id


def test_runner_collects_orphans(tmp_path: Path):
    _seed_valid(tmp_path, "wiki/entities/foo.md")
    _seed_valid(tmp_path, "wiki/entities/bar.md")
    report = LintRunner(tmp_path).run()
    orphan_findings = [f for f in report.findings if f.rule_id == "orphan_pages"]
    assert len(orphan_findings) == 2


def test_runner_summary_breakdown(tmp_path: Path):
    _seed_valid(tmp_path, "wiki/entities/orphan.md")
    report = LintRunner(tmp_path).run()
    assert report.summary.total >= 1
    assert "warning" in report.summary.by_severity
    assert "orphan_pages" in report.summary.by_rule


def test_runner_detects_parse_failed(tmp_path: Path):
    p = tmp_path / "wiki/entities/broken.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("invalid", encoding="utf-8")
    report = LintRunner(tmp_path).run()
    assert any(f.rule_id == "page_parse_failed" for f in report.findings)


def test_runner_timestamps_finite(tmp_path: Path):
    report = LintRunner(tmp_path).run()
    assert report.started_at <= report.finished_at
    assert report.started_at.tzinfo is not None
