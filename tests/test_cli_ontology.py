from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.cli import build_parser, main
from claude_mnemos.state.ontology import (
    Suggestion,
    SuggestionFrontmatter,
    SuggestionStore,
)


def _write_page(vault: Path, rel: str, body: str = "") -> None:
    fm = "---\ntitle: T\ntype: entity\n---\n\n"
    (vault / rel).parent.mkdir(parents=True, exist_ok=True)
    (vault / rel).write_text(fm + body, encoding="utf-8")


def _suggestion(sid: str = "ont-2026-04-26-aaaaaa") -> Suggestion:
    return Suggestion(
        frontmatter=SuggestionFrontmatter(
            id=sid,
            created=datetime(2026, 4, 26, tzinfo=UTC),
            operation="merge_entities",
            affected_pages=["wiki/entities/foo.md", "wiki/entities/bar.md"],
            proposed_target="wiki/entities/foobar.md",
        ),
        body="reason",
    )


# ─── parser ─────────────────────────────────────────────────────────────────


def test_parser_ontology_list(tmp_path: Path):
    args = build_parser().parse_args(["ontology", "list", "--vault", str(tmp_path)])
    assert args.command == "ontology"
    assert args.ontology_cmd == "list"
    assert args.all is False


def test_parser_ontology_list_all(tmp_path: Path):
    args = build_parser().parse_args(
        ["ontology", "list", "--all", "--vault", str(tmp_path)]
    )
    assert args.all is True


def test_parser_ontology_approve(tmp_path: Path):
    args = build_parser().parse_args(
        ["ontology", "approve", "ont-x", "--vault", str(tmp_path)]
    )
    assert args.ontology_cmd == "approve"
    assert args.suggestion_id == "ont-x"


def test_parser_ontology_reject(tmp_path: Path):
    args = build_parser().parse_args(
        ["ontology", "reject", "ont-x", "--vault", str(tmp_path)]
    )
    assert args.ontology_cmd == "reject"


def test_parser_ontology_defer(tmp_path: Path):
    args = build_parser().parse_args(
        ["ontology", "defer", "ont-x", "--vault", str(tmp_path)]
    )
    assert args.ontology_cmd == "defer"


def test_parser_ontology_propose_merge_requires_target(tmp_path: Path):
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["ontology", "propose", "merge", "--source", "a", "--source", "b"]
        )


def test_parser_ontology_propose_merge_full(tmp_path: Path):
    args = build_parser().parse_args(
        [
            "ontology",
            "propose",
            "merge",
            "--source", "wiki/entities/a.md",
            "--source", "wiki/entities/b.md",
            "--target", "wiki/entities/c.md",
            "--reason", "test",
            "--confidence", "0.9",
            "--vault", str(tmp_path),
        ]
    )
    assert args.propose_op == "merge"
    assert args.source == ["wiki/entities/a.md", "wiki/entities/b.md"]
    assert args.target == "wiki/entities/c.md"
    assert args.reason == "test"
    assert args.confidence == 0.9


def test_parser_ontology_propose_rename(tmp_path: Path):
    args = build_parser().parse_args(
        [
            "ontology", "propose", "rename",
            "--source", "wiki/entities/old.md",
            "--target", "wiki/entities/new.md",
            "--vault", str(tmp_path),
        ]
    )
    assert args.propose_op == "rename"
    assert args.source == "wiki/entities/old.md"


def test_parser_ontology_propose_delete(tmp_path: Path):
    args = build_parser().parse_args(
        [
            "ontology", "propose", "delete",
            "--source", "wiki/entities/x.md",
            "--vault", str(tmp_path),
        ]
    )
    assert args.propose_op == "delete"


# ─── handlers ──────────────────────────────────────────────────────────────


def test_list_empty(tmp_path: Path, capsys):
    rc = main(["ontology", "list", "--vault", str(tmp_path)])
    assert rc == 0
    assert "no suggestions" in capsys.readouterr().out


