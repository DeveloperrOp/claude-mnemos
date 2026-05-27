from datetime import date
from pathlib import Path

from claude_mnemos.core.page_io import ParsedPage, read_page
from claude_mnemos.lint.models import LintFixKind, LintSeverity
from claude_mnemos.lint.rules import RULE_REGISTRY


def _seed(vault: Path, rel: str, fm_overrides: dict | None = None, body: str = "body\n") -> Path:
    fm = {
        "title": "T",
        "type": "entity",
        "status": "draft",
        "confidence": 0.7,
        "flavor": [],
        "sources": [],
        "related": [],
        "created": date(2026, 4, 26).isoformat(),
        "updated": date(2026, 4, 26).isoformat(),
        "agent_written": True,
    }
    if fm_overrides:
        fm.update(fm_overrides)
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v if not isinstance(v, list) else '[]'}")
    lines.append("---")
    lines.append(body.rstrip("\n"))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _parse_all(vault: Path) -> list[tuple[Path, ParsedPage | None]]:
    out = []
    for p in sorted(vault.glob("wiki/**/*.md")):
        try:
            out.append((p, read_page(p)))
        except Exception:
            out.append((p, None))
    return out


# --- wikilinks_broken ---


def test_wikilinks_broken_detected(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/foo.md", body="See [[nonexistent-thing]]\n")
    _seed(tmp_path, "wiki/entities/bar.md", body="ok\n")
    findings = RULE_REGISTRY["wikilinks_broken"](tmp_path, _parse_all(tmp_path))
    assert any(f.metadata.get("target") == "nonexistent-thing" for f in findings)


def test_wikilinks_broken_with_typo_candidate(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/foo.md", body="See [[file-lock-bub]]\n")
    _seed(tmp_path, "wiki/entities/file-lock-bug.md", body="ok\n")
    findings = RULE_REGISTRY["wikilinks_broken"](tmp_path, _parse_all(tmp_path))
    f = [f for f in findings if f.metadata.get("target") == "file-lock-bub"][0]
    assert f.fixable is True
    assert f.fix_kind == LintFixKind.FIX_WIKILINK_TYPO
    assert f.metadata.get("candidate") == "file-lock-bug"


def test_wikilinks_existing_no_finding(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/foo.md", body="See [[bar]]\n")
    _seed(tmp_path, "wiki/entities/bar.md", body="ok\n")
    findings = RULE_REGISTRY["wikilinks_broken"](tmp_path, _parse_all(tmp_path))
    assert findings == []


# --- orphan_pages ---


def test_orphan_pages_isolated_entity(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/lonely.md", body="no links\n")
    _seed(tmp_path, "wiki/entities/other.md", body="also no links\n")
    findings = RULE_REGISTRY["orphan_pages"](tmp_path, _parse_all(tmp_path))
    assert {f.page_path for f in findings} == {
        "wiki/entities/lonely.md",
        "wiki/entities/other.md",
    }


def test_orphan_pages_with_backlink(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/foo.md", body="See [[bar]]\n")
    _seed(tmp_path, "wiki/entities/bar.md", body="referenced\n")
    findings = RULE_REGISTRY["orphan_pages"](tmp_path, _parse_all(tmp_path))
    paths = {f.page_path for f in findings}
    assert "wiki/entities/bar.md" not in paths


def test_orphan_pages_skips_sources(tmp_path: Path):
    _seed(tmp_path, "wiki/sources/2026-04-26-abc.md", fm_overrides={"type": "source"})
    findings = RULE_REGISTRY["orphan_pages"](tmp_path, _parse_all(tmp_path))
    assert findings == []


# --- stale_pages ---


def test_stale_pages_old_low_confidence(tmp_path: Path):
    _seed(
        tmp_path,
        "wiki/entities/old.md",
        fm_overrides={
            "updated": date(2025, 1, 1).isoformat(),
            "confidence": 0.3,
            "status": "draft",
        },
    )
    findings = RULE_REGISTRY["stale_pages"](tmp_path, _parse_all(tmp_path))
    assert len(findings) == 1
    assert findings[0].severity == LintSeverity.INFO


def test_stale_pages_verified_skipped(tmp_path: Path):
    _seed(
        tmp_path,
        "wiki/entities/verified.md",
        fm_overrides={
            "updated": date(2025, 1, 1).isoformat(),
            "confidence": 0.3,
            "status": "verified",
        },
    )
    findings = RULE_REGISTRY["stale_pages"](tmp_path, _parse_all(tmp_path))
    assert findings == []


# --- duplicate_titles ---


def test_duplicate_titles_detects_two(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/a.md", fm_overrides={"title": "Race Condition"})
    _seed(tmp_path, "wiki/entities/b.md", fm_overrides={"title": "race condition"})
    findings = RULE_REGISTRY["duplicate_titles"](tmp_path, _parse_all(tmp_path))
    assert len(findings) == 2
    assert all(f.severity == LintSeverity.WARNING for f in findings)


# --- provenance_inferred_high / provenance_ambiguous_high ---


def test_provenance_inferred_high(tmp_path: Path):
    _seed(
        tmp_path,
        "wiki/entities/p.md",
        fm_overrides={
            "provenance": "{extracted_pct: 30, inferred_pct: 60, ambiguous_pct: 10}",
        },
    )
    findings = RULE_REGISTRY["provenance_inferred_high"](tmp_path, _parse_all(tmp_path))
    assert len(findings) == 1
    assert findings[0].metadata["inferred_pct"] == 60


def test_provenance_ambiguous_high(tmp_path: Path):
    _seed(
        tmp_path,
        "wiki/entities/p.md",
        fm_overrides={
            "provenance": "{extracted_pct: 50, inferred_pct: 15, ambiguous_pct: 35}",
        },
    )
    findings = RULE_REGISTRY["provenance_ambiguous_high"](tmp_path, _parse_all(tmp_path))
    assert len(findings) == 1
    assert findings[0].metadata["ambiguous_pct"] == 35


# --- trailing_whitespace ---


def test_trailing_whitespace_in_body(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/ws.md", body="line one  \nline two\n")
    findings = RULE_REGISTRY["trailing_whitespace"](tmp_path, _parse_all(tmp_path))
    assert len(findings) == 1
    assert findings[0].fixable is True
    assert findings[0].fix_kind == LintFixKind.STRIP_TRAILING_WS


def test_trailing_whitespace_clean_no_finding(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/clean.md", body="line one\nline two\n")
    findings = RULE_REGISTRY["trailing_whitespace"](tmp_path, _parse_all(tmp_path))
    assert findings == []


# --- page_parse_failed ---


def test_page_parse_failed_detects_broken_yaml(tmp_path: Path):
    p = tmp_path / "wiki/entities/broken.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not a markdown page\n", encoding="utf-8")
    findings = RULE_REGISTRY["page_parse_failed"](tmp_path, _parse_all(tmp_path))
    assert len(findings) == 1
    assert findings[0].severity == LintSeverity.ERROR
