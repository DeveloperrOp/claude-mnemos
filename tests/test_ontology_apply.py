from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.core.ontology_apply import (
    OntologyError,
    apply_delete_page,
    apply_merge_entities,
    apply_rename_entity,
    apply_suggestion,
)
from claude_mnemos.state.activity import ActivityLog
from claude_mnemos.state.ontology import Suggestion, SuggestionFrontmatter, SuggestionStore


def _write_page(
    vault: Path,
    rel: str,
    *,
    title: str,
    page_type: str = "entity",
    body: str = "",
    flavor: list[str] | None = None,
) -> None:
    fm_lines = ["---", f"title: {title}", f"type: {page_type}"]
    if flavor:
        fm_lines.append(f"flavor: [{', '.join(flavor)}]")
    fm_lines.append("---")
    text = "\n".join(fm_lines) + "\n\n" + body
    (vault / rel).parent.mkdir(parents=True, exist_ok=True)
    (vault / rel).write_text(text, encoding="utf-8")


def _make_suggestion(
    *,
    operation: str,
    affected: list[str],
    target: str | None = None,
    sid: str = "ont-2026-04-26-aaaaaa",
) -> Suggestion:
    return Suggestion(
        frontmatter=SuggestionFrontmatter(
            id=sid,
            created=datetime(2026, 4, 26, tzinfo=UTC),
            operation=operation,  # type: ignore[arg-type]
            affected_pages=affected,
            proposed_target=target,
        ),
        body="reason",
    )


# ─── apply_merge_entities ──────────────────────────────────────────────────


