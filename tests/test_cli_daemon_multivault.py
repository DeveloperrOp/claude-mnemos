"""Tests for `mnemos daemon start|foreground` CLI — Task 22.

Covers:
- default (no filter) → boot_filter is None
- --all flag → BootFilter(all=True)
- --project alpha,beta → BootFilter(names=["alpha", "beta"])
- --vault PATH (legacy) → hard SystemExit(2) with migration hint
- --all/--project mutually exclusive group
- foreground mirrors start (same flags)
"""
from __future__ import annotations

import pytest

from claude_mnemos.cli import _resolve_daemon_config, build_parser
from claude_mnemos.daemon.config import BootFilter

# ── start subcommand ──────────────────────────────────────────────────────────


def test_daemon_start_default_no_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "start"])
    cfg = _resolve_daemon_config(args)
    assert cfg.boot_filter is None  # None == "all"


def test_daemon_start_all_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "start", "--all"])
    cfg = _resolve_daemon_config(args)
    assert cfg.boot_filter == BootFilter(all=True)


def test_daemon_start_project_subset(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "start", "--project", "alpha,beta"])
    cfg = _resolve_daemon_config(args)
    assert cfg.boot_filter == BootFilter(names=["alpha", "beta"])


def test_daemon_start_vault_flag_rejected():
    """--vault PATH legacy flag must exit with code 2 + migration hint."""
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["daemon", "start", "--vault", "/v"])
    assert exc.value.code == 2


def test_daemon_start_all_and_project_mutually_exclusive():
    """--all and --project cannot be used together."""
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["daemon", "start", "--all", "--project", "alpha"])
    assert exc.value.code == 2


def test_daemon_start_project_single(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "start", "--project", "solo"])
    cfg = _resolve_daemon_config(args)
    assert cfg.boot_filter == BootFilter(names=["solo"])


def test_daemon_start_project_strips_whitespace(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "start", "--project", " a , b , c "])
    cfg = _resolve_daemon_config(args)
    assert cfg.boot_filter == BootFilter(names=["a", "b", "c"])


def test_daemon_start_port_override(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "start", "--port", "9999"])
    cfg = _resolve_daemon_config(args)
    assert cfg.port == 9999
    assert cfg.boot_filter is None


# ── foreground subcommand mirrors start ───────────────────────────────────────


def test_daemon_foreground_default_no_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "foreground"])
    cfg = _resolve_daemon_config(args)
    assert cfg.boot_filter is None


def test_daemon_foreground_all_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "foreground", "--all"])
    cfg = _resolve_daemon_config(args)
    assert cfg.boot_filter == BootFilter(all=True)


def test_daemon_foreground_project_subset(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    args = build_parser().parse_args(["daemon", "foreground", "--project", "x,y"])
    cfg = _resolve_daemon_config(args)
    assert cfg.boot_filter == BootFilter(names=["x", "y"])


def test_daemon_foreground_vault_flag_rejected():
    """--vault PATH legacy flag must exit with code 2 on foreground too."""
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["daemon", "foreground", "--vault", "/v"])
    assert exc.value.code == 2
