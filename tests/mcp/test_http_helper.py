"""Tests for claude_mnemos.mcp.write_tools._http — call_daemon error parsing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from claude_mnemos.mcp.errors import DaemonRefusedError, DaemonTimeoutError, DaemonUnreachableError
from claude_mnemos.mcp.write_tools._http import call_daemon


def _fake_response(status: int, body: object) -> MagicMock:
    """Build a mock httpx.Response with given status and JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.is_success = status < 400
    resp.content = b"x"
    resp.json.return_value = body
    resp.text = str(body)
    return resp


async def _client_returning(response: MagicMock) -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(return_value=response)
    return client


# ---------------------------------------------------------------------------
# Nested-detail parsing (Fix 5)
# ---------------------------------------------------------------------------


async def test_nested_detail_dict_error_extracted() -> None:
    """FastAPI HTTPException(detail={'error': '...', ...}) → error field extracted."""
    resp = _fake_response(
        404,
        {"detail": {"error": "not_found", "hint": "check the id"}},
    )
    client = await _client_returning(resp)
    with pytest.raises(DaemonRefusedError) as exc_info:
        await call_daemon(client, "GET", "http://daemon/resource")
    err = exc_info.value
    assert err.error == "not_found"
    assert err.detail is not None
    # detail should contain human-readable text from the nested dict
    assert "not_found" in str(err.detail) or "check the id" in str(err.detail)


async def test_nested_detail_dict_hint_used_as_detail() -> None:
    """When nested detail has 'hint', it becomes the human-readable detail."""
    resp = _fake_response(
        409,
        {"detail": {"error": "conflict", "hint": "retry later"}},
    )
    client = await _client_returning(resp)
    with pytest.raises(DaemonRefusedError) as exc_info:
        await call_daemon(client, "POST", "http://daemon/resource")
    err = exc_info.value
    assert err.error == "conflict"
    assert "retry later" in str(err.detail)


async def test_flat_string_detail_still_works() -> None:
    """Plain string detail (non-FastAPI style) still parses correctly."""
    resp = _fake_response(422, {"detail": "validation error"})
    client = await _client_returning(resp)
    with pytest.raises(DaemonRefusedError) as exc_info:
        await call_daemon(client, "POST", "http://daemon/resource")
    err = exc_info.value
    assert err.detail == "validation error"


async def test_flat_error_field_still_works() -> None:
    """Body with top-level 'error' and no 'detail' still sets error correctly."""
    resp = _fake_response(400, {"error": "bad_request"})
    client = await _client_returning(resp)
    with pytest.raises(DaemonRefusedError) as exc_info:
        await call_daemon(client, "POST", "http://daemon/resource")
    err = exc_info.value
    assert err.error == "bad_request"


async def test_nested_detail_no_error_key_falls_back_to_top_level() -> None:
    """If nested dict has no 'error' key, falls back to top-level body['error']."""
    resp = _fake_response(
        500,
        {"error": "server_error", "detail": {"message": "something went wrong"}},
    )
    client = await _client_returning(resp)
    with pytest.raises(DaemonRefusedError) as exc_info:
        await call_daemon(client, "GET", "http://daemon/resource")
    err = exc_info.value
    assert err.error == "server_error"


async def test_connect_error_raises_unreachable() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(DaemonUnreachableError):
        await call_daemon(client, "GET", "http://daemon/resource")


async def test_timeout_raises_timeout() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(DaemonTimeoutError):
        await call_daemon(client, "GET", "http://daemon/resource")


async def test_success_returns_body() -> None:
    resp = _fake_response(200, {"run_id": "r1", "findings": []})
    client = await _client_returning(resp)
    body = await call_daemon(client, "GET", "http://daemon/resource")
    assert body["run_id"] == "r1"