def test_list_with_pending(tmp_path: Path, capsys):
    store = SuggestionStore(tmp_path)
    store.create(_suggestion("ont-2026-04-26-aaaaaa"))
    rc = main(["ontology", "list", "--vault", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ont-2026-04-26-aaaaaa" in out
    assert "merge_entities" in out


def test_propose_merge_creates_suggestion(tmp_path: Path, capsys):
    _write_page(tmp_path, "wiki/entities/foo.md")
    _write_page(tmp_path, "wiki/entities/bar.md")
    rc = main(
        [
            "ontology", "propose", "merge",
            "--source", "wiki/entities/foo.md",
            "--source", "wiki/entities/bar.md",
            "--target", "wiki/entities/foobar.md",
            "--reason", "test",
            "--vault", str(tmp_path),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "created:" in out
    store = SuggestionStore(tmp_path)
    items = store.list()
    assert len(items) == 1


def test_propose_merge_source_missing(tmp_path: Path, capsys):
    rc = main(
        [
            "ontology", "propose", "merge",
            "--source", "wiki/entities/missing1.md",
            "--source", "wiki/entities/missing2.md",
            "--target", "wiki/entities/x.md",
            "--vault", str(tmp_path),
        ]
    )
    assert rc == 81
    err = capsys.readouterr().err
    assert "missing" in err


def test_propose_merge_target_exists(tmp_path: Path, capsys):
    _write_page(tmp_path, "wiki/entities/foo.md")
    _write_page(tmp_path, "wiki/entities/bar.md")
    _write_page(tmp_path, "wiki/entities/exists.md")
    rc = main(
        [
            "ontology", "propose", "merge",
            "--source", "wiki/entities/foo.md",
            "--source", "wiki/entities/bar.md",
            "--target", "wiki/entities/exists.md",
            "--vault", str(tmp_path),
        ]
    )
    assert rc == 81


def test_approve_unknown_id(tmp_path: Path, capsys):
    rc = main(["ontology", "approve", "ont-2026-04-26-zzzzzz", "--vault", str(tmp_path)])
    assert rc == 81


def test_approve_happy(tmp_path: Path, capsys):
    _write_page(tmp_path, "wiki/entities/foo.md", "A")
    _write_page(tmp_path, "wiki/entities/bar.md", "B")
    main(
        [
            "ontology", "propose", "merge",
            "--source", "wiki/entities/foo.md",
            "--source", "wiki/entities/bar.md",
            "--target", "wiki/entities/foobar.md",
            "--vault", str(tmp_path),
        ]
    )
    capsys.readouterr()
    store = SuggestionStore(tmp_path)
    sid = store.list()[0].frontmatter.id
    rc = main(["ontology", "approve", sid, "--vault", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "wiki/entities/foobar.md").exists()


def test_reject_happy(tmp_path: Path, capsys):
    store = SuggestionStore(tmp_path)
    store.create(_suggestion("ont-2026-04-26-aaaaaa"))
    rc = main(["ontology", "reject", "ont-2026-04-26-aaaaaa", "--vault", str(tmp_path)])
    assert rc == 0
    reloaded = store.get("ont-2026-04-26-aaaaaa")
    assert reloaded is not None
    assert reloaded.frontmatter.status == "rejected"


def test_reject_unknown(tmp_path: Path, capsys):
    rc = main(["ontology", "reject", "ont-2026-04-26-zzzzzz", "--vault", str(tmp_path)])
    assert rc == 81


def test_defer_happy(tmp_path: Path, capsys):
    store = SuggestionStore(tmp_path)
    store.create(_suggestion("ont-2026-04-26-aaaaaa"))
    rc = main(["ontology", "defer", "ont-2026-04-26-aaaaaa", "--vault", str(tmp_path)])
    assert rc == 0
    reloaded = store.get("ont-2026-04-26-aaaaaa")
    assert reloaded is not None
    assert reloaded.frontmatter.status == "deferred"
