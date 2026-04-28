from __future__ import annotations

from pathlib import Path

from claude_mnemos.daemon.vault_runtime import (
    VaultBusyError,
    VaultMountError,
    VaultRuntime,
)
from claude_mnemos.state.projects import ProjectMapEntry
from claude_mnemos.state.settings import ProjectSettings


def _entry(tmp_path: Path, name: str = "demo") -> ProjectMapEntry:
    vault = tmp_path / name
    vault.mkdir()
    return ProjectMapEntry(name=name, vault_root=vault, cwd_patterns=[])


def test_construction_does_not_mount(tmp_path: Path) -> None:
    rt = VaultRuntime(project=_entry(tmp_path), settings=ProjectSettings())
    assert rt.is_mounted is False
    assert rt.observer is None
    assert rt.job_worker is None
    assert rt.name == "demo"
    assert rt.vault_root == tmp_path / "demo"
    rt.job_store.close()


def test_busy_error_carries_counts() -> None:
    err = VaultBusyError(name="demo", queued=2, running=1)
    assert err.queued == 2
    assert err.running == 1
    assert err.name == "demo"
    assert "2 queued" in str(err)
    assert "1 running" in str(err)


def test_mount_error_inherits_runtime_error() -> None:
    err = VaultMountError("boom")
    assert isinstance(err, Exception)
