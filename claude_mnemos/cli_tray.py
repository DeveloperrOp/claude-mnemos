"""`mnemos tray ...` subcommand — thin shim over claude_mnemos.tray.__main__.

Registered by claude_mnemos.cli.main(). The actual logic lives in the tray
module so the entrypoint `mnemos-tray` and the CLI subcommand share code.
"""

from __future__ import annotations

import sys

from claude_mnemos.tray import __main__ as tray_main


def run(argv: list[str]) -> int:
    """Replace argv[0] so argparse inside tray_main sees correct prog name."""
    saved = sys.argv
    sys.argv = ["mnemos-tray", *argv]
    try:
        return tray_main.main()
    finally:
        sys.argv = saved
