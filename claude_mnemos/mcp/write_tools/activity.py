from __future__ import annotations

from typing import Any

import httpx

from claude_mnemos.mcp.write_tools._http import call_daemon


async def undo_operation(
    client: httpx.AsyncClient,
    daemon_url: str,
    project: str,
    op_id: str,
) -> dict[str, Any]:
    return await call_daemon(
        client,
        "POST",
        f"{daemon_url.rstrip('/')}/activity/{project}/{op_id}/undo",
    )
