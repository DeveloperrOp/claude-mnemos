from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from claude_mnemos.state.ontology import (
    OntologyCorruptError,
    Suggestion,
    SuggestionFrontmatter,
    SuggestionStore,
    generate_suggestion_id,
)


def _fm(
    *,
    id: str = "ont-2026-04-26-abc123",
    operation: str = "merge_entities",
    affected_pages: list[str] | None = None,
    proposed_target: str | None = "wiki/entities/concurrency-issues.md",
    status: str = "pending",
) -> SuggestionFrontmatter:
    return SuggestionFrontmatter(
        id=id,
        created=datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC),
        operation=operation,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        affected_pages=affected_pages
        or ["wiki/entities/file-lock-bug.md", "wiki/entities/race-condition-bug.md"],
        proposed_target=proposed_target,
    )


def _suggestion(**kwargs) -> Suggestion:
    return Suggestion(frontmatter=_fm(**kwargs), body="Reasoning text.\n")


def test_id_pattern_validates():
    SuggestionFrontmatter.model_validate(
        {
            "id": "ont-2026-04-26-abc123",
            "created": "2026-04-26T00:00:00Z",
            "operation": "merge_entities",
            "affected_pages": ["x.md"],
        }
    )
    with pytest.raises(ValidationError):
        SuggestionFrontmatter.model_validate(
            {
                "id": "wrong-format",
                "created": "2026-04-26T00:00:00Z",
                "operation": "merge_entities",
                "affected_pages": ["x.md"],
            }
        )


def test_status_enum_validation():
    with pytest.raises(ValidationError):
        SuggestionFrontmatter.model_validate(
            {
                "id": "ont-2026-04-26-abc123",
                "created": "2026-04-26T00:00:00Z",
                "operation": "merge_entities",
                "status": "weird",
                "affected_pages": ["x.md"],
            }
        )


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        _fm()
        SuggestionFrontmatter(
            id="ont-2026-04-26-abc123",
            created=datetime(2026, 4, 26, tzinfo=UTC),
            operation="merge_entities",
            confidence=1.5,
            affected_pages=["x.md"],
        )
    with pytest.raises(ValidationError):
        SuggestionFrontmatter(
            id="ont-2026-04-26-abc123",
            created=datetime(2026, 4, 26, tzinfo=UTC),
            operation="merge_entities",
            confidence=-0.1,
            affected_pages=["x.md"],
        )


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        SuggestionFrontmatter.model_validate(
            {
                "id": "ont-2026-04-26-abc123",
                "created": "2026-04-26T00:00:00Z",
                "operation": "merge_entities",
                "affected_pages": ["x.md"],
                "weird_field": 1,
            }
        )


def test_affected_pages_min_length():
    with pytest.raises(ValidationError):
        SuggestionFrontmatter(
            id="ont-2026-04-26-abc123",
            created=datetime(2026, 4, 26, tzinfo=UTC),
            operation="merge_entities",
            affected_pages=[],
        )


def test_serialize_roundtrip():
    s = _suggestion()
    text = s.serialize()
    assert text.startswith("---\n")
    parsed = Suggestion.parse(text)
    assert parsed.frontmatter.id == s.frontmatter.id
    assert parsed.frontmatter.operation == s.frontmatter.operation
    assert "Reasoning text." in parsed.body


def test_parse_missing_frontmatter():
    with pytest.raises(OntologyCorruptError):
        Suggestion.parse("no frontmatter here")


def test_parse_unterminated_frontmatter():
    with pytest.raises(OntologyCorruptError):
        Suggestion.parse("---\nid: ont-2026-04-26-abc123\nbody without end")


def test_parse_invalid_yaml():
    with pytest.raises(OntologyCorruptError):
        Suggestion.parse("---\n[unbalanced\n---\nbody")


def test_parse_yaml_not_mapping():
    with pytest.raises(OntologyCorruptError):
        Suggestion.parse("---\n- item1\n- item2\n---\nbody")


def test_parse_schema_mismatch():
    with pytest.raises(OntologyCorruptError):
        Suggestion.parse(
            "---\nid: bad\noperation: merge_entities\naffected_pages: []\n---\nbody"
        )


