from __future__ import annotations

from typing import Any

import httpx

from claude_mnemos.mcp.write_tools._http import call_daemon


async def create_snapshot(
    client: httpx.AsyncClient,
    daemon_url: str,
    *,
    project: str,
    label: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if label is not None:
        body["label"] = label
    return await call_daemon(
        client,
        "POST",
        f"{daemon_url.rstrip('/')}/snapshots/{project}",
        json_body=body,
    )


async def restore_snapshot(
    client: httpx.AsyncClient,
    daemon_url: str,
    *,
    project: str,
    name: str,
) -> dict[str, Any]:
    return await call_daemon(
        client,
        "POST",
        f"{daemon_url.rstrip('/')}/snapshots/{project}/{name}/restore",
    )


async def delete_snapshot(
    client: httpx.AsyncClient,
    daemon_url: str,
    *,
    project: str,
    name: str,
) -> dict[str, Any]:
    return await call_daemon(
        client,
        "DELETE",
        f"{daemon_url.rstrip('/')}/snapshots/{project}/{name}",
    )
