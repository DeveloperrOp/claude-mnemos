from __future__ import annotations

import json

from claude_mnemos.cli import main as cli_main
from claude_mnemos.state.projects import (
    HOME_CONFIG_DIRNAME,
    PROJECT_MAP_FILENAME,
)


def test_project_add_writes_map(tmp_path):
    rc = cli_main([
        "project", "add",
        "--name", "claude-mnemos",
        "--vault", str(tmp_path / "v"),
        "--cwd-pattern", "~/code/cm*",
    ])
    assert rc == 0
    f = tmp_path / HOME_CONFIG_DIRNAME / PROJECT_MAP_FILENAME
    data = json.loads(f.read_text())
    assert data["projects"][0]["name"] == "claude-mnemos"
    assert data["projects"][0]["cwd_patterns"] == ["~/code/cm*"]


def test_project_add_duplicate_returns_error(tmp_path):
    cli_main(["project", "add", "--name", "x",
              "--vault", str(tmp_path / "v"), "--cwd-pattern", "~/x"])
    rc = cli_main(["project", "add", "--name", "x",
                   "--vault", str(tmp_path / "v2"), "--cwd-pattern", "~/y"])
    assert rc != 0


def test_project_add_invalid_name_returns_error(tmp_path):
    rc = cli_main(["project", "add", "--name", "Bad Name",
                   "--vault", str(tmp_path / "v")])
    assert rc != 0


def test_project_list_empty(capsys):
    rc = cli_main(["project", "list", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert json.loads(out) == []


def test_project_list_after_add(tmp_path, capsys):
    cli_main(["project", "add", "--name", "x",
              "--vault", str(tmp_path / "v"), "--cwd-pattern", "~/x"])
    capsys.readouterr()
    cli_main(["project", "list", "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["name"] == "x"


def test_project_show_returns_view(tmp_path, capsys):
    cli_main(["project", "add", "--name", "x",
              "--vault", str(tmp_path / "v"), "--cwd-pattern", "~/x"])
    capsys.readouterr()
    cli_main(["project", "show", "x", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "x"
    assert "settings" in data
    assert data["settings"]["snapshots"]["retention_days"] == 180


def test_project_update_replaces_cwd_patterns(tmp_path):
    cli_main(["project", "add", "--name", "x",
              "--vault", str(tmp_path / "v"), "--cwd-pattern", "~/old"])
    rc = cli_main(["project", "update", "x",
                   "--add-cwd-pattern", "~/new",
                   "--remove-cwd-pattern", "~/old"])
    assert rc == 0
    from claude_mnemos.state.projects import ProjectStore
    e = ProjectStore().get("x")
    assert e.cwd_patterns == ["~/new"]


def test_project_update_add_cwd_pattern_appends(tmp_path):
    """--add-cwd-pattern must append to existing patterns, not replace."""
    cli_main(["project", "add", "--name", "x",
              "--vault", str(tmp_path / "v"),
              "--cwd-pattern", "a", "--cwd-pattern", "b"])
    rc = cli_main(["project", "update", "x", "--add-cwd-pattern", "x-new"])
    assert rc == 0
    from claude_mnemos.state.projects import ProjectStore
    e = ProjectStore().get("x")
    assert e.cwd_patterns == ["a", "b", "x-new"]


def test_project_update_remove_cwd_pattern(tmp_path):
    """--remove-cwd-pattern must remove the entry from existing patterns."""
    cli_main(["project", "add", "--name", "x",
              "--vault", str(tmp_path / "v"),
              "--cwd-pattern", "a", "--cwd-pattern", "b"])
    rc = cli_main(["project", "update", "x", "--remove-cwd-pattern", "a"])
    assert rc == 0
    from claude_mnemos.state.projects import ProjectStore
    e = ProjectStore().get("x")
    assert e.cwd_patterns == ["b"]


def test_update_does_not_pre_read(monkeypatch, tmp_path):
    """_handle_update must build PATCH body purely from CLI args (no pre-GET)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
    vault = tmp_path / "v"
    vault.mkdir()
    ProjectStore().add(ProjectMapEntry(name="x", vault_root=vault, cwd_patterns=[]))

    calls: list[str] = []
    real_get = ProjectStore.get

    def spy_get(self: ProjectStore, name: str) -> object:
        calls.append(name)
        return real_get(self, name)

    monkeypatch.setattr(ProjectStore, "get", spy_get)

    import httpx
    captured: dict[str, object] = {}

    def fake_patch(_url: str, json: object, **kw: object) -> httpx.Response:
        captured["json"] = json
        return httpx.Response(
            200,
            json={"name": "x", "vault_root": str(vault), "cwd_patterns": ["p"]},
        )

    monkeypatch.setattr(httpx, "patch", fake_patch)

    import argparse

    from claude_mnemos.cli_project import _handle_update

    ns = argparse.Namespace(name="x", vault=None, add_cwd_pattern=["p"], remove_cwd_pattern=[])
    _handle_update(ns)

    assert "x" not in calls  # no pre-read of the entry
    assert captured["json"] == {"add_cwd_patterns": ["p"]}


def test_project_remove_cleans_settings(tmp_path):
    from claude_mnemos.state.projects import project_settings_path
    cli_main(["project", "add", "--name", "x",
              "--vault", str(tmp_path / "v"), "--cwd-pattern", "~/x"])
    sp = project_settings_path("x")
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text("{}")
    rc = cli_main(["project", "remove", "x", "--yes"])
    assert rc == 0
    assert not sp.exists()


def test_project_resolve_with_explicit_cwd(tmp_path, capsys):
    cwd = tmp_path / "code" / "x"
    cwd.mkdir(parents=True)
    cli_main(["project", "add", "--name", "x",
              "--vault", str(tmp_path / "v"), "--cwd-pattern", str(cwd)])
    capsys.readouterr()
    rc = cli_main(["project", "resolve", "--cwd", str(cwd), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "x"


def test_project_resolve_no_match_nonzero(tmp_path):
    rc = cli_main(["project", "resolve", "--cwd", str(tmp_path / "elsewhere"), "--json"])
    assert rc != 0


def test_project_add_with_display_name(tmp_path):
    """`mnemos project add ... --display-name ...` stores display_name."""
    rc = cli_main([
        "project", "add",
        "--name", "foo",
        "--vault", str(tmp_path / "v"),
        "--display-name", "Foo Project",
    ])
    assert rc == 0
    f = tmp_path / HOME_CONFIG_DIRNAME / PROJECT_MAP_FILENAME
    data = json.loads(f.read_text())
    entries = {p["name"]: p for p in data["projects"]}
    assert entries["foo"]["display_name"] == "Foo Project"


def test_project_add_without_display_name_stores_none(tmp_path):
    """add without --display-name → display_name=None in stored entry."""
    rc = cli_main([
        "project", "add",
        "--name", "foo",
        "--vault", str(tmp_path / "v"),
    ])
    assert rc == 0
    f = tmp_path / HOME_CONFIG_DIRNAME / PROJECT_MAP_FILENAME
    data = json.loads(f.read_text())
    entries = {p["name"]: p for p in data["projects"]}
    assert entries["foo"]["display_name"] is None
