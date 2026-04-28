"""Task 15: verify that primary_runtime / _primary_runtime / _recompute_primary
and app.state.vault_root have been removed from MnemosDaemon.
"""
from __future__ import annotations


def test_daemon_has_no_primary_runtime_property(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from claude_mnemos.daemon.config import DaemonConfig
    from claude_mnemos.daemon.process import MnemosDaemon

    daemon = MnemosDaemon(DaemonConfig(pid_file=tmp_path / "d.pid"))
    assert not hasattr(daemon, "primary_runtime")
    assert not hasattr(daemon, "_primary_runtime")
    assert not hasattr(daemon, "_recompute_primary")
    # app.state.vault_root may exist but should not be set
    assert getattr(daemon.app.state, "vault_root", None) is None


def test_global_settings_no_primary_project_field():
    from claude_mnemos.state.settings import GlobalSettings

    g = GlobalSettings()
    # primary_project removed from schema; extra=ignore tolerates it on read
    assert not hasattr(g, "primary_project") or g.primary_project is None  # type: ignore[attr-defined]
