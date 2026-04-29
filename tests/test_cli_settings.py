from __future__ import annotations

import json

from claude_mnemos.cli import main as cli_main


def test_settings_get_returns_defaults(capsys):
    rc = cli_main(["settings", "get", "--project", "foo", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["snapshots"]["retention_days"] == 180


def test_settings_get_dot_path_scalar(capsys):
    rc = cli_main(["settings", "get", "--project", "foo", "snapshots.retention_days"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "180"


def test_settings_set_scalar(capsys):
    rc = cli_main([
        "settings", "set", "--project", "foo",
        "snapshots.retention_days", "30",
    ])
    assert rc == 0
    capsys.readouterr()
    cli_main(["settings", "get", "--project", "foo", "snapshots.retention_days"])
    assert capsys.readouterr().out.strip() == "30"


def test_settings_set_list():
    rc = cli_main([
        "settings", "set", "--project", "foo",
        "lint.enabled_rules", '["frontmatter_required"]',
    ])
    assert rc == 0
    from claude_mnemos.state.settings import SettingsStore
    s = SettingsStore().get_project("foo")
    assert s.lint.enabled_rules == ["frontmatter_required"]


def test_settings_set_invalid_json():
    rc = cli_main(["settings", "set", "--project", "foo",
                   "lint.schedule", "not json"])
    assert rc != 0


def test_settings_set_invalid_value_type():
    rc = cli_main(["settings", "set", "--project", "foo",
                   "snapshots.retention_days", "-5"])
    assert rc != 0


def test_settings_reset_field():
    cli_main(["settings", "set", "--project", "foo",
              "snapshots.retention_days", "30"])
    rc = cli_main(["settings", "reset", "--project", "foo",
                   "snapshots.retention_days"])
    assert rc == 0
    from claude_mnemos.state.settings import SettingsStore
    assert SettingsStore().get_project("foo").snapshots.retention_days == 180


def test_settings_reset_all():
    cli_main(["settings", "set", "--project", "foo",
              "snapshots.retention_days", "30"])
    rc = cli_main(["settings", "reset", "--project", "foo"])
    assert rc == 0
    from claude_mnemos.state.settings import SettingsStore
    assert SettingsStore().get_project("foo").snapshots.retention_days == 180


def test_settings_global_get_set(capsys):
    rc = cli_main(["settings", "get", "--global", "--json"])
    assert rc == 0
    capsys.readouterr()
    cli_main(["settings", "set", "--global", "locale", '"en"'])
    capsys.readouterr()
    cli_main(["settings", "get", "--global", "locale"])
    assert capsys.readouterr().out.strip() == "en"


def test_settings_get_unknown_key_errors():
    rc = cli_main(["settings", "get", "--project", "foo", "no.such.key"])
    assert rc != 0
