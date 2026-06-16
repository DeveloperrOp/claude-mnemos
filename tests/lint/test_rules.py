import json
from datetime import date
from pathlib import Path

import pytest

from claude_mnemos.core.page_io import ParsedPage, read_page
from claude_mnemos.lint.models import LintFixKind, LintSeverity
from claude_mnemos.lint.rules import RULE_REGISTRY, _normalize_link_target


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


def test_wikilinks_path_form_target_resolves(tmp_path: Path):
    # Obsidian resolves [[sources/<stem>]] to wiki/sources/<stem>.md.
    _seed(
        tmp_path,
        "wiki/entities/foo.md",
        body="See [[sources/2026-05-02-ce160185]]\n",
    )
    _seed(
        tmp_path,
        "wiki/sources/2026-05-02-ce160185.md",
        fm_overrides={"type": "source"},
        body="recording\n",
    )
    findings = RULE_REGISTRY["wikilinks_broken"](tmp_path, _parse_all(tmp_path))
    assert findings == []


def test_wikilinks_raw_chats_backlink_resolves(tmp_path: Path):
    # A bare [[<uuid>]] backlink resolves to raw/chats/<uuid>.md anywhere.
    uuid = "00811ba3-b79f-417e-9ebe-6d518e91e481"
    _seed(tmp_path, "wiki/sources/src.md", body=f"[[{uuid}|Open transcript]]\n")
    raw = tmp_path / "raw" / "chats" / f"{uuid}.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("transcript\n", encoding="utf-8")
    findings = RULE_REGISTRY["wikilinks_broken"](tmp_path, _parse_all(tmp_path))
    assert findings == []


def test_wikilinks_dot_md_suffix_resolves(tmp_path: Path):
    _seed(tmp_path, "wiki/entities/foo.md", body="See [[bar.md]]\n")
    _seed(tmp_path, "wiki/entities/bar.md", body="ok\n")
    findings = RULE_REGISTRY["wikilinks_broken"](tmp_path, _parse_all(tmp_path))
    assert findings == []


def test_wikilinks_missing_basename_still_broken(tmp_path: Path):
    # No file by this basename anywhere → genuinely broken, not fixable.
    _seed(
        tmp_path,
        "wiki/entities/foo.md",
        body="See [[POST /api/signup route (storefront)]]\n",
    )
    findings = RULE_REGISTRY["wikilinks_broken"](tmp_path, _parse_all(tmp_path))
    broken = [
        f for f in findings if f.metadata.get("target") == "POST /api/signup route (storefront)"
    ]
    assert len(broken) == 1
    assert broken[0].fixable is False
    assert broken[0].fix_kind is None


def test_wikilinks_path_form_missing_still_broken(tmp_path: Path):
    # Path-form target whose basename has no file anywhere → still broken.
    _seed(tmp_path, "wiki/entities/foo.md", body="See [[sources/does-not-exist]]\n")
    findings = RULE_REGISTRY["wikilinks_broken"](tmp_path, _parse_all(tmp_path))
    broken = [f for f in findings if f.metadata.get("target") == "sources/does-not-exist"]
    assert len(broken) == 1
    assert broken[0].fixable is False
    # Original target (what the user wrote) is preserved in metadata + message.
    assert "[[sources/does-not-exist]]" in broken[0].message


def test_wikilinks_heading_anchor_to_existing_page_resolves(tmp_path: Path):
    # [[page#heading]] points at an existing page.md → not broken (the anchor is
    # stripped for resolution, matching Obsidian).
    _seed(tmp_path, "wiki/entities/foo.md", body="See [[bar#Section Two]]\n")
    _seed(tmp_path, "wiki/entities/bar.md", body="ok\n")
    findings = RULE_REGISTRY["wikilinks_broken"](tmp_path, _parse_all(tmp_path))
    assert findings == []


def test_wikilinks_pure_anchor_is_not_broken(tmp_path: Path):
    # A same-page anchor [[#heading]] has no page target → never broken.
    _seed(tmp_path, "wiki/entities/foo.md", body="Jump to [[#Summary]]\n")
    findings = RULE_REGISTRY["wikilinks_broken"](tmp_path, _parse_all(tmp_path))
    assert findings == []


def test_wikilinks_heading_anchor_broken_is_never_typo_fixable(tmp_path: Path):
    # A heading-anchored link to a NON-existing page is flagged broken but must
    # NEVER be offered as FIX_WIKILINK_TYPO: the autofix rewrites [[target]] ->
    # [[candidate]] and would silently delete the #anchor (data loss). Here the
    # base "ghos" is edit-distance 1 from existing "ghost" — a unique typo
    # candidate that the '#' guard must suppress.
    _seed(tmp_path, "wiki/entities/foo.md", body="See [[ghos#Section]]\n")
    _seed(tmp_path, "wiki/entities/ghost.md", body="ok\n")
    findings = RULE_REGISTRY["wikilinks_broken"](tmp_path, _parse_all(tmp_path))
    broken = [f for f in findings if f.metadata.get("target") == "ghos#Section"]
    assert len(broken) == 1
    assert broken[0].fixable is False
    assert broken[0].fix_kind is None


