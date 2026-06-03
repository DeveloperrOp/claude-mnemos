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


def test_runner_respects_enabled_rules(tmp_path: Path):
    # Two orphan pages would normally trip the orphan_pages rule.
    _seed_valid(tmp_path, "wiki/entities/foo.md")
    _seed_valid(tmp_path, "wiki/entities/bar.md")
    # With orphan_pages absent from enabled_rules, it must not run.
    report = LintRunner(tmp_path, enabled_rules=["page_parse_failed"]).run()
    assert all(f.rule_id != "orphan_pages" for f in report.findings)


def test_runner_enabled_rules_none_runs_all(tmp_path: Path):
    # None preserves the default "all rules" behaviour.
    _seed_valid(tmp_path, "wiki/entities/foo.md")
    _seed_valid(tmp_path, "wiki/entities/bar.md")
    report = LintRunner(tmp_path, enabled_rules=None).run()
    assert any(f.rule_id == "orphan_pages" for f in report.findings)


def test_runner_scans_vault_inside_dot_directory(tmp_path: Path):
    # Real mnemos vaults live under a dot-prefixed dir (~/.mnemos-dev). The
    # dot-component filter must look at the path RELATIVE to the vault, not
    # the absolute path — otherwise every page is skipped and lint is a no-op.
    vault = tmp_path / ".mnemos-dev"
    vault.mkdir()
    _seed_valid(vault, "wiki/entities/foo.md")
    _seed_valid(vault, "wiki/entities/bar.md")
    report = LintRunner(vault).run()
    assert any(f.rule_id == "orphan_pages" for f in report.findings)


def test_runner_skips_dot_subdirs_inside_vault(tmp_path: Path):
    # Pages under a dot-subdir INSIDE the vault (e.g. wiki/.archive/) are
    # still skipped — that's what the filter is actually for.
    _seed_valid(tmp_path, "wiki/.archive/old.md")
    report = LintRunner(tmp_path).run()
    assert all(".archive" not in f.page_path for f in report.findings)
    assert report.summary.total == 0
