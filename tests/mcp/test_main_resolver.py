from __future__ import annotations

import pytest

from claude_mnemos.mcp.__main__ import (
    build_parser,
    resolve_vault_for_mcp,
)


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_explicit_vault(tmp_path):
    args = build_parser().parse_args(["--vault", str(tmp_path / "v")])
    vault, err = resolve_vault_for_mcp(args)
    assert vault == tmp_path / "v"
    assert err is None


def test_explicit_project_unknown(tmp_path):
    args = build_parser().parse_args(["--project", "nope"])
    vault, err = resolve_vault_for_mcp(args)
    assert vault is None
    assert err and "not registered" in err


def test_auto_resolve_no_match_returns_error_not_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = build_parser().parse_args(["--auto-resolve"])
    vault, err = resolve_vault_for_mcp(args)
    assert vault is None
    assert err is not None


def test_auto_resolve_hit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(
        name="x", vault_root=vault, cwd_patterns=[str(tmp_path)],
    ))
    args = build_parser().parse_args(["--auto-resolve"])
    v, err = resolve_vault_for_mcp(args)
    assert v == vault
    assert err is None


def test_project_name_hit(tmp_path):
    from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))
    args = build_parser().parse_args(["--project", "x"])
    v, err = resolve_vault_for_mcp(args)
    assert v == vault
    assert err is None


def test_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--vault", str(tmp_path), "--project", "x"])


def test_no_arg_falls_back_to_auto_resolve(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # No args -> auto_resolve=True default behavior
    args = build_parser().parse_args([])
    vault, err = resolve_vault_for_mcp(args)
    assert vault is None
    assert err is not None  # cwd not registered, not crash


def test_degraded_server_can_be_built():
    """build_degraded_server should succeed with any error message."""
    from claude_mnemos.mcp.degraded import build_degraded_server
    server = build_degraded_server("test error")
    # Just verify it returns a Server instance with a name attribute
    assert server is not None
