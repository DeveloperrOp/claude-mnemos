import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from claude_mnemos.mcp.config import MCPConfig
from claude_mnemos.mcp.errors import DaemonRefusedError, DaemonUnreachableError
from claude_mnemos.mcp.read_tools.ontology import list_suggestions
from claude_mnemos.mcp.server import build_server
from claude_mnemos.mcp.write_tools.ontology import (
    apply_ontology_suggestion,
    propose_ontology_change,
)
from claude_mnemos.state.ontology import (
    Suggestion,
    SuggestionFrontmatter,
    SuggestionStore,
)


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


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ─── read tool ──────────────────────────────────────────────────────────────


def test_list_suggestions_empty(tmp_path: Path):
    assert list_suggestions(tmp_path) == []


def test_list_suggestions_pending_default(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    store.create(_suggestion("ont-2026-04-26-aaaaaa"))
    items = list_suggestions(tmp_path)
    assert len(items) == 1
    assert items[0]["frontmatter"]["id"] == "ont-2026-04-26-aaaaaa"


def test_list_suggestions_status_all(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    store.create(_suggestion("ont-2026-04-26-aaaaaa"))
    store.create(_suggestion("ont-2026-04-26-bbbbbb"))
    store.archive_suggestion("ont-2026-04-26-bbbbbb")
    items = list_suggestions(tmp_path, status="all")
    assert len(items) == 2


# ─── write tools ────────────────────────────────────────────────────────────


async def test_apply_ontology_suggestion_happy():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/suggestions/ont-2026-04-26-aaaaaa/approve"
        return httpx.Response(
            200,
            json={
                "success": True,
                "operation": "merge_entities",
                "suggestion_id": "ont-2026-04-26-aaaaaa",
                "activity_id": "abc",
                "target_path": "wiki/entities/foobar.md",
                "affected_pages": [],
                "wikilinks_rewritten": 0,
            },
        )

    async with _client(handler) as client:
        result = await apply_ontology_suggestion(
            client, "http://daemon", "ont-2026-04-26-aaaaaa"
        )
    assert result["success"] is True
    assert result["operation"] == "merge_entities"


async def test_apply_ontology_suggestion_409():
    def handler(_request):
        return httpx.Response(
            409,
            json={
                "error": "ontology_apply_failed",
                "detail": "suggestion already approved",
            },
        )

    async with _client(handler) as client:
        with pytest.raises(DaemonRefusedError) as exc_info:
            await apply_ontology_suggestion(
                client, "http://daemon", "ont-2026-04-26-aaaaaa"
            )
    assert exc_info.value.status_code == 409


async def test_apply_ontology_suggestion_unreachable():
    def handler(_request):
        raise httpx.ConnectError("refused")

    async with _client(handler) as client:
        with pytest.raises(DaemonUnreachableError):
            await apply_ontology_suggestion(
                client, "http://daemon", "ont-2026-04-26-aaaaaa"
            )


async def test_propose_ontology_change_happy():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content.decode())
        captured["path"] = request.url.path
        return httpx.Response(
            201,
            json={
                "frontmatter": {
                    "id": "ont-2026-04-26-aaaaaa",
                    "operation": "merge_entities",
                    "status": "pending",
                },
                "body": "test reason",
            },
        )

    async with _client(handler) as client:
        result = await propose_ontology_change(
            client,
            "http://daemon",
            operation="merge_entities",
            affected_pages=["wiki/entities/foo.md", "wiki/entities/bar.md"],
            proposed_target="wiki/entities/foobar.md",
            reason="test reason",
            confidence=0.85,
        )
    assert result["frontmatter"]["id"] == "ont-2026-04-26-aaaaaa"
    assert captured["path"] == "/suggestions"
    assert captured["body"]["operation"] == "merge_entities"
    assert captured["body"]["proposed_target"] == "wiki/entities/foobar.md"
    assert captured["body"]["confidence"] == 0.85


async def test_propose_ontology_change_no_target():
    def handler(request):
        body = json.loads(request.content.decode())
        assert "proposed_target" not in body
        return httpx.Response(
            201,
            json={"frontmatter": {"id": "ont-2026-04-26-aaaaaa"}, "body": ""},
        )

    async with _client(handler) as client:
        await propose_ontology_change(
            client,
            "http://daemon",
            operation="delete_page",
            affected_pages=["wiki/entities/orphan.md"],
        )


# ─── server registration ────────────────────────────────────────────────────


async def _call_tool(server, name: str, arguments: dict | None = None):
    from mcp import types
    handler = server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments or {}),
    )
    result = await handler(request)
    return result.root


async def test_call_list_suggestions_via_server(tmp_path: Path):
    store = SuggestionStore(tmp_path)
    store.create(_suggestion("ont-2026-04-26-aaaaaa"))
    server = build_server(MCPConfig(vault_root=tmp_path, daemon_url="http://daemon"))
    result = await _call_tool(server, "list_suggestions", {})
    parsed = json.loads(result.content[0].text)
    assert isinstance(parsed, list)
    assert len(parsed) == 1


async def test_call_apply_ontology_suggestion_daemon_unreachable(tmp_path: Path, monkeypatch):
    server = build_server(MCPConfig(vault_root=tmp_path, daemon_url="http://daemon"))

    class FakeClient:
        def __init__(self, *_, **__): ...
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return False
        async def request(self, *_args, **_kwargs):
            raise httpx.ConnectError("refused")

    monkeypatch.setattr("claude_mnemos.mcp.server.httpx.AsyncClient", FakeClient)

    result = await _call_tool(
        server, "apply_ontology_suggestion", {"suggestion_id": "ont-x"}
    )
    text = result.content[0].text
    assert "daemon not reachable" in text


async def test_call_propose_ontology_change_routes_correctly(tmp_path: Path, monkeypatch):
    server = build_server(MCPConfig(vault_root=tmp_path, daemon_url="http://daemon"))
    captured = {}

    class FakeClient:
        def __init__(self, *_, **__): ...
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return False
        async def request(self, _method, url, json=None):
            captured["url"] = url
            captured["body"] = json
            return httpx.Response(
                201,
                json={
                    "frontmatter": {
                        "id": "ont-2026-04-26-zzzzzz",
                        "operation": "delete_page",
                        "status": "pending",
                    },
                    "body": "",
                },
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr("claude_mnemos.mcp.server.httpx.AsyncClient", FakeClient)

    result = await _call_tool(
        server,
        "propose_ontology_change",
        {
            "operation": "delete_page",
            "affected_pages": ["wiki/entities/orphan.md"],
        },
    )
    parsed = json.loads(result.content[0].text)
    assert parsed["frontmatter"]["id"] == "ont-2026-04-26-zzzzzz"
    assert "/suggestions" in captured["url"]
    assert captured["body"]["operation"] == "delete_page"
