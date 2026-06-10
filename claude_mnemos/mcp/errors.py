from __future__ import annotations

# Single canonical definition lives in core.pages (a LookupError). Re-exported
# here so the MCP layer keeps its `from claude_mnemos.mcp.errors import
# PageRefError` import path, but `except PageRefError` now catches the same
# class no matter which module raised it — previously there were TWO unrelated
# PageRefError classes (ValueError here vs LookupError in core.pages), so a
# handler importing one silently failed to catch the other.
from claude_mnemos.core.pages import PageRefError

__all__ = [
    "DaemonRefusedError",
    "DaemonTimeoutError",
    "DaemonUnreachableError",
    "PageRefError",
]


class DaemonUnreachableError(RuntimeError):
    """Raised when MCP write tool cannot reach the mnemos daemon (connection
    refused, DNS error, etc.).
    """


class DaemonTimeoutError(RuntimeError):
    """Raised when daemon REST call exceeds configured timeout."""


class DaemonRefusedError(RuntimeError):
    """Raised when daemon returned a 4xx/5xx response (e.g. 409 undo_failed)."""

    def __init__(self, status_code: int, error: str | None, detail: str | None) -> None:
        self.status_code = status_code
        self.error = error or "unknown_error"
        self.detail = detail or ""
        super().__init__(f"daemon HTTP {status_code} {self.error}: {self.detail}")


def daemon_unreachable_message(daemon_url: str, vault_root: str) -> str:
    return (
        f"backend daemon not reachable at {daemon_url}. "
        f"Start it with: mnemos daemon start --vault {vault_root}"
    )


def format_error(exc: BaseException) -> str:
    """Pretty single-line error string for TextContent payloads.

    Avoids leaking stack traces; full traceback should be logged to stderr.
    """
    return f"{type(exc).__name__}: {exc}"
