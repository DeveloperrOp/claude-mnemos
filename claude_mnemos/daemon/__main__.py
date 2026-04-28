from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from claude_mnemos.daemon.config import (
    DEFAULT_LOG_LEVEL,
    BootFilter,
    DaemonConfig,
    default_pid_file,
)
from claude_mnemos.daemon.process import MnemosDaemon


class _VaultDeprecated(argparse.Action):
    """Hard-error for the removed ``--vault PATH`` flag."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        _namespace: argparse.Namespace,
        _values: object,
        _option_string: str | None = None,
    ) -> None:
        parser.exit(
            2,
            (
                "--vault is no longer supported. Register the vault first:\n"
                "    mnemos project add NAME --vault PATH\n"
                "Then start daemon with `mnemos daemon start` (mounts all projects)\n"
                "or `mnemos daemon start --project NAME`.\n"
            ),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude_mnemos.daemon")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="Run the daemon in foreground")
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=5757)
    run.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=["debug", "info", "warning", "error"],
    )
    run.add_argument("--pid-file", type=Path, default=default_pid_file())
    grp = run.add_mutually_exclusive_group()
    grp.add_argument(
        "--all",
        action="store_true",
        help="Mount every project in project-map (default).",
    )
    grp.add_argument(
        "--project",
        default="",
        help="Comma-separated subset of project names to mount.",
    )
    run.add_argument(
        "--vault", action=_VaultDeprecated, nargs="?", help=argparse.SUPPRESS
    )
    return parser


def _build_config(args: argparse.Namespace) -> DaemonConfig:
    boot_filter: BootFilter | None
    if args.project:
        names = [n.strip() for n in args.project.split(",") if n.strip()]
        boot_filter = BootFilter(all=False, names=names)
    elif args.all:
        boot_filter = BootFilter(all=True)
    else:
        boot_filter = None  # None == all by convention
    return DaemonConfig(
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        pid_file=args.pid_file,
        boot_filter=boot_filter,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd != "run":
        return 1
    config = _build_config(args)
    daemon = MnemosDaemon(config)
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
