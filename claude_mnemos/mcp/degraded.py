"""Degraded MCP server: returned when vault resolution fails.

Every registered tool returns a single TextContent describing why
the server is degraded and how to fix the configuration.

Why not crash on startup? Claude Code respawns crashed MCP servers
in a loop, hammering the user with the same error. A degraded server
that responds politely keeps the surface area visible without
producing noise.
"""

from __future__ import annotations

from typing import Any

from mcp.server.lowlevel import Server
from mcp.types import TextContent, Tool

# Tool names match the production set in claude_mnemos/mcp/server.py.
_TOOL_NAMES: tuple[str, ...] = (
    "list_pages",
    "read_page",
    "search_pages",
    "get_status",
    "get_recent_activity",
    "undo_operation",
    "create_snapshot",
    "restore_snapshot",
    "delete_snapshot",
    "list_suggestions",
    "apply_ontology_suggestion",
    "propose_ontology_change",
    "run_lint",
    "get_lint_results",
)


def build_degraded_server(error_message: str) -> Server:
    server: Server = Server("claude-mnemos-mcp")

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=name,
                description=f"(degraded) {error_message}",
                inputSchema={"type": "object"},
            )
            for name in _TOOL_NAMES
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(_name: str, _arguments: dict[str, Any]) -> list[TextContent]:
        return [TextContent(
            type="text",
            text=(
                "claude-mnemos MCP is in degraded mode: "
                + error_message
                + ". Fix project-map (or pass --vault PATH) and restart Claude Code."
            ),
        )]

    return server
