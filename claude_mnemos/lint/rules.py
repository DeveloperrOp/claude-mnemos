"""Lint rules: each is a callable (vault, parsed_pages) -> list[LintFinding].

Pages where parsing failed are passed as (path, None). Most rules skip them
(they show up only in `page_parse_failed`).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from claude_mnemos.core.page_io import ParsedPage
from claude_mnemos.core.wikilinks import extract_wikilinks
from claude_mnemos.lint.models import LintFinding, LintFixKind, LintSeverity
from claude_mnemos.lint.utils import (
    build_resolvable_targets,
    build_slug_index,
    levenshtein_distance,
)

PageEntry = tuple[Path, ParsedPage | None]
RuleFn = Callable[[Path, list[PageEntry]], list[LintFinding]]

STALE_DAYS = 90
LEVENSHTEIN_TYPO_THRESHOLD = 2
INFERRED_PCT_THRESHOLD = 50
AMBIGUOUS_PCT_THRESHOLD = 30
RULE_VERSIONS = {
    "page_parse_failed": "v1",
    # v2: resolve path-form ([[dir/name]]) and raw/chats backlinks ([[uuid]])
    # against every .md basename in the vault, not just wiki/* slugs.
    "wikilinks_broken": "v2",
    "orphan_pages": "v1",
    "stale_pages": "v1",
    "duplicate_titles": "v1",
    "provenance_inferred_high": "v1",
    "provenance_ambiguous_high": "v1",
    "trailing_whitespace": "v1",
}


def _finding_id(rule_id: str, page_path: str, message: str) -> str:
    h = hashlib.sha256(f"{page_path}|{message}".encode()).hexdigest()[:8]
    return f"{rule_id}:{h}"


def _rel(vault: Path, p: Path) -> str:
    return p.relative_to(vault).as_posix()


# ---------------------------------------------------------------- synthetic


def page_parse_failed(vault: Path, pages: list[PageEntry]) -> list[LintFinding]:
    out: list[LintFinding] = []
    for p, parsed in pages:
        if parsed is not None:
            continue
        rel = _rel(vault, p)
        msg = "page could not be parsed (frontmatter invalid or missing)"
        out.append(
            LintFinding(
                id=_finding_id("page_parse_failed", rel, msg),
                rule_id="page_parse_failed",
                severity=LintSeverity.ERROR,
                message=msg,
                page_path=rel,
                fixable=False,
                fix_kind=None,
                metadata={},
            )
        )
    return out


# ---------------------------------------------------------------- wikilinks


def _normalize_link_target(target: str) -> str:
    """Reduce a wikilink target to the basename Obsidian would resolve.

    Strips a ``#heading`` anchor, any directory prefix (after the last `/` or
    `\\`), and a trailing `.md` suffix (case-insensitive). We do NOT slugify —
    Obsidian matches real filenames/headings, so a free-text title-form target
    stays as-is and is correctly flagged broken when no file by that basename
    exists. A pure same-page anchor (``[[#heading]]``) normalizes to ``""``.

    Examples: "page#Section" -> "page"; "sources/2026-05-02-x" -> "2026-05-02-x";
    "x.md" -> "x"; "x" -> "x".
    """
    # Drop a heading anchor first so [[page#heading]] resolves to page.md and is
    # never fed to the typo autofix (which would silently delete the anchor).
    base = target.split("#", 1)[0]
    base = base.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if base.lower().endswith(".md"):
        base = base[: -len(".md")]
    return base


def wikilinks_broken(vault: Path, pages: list[PageEntry]) -> list[LintFinding]:
    out: list[LintFinding] = []
    slug_index = build_slug_index(vault)
    known = set(slug_index.keys())
    # Obsidian-style resolution: a bare [[name]] or path-form [[dir/name]]
    # resolves to any name.md anywhere in the vault (incl. raw/chats/).
    resolvable = build_resolvable_targets(vault)
    for p, parsed in pages:
        if parsed is None:
            continue
        rel = _rel(vault, p)
        for link in extract_wikilinks(parsed.body):
            target = link.target
            norm = _normalize_link_target(target)
            # A pure same-page anchor ([[#heading]]) targets the current page —
            # it always resolves and is never broken.
            if norm == "":
                continue
            # Fast back-compat path + Obsidian-style basename resolution.
            if target in known or norm in resolvable:
                continue
            # A heading-anchored link ([[page#x]]) that didn't resolve must NOT
            # be offered as a typo autofix: FIX_WIKILINK_TYPO rewrites
            # [[target]] -> [[candidate]] and would silently drop the #anchor.
            # Flag it broken-but-not-fixable instead.
            allow_typo_fix = "#" not in target
            candidates = (
                [
                    s
                    for s in known
                    if levenshtein_distance(norm, s) <= LEVENSHTEIN_TYPO_THRESHOLD
                ]
                if allow_typo_fix
                else []
            )
            unique_candidate = candidates[0] if len(candidates) == 1 else None
            if unique_candidate is not None:
                msg = f"broken wikilink [[{target}]] (likely typo of [[{unique_candidate}]])"
                out.append(
                    LintFinding(
                        id=_finding_id("wikilinks_broken", rel, msg),
                        rule_id="wikilinks_broken",
                        severity=LintSeverity.WARNING,
                        message=msg,
                        page_path=rel,
                        fixable=True,
                        fix_kind=LintFixKind.FIX_WIKILINK_TYPO,
                        metadata={"target": target, "candidate": unique_candidate},
                    )
                )
            else:
                msg = f"broken wikilink [[{target}]]"
                out.append(
                    LintFinding(
                        id=_finding_id("wikilinks_broken", rel, msg),
                        rule_id="wikilinks_broken",
                        severity=LintSeverity.WARNING,
                        message=msg,
                        page_path=rel,
                        fixable=False,
                        fix_kind=None,
                        metadata={"target": target, "candidate": None},
                    )
                )
    return out


# ---------------------------------------------------------------- orphan_pages


def orphan_pages(vault: Path, pages: list[PageEntry]) -> list[LintFinding]:
    backlinks: dict[str, set[str]] = {}
    for p, parsed in pages:
        if parsed is None:
            continue
        rel = _rel(vault, p)
        for link in extract_wikilinks(parsed.body):
            backlinks.setdefault(link.target, set()).add(rel)
    out: list[LintFinding] = []
    for p, parsed in pages:
        if parsed is None:
            continue
        if parsed.frontmatter.type == "source":
            continue  # sources are recordings, never orphans
        slug = p.stem
        if backlinks.get(slug):
            continue
        rel = _rel(vault, p)
        msg = "page has no incoming wikilinks (orphan)"
        out.append(
            LintFinding(
                id=_finding_id("orphan_pages", rel, msg),
                rule_id="orphan_pages",
                severity=LintSeverity.WARNING,
                message=msg,
                page_path=rel,
                fixable=False,
                fix_kind=None,
                metadata={},
            )
        )
    return out


# ---------------------------------------------------------------- stale_pages


def stale_pages(vault: Path, pages: list[PageEntry]) -> list[LintFinding]:
    today = datetime.now(UTC).date()
    out: list[LintFinding] = []
    for p, parsed in pages:
        if parsed is None:
            continue
        fm = parsed.frontmatter
        if fm.status == "verified":
            continue
        if (today - fm.updated).days < STALE_DAYS:
            continue
        if fm.confidence >= 0.5:
            continue
        rel = _rel(vault, p)
        msg = (
            f"page is stale: updated {fm.updated.isoformat()}, "
            f"confidence {fm.confidence:.2f}"
        )
        out.append(
            LintFinding(
                id=_finding_id("stale_pages", rel, msg),
                rule_id="stale_pages",
                severity=LintSeverity.INFO,
                message=msg,
                page_path=rel,
                fixable=False,
                fix_kind=None,
                metadata={
                    "updated": fm.updated.isoformat(),
                    "confidence": fm.confidence,
                    "status": fm.status,
                },
            )
        )
    return out


# ---------------------------------------------------------------- duplicate_titles


def duplicate_titles(vault: Path, pages: list[PageEntry]) -> list[LintFinding]:
    by_title: dict[str, list[Path]] = {}
    for p, parsed in pages:
        if parsed is None:
            continue
        title_norm = parsed.frontmatter.title.strip().lower()
        by_title.setdefault(title_norm, []).append(p)
    out: list[LintFinding] = []
    for title, paths in by_title.items():
        if len(paths) < 2:
            continue
        all_rels = [_rel(vault, q) for q in paths]
        for i, _p in enumerate(paths):
            rel = all_rels[i]
            others = [r for j, r in enumerate(all_rels) if j != i]
            msg = f"duplicate title '{title}' shared with {len(others)} other page(s)"
            out.append(
                LintFinding(
                    id=_finding_id("duplicate_titles", rel, msg),
                    rule_id="duplicate_titles",
                    severity=LintSeverity.WARNING,
                    message=msg,
                    page_path=rel,
                    fixable=False,
                    fix_kind=None,
                    metadata={"title": title, "other_pages": others},
                )
            )
    return out


# ---------------------------------------------------------------- provenance


def provenance_inferred_high(vault: Path, pages: list[PageEntry]) -> list[LintFinding]:
    out: list[LintFinding] = []
    for p, parsed in pages:
        if parsed is None or parsed.frontmatter.provenance is None:
            continue
        pct = parsed.frontmatter.provenance.inferred_pct
        if pct < INFERRED_PCT_THRESHOLD:
            continue
        rel = _rel(vault, p)
        msg = f"provenance inferred_pct={pct} (threshold {INFERRED_PCT_THRESHOLD}); review accuracy"
        out.append(
            LintFinding(
                id=_finding_id("provenance_inferred_high", rel, msg),
                rule_id="provenance_inferred_high",
                severity=LintSeverity.INFO,
                message=msg,
                page_path=rel,
                fixable=False,
                fix_kind=None,
                metadata={"inferred_pct": pct},
            )
        )
    return out


def provenance_ambiguous_high(vault: Path, pages: list[PageEntry]) -> list[LintFinding]:
    out: list[LintFinding] = []
    for p, parsed in pages:
        if parsed is None or parsed.frontmatter.provenance is None:
            continue
        pct = parsed.frontmatter.provenance.ambiguous_pct
        if pct <= AMBIGUOUS_PCT_THRESHOLD:
            continue
        rel = _rel(vault, p)
        msg = (
            f"provenance ambiguous_pct={pct} "
            f"(threshold >{AMBIGUOUS_PCT_THRESHOLD}); review wording"
        )
        out.append(
            LintFinding(
                id=_finding_id("provenance_ambiguous_high", rel, msg),
                rule_id="provenance_ambiguous_high",
                severity=LintSeverity.INFO,
                message=msg,
                page_path=rel,
                fixable=False,
                fix_kind=None,
                metadata={"ambiguous_pct": pct},
            )
        )
    return out


# ---------------------------------------------------------------- trailing_ws

_TRAILING_WS_RE = re.compile(r"[ \t]+$")


def trailing_whitespace(vault: Path, pages: list[PageEntry]) -> list[LintFinding]:
    out: list[LintFinding] = []
    for p, parsed in pages:
        if parsed is None:
            continue
        offending: list[int] = []
        for i, line in enumerate(parsed.body.splitlines(), start=1):
            if _TRAILING_WS_RE.search(line):
                offending.append(i)
        if not offending:
            continue
        rel = _rel(vault, p)
        msg = f"trailing whitespace on lines {offending}"
        out.append(
            LintFinding(
                id=_finding_id("trailing_whitespace", rel, msg),
                rule_id="trailing_whitespace",
                severity=LintSeverity.INFO,
                message=msg,
                page_path=rel,
                fixable=True,
                fix_kind=LintFixKind.STRIP_TRAILING_WS,
                metadata={"lines": offending},
            )
        )
    return out


# ---------------------------------------------------------------- registry

RULE_REGISTRY: dict[str, RuleFn] = {
    "page_parse_failed": page_parse_failed,
    "wikilinks_broken": wikilinks_broken,
    "orphan_pages": orphan_pages,
    "stale_pages": stale_pages,
    "duplicate_titles": duplicate_titles,
    "provenance_inferred_high": provenance_inferred_high,
    "provenance_ambiguous_high": provenance_ambiguous_high,
    "trailing_whitespace": trailing_whitespace,
}
