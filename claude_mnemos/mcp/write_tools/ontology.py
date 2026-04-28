from __future__ import annotations

from typing import Any

import httpx

from claude_mnemos.mcp.write_tools._http import call_daemon


async def apply_ontology_suggestion(
    client: httpx.AsyncClient,
    daemon_url: str,
    project: str,
    suggestion_id: str,
) -> dict[str, Any]:
    return await call_daemon(
        client,
        "POST",
        f"{daemon_url.rstrip('/')}/ontology/{project}/suggestions/{suggestion_id}/approve",
    )


async def propose_ontology_change(
    client: httpx.AsyncClient,
    daemon_url: str,
    *,
    project: str,
    operation: str,
    affected_pages: list[str],
    proposed_target: str | None = None,
    reason: str = "",
    confidence: float = 0.7,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "operation": operation,
        "affected_pages": affected_pages,
        "reason": reason,
        "confidence": confidence,
    }
    if proposed_target is not None:
        body["proposed_target"] = proposed_target
    return await call_daemon(
        client,
        "POST",
        f"{daemon_url.rstrip('/')}/ontology/{project}/suggestions",
        json_body=body,
    )
