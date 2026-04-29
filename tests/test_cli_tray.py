from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


def test_mnemos_tray_run_routes_to_tray_main() -> None:
    """`mnemos tray run` should delegate to claude_mnemos.tray.__main__:main."""
    import claude_mnemos.cli as cli

    with patch("claude_mnemos.cli_tray.tray_main.main", return_value=0) as fake_main, \
         patch.object(sys, "argv", ["mnemos", "tray", "run"]):
        rc = cli.main()
    assert rc == 0
    fake_main.assert_called_once()


@pytest.mark.parametrize("subcmd", ["install", "uninstall", "status"])
def test_mnemos_tray_subcommands_route(subcmd: str) -> None:
    import claude_mnemos.cli as cli

    with patch("claude_mnemos.cli_tray.tray_main.main", return_value=0) as fake_main, \
         patch.object(sys, "argv", ["mnemos", "tray", subcmd]):
        rc = cli.main()
    assert rc == 0
    fake_main.assert_called_once()
