"""MCP read tool: get_lint_results — direct file read of .lint-results.json."""

from __future__ import annotations

from pathlib import Path

from mcp import types

from claude_mnemos.lint.exceptions import LintCorruptError
from claude_mnemos.lint.state import load_last_report


async def get_lint_results(vault_root: Path) -> list[types.TextContent]:
    """Return the cached lint report (or a stub message if absent / corrupt)."""
    try:
        report = load_last_report(vault_root)
    except LintCorruptError as exc:
        return [types.TextContent(type="text", text=f"lint results corrupt: {exc}")]
    if report is None:
        return [
            types.TextContent(
                type="text",
                text="no lint run yet — call run_lint or `mnemos lint run`",
            )
        ]
    return [types.TextContent(type="text", text=report.model_dump_json(indent=2))]
