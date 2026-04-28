from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.state.projects import ProjectMapEntry
from claude_mnemos.state.settings import GlobalSettings, SettingsStore


def _setup_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def _config(tmp_path: Path, **kwargs: object) -> DaemonConfig:
    return DaemonConfig(pid_file=tmp_path / "d.pid", **kwargs)  # type: ignore[arg-type]


def test_init_empty_runtimes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_home(tmp_path, monkeypatch)
    daemon = MnemosDaemon(_config(tmp_path))
    assert daemon.runtimes == {}
    assert daemon.primary_runtime is None
    assert daemon.app.state.vault_root is None


def test_recompute_primary_alphabetical_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_home(tmp_path, monkeypatch)
    daemon = MnemosDaemon(_config(tmp_path))

    from claude_mnemos.daemon.vault_runtime import VaultRuntime
    from claude_mnemos.state.settings import ProjectSettings

    for name in ("zeta", "alpha", "mike"):
        v = tmp_path / name
        v.mkdir()
        rt = VaultRuntime(
            project=ProjectMapEntry(name=name, vault_root=v, cwd_patterns=[]),
            settings=ProjectSettings(),
        )
        daemon.runtimes[name] = rt
        rt.job_store.close()  # we won't mount here — just test selection

    daemon._recompute_primary()
    assert daemon.primary_runtime is not None
    assert daemon.primary_runtime.name == "alpha"
    assert daemon.app.state.vault_root == tmp_path / "alpha"


def test_recompute_primary_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_home(tmp_path, monkeypatch)

    SettingsStore().set_global(GlobalSettings(primary_project="mike"))

    daemon = MnemosDaemon(_config(tmp_path))

    from claude_mnemos.daemon.vault_runtime import VaultRuntime
    from claude_mnemos.state.settings import ProjectSettings

    for name in ("zeta", "alpha", "mike"):
        v = tmp_path / name
        v.mkdir()
        rt = VaultRuntime(
            project=ProjectMapEntry(name=name, vault_root=v, cwd_patterns=[]),
            settings=ProjectSettings(),
        )
        daemon.runtimes[name] = rt
        rt.job_store.close()

    daemon._recompute_primary()
    assert daemon.primary_runtime is not None
    assert daemon.primary_runtime.name == "mike"


def test_recompute_primary_pinned_missing_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_home(tmp_path, monkeypatch)
    SettingsStore().set_global(GlobalSettings(primary_project="absent"))

    daemon = MnemosDaemon(_config(tmp_path))

    from claude_mnemos.daemon.vault_runtime import VaultRuntime
    from claude_mnemos.state.settings import ProjectSettings

    for name in ("alpha", "beta"):
        v = tmp_path / name
        v.mkdir()
        rt = VaultRuntime(
            project=ProjectMapEntry(name=name, vault_root=v, cwd_patterns=[]),
            settings=ProjectSettings(),
        )
        daemon.runtimes[name] = rt
        rt.job_store.close()

    daemon._recompute_primary()
    assert daemon.primary_runtime is not None
    assert daemon.primary_runtime.name == "alpha"  # alphabetical first


def test_recompute_primary_empty_runtimes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_home(tmp_path, monkeypatch)
    daemon = MnemosDaemon(_config(tmp_path))
    daemon._recompute_primary()
    assert daemon.primary_runtime is None
    assert daemon.app.state.vault_root is None
