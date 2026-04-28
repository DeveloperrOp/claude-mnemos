from __future__ import annotations

from typing import Any

import httpx

from claude_mnemos.mcp.errors import (
    DaemonRefusedError,
    DaemonTimeoutError,
    DaemonUnreachableError,
)


async def call_daemon(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send request to daemon, normalise errors into MCP-specific exceptions.

    Returns the parsed JSON body on 2xx.
    Raises:
      - DaemonUnreachableError on connection refused / network error
      - DaemonTimeoutError on request timeout
      - DaemonRefusedError on 4xx/5xx responses
    """
    try:
        response = await client.request(method, url, json=json_body)
    except httpx.ConnectError as exc:
        raise DaemonUnreachableError(str(exc)) from exc
    except httpx.TimeoutException as exc:
        raise DaemonTimeoutError(str(exc)) from exc

    if response.is_success:
        if not response.content:
            return {}
        data: dict[str, Any] = response.json()
        return data

    error: str | None = None
    detail: str | None = None
    try:
        body = response.json()
        if isinstance(body, dict):
            detail_field = body.get("detail")
            if isinstance(detail_field, dict):
                # FastAPI HTTPException(detail={"error": "...", ...}) nests the
                # structured payload under "detail".  Extract the "error" key
                # from there; use "hint" or the whole dict-str as human-readable
                # detail.
                error = detail_field.get("error") or body.get("error")
                detail = (
                    detail_field.get("detail")
                    or detail_field.get("hint")
                    or str(detail_field)
                )
            elif isinstance(detail_field, str):
                error = body.get("error")
                detail = detail_field
            else:
                error = body.get("error")
                detail = None
    except ValueError:
        detail = response.text or None

    raise DaemonRefusedError(
        status_code=response.status_code, error=error, detail=detail
    )
