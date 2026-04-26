import json

import httpx
import pytest

from claude_mnemos.mcp.errors import DaemonRefusedError
from claude_mnemos.mcp.write_tools.snapshots import (
    create_snapshot,
    delete_snapshot,
    restore_snapshot,
)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_create_snapshot_no_label():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/snapshots"
        body = json.loads(request.content.decode())
        assert body == {}
        return httpx.Response(
            201,
            json={"name": "manual-2026-04-26-12-00-00", "kind": "manual"},
        )

    async with _client(handler) as client:
        r = await create_snapshot(client, "http://daemon")
    assert r["kind"] == "manual"


async def test_create_snapshot_with_label():
    def handler(request):
        body = json.loads(request.content.decode())
        assert body == {"label": "release"}
        return httpx.Response(
            201,
            json={"name": "manual-x-release", "kind": "manual", "label": "release"},
        )

    async with _client(handler) as client:
        r = await create_snapshot(client, "http://daemon", label="release")
    assert r["label"] == "release"


async def test_restore_snapshot_happy():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/snapshots/daily-2026-04-26/restore"
        return httpx.Response(
            200,
            json={
                "success": True,
                "snapshot": "daily-2026-04-26",
                "activity_id": "newid",
            },
        )

    async with _client(handler) as client:
        r = await restore_snapshot(client, "http://daemon", "daily-2026-04-26")
    assert r["success"] is True


async def test_restore_snapshot_404():
    def handler(_request):
        return httpx.Response(404, json={"error": "not_found", "name": "x"})

    async with _client(handler) as client:
        with pytest.raises(DaemonRefusedError) as exc_info:
            await restore_snapshot(client, "http://daemon", "missing")
    assert exc_info.value.status_code == 404


async def test_delete_snapshot_happy():
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == "/snapshots/daily-2026-04-26"
        return httpx.Response(200, json={"deleted": "daily-2026-04-26"})

    async with _client(handler) as client:
        r = await delete_snapshot(client, "http://daemon", "daily-2026-04-26")
    assert r["deleted"] == "daily-2026-04-26"


async def test_delete_snapshot_400_invalid():
    def handler(_request):
        return httpx.Response(
            400,
            json={"error": "invalid_name", "detail": "name escapes .backups/"},
        )

    async with _client(handler) as client:
        with pytest.raises(DaemonRefusedError) as exc_info:
            await delete_snapshot(client, "http://daemon", "../etc")
    assert exc_info.value.status_code == 400


async def test_create_snapshot_trailing_slash_in_url():
    """daemon_url with trailing slash shouldn't double-slash."""
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        return httpx.Response(201, json={"name": "x", "kind": "manual"})

    async with _client(handler) as client:
        await create_snapshot(client, "http://daemon/", label=None)
    assert captured["path"] == "/snapshots"
