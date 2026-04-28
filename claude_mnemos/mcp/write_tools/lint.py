"""MCP write tool: run_lint — POST /lint/{project}/run via daemon REST."""

from __future__ import annotations

import httpx
from mcp import types

from claude_mnemos.mcp.errors import (
    DaemonRefusedError,
    DaemonTimeoutError,
    DaemonUnreachableError,
)
from claude_mnemos.mcp.write_tools._http import call_daemon


async def run_lint(
    daemon_url: str, *, project: str, timeout_s: float = 30.0
) -> list[types.TextContent]:
    """POST <daemon_url>/lint/{project}/run and surface daemon errors as TextContent."""
    timeout = httpx.Timeout(timeout_s)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            body = await call_daemon(
                client, "POST", f"{daemon_url.rstrip('/')}/lint/{project}/run"
            )
    except DaemonUnreachableError as exc:
        return [
            types.TextContent(
                type="text",
                text=(
                    f"daemon unreachable: {exc}. "
                    "Start it with: mnemos daemon start --vault <path>"
                ),
            )
        ]
    except DaemonTimeoutError as exc:
        return [
            types.TextContent(
                type="text",
                text=f"daemon timeout after {timeout_s}s: {exc}",
            )
        ]
    except DaemonRefusedError as exc:
        return [
            types.TextContent(
                type="text",
                text=f"daemon HTTP {exc.status_code} {exc.error}: {exc.detail}",
            )
        ]
    summary = body.get("summary") or {}
    return [
        types.TextContent(
            type="text",
            text=(
                f"lint complete. run_id={body.get('run_id')} "
                f"findings={summary.get('total')}"
            ),
        )
    ]
