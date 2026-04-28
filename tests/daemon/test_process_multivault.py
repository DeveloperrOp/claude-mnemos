from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from claude_mnemos.daemon.config import BootFilter, DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore
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


# ─── Task 13: _select_boot_entries + _bootstrap_runtimes ──────────────────────


def _add_project(name: str, vault: Path) -> ProjectMapEntry:
    vault.mkdir(parents=True, exist_ok=True)
    e = ProjectMapEntry(name=name, vault_root=vault, cwd_patterns=[])
    ProjectStore().add(e)
    return e


def test_select_boot_entries_all_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_home(tmp_path, monkeypatch)
    _add_project("alpha", tmp_path / "a")
    _add_project("beta", tmp_path / "b")

    daemon = MnemosDaemon(_config(tmp_path))
    selected = daemon._select_boot_entries()
    assert [e.name for e in selected] == ["alpha", "beta"]


def test_select_boot_entries_filter_subset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_home(tmp_path, monkeypatch)
    _add_project("alpha", tmp_path / "a")
    _add_project("beta", tmp_path / "b")
    _add_project("gamma", tmp_path / "g")

    daemon = MnemosDaemon(
        _config(tmp_path, boot_filter=BootFilter(names=["alpha", "gamma"]))
    )
    selected = daemon._select_boot_entries()
    assert [e.name for e in selected] == ["alpha", "gamma"]


def test_select_boot_entries_missing_name_alerts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_home(tmp_path, monkeypatch)
    _add_project("alpha", tmp_path / "a")

    daemon = MnemosDaemon(
        _config(tmp_path, boot_filter=BootFilter(names=["alpha", "ghost"]))
    )
    selected = daemon._select_boot_entries()
    assert [e.name for e in selected] == ["alpha"]
    msgs = [a.message for a in daemon.alerts.list()]
    assert any("'ghost'" in m for m in msgs)


def test_select_boot_entries_empty_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_home(tmp_path, monkeypatch)
    daemon = MnemosDaemon(_config(tmp_path))
    assert daemon._select_boot_entries() == []


@pytest.mark.asyncio
async def test_bootstrap_runtimes_mounts_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_home(tmp_path, monkeypatch)
    _add_project("alpha", tmp_path / "a")
    _add_project("beta", tmp_path / "b")

    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        await daemon._bootstrap_runtimes()
        assert set(daemon.runtimes.keys()) == {"alpha", "beta"}
        for rt in daemon.runtimes.values():
            assert rt.is_mounted is True
    finally:
        async with daemon._runtimes_lock:
            for rt in list(daemon.runtimes.values()):
                await rt.unmount(timeout=2.0, force=True)
            daemon.runtimes.clear()
        daemon.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_bootstrap_runtimes_partial_failure_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_home(tmp_path, monkeypatch)
    _add_project("good", tmp_path / "good")
    bad = tmp_path / "bad"
    bad.mkdir()
    _add_project("bad", bad)

    from claude_mnemos.daemon import vault_runtime as vr
    from claude_mnemos.daemon.watchdog_observer import VaultObserver as _RealObserver

    real_observer = _RealObserver

    class _MaybeBoom:
        def __init__(self, root: Path, handler: object) -> None:
            self._root = root
            self._real = real_observer(root, handler)  # type: ignore[arg-type]

        def start(self) -> None:
            if "bad" in str(self._root):
                raise RuntimeError("simulated mount failure")
            return self._real.start()

        def stop(self) -> None:
            with contextlib.suppress(Exception):
                self._real.stop()

    monkeypatch.setattr(vr, "VaultObserver", _MaybeBoom)

    daemon = MnemosDaemon(_config(tmp_path))
    daemon.scheduler.start()
    try:
        await daemon._bootstrap_runtimes()
        assert "good" in daemon.runtimes
        assert "bad" not in daemon.runtimes
        msgs = [a.message for a in daemon.alerts.list()]
        assert any("simulated mount failure" in m for m in msgs)
    finally:
        async with daemon._runtimes_lock:
            for rt in list(daemon.runtimes.values()):
                await rt.unmount(timeout=2.0, force=True)
            daemon.runtimes.clear()
        daemon.scheduler.shutdown(wait=False)