def test_merge_happy_path(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_page(
        vault, "wiki/entities/foo.md", title="Foo", body="Foo body.\n",
        flavor=["pattern"],
    )
    _write_page(
        vault, "wiki/entities/bar.md", title="Bar", body="Bar body.\n",
        flavor=["lesson"],
    )
    _write_page(
        vault, "wiki/concepts/ref.md", title="Ref",
        body="Links to [[foo]] and [[bar]] here.\n",
    )

    suggestion = _make_suggestion(
        operation="merge_entities",
        affected=["wiki/entities/foo.md", "wiki/entities/bar.md"],
        target="wiki/entities/concurrency.md",
    )

    result = apply_merge_entities(vault, suggestion)
    assert result.success is True
    assert result.operation == "merge_entities"
    assert result.target_path == "wiki/entities/concurrency.md"
    assert result.wikilinks_rewritten == 1

    target = (vault / "wiki/entities/concurrency.md").read_text()
    assert "Foo body" in target
    assert "Bar body" in target
    assert not (vault / "wiki/entities/foo.md").exists()
    assert not (vault / "wiki/entities/bar.md").exists()

    ref = (vault / "wiki/concepts/ref.md").read_text()
    assert "[[concurrency]]" in ref
    assert "[[foo]]" not in ref
    assert "[[bar]]" not in ref

    # Activity entry written
    log = ActivityLog.load(vault)
    assert len(log.entries) == 1
    entry = log.entries[0]
    assert entry.operation_type == "ontology_apply"
    assert entry.metadata["suggestion_id"] == "ont-2026-04-26-aaaaaa"
    assert entry.metadata["operation"] == "merge_entities"
    assert entry.metadata["wikilinks_rewritten"] == 1


def test_merge_target_exists_raises(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_page(vault, "wiki/entities/foo.md", title="Foo")
    _write_page(vault, "wiki/entities/bar.md", title="Bar")
    _write_page(vault, "wiki/entities/target.md", title="Target")

    suggestion = _make_suggestion(
        operation="merge_entities",
        affected=["wiki/entities/foo.md", "wiki/entities/bar.md"],
        target="wiki/entities/target.md",
    )
    with pytest.raises(OntologyError, match="already exists"):
        apply_merge_entities(vault, suggestion)
    # Vault unchanged
    assert (vault / "wiki/entities/foo.md").exists()


def test_merge_source_missing_raises(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_page(vault, "wiki/entities/foo.md", title="Foo")

    suggestion = _make_suggestion(
        operation="merge_entities",
        affected=["wiki/entities/foo.md", "wiki/entities/missing.md"],
        target="wiki/entities/x.md",
    )
    with pytest.raises(OntologyError, match="missing"):
        apply_merge_entities(vault, suggestion)


def test_merge_requires_target(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_page(vault, "wiki/entities/foo.md", title="Foo")
    _write_page(vault, "wiki/entities/bar.md", title="Bar")
    suggestion = _make_suggestion(
        operation="merge_entities",
        affected=["wiki/entities/foo.md", "wiki/entities/bar.md"],
        target=None,
    )
    with pytest.raises(OntologyError, match="proposed_target"):
        apply_merge_entities(vault, suggestion)


def test_merge_requires_two_sources(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_page(vault, "wiki/entities/foo.md", title="Foo")
    suggestion = _make_suggestion(
        operation="merge_entities",
        affected=["wiki/entities/foo.md"],
        target="wiki/entities/x.md",
    )
    with pytest.raises(OntologyError, match="at least 2"):
        apply_merge_entities(vault, suggestion)


def test_merge_frontmatter_unions_flavors(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_page(
        vault, "wiki/entities/a.md", title="A", flavor=["pattern", "lesson"],
        body="A.",
    )
    _write_page(
        vault, "wiki/entities/b.md", title="B", flavor=["lesson", "decision"],
        body="B.",
    )
    suggestion = _make_suggestion(
        operation="merge_entities",
        affected=["wiki/entities/a.md", "wiki/entities/b.md"],
        target="wiki/entities/c.md",
    )
    apply_merge_entities(vault, suggestion)
    text = (vault / "wiki/entities/c.md").read_text()
    # All 3 flavors should appear
    assert "pattern" in text
    assert "lesson" in text
    assert "decision" in text


# ─── apply_rename_entity ───────────────────────────────────────────────────


def test_rename_happy_path(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_page(vault, "wiki/entities/old.md", title="Old", body="content")
    _write_page(vault, "wiki/concepts/ref.md", title="Ref", body="see [[old]]")

    suggestion = _make_suggestion(
        operation="rename_entity",
        affected=["wiki/entities/old.md"],
        target="wiki/entities/new.md",
    )
    result = apply_rename_entity(vault, suggestion)
    assert result.success is True
    assert result.target_path == "wiki/entities/new.md"
    assert not (vault / "wiki/entities/old.md").exists()
    assert (vault / "wiki/entities/new.md").read_text().endswith("content")
    assert "[[new]]" in (vault / "wiki/concepts/ref.md").read_text()


def test_rename_target_exists_raises(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_page(vault, "wiki/entities/old.md", title="Old")
    _write_page(vault, "wiki/entities/new.md", title="New")
    suggestion = _make_suggestion(
        operation="rename_entity",
        affected=["wiki/entities/old.md"],
        target="wiki/entities/new.md",
    )
    with pytest.raises(OntologyError, match="already exists"):
        apply_rename_entity(vault, suggestion)


def test_rename_source_missing_raises(tmp_path: Path):
    vault = tmp_path / "vault"
    suggestion = _make_suggestion(
        operation="rename_entity",
        affected=["wiki/entities/missing.md"],
        target="wiki/entities/x.md",
    )
    (vault / "wiki/entities").mkdir(parents=True)
    with pytest.raises(OntologyError, match="missing"):
        apply_rename_entity(vault, suggestion)


# ─── apply_delete_page ─────────────────────────────────────────────────────


def test_delete_happy_path(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_page(vault, "wiki/entities/orphan.md", title="Orphan", body="x")
    _write_page(vault, "wiki/concepts/ref.md", title="Ref", body="[[orphan]]")

    suggestion = _make_suggestion(
        operation="delete_page",
        affected=["wiki/entities/orphan.md"],
    )
    result = apply_delete_page(vault, suggestion)
    assert result.success is True
    assert not (vault / "wiki/entities/orphan.md").exists()
    # Wikilinks left as-is — Lint will catch (Plan #10)
    assert "[[orphan]]" in (vault / "wiki/concepts/ref.md").read_text()
    # Trash contains the deleted page
    trash_root = vault / ".trash"
    deleted_dirs = [
        p for p in trash_root.iterdir() if p.name.startswith("deleted-orphan-")
    ]
    assert len(deleted_dirs) == 1


def test_delete_source_missing_raises(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "wiki/entities").mkdir(parents=True)
    suggestion = _make_suggestion(
        operation="delete_page", affected=["wiki/entities/missing.md"]
    )
    with pytest.raises(OntologyError, match="missing"):
        apply_delete_page(vault, suggestion)


# ─── apply_suggestion (dispatcher + lifecycle) ─────────────────────────────


def test_apply_suggestion_dispatches_and_archives(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_page(vault, "wiki/entities/foo.md", title="Foo", body="x")
    _write_page(vault, "wiki/entities/bar.md", title="Bar", body="y")

    store = SuggestionStore(vault)
    suggestion = _make_suggestion(
        operation="merge_entities",
        affected=["wiki/entities/foo.md", "wiki/entities/bar.md"],
        target="wiki/entities/foobar.md",
        sid="ont-2026-04-26-bbbbbb",
    )
    store.create(suggestion)

    result = apply_suggestion(vault, "ont-2026-04-26-bbbbbb")
    assert result.success is True

    # Suggestion archived with status=approved
    reloaded = store.get("ont-2026-04-26-bbbbbb")
    assert reloaded is not None
    assert reloaded.frontmatter.status == "approved"
    assert reloaded.frontmatter.applied_op_id == result.activity_id


def test_apply_suggestion_unknown_id(tmp_path: Path):
    (tmp_path / "vault").mkdir()
    with pytest.raises(OntologyError, match="not found"):
        apply_suggestion(tmp_path / "vault", "ont-2026-04-26-zzzzzz")


def test_apply_suggestion_already_approved(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_page(vault, "wiki/entities/foo.md", title="Foo")
    _write_page(vault, "wiki/entities/bar.md", title="Bar")
    store = SuggestionStore(vault)
    suggestion = _make_suggestion(
        operation="merge_entities",
        affected=["wiki/entities/foo.md", "wiki/entities/bar.md"],
        target="wiki/entities/foobar.md",
        sid="ont-2026-04-26-cccccc",
    )
    store.create(suggestion)
    apply_suggestion(vault, "ont-2026-04-26-cccccc")
    with pytest.raises(OntologyError, match="approved"):
        apply_suggestion(vault, "ont-2026-04-26-cccccc")
