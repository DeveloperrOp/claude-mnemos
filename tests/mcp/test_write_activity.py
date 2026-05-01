import httpx
import pytest

from claude_mnemos.mcp.errors import (
    DaemonRefusedError,
    DaemonTimeoutError,
    DaemonUnreachableError,
)
from claude_mnemos.mcp.write_tools.activity import undo_operation


def _client(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


async def test_undo_happy_path():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/activity/myproject/abc123/undo"
        return httpx.Response(
            200,
            json={
                "success": True,
                "op_id": "abc123",
                "restored_pages": ["wiki/entities/foo.md"],
                "new_entry_id": "newid",
            },
        )

    async with _client(handler) as client:
        result = await undo_operation(client, "http://daemon", "myproject", "abc123")
    assert result["success"] is True
    assert result["new_entry_id"] == "newid"


async def test_undo_409_raises_refused():
    def handler(_request):
        return httpx.Response(
            409,
            json={"error": "undo_failed", "detail": "already undone"},
        )

    async with _client(handler) as client:
        with pytest.raises(DaemonRefusedError) as exc_info:
            await undo_operation(client, "http://daemon", "myproject", "abc")
    assert exc_info.value.status_code == 409
    assert exc_info.value.error == "undo_failed"
    assert "already undone" in exc_info.value.detail


async def test_undo_connect_error_raises_unreachable():
    def handler(_request):
        raise httpx.ConnectError("connection refused")

    async with _client(handler) as client:
        with pytest.raises(DaemonUnreachableError):
            await undo_operation(client, "http://daemon", "myproject", "abc")


async def test_undo_timeout_raises_timeout():
    def handler(_request):
        raise httpx.ReadTimeout("read timed out")

    async with _client(handler) as client:
        with pytest.raises(DaemonTimeoutError):
            await undo_operation(client, "http://daemon", "myproject", "abc")


async def test_undo_unknown_5xx_raises_refused():
    def handler(_request):
        return httpx.Response(500, text="internal error")

    async with _client(handler) as client:
        with pytest.raises(DaemonRefusedError) as exc_info:
            await undo_operation(client, "http://daemon", "myproject", "abc")
    assert exc_info.value.status_code == 500
