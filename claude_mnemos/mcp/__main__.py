from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import mcp.server.stdio
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions

from claude_mnemos import __version__
from claude_mnemos.mcp.config import (
    DEFAULT_DAEMON_URL,
    DEFAULT_LOG_LEVEL,
    DEFAULT_TIMEOUT_S,
    MCPConfig,
)
from claude_mnemos.mcp.server import SERVER_NAME, build_server

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude_mnemos.mcp")
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--daemon-url", default=DEFAULT_DAEMON_URL)
    parser.add_argument(
        "--daemon-timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help="Daemon REST timeout in seconds",
    )
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=["debug", "info", "warning", "error"],
    )
    return parser


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run(config: MCPConfig) -> None:
    server = build_server(config)
    init = InitializationOptions(
        server_name=SERVER_NAME,
        server_version=__version__,
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = MCPConfig(
        vault_root=args.vault,
        daemon_url=args.daemon_url,
        daemon_timeout_s=args.daemon_timeout,
        log_level=args.log_level,
    )
    _configure_logging(config.log_level)
    logger.info(
        "starting MCP server %s vault=%s daemon=%s",
        SERVER_NAME,
        config.vault_root,
        config.daemon_url,
    )
    try:
        asyncio.run(_run(config))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
