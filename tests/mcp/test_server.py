"""Direct tests for build_server: exercise registered handlers via in-process call.

In MCP SDK 1.12 the low-level Server stores typed handlers in `request_handlers`
keyed by the request type. We fish them out and call them directly — no stdio
required.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from mcp import types

from claude_mnemos.mcp.config import MCPConfig
from claude_mnemos.mcp.server import (
    READ_TOOL_NAMES,
    SERVER_NAME,
    TOOL_DEFS,
    TOOL_NAMES,
    WRITE_TOOL_NAMES,
    build_server,
)
from claude_mnemos.state.activity import ActivityEntry, ActivityLog


def _config(vault: Path, daemon_url: str = "http://daemon") -> MCPConfig:
    return MCPConfig(vault_root=vault, daemon_url=daemon_url)


def test_tool_defs_count_and_names():
    assert len({t.name for t in TOOL_DEFS}) == 14
    expected = {
        "list_pages",
        "read_page",
        "search_pages",
        "get_status",
        "get_recent_activity",
        "undo_operation",
        "create_snapshot",
        "restore_snapshot",
        "delete_snapshot",
        "list_suggestions",
        "apply_ontology_suggestion",
        "propose_ontology_change",
        "get_lint_results",
        "run_lint",
    }
    assert expected == TOOL_NAMES
    assert READ_TOOL_NAMES.isdisjoint(WRITE_TOOL_NAMES)


def test_build_server_returns_named_server(tmp_path: Path):
    server = build_server(_config(tmp_path))
    assert server.name == SERVER_NAME


async def _list_tools(server) -> list[types.Tool]:
    handler = server.request_handlers[types.ListToolsRequest]
    request = types.ListToolsRequest(method="tools/list", params=None)
    result = await handler(request)
    return result.root.tools


async def _call_tool(server, name: str, arguments: dict | None = None):
    handler = server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments or {}),
    )
    result = await handler(request)
    return result.root


async def test_list_tools_via_handler(tmp_path: Path):
    server = build_server(_config(tmp_path))
    tools = await _list_tools(server)
    assert len(tools) == 14
    names = {t.name for t in tools}
    assert names == TOOL_NAMES


async def test_call_unknown_tool_returns_text_error(tmp_path: Path):
    server = build_server(_config(tmp_path))
    result = await _call_tool(server, "no_such_tool", {})
    text = result.content[0].text
    assert "unknown tool" in text


async def test_call_get_status_returns_json_text(tmp_path: Path):
    server = build_server(_config(tmp_path))
    result = await _call_tool(server, "get_status", {})
    text = result.content[0].text
    parsed = json.loads(text)
    assert parsed["vault"] == str(tmp_path)
    assert parsed["wiki_pages"] == 0


async def test_call_list_pages_returns_array(tmp_path: Path):
    (tmp_path / "wiki/entities").mkdir(parents=True)
    (tmp_path / "wiki/entities/foo.md").write_text(
        "---\ntitle: Foo\ntype: entity\n---\nbody",
        encoding="utf-8",
    )
    server = build_server(_config(tmp_path))
    result = await _call_tool(server, "list_pages", {})
    parsed = json.loads(result.content[0].text)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["title"] == "Foo"


async def test_call_read_page_traversal_returns_error(tmp_path: Path):
    server = build_server(_config(tmp_path))
    result = await _call_tool(server, "read_page", {"page_ref": "../etc/passwd"})
    text = result.content[0].text
    assert "PageRefError" in text


async def test_call_get_recent_activity_returns_entries(tmp_path: Path):
    log = ActivityLog()
    log.append(
        ActivityEntry(
            id=uuid4().hex,
            timestamp=datetime(2026, 4, 26, tzinfo=UTC),
            operation_type="ingest_extracted",
            status="success",
            snapshot_path=None,
            can_undo=True,
        )
    )
    log.save(tmp_path)
    server = build_server(_config(tmp_path))
    result = await _call_tool(server, "get_recent_activity", {"limit": 5})
    parsed = json.loads(result.content[0].text)
    assert len(parsed) == 1


async def test_call_write_tool_daemon_unreachable(tmp_path: Path, monkeypatch):
    """undo_operation against an unreachable URL returns helpful error text."""
    server = build_server(_config(tmp_path, daemon_url="http://127.0.0.1:1"))
    # We won't be able to actually connect to port 1 — patch httpx.AsyncClient
    # to raise ConnectError predictably.

    class FakeClient:
        def __init__(self, *_, **__): ...
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return False
        async def request(self, *_args, **_kwargs):
            raise httpx.ConnectError("refused")

    monkeypatch.setattr("claude_mnemos.mcp.server.httpx.AsyncClient", FakeClient)

    result = await _call_tool(server, "undo_operation", {"op_id": "abc"})
    text = result.content[0].text
    assert "daemon not reachable" in text
    assert "mnemos daemon start" in text


async def test_call_write_tool_daemon_4xx(tmp_path: Path, monkeypatch):
    server = build_server(_config(tmp_path, daemon_url="http://daemon"))

    class FakeClient:
        def __init__(self, *_, **__): ...
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return False
        async def request(self, *_args, **_kwargs):
            return httpx.Response(
                409, json={"error": "undo_failed", "detail": "already undone"},
                request=httpx.Request("POST", "http://daemon/x"),
            )

    monkeypatch.setattr("claude_mnemos.mcp.server.httpx.AsyncClient", FakeClient)

    result = await _call_tool(server, "undo_operation", {"op_id": "abc"})
    text = result.content[0].text
    assert "409" in text
    assert "undo_failed" in text
    assert "already undone" in text


async def test_call_write_tool_happy_path(tmp_path: Path, monkeypatch):
    server = build_server(_config(tmp_path, daemon_url="http://daemon"))

    class FakeClient:
        def __init__(self, *_, **__): ...
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return False
        async def request(self, _method, url, json=None):
            assert "snapshots" in url
            return httpx.Response(
                201, json={"name": "manual-x", "kind": "manual", "label": None},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr("claude_mnemos.mcp.server.httpx.AsyncClient", FakeClient)

    result = await _call_tool(server, "create_snapshot", {})
    parsed = json.loads(result.content[0].text)
    assert parsed["name"] == "manual-x"


async def test_unhandled_exception_in_read_tool_caught(tmp_path: Path, monkeypatch):
    """Generic exception from read tool is caught by build_server's outer try."""
    server = build_server(_config(tmp_path))

    def boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("claude_mnemos.mcp.server.get_status", boom)
    result = await _call_tool(server, "get_status", {})
    text = result.content[0].text
    assert "RuntimeError" in text
    assert "kaboom" in text


@pytest.mark.parametrize("name", sorted(TOOL_NAMES))
def test_every_tool_has_input_schema(name):
    tool = next(t for t in TOOL_DEFS if t.name == name)
    assert isinstance(tool.inputSchema, dict)
    assert tool.inputSchema["type"] == "object"
