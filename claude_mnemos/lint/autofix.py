"""Apply whitelisted lint autofixes through StagingTransaction."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from claude_mnemos.config import Config
from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.page_io import ParsedPage, read_page, serialize_page
from claude_mnemos.core.staging import StagingTransaction
from claude_mnemos.core.wikilinks import rewrite_wikilinks
from claude_mnemos.lint.exceptions import LintError
from claude_mnemos.lint.models import (
    LintFinding,
    LintFixKind,
    LintReport,
)
from claude_mnemos.state.activity import (
    ACTIVITY_FILENAME,
    ActivityEntry,
    ActivityLog,
)

if TYPE_CHECKING:
    from claude_mnemos.daemon.our_writes import OurWritesTracker

SAFE_FIX_KINDS: set[LintFixKind] = {
    LintFixKind.STRIP_TRAILING_WS,
    LintFixKind.FIX_WIKILINK_TYPO,
    LintFixKind.ADD_DEFAULT_FRONTMATTER_FIELD,
}


@dataclass(frozen=True)
class AutofixResult:
    success: bool
    snapshot_path: Path | None = None
    fixed_findings: list[str] = field(default_factory=list)
    skipped_findings: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    activity_id: str | None = None


def apply_autofix(
    vault: Path,
    report: LintReport,
    *,
    tracker: OurWritesTracker | None = None,
    cfg: Config | None = None,
) -> AutofixResult:
    cfg = cfg or Config.from_env()
    applicable: list[LintFinding] = [
        f
        for f in report.findings
        if f.fixable and f.fix_kind is not None and f.fix_kind in SAFE_FIX_KINDS
    ]
    skipped: list[str] = [
        f.id
        for f in report.findings
        if f.fixable and (f.fix_kind is None or f.fix_kind not in SAFE_FIX_KINDS)
    ]

    if not applicable:
        return AutofixResult(
            success=True,
            snapshot_path=None,
            fixed_findings=[],
            skipped_findings=skipped,
            errors=[],
            activity_id=None,
        )

    by_page: dict[str, list[LintFinding]] = defaultdict(list)
    for f in applicable:
        by_page[f.page_path].append(f)

    # Pre-pass: parse and apply fixes in memory so a broken page doesn't abort
    # the whole batch or open a useless StagingTransaction.
    fixed_findings: list[str] = []
    errors: list[tuple[str, str]] = []
    prepared: list[tuple[str, str]] = []  # (page_rel, serialized_content)
    fixed_by_page: dict[str, list[LintFinding]] = {}

    for page_rel, fixes in by_page.items():
        full = vault / page_rel
        try:
            parsed = read_page(full)
            new_parsed = parsed
            for fix in fixes:
                new_parsed = _apply_fix(new_parsed, fix)
            content = serialize_page(new_parsed)
        except (FileNotFoundError, OSError) as exc:
            errors.append((fixes[0].id, f"page unreadable: {exc}"))
            continue
        except Exception as exc:  # PageParseError + anything else from _apply_fix
            errors.append((fixes[0].id, f"{type(exc).__name__}: {exc}"))
            continue
        prepared.append((page_rel, content))
        fixed_by_page[page_rel] = fixes
        fixed_findings.extend(f.id for f in fixes)

    if not prepared:
        # All pages failed (or none were applicable after errors). Surface
        # errors but skip staging/activity entirely — symmetrical with the
        # empty-applicable case.
        return AutofixResult(
            success=len(errors) == 0,
            snapshot_path=None,
            fixed_findings=[],
            skipped_findings=skipped,
            errors=errors,
            activity_id=None,
        )

    op_id = uuid4().hex
    fixed_findings_objs = [f for fixes in fixed_by_page.values() for f in fixes]
    with (
        pipeline_lock(vault, timeout=cfg.lock_timeout),
        StagingTransaction(vault, op_id, operation_type="lint_fix") as txn,
    ):
        for page_rel, content in prepared:
            txn.write(Path(page_rel), content)

        snap = txn.pre_promote_snapshot_path()
        activity = ActivityLog.load(vault)
        activity.append(
            ActivityEntry(
                id=op_id,
                timestamp=datetime.now(UTC),
                operation_type="lint_fix",
                status="success",
                snapshot_path=snap.relative_to(vault).as_posix(),
                can_undo=True,
                affected_pages=sorted(fixed_by_page.keys()),
                metadata={
                    "fixed_finding_ids": fixed_findings,
                    "rule_breakdown": _count_by_rule(fixed_findings_objs),
                },
            )
        )
        txn.write(Path(ACTIVITY_FILENAME), activity.serialize_to_string())

        promote = txn.promote_to_vault(tracker=tracker)

    return AutofixResult(
        success=len(errors) == 0,
        snapshot_path=promote.snapshot,
        fixed_findings=fixed_findings,
        skipped_findings=skipped,
        errors=errors,
        activity_id=op_id,
    )


def _apply_fix(parsed: ParsedPage, finding: LintFinding) -> ParsedPage:
    if finding.fix_kind == LintFixKind.STRIP_TRAILING_WS:
        body_lines = parsed.body.splitlines()
        new_body = "\n".join(line.rstrip() for line in body_lines)
        if parsed.body.endswith("\n"):
            new_body += "\n"
        return ParsedPage(parsed.frontmatter, parsed.extra_fm, new_body)

    if finding.fix_kind == LintFixKind.FIX_WIKILINK_TYPO:
        target = finding.metadata["target"]
        candidate = finding.metadata["candidate"]
        new_body = rewrite_wikilinks(parsed.body, {target: candidate})
        return ParsedPage(parsed.frontmatter, parsed.extra_fm, new_body)

    if finding.fix_kind == LintFixKind.ADD_DEFAULT_FRONTMATTER_FIELD:
        field_name = finding.metadata["field"]
        default_value = finding.metadata["default_value"]
        new_fm = parsed.frontmatter.model_copy(update={field_name: default_value})
        return ParsedPage(new_fm, parsed.extra_fm, parsed.body)

    raise LintError(f"unknown fix_kind: {finding.fix_kind}")


def _count_by_rule(findings: Iterable[LintFinding]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in findings:
        out[f.rule_id] = out.get(f.rule_id, 0) + 1
    return out
