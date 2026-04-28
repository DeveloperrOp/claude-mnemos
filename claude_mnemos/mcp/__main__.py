from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import mcp.server.stdio
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from claude_mnemos import __version__
from claude_mnemos.daemon_url import daemon_base_url
from claude_mnemos.mapping.resolver import ProjectResolver, ResolverAmbiguityError
from claude_mnemos.mcp.config import (
    DEFAULT_LOG_LEVEL,
    DEFAULT_TIMEOUT_S,
    MCPConfig,
)
from claude_mnemos.mcp.degraded import build_degraded_server
from claude_mnemos.mcp.server import SERVER_NAME, build_server

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude_mnemos.mcp")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--vault", type=Path, default=None,
        help="Direct vault path (legacy escape hatch)",
    )
    group.add_argument(
        "--project", type=str, default=None,
        help="Project name in ~/.claude-mnemos/project-map.json",
    )
    group.add_argument(
        "--auto-resolve", action="store_true",
        help="Resolve vault from cwd via project-map.json (default)",
    )
    parser.add_argument("--daemon-url", default=daemon_base_url())
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


def resolve_vault_for_mcp(args: argparse.Namespace) -> tuple[Path | None, str | None]:
    """Return (vault_path, error_message). Either is None depending on outcome."""
    if args.vault is not None:
        return args.vault, None
    resolver = ProjectResolver()
    if args.project:
        entry = resolver.resolve_by_name(args.project)
        if entry is None:
            return None, f"project {args.project!r} not registered in project-map"
        return Path(entry.vault_root), None
    # default + --auto-resolve both fall here
    cwd = Path.cwd()
    try:
        entry = resolver.resolve_by_cwd(cwd)
    except ResolverAmbiguityError as exc:
        return None, str(exc)
    if entry is None:
        return None, (
            f"cwd {cwd} not registered in project-map. "
            "Run: mnemos project add --name NAME --vault PATH "
            '--cwd-pattern "<cwd_glob>"'
        )
    return Path(entry.vault_root), None


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run(server: Server) -> None:
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
    _configure_logging(args.log_level)
    vault, err = resolve_vault_for_mcp(args)
    server: Server
    if vault is None:
        logger.warning("MCP starting in degraded mode: %s", err)
        server = build_degraded_server(err or "no vault resolved")
    else:
        config = MCPConfig(
            vault_root=vault,
            daemon_url=args.daemon_url,
            daemon_timeout_s=args.daemon_timeout,
            log_level=args.log_level,
        )
        logger.info(
            "starting MCP server %s vault=%s daemon=%s",
            SERVER_NAME, config.vault_root, config.daemon_url,
        )
        server = build_server(config)
    try:
        asyncio.run(_run(server))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
