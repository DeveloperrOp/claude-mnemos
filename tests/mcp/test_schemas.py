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
    assert s["required"] == ["op_id"]


def test_create_snapshot_label_optional():
    s = schemas.CREATE_SNAPSHOT
    _is_valid_object_schema(s)
    assert "label" in s["properties"]
    assert "required" not in s


def test_restore_snapshot_requires_name():
    s = schemas.RESTORE_SNAPSHOT
    _is_valid_object_schema(s)
    assert s["required"] == ["name"]


def test_delete_snapshot_same_as_restore():
    assert schemas.DELETE_SNAPSHOT == schemas.RESTORE_SNAPSHOT
