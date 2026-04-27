from __future__ import annotations

from claude_mnemos.daemon.config import (
    default_pid_file,
    default_runtime_config_file,
    migrate_legacy_dotmnemos,
)


def test_default_pid_file_is_in_claude_mnemos(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    p = default_pid_file()
    assert ".claude-mnemos" in p.parts


def test_default_runtime_config_file_is_in_claude_mnemos(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    p = default_runtime_config_file()
    assert ".claude-mnemos" in p.parts


def test_migrate_legacy_dotmnemos_moves_pid(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    legacy = tmp_path / ".mnemos"
    legacy.mkdir()
    (legacy / "daemon.pid").write_text("12345")
    (legacy / "daemon.config.json").write_text("{}")
    migrated = migrate_legacy_dotmnemos()
    assert migrated  # truthy when something moved
    new = tmp_path / ".claude-mnemos"
    assert (new / "daemon.pid").read_text() == "12345"
    assert (new / "daemon.config.json").read_text() == "{}"
    assert not (legacy / "daemon.pid").exists()
    assert not (legacy / "daemon.config.json").exists()


def test_migrate_legacy_does_not_overwrite_new(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    legacy = tmp_path / ".mnemos"
    legacy.mkdir()
    (legacy / "daemon.pid").write_text("OLD")
    new = tmp_path / ".claude-mnemos"
    new.mkdir()
    (new / "daemon.pid").write_text("NEW")
    migrate_legacy_dotmnemos()
    assert (new / "daemon.pid").read_text() == "NEW"


def test_migrate_legacy_idempotent_when_no_legacy(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert migrate_legacy_dotmnemos() is False


def test_migrate_legacy_returns_false_when_legacy_dir_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    (tmp_path / ".mnemos").mkdir()
    assert migrate_legacy_dotmnemos() is False