# --- _normalize_link_target ---


@pytest.mark.parametrize(
    "target, expected",
    [
        ("sources/2026-05-02-x", "2026-05-02-x"),
        ("x.md", "x"),
        ("x", "x"),
        ("x.MD", "x"),
        ("a/b/c", "c"),
        ("wiki\\entities\\foo", "foo"),
        ("raw/chats/uuid.md", "uuid"),
        ("page#Section", "page"),
        ("dir/page#H", "page"),
        ("#anchor-only", ""),
        ("", ""),
    ],
)
def test_normalize_link_target(target: str, expected: str):
    assert _normalize_link_target(target) == expected


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


# --- manifest_drift ---


def _write_manifest(vault: Path, records: dict) -> None:
    (vault / ".manifest.json").write_text(
        json.dumps({"version": 1, "ingested": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_manifest_drift_flags_missing_raw(tmp_path: Path):
    _write_manifest(tmp_path, {
        "sha1": {
            "session_id": "s1", "ingested_at": "2026-04-26T00:00:00Z",
            "raw_path": "raw/chats/gone.md", "source_path": None,
            "created_pages": ["raw/chats/gone.md"], "skipped_collisions": [],
            "model": None, "input_tokens": None, "output_tokens": None,
        }
    })
    findings = RULE_REGISTRY["manifest_drift"](tmp_path, _parse_all(tmp_path))
    missing = [f for f in findings if f.metadata.get("missing") == "raw/chats/gone.md"]
    assert len(missing) == 1
    assert missing[0].severity == LintSeverity.WARNING
    assert missing[0].fixable is False


def test_manifest_drift_ignores_missing_wiki_page(tmp_path: Path):
    # Raw present, but a knowledge page recorded in the manifest was deleted /
    # merged / trashed by curation (which doesn't rewrite the manifest). That is
    # NOT drift — the rule flags only a missing RAW transcript, so it stays
    # silent here. Prevents false-ERROR spam on any well-tended vault.
    raw = tmp_path / "raw" / "chats" / "here.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("x", encoding="utf-8")
    _write_manifest(tmp_path, {
        "sha1": {
            "session_id": "s1", "ingested_at": "2026-04-26T00:00:00Z",
            "raw_path": "raw/chats/here.md",
            "source_path": "wiki/sources/2026-04-26-s1.md",  # deleted, not on disk
            "created_pages": ["wiki/entities/gone.md", "raw/chats/here.md"],
            "skipped_collisions": [],
            "model": None, "input_tokens": None, "output_tokens": None,
        }
    })
    findings = RULE_REGISTRY["manifest_drift"](tmp_path, _parse_all(tmp_path))
    assert findings == []


def test_manifest_drift_anchors_to_existing_source_page(tmp_path: Path):
    # Raw is GONE but the orphaned source page survives — the finding links to
    # that page (actionable) and is a WARNING, not an ERROR.
    src = tmp_path / "wiki" / "sources" / "2026-05-02-s1.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("orphaned source\n", encoding="utf-8")
    _write_manifest(tmp_path, {
        "sha1": {
            "session_id": "s1", "ingested_at": "2026-04-26T00:00:00Z",
            "raw_path": "raw/chats/gone.md",
            "source_path": "wiki/sources/2026-05-02-s1.md",
            "created_pages": ["wiki/sources/2026-05-02-s1.md"],
            "skipped_collisions": [],
            "model": None, "input_tokens": None, "output_tokens": None,
        }
    })
    findings = RULE_REGISTRY["manifest_drift"](tmp_path, _parse_all(tmp_path))
    assert len(findings) == 1
    assert findings[0].severity == LintSeverity.WARNING
    assert findings[0].page_path == "wiki/sources/2026-05-02-s1.md"
    assert findings[0].metadata.get("missing") == "raw/chats/gone.md"


def test_manifest_drift_clean_when_files_present(tmp_path: Path):
    raw = tmp_path / "raw" / "chats" / "here.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("x", encoding="utf-8")
    _write_manifest(tmp_path, {
        "sha1": {
            "session_id": "s1", "ingested_at": "2026-04-26T00:00:00Z",
            "raw_path": "raw/chats/here.md", "source_path": None,
            "created_pages": ["raw/chats/here.md"], "skipped_collisions": [],
            "model": None, "input_tokens": None, "output_tokens": None,
        }
    })
    findings = RULE_REGISTRY["manifest_drift"](tmp_path, _parse_all(tmp_path))
    assert findings == []


def test_manifest_drift_no_manifest_is_noop(tmp_path: Path):
    assert RULE_REGISTRY["manifest_drift"](tmp_path, _parse_all(tmp_path)) == []
