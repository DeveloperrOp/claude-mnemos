"""Route helpers shared across per-project and cross-vault endpoints (β2).

After β2 every per-project route resolves its target VaultRuntime via
``get_runtime(request, project_name)`` (404 on unknown), and every
cross-vault aggregation route iterates the full set via
``all_runtimes(request)`` (sorted by project name; empty list when no
mounted vaults).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from claude_mnemos.daemon.vault_runtime import VaultRuntime


def get_runtime(request: Request, project_name: str) -> VaultRuntime:
    """Resolve a project's VaultRuntime or raise HTTP 404 / 503."""
    daemon = request.app.state.daemon
    if daemon is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "daemon_unavailable"},
        )
    runtime = daemon.runtimes.get(project_name)
    if runtime is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "unknown_project",
                "project_name": project_name,
                "hint": "GET /projects to list registered projects",
            },
        )
    rt: VaultRuntime = runtime
    return rt


def all_runtimes(request: Request) -> list[VaultRuntime]:
    """Iterate every mounted runtime, sorted alphabetically by name.

    Returns empty list when daemon is None or no runtimes are mounted.
    """
    daemon = request.app.state.daemon
    if daemon is None:
        return []
    runtimes: dict[str, VaultRuntime] = daemon.runtimes
    return [runtimes[name] for name in sorted(runtimes)]
