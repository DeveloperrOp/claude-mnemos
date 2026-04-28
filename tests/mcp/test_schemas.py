"""Sanity that JSON Schema dicts have the shape we expect (required keys, types).

Not full JSON Schema validation — we just guard against typos and structural drift.
"""

from claude_mnemos.mcp import schemas


def _is_valid_object_schema(s):
    assert isinstance(s, dict)
    assert s["type"] == "object"
    assert "properties" in s
    assert s.get("additionalProperties") is False
    return True


def test_list_pages_schema():
    s = schemas.LIST_PAGES
    _is_valid_object_schema(s)
    assert "type" in s["properties"]
    assert s["properties"]["type"]["enum"] == ["entity", "concept", "source"]
    assert s["properties"]["limit"]["maximum"] == 500


def test_read_page_requires_page_ref():
    s = schemas.READ_PAGE
    _is_valid_object_schema(s)
    assert s["required"] == ["page_ref"]
    assert s["properties"]["page_ref"]["type"] == "string"


def test_search_pages_requires_query():
    s = schemas.SEARCH_PAGES
    _is_valid_object_schema(s)
    assert s["required"] == ["query"]


def test_get_status_no_args():
    s = schemas.GET_STATUS
    _is_valid_object_schema(s)
    assert s["properties"] == {}


def test_get_recent_activity_limit():
    s = schemas.GET_RECENT_ACTIVITY
    _is_valid_object_schema(s)
    assert s["properties"]["limit"]["default"] == 10


def test_undo_operation_requires_op_id():
    s = schemas.UNDO_OPERATION
    _is_valid_object_schema(s)
    assert "project" in s["required"]
    assert "op_id" in s["required"]


def test_create_snapshot_requires_project():
    s = schemas.CREATE_SNAPSHOT
    _is_valid_object_schema(s)
    assert "project" in s.get("required", [])
    assert "label" in s["properties"]


def test_restore_snapshot_requires_name_and_project():
    s = schemas.RESTORE_SNAPSHOT
    _is_valid_object_schema(s)
    assert "project" in s["required"]
    assert "name" in s["required"]


def test_delete_snapshot_requires_name_and_project():
    s = schemas.DELETE_SNAPSHOT
    _is_valid_object_schema(s)
    assert "project" in s["required"]
    assert "name" in s["required"]


def test_run_lint_requires_project():
    s = schemas.RUN_LINT
    _is_valid_object_schema(s)
    assert "project" in s.get("required", [])


def test_apply_ontology_suggestion_requires_project():
    s = schemas.APPLY_ONTOLOGY_SUGGESTION
    _is_valid_object_schema(s)
    assert "project" in s["required"]
    assert "suggestion_id" in s["required"]


def test_propose_ontology_change_requires_project():
    s = schemas.PROPOSE_ONTOLOGY_CHANGE
    _is_valid_object_schema(s)
    assert "project" in s["required"]
