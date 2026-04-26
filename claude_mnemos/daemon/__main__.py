from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from claude_mnemos.daemon.config import DEFAULT_LOG_LEVEL, DaemonConfig, default_pid_file
from claude_mnemos.daemon.process import MnemosDaemon


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude_mnemos.daemon")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="Run the daemon in foreground")
    run.add_argument("--vault", type=Path, required=True)
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=5757)
    run.add_argument("--retention-days", type=int, default=180)
    run.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=["debug", "info", "warning", "error"],
    )
    run.add_argument("--pid-file", type=Path, default=default_pid_file())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd != "run":
        return 1
    config = DaemonConfig(
        vault_root=args.vault,
        host=args.host,
        port=args.port,
        retention_days=args.retention_days,
        log_level=args.log_level,
        pid_file=args.pid_file,
    )
    daemon = MnemosDaemon(config)
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
