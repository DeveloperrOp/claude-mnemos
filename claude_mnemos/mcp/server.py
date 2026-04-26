from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from mcp import types
from mcp.server.lowlevel import Server

from claude_mnemos.mcp import schemas
from claude_mnemos.mcp.config import MCPConfig
from claude_mnemos.mcp.errors import (
    DaemonRefusedError,
    DaemonTimeoutError,
    DaemonUnreachableError,
    PageRefError,
    daemon_unreachable_message,
    format_error,
)
from claude_mnemos.mcp.read_tools import (
    get_recent_activity,
    get_status,
    list_pages,
    read_page,
    search_pages,
)
from claude_mnemos.mcp.write_tools import (
    create_snapshot,
    delete_snapshot,
    restore_snapshot,
    undo_operation,
)

logger = logging.getLogger(__name__)

SERVER_NAME = "claude-mnemos"

TOOL_DEFS: list[types.Tool] = [
    types.Tool(
        name="list_pages",
        description=(
            "List wiki pages from the vault, optionally filtered by type "
            "(entity/concept/source) and flavor (pattern/mistake/decision/lesson/reference). "
            "Newest mtime first."
        ),
        inputSchema=schemas.LIST_PAGES,
    ),
    types.Tool(
        name="read_page",
        description=(
            "Read a wiki page by reference. `page_ref` may be a bare name "
            "(e.g. 'fastapi') or a path relative to vault root "
            "(e.g. 'wiki/entities/fastapi.md'). Returns frontmatter + body."
        ),
        inputSchema=schemas.READ_PAGE,
    ),
    types.Tool(
        name="search_pages",
        description=(
            "Case-insensitive substring search across wiki page filenames and bodies. "
            "Returns up to `limit` matches with snippets."
        ),
        inputSchema=schemas.SEARCH_PAGES,
    ),
    types.Tool(
        name="get_status",
        description=(
            "Get vault summary: counts of raw chats, wiki pages, manifest entries, "
            "activity entries, snapshots and total size in bytes."
        ),
        inputSchema=schemas.GET_STATUS,
    ),
    types.Tool(
        name="get_recent_activity",
        description=(
            "List the most recent activity log entries (newest first). "
            "Useful to find op_ids for undo_operation."
        ),
        inputSchema=schemas.GET_RECENT_ACTIVITY,
    ),
    types.Tool(
        name="undo_operation",
        description=(
            "Undo a previously logged operation by activity entry id. "
            "Routed through the mnemos daemon for atomicity."
        ),
        inputSchema=schemas.UNDO_OPERATION,
    ),
    types.Tool(
        name="create_snapshot",
        description=(
            "Create a manual vault snapshot. Optional `label` is appended to "
            "the snapshot directory name."
        ),
        inputSchema=schemas.CREATE_SNAPSHOT,
    ),
    types.Tool(
        name="restore_snapshot",
        description=(
            "Restore the vault from a named snapshot. Existing state is rolled back."
        ),
        inputSchema=schemas.RESTORE_SNAPSHOT,
    ),
    types.Tool(
        name="delete_snapshot",
        description="Delete a snapshot directory by name.",
        inputSchema=schemas.DELETE_SNAPSHOT,
    ),
]

TOOL_NAMES = {t.name for t in TOOL_DEFS}


def _to_text(payload: Any) -> list[types.TextContent]:
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    return [types.TextContent(type="text", text=text)]


def _error_text(message: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=message)]


async def _dispatch_read(
    name: str, arguments: dict[str, Any], config: MCPConfig
) -> list[types.TextContent]:
    vault = config.vault_root
    result: Any
    if name == "list_pages":
        result = await asyncio.to_thread(
            list_pages,
            vault,
            type=arguments.get("type"),
            flavor=arguments.get("flavor"),
            limit=arguments.get("limit", 50),
        )
        return _to_text(result)
    if name == "read_page":
        try:
            result = await asyncio.to_thread(
                read_page, vault, arguments["page_ref"]
            )
        except PageRefError as exc:
            return _error_text(format_error(exc))
        return _to_text(result)
    if name == "search_pages":
        result = await asyncio.to_thread(
            search_pages,
            vault,
            arguments["query"],
            limit=arguments.get("limit", 20),
        )
        return _to_text(result)
    if name == "get_status":
        result = await asyncio.to_thread(get_status, vault)
        return _to_text(result)
    if name == "get_recent_activity":
        result = await asyncio.to_thread(
            get_recent_activity, vault, limit=arguments.get("limit", 10)
        )
        return _to_text(result)
    raise ValueError(f"unknown read tool: {name}")


async def _dispatch_write(
    name: str, arguments: dict[str, Any], config: MCPConfig
) -> list[types.TextContent]:
    timeout = httpx.Timeout(config.daemon_timeout_s)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if name == "undo_operation":
                result = await undo_operation(
                    client, config.daemon_url, arguments["op_id"]
                )
            elif name == "create_snapshot":
                result = await create_snapshot(
                    client, config.daemon_url, label=arguments.get("label")
                )
            elif name == "restore_snapshot":
                result = await restore_snapshot(
                    client, config.daemon_url, arguments["name"]
                )
            elif name == "delete_snapshot":
                result = await delete_snapshot(
                    client, config.daemon_url, arguments["name"]
                )
            else:
                raise ValueError(f"unknown write tool: {name}")
    except DaemonUnreachableError:
        return _error_text(
            daemon_unreachable_message(config.daemon_url, str(config.vault_root))
        )
    except DaemonTimeoutError as exc:
        return _error_text(
            f"daemon timeout after {config.daemon_timeout_s}s: {exc}"
        )
    except DaemonRefusedError as exc:
        return _error_text(
            f"daemon HTTP {exc.status_code} {exc.error}: {exc.detail}"
        )
    return _to_text(result)


READ_TOOL_NAMES = {
    "list_pages",
    "read_page",
    "search_pages",
    "get_status",
    "get_recent_activity",
}
WRITE_TOOL_NAMES = {
    "undo_operation",
    "create_snapshot",
    "restore_snapshot",
    "delete_snapshot",
}


def build_server(config: MCPConfig) -> Server:
    server: Server = Server(SERVER_NAME)

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def _list_tools() -> list[types.Tool]:
        return TOOL_DEFS

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent]:
        args = arguments or {}
        if name not in TOOL_NAMES:
            return _error_text(f"unknown tool: {name}")
        try:
            if name in READ_TOOL_NAMES:
                return await _dispatch_read(name, args, config)
            return await _dispatch_write(name, args, config)
        except Exception as exc:
            logger.exception("tool %s failed", name)
            return _error_text(format_error(exc))

    return server
