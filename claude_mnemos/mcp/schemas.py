"""JSON Schema dicts for the MCP `inputSchema` of every tool.

These mirror the contracts described in design §4.
"""

from __future__ import annotations

from typing import Any

LIST_PAGES: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["entity", "concept", "source"],
            "description": "Filter by page type",
        },
        "flavor": {
            "type": "string",
            "enum": ["pattern", "mistake", "decision", "lesson", "reference"],
            "description": "Filter by flavor tag",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 500,
            "default": 50,
        },
    },
    "additionalProperties": False,
}

READ_PAGE: dict[str, Any] = {
    "type": "object",
    "required": ["page_ref"],
    "properties": {
        "page_ref": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Page name (e.g. 'foo') or path relative to vault root "
                "(e.g. 'wiki/entities/foo.md'). Path traversal forbidden."
            ),
        },
    },
    "additionalProperties": False,
}

SEARCH_PAGES: dict[str, Any] = {
    "type": "object",
    "required": ["query"],
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "description": "Case-insensitive substring (filename + body)",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 20,
        },
    },
    "additionalProperties": False,
}

GET_STATUS: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

GET_RECENT_ACTIVITY: dict[str, Any] = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 200,
            "default": 10,
        },
    },
    "additionalProperties": False,
}

UNDO_OPERATION: dict[str, Any] = {
    "type": "object",
    "required": ["op_id"],
    "properties": {
        "op_id": {
            "type": "string",
            "minLength": 1,
            "description": "Activity entry id (full UUID hex)",
        },
    },
    "additionalProperties": False,
}

CREATE_SNAPSHOT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "maxLength": 128,
            "description": "Optional human-readable label appended to snapshot name",
        },
    },
    "additionalProperties": False,
}

RESTORE_SNAPSHOT: dict[str, Any] = {
    "type": "object",
    "required": ["name"],
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "description": "Snapshot directory name (e.g. 'daily-2026-04-26')",
        },
    },
    "additionalProperties": False,
}

DELETE_SNAPSHOT: dict[str, Any] = RESTORE_SNAPSHOT
