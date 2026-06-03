"""Top-level lint executor: parse all wiki/*.md, run every rule, build report."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from claude_mnemos.core.page_io import ParsedPage, read_page
from claude_mnemos.lint.models import (
    LintFinding,
    LintReport,
    LintReportSummary,
    LintSeverity,
)
from claude_mnemos.lint.rules import RULE_REGISTRY, RULE_VERSIONS

PageEntry = tuple[Path, ParsedPage | None]


class LintRunner:
    def __init__(self, vault: Path, enabled_rules: list[str] | None = None) -> None:
        self.vault = vault
        # None → run every rule (default). A list → run only those rule_ids;
        # the rest are skipped. Mirrors LintSettings.enabled_rules semantics
        # ("all ticked" normalises to None on the frontend).
        self.enabled_rules = enabled_rules

    def run(self) -> LintReport:
        run_id = uuid4().hex
        started = datetime.now(UTC)

        pages: list[PageEntry] = []
        for p in sorted(self.vault.glob("wiki/**/*.md")):
            # Skip dot-subdirs *inside* the vault (e.g. wiki/.archive/). Use the
            # path relative to the vault — the vault itself often lives under a
            # dot-dir (~/.mnemos-dev), and the absolute path would otherwise skip
            # every page.
            if any(part.startswith(".") for part in p.relative_to(self.vault).parts):
                continue
            try:
                pages.append((p, read_page(p)))
            except Exception:
                pages.append((p, None))

        all_findings: list[LintFinding] = []
        for rule_id, rule_fn in RULE_REGISTRY.items():
            if self.enabled_rules is not None and rule_id not in self.enabled_rules:
                continue
            try:
                all_findings.extend(rule_fn(self.vault, pages))
            except Exception as exc:
                all_findings.append(
                    LintFinding(
                        id=f"runner_error:{rule_id}",
                        rule_id=rule_id,
                        severity=LintSeverity.ERROR,
                        message=f"rule crashed: {exc}",
                        page_path="",
                        fixable=False,
                        fix_kind=None,
                        metadata={"exception": type(exc).__name__},
                    )
                )

        finished = datetime.now(UTC)
        summary = self._build_summary(all_findings)
        return LintReport(
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            vault_root=str(self.vault.resolve()),
            rule_versions=dict(RULE_VERSIONS),
            summary=summary,
            findings=all_findings,
        )

    @staticmethod
    def _build_summary(findings: list[LintFinding]) -> LintReportSummary:
        by_severity: dict[str, int] = {}
        by_rule: dict[str, int] = {}
        fixable = 0
        for f in findings:
            sev = f.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_rule[f.rule_id] = by_rule.get(f.rule_id, 0) + 1
            if f.fixable:
                fixable += 1
        return LintReportSummary(
            total=len(findings),
            by_severity=by_severity,
            by_rule=by_rule,
            fixable_count=fixable,
        )
