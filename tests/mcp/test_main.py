from pathlib import Path

import pytest

from claude_mnemos.mcp.__main__ import build_parser


def test_parser_minimal(tmp_path: Path):
    args = build_parser().parse_args(["--vault", str(tmp_path)])
    assert args.vault == tmp_path
    assert args.daemon_url == "http://127.0.0.1:5757"
    assert args.daemon_timeout == 30.0
    assert args.log_level == "info"


def test_parser_overrides(tmp_path: Path):
    args = build_parser().parse_args(
        [
            "--vault",
            str(tmp_path),
            "--daemon-url",
            "http://10.0.0.1:9999",
            "--daemon-timeout",
            "5",
            "--log-level",
            "debug",
        ]
    )
    assert args.daemon_url == "http://10.0.0.1:9999"
    assert args.daemon_timeout == 5.0
    assert args.log_level == "debug"


def test_parser_requires_vault():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_parser_invalid_log_level(tmp_path: Path):
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["--vault", str(tmp_path), "--log-level", "verbose"]
        )