def test_generate_suggestion_id_pattern():
    sid = generate_suggestion_id(datetime(2026, 4, 26, tzinfo=UTC))
    assert sid.startswith("ont-2026-04-26-")
    assert len(sid) == len("ont-YYYY-MM-DD-XXXXXX")
    SuggestionFrontmatter(
        id=sid,
        created=datetime(2026, 4, 26, tzinfo=UTC),
        operation="merge_entities",
        affected_pages=["x.md"],
    )


def test_store_list_empty(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    assert store.list() == []


def test_store_create_and_list(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    s1 = _suggestion(id="ont-2026-04-26-aaaaaa")
    s2 = _suggestion(id="ont-2026-04-26-bbbbbb")
    store.create(s1)
    store.create(s2)
    items = store.list()
    ids = sorted(s.frontmatter.id for s in items)
    assert ids == ["ont-2026-04-26-aaaaaa", "ont-2026-04-26-bbbbbb"]


def test_store_create_duplicate_raises(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    s = _suggestion()
    store.create(s)
    with pytest.raises(ValueError):
        store.create(s)


def test_store_get_known_and_missing(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    s = _suggestion(id="ont-2026-04-26-cccccc")
    store.create(s)
    got = store.get("ont-2026-04-26-cccccc")
    assert got is not None
    assert got.frontmatter.id == "ont-2026-04-26-cccccc"
    assert store.get("ont-2026-04-26-zzzzzz") is None


def test_store_archive_moves_file(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    s = _suggestion(id="ont-2026-04-26-dddddd")
    src = store.create(s)
    assert src.is_file()
    archived = store.archive_suggestion("ont-2026-04-26-dddddd")
    assert not src.exists()
    assert archived.is_file()
    assert archived.parent.name == "archive"


def test_store_update_status_pending(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    s = _suggestion(id="ont-2026-04-26-eeeeee")
    store.create(s)
    updated = store.update_status(
        "ont-2026-04-26-eeeeee",
        "approved",
        applied_at=datetime(2026, 4, 26, 15, 0, tzinfo=UTC),
        applied_op_id="aaaa-bbbb",
    )
    assert updated.frontmatter.status == "approved"
    assert updated.frontmatter.applied_op_id == "aaaa-bbbb"
    reloaded = store.get("ont-2026-04-26-eeeeee")
    assert reloaded is not None
    assert reloaded.frontmatter.status == "approved"


def test_store_update_status_archived(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    s = _suggestion(id="ont-2026-04-26-ffffff")
    store.create(s)
    store.archive_suggestion("ont-2026-04-26-ffffff")
    updated = store.update_status("ont-2026-04-26-ffffff", "rejected")
    assert updated.frontmatter.status == "rejected"


def test_store_update_status_missing_raises(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    with pytest.raises(ValueError):
        store.update_status("ont-2026-04-26-nope1z", "rejected")


def test_store_list_include_archive(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    s_pending = _suggestion(id="ont-2026-04-26-aaaaaa")
    s_archived = _suggestion(id="ont-2026-04-26-bbbbbb")
    store.create(s_pending)
    store.create(s_archived)
    store.archive_suggestion("ont-2026-04-26-bbbbbb")

    pending_only = store.list()
    assert {s.frontmatter.id for s in pending_only} == {"ont-2026-04-26-aaaaaa"}

    all_items = store.list(include_archive=True)
    assert {s.frontmatter.id for s in all_items} == {
        "ont-2026-04-26-aaaaaa",
        "ont-2026-04-26-bbbbbb",
    }


def test_store_list_skips_corrupt_files(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    s = _suggestion(id="ont-2026-04-26-aaaaaa")
    store.create(s)
    corrupt_path = store.root / "ont-2026-04-26-bbbbbb.md"
    corrupt_path.write_text("not a valid suggestion file", encoding="utf-8")
    items = store.list()
    assert len(items) == 1
    assert items[0].frontmatter.id == "ont-2026-04-26-aaaaaa"


def test_store_get_corrupt_raises(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    store.root.mkdir(parents=True)
    (store.root / "ont-2026-04-26-aaaaaa.md").write_text("garbage", encoding="utf-8")
    with pytest.raises(OntologyCorruptError):
        store.get("ont-2026-04-26-aaaaaa")
