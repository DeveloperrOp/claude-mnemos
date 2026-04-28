from __future__ import annotations

from pathlib import Path


def _set_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_daemon_base_url_default(tmp_path, monkeypatch):
    _set_home(tmp_path, monkeypatch)
    from claude_mnemos.daemon_url import daemon_base_url
    assert daemon_base_url() == "http://127.0.0.1:5757"


def test_daemon_base_url_reads_from_settings(tmp_path, monkeypatch):
    _set_home(tmp_path, monkeypatch)
    from claude_mnemos.state.settings import GlobalSettings, SettingsStore
    SettingsStore().set_global(GlobalSettings(daemon_port=5800))
    from claude_mnemos.daemon_url import daemon_base_url
    assert daemon_base_url() == "http://127.0.0.1:5800"


def test_daemon_base_url_custom_host(tmp_path, monkeypatch):
    _set_home(tmp_path, monkeypatch)
    from claude_mnemos.daemon_url import daemon_base_url
    assert daemon_base_url(host="0.0.0.0") == "http://0.0.0.0:5757"
