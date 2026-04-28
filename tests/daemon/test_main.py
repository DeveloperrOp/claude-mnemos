"""Tests for claude_mnemos.daemon.__main__.build_parser."""
from __future__ import annotations

import pytest

from claude_mnemos.daemon.__main__ import build_parser


def test_parser_default_no_filter():
    args = build_parser().parse_args(["run"])
    assert args.cmd == "run"
    assert getattr(args, "all", False) is False
    assert getattr(args, "project", "") == ""


def test_parser_all_flag():
    args = build_parser().parse_args(["run", "--all"])
    assert args.all is True
    assert args.project == ""


def test_parser_project_subset():
    args = build_parser().parse_args(["run", "--project", "alpha,beta"])
    assert args.project == "alpha,beta"


def test_parser_all_and_project_conflict():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "--all", "--project", "alpha"])


def test_parser_drops_vault_flag():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "--vault", "/x"])
