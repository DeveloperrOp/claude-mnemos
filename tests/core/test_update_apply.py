"""Tests for core.update_apply (V2.1) — the one-click portable-zip self-updater.

ALL mocked. We never download, never spawn powershell, never taskkill. The real
swap needs a live frozen install; here we assert on the generated PowerShell
TEXT to prove the design: validate-before-kill, single-flight (O_EXCL marker),
extract into a SAME-VOLUME ``.new`` sibling so both swap steps are atomic
renames, rename-back restore, a UAC-cancel branch, and a WMI-spawned outer that
survives the daemon's tree-kill.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest

from claude_mnemos.core import update_apply
from claude_mnemos.core.update_apply import UpdateApplyError


def _make_zip(names: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, b"x" * 16)
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    def __enter__(self) -> io.BytesIO:
        return self._buf

    def __exit__(self, *exc: object) -> None:
        self._buf.close()

    def read(self, *a: object, **k: object) -> bytes:
        return self._buf.read(*a, **k)


def _opener_for(data: bytes):
    def _opener(req, *a, **k):  # noqa: ANN001 — test stub
        return _FakeResponse(data)

    return _opener


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(update_apply, "updates_dir", lambda: tmp_path / "updates")
    monkeypatch.setattr(
        update_apply, "current_install_dir", lambda: tmp_path / "Install"
    )
    monkeypatch.setattr(update_apply, "current_username", lambda: "joe")


# --------------------------------------------------------------------------
# can_apply
# --------------------------------------------------------------------------


def test_can_apply_false_in_dev() -> None:
    ok, reason = update_apply.can_apply()
    assert ok is False
    assert isinstance(reason, str) and reason


# --------------------------------------------------------------------------
# download_and_validate (download + validate ONLY; the inner extracts)
# --------------------------------------------------------------------------


def test_download_and_validate_valid_zip() -> None:
    payload = _make_zip(["claude-mnemos.exe", "_internal/x"])
    zip_path = update_apply.download_and_validate(
        "https://example/portable.zip", "0.9.0", opener=_opener_for(payload)
    )
    assert zip_path.name == "portable.zip"
    assert zipfile.is_zipfile(zip_path)
    # NOT extracted in Python (the elevated inner does that, into <install>.new).
    assert not (zip_path.parent / "extract").exists()


def test_download_and_validate_rejects_non_zip() -> None:
    with pytest.raises(UpdateApplyError):
        update_apply.download_and_validate(
            "https://example/portable.zip", "0.9.0", opener=_opener_for(b"nope")
        )


def test_download_and_validate_rejects_zip_without_exe() -> None:
    payload = _make_zip(["_internal/x", "readme.txt"])
    with pytest.raises(UpdateApplyError):
        update_apply.download_and_validate(
            "https://example/portable.zip", "0.9.0", opener=_opener_for(payload)
        )


def test_download_and_validate_rejects_low_disk(monkeypatch) -> None:
    class _Usage:
        free = 1

    monkeypatch.setattr(update_apply.shutil, "disk_usage", lambda _p: _Usage())
    payload = _make_zip(["claude-mnemos.exe", "_internal/x"])
    with pytest.raises(UpdateApplyError):
        update_apply.download_and_validate(
            "https://example/portable.zip", "0.9.0", opener=_opener_for(payload)
        )


# --------------------------------------------------------------------------
# single-flight marker
# --------------------------------------------------------------------------


def test_marker_single_flight_blocks_second() -> None:
    update_apply.write_pending_marker(
        version="0.9.0", install_dir=Path(r"C:\I"), old_dir=Path(r"C:\I.old")
    )
    assert update_apply.update_in_progress() is True
    # A second concurrent claim loses the O_EXCL race.
    with pytest.raises(UpdateApplyError):
        update_apply.write_pending_marker(
            version="0.9.0", install_dir=Path(r"C:\I"), old_dir=Path(r"C:\I.old")
        )


def test_stale_marker_is_superseded(monkeypatch) -> None:
    update_apply.write_pending_marker(
        version="0.9.0", install_dir=Path(r"C:\I"), old_dir=Path(r"C:\I.old")
    )
    # Pretend the marker is old: update_in_progress() -> False -> retry allowed.
    monkeypatch.setattr(update_apply, "update_in_progress", lambda: False)
    # Should not raise — the stale marker is removed + reclaimed.
    update_apply.write_pending_marker(
        version="0.9.1", install_dir=Path(r"C:\I"), old_dir=Path(r"C:\I.old")
    )


# --------------------------------------------------------------------------
# render_inner_script  (extract to .new -> two same-volume renames -> restore)
# --------------------------------------------------------------------------


@pytest.fixture
def inner() -> str:
    return update_apply.render_inner_script(
        install_dir=Path(r"C:\Program Files\ClaudeMnemos"),
        old_dir=Path(r"C:\Program Files\ClaudeMnemos.old"),
        new_dir=Path(r"C:\Program Files\ClaudeMnemos.new"),
        zip_path=Path(r"C:\Users\joe\.claude-mnemos\updates\0.9.0\portable.zip"),
        result_path=Path(r"C:\Users\joe\.claude-mnemos\updates\0.9.0\result.txt"),
        version="0.9.0",
    )


def test_inner_error_action_stop_and_wildcard_kill(inner: str) -> None:
    assert '$ErrorActionPreference = "Stop"' in inner
    # No /T: the tree-kill would take down the interactively-spawned outer
    # (a child of the daemon) mid-swap. /IM alone still kills supervisor +
    # daemon + launcher (all claude-mnemos.exe).
    assert "taskkill /F /IM claude-mnemos.exe" in inner
    assert "taskkill /F /IM claude-mnemos-cli.exe" in inner
    assert "taskkill /F /IM claude-mnemos.exe /T" not in inner
    assert "Get-Process claude-mnemos*" in inner


def test_inner_kills_in_loop_until_processes_gone(inner: str) -> None:
    # A single taskkill can lose the race against the tray supervisor respawning
    # the daemon (v0.0.56 regression → swap spun forever). The kill must LOOP and
    # re-check Get-Process until the process list is actually empty.
    assert "while" in inner
    # in-loop liveness check + the final post-loop guard = at least 2 references
    assert inner.count("Get-Process claude-mnemos*") >= 2


def test_inner_aborts_clean_when_processes_survive(inner: str) -> None:
    # If the processes can't be freed within the deadline, ABORT before any
    # rename so the install is byte-for-byte intact (no half-swap, no loop).
    assert "still running" in inner
    abort_idx = inner.index("still running")
    first_rename_idx = inner.index(
        'Move-Item -LiteralPath "C:\\Program Files\\ClaudeMnemos" '
    )
    assert abort_idx < first_rename_idx


def test_inner_renames_stale_aside_no_blocking_delete_before_kill(inner: str) -> None:
    # v0.0.58 hung because it Remove-Item -Recurse'd the stale .old BEFORE the
    # kill (a recursive delete on a large/locked tree can block forever). Now:
    # kill first, then move stale leftovers ASIDE with an INSTANT rename to a
    # unique .trash name. There must be NO recursive delete of the .old backup
    # before the abort/kill stage.
    assert ".trash-" in inner
    abort_idx = inner.index("still running")
    before_abort = inner[:abort_idx]
    assert (
        'Remove-Item -LiteralPath "C:\\Program Files\\ClaudeMnemos.old"'
        not in before_abort
    )


def test_inner_catch_restores_only_when_this_run_renamed(inner: str) -> None:
    # Corruption guard: the rollback restores the backup ONLY if THIS run did
    # the install -> .old rename, so a stale/unrelated .old can never be moved
    # over a healthy install.
    assert "$renamed = $false" in inner
    assert "if ($renamed)" in inner


def test_inner_extracts_into_samevolume_new_sibling(inner: str) -> None:
    assert (
        'Expand-Archive -Path "C:\\Users\\joe\\.claude-mnemos\\updates\\0.9.0\\portable.zip" '
        '-DestinationPath "C:\\Program Files\\ClaudeMnemos.new"' in inner
    )
    assert r'Test-Path -LiteralPath "C:\Program Files\ClaudeMnemos.new\claude-mnemos.exe"' in inner


def test_inner_two_atomic_renames(inner: str) -> None:
    assert (
        'Move-Item -LiteralPath "C:\\Program Files\\ClaudeMnemos" '
        '-Destination "C:\\Program Files\\ClaudeMnemos.old"' in inner
    )
    assert (
        'Move-Item -LiteralPath "C:\\Program Files\\ClaudeMnemos.new" '
        '-Destination "C:\\Program Files\\ClaudeMnemos"' in inner
    )
    assert "robocopy" not in inner and "/MIR" not in inner and "schtasks" not in inner


def test_inner_retries_both_renames_and_probes_locker_on_giveup(inner: str) -> None:
    # Both renames retry (a transient AV/handle lock clears within the window),
    # and on final give-up the Restart-Manager probe is invoked to name the holder.
    assert "$i -lt 36" in inner  # aside-rename retry window
    assert "$j -lt 36" in inner  # new->install retry window
    assert "lockcheck.ps1" in inner
    assert "mnemos-lockers.log" in inner


def test_inner_leaves_install_cwd_before_rename(inner: str) -> None:
    # THE root cause: a directory can't be renamed while a process holds it as
    # its cwd, and the swap's cwd is inherited from the daemon living in the
    # install dir (RM reports no file locker — it isn't a handle). So the swap
    # must Set-Location away BEFORE the install->.old rename.
    assert "Set-Location $env:SystemRoot" in inner
    cwd_at = inner.index("Set-Location $env:SystemRoot")
    rename_at = inner.index('-Destination "C:\\Program Files\\ClaudeMnemos.old"')
    assert cwd_at < rename_at, "must leave the install cwd before renaming it"


def test_outer_leaves_install_cwd(outer: str) -> None:
    # The outer (and the swap it spawns, which inherits its cwd) must also not
    # sit in the install dir, or it blocks the rename just the same.
    assert "Set-Location $env:SystemRoot" in outer


def test_lockcheck_script_is_ascii_and_uses_restart_manager() -> None:
    s = update_apply.render_lockcheck_script()
    assert "RmGetList" in s and "RmStartSession" in s
    assert all(ord(c) < 128 for c in s)  # frozen exe reads no-BOM scripts as ANSI


def test_inner_restore_renames_old_back(inner: str) -> None:
    assert "catch" in inner
    assert (
        'Move-Item -LiteralPath "C:\\Program Files\\ClaudeMnemos.old" '
        '-Destination "C:\\Program Files\\ClaudeMnemos"' in inner
    )
    assert "OK 0.9.0" in inner
    assert "FAILED:" in inner


def test_inner_script_escapes_double_quotes_in_paths() -> None:
    inner = update_apply.render_inner_script(
        install_dir=Path(r'C:\My "Apps"\claude-mnemos'),
        old_dir=Path(r'C:\My "Apps"\claude-mnemos.old'),
        new_dir=Path(r'C:\My "Apps"\claude-mnemos.new'),
        zip_path=Path(r'C:\x\p.zip'),
        result_path=Path(r'C:\x\result.txt'),
        version="0.0.99",
    )
    # A raw unescaped " would terminate the PS string early. After escaping
    # (PowerShell uses backtick-quote inside double quotes) the escaped form must appear.
    assert '`"' in inner
    assert 'My `"Apps`"' in inner


# --------------------------------------------------------------------------
# render_outer_script  (UAC-cancel branch + relaunch + version-verify)
# --------------------------------------------------------------------------


@pytest.fixture
def outer() -> str:
    return update_apply.render_outer_script(
        install_dir=Path(r"C:\Program Files\ClaudeMnemos"),
        inner_path=Path(r"C:\Users\joe\.claude-mnemos\updates\0.9.0\swap.ps1"),
        old_dir=Path(r"C:\Program Files\ClaudeMnemos.old"),
        marker_path=Path(r"C:\Users\joe\.claude-mnemos\updates\swap.pending"),
        result_path=Path(r"C:\Users\joe\.claude-mnemos\updates\0.9.0\result.txt"),
        version="0.9.0",
        daemon_url="http://127.0.0.1:5757",
    )


def test_outer_elevates_and_waits(outer: str) -> None:
    assert "Start-Process powershell -Verb RunAs -Wait" in outer
    assert r"C:\Users\joe\.claude-mnemos\updates\0.9.0\swap.ps1" in outer


def test_outer_uac_cancel_branch(outer: str) -> None:
    # No result.txt -> swap never ran (UAC declined) -> drop marker, relaunch
    # old, return without a 'failed' verdict.
    assert r'if (-not (Test-Path -LiteralPath "C:\Users\joe\.claude-mnemos\updates\0.9.0\result.txt"))' in outer
    assert "return" in outer


def test_outer_relaunch_and_verify(outer: str) -> None:
    assert (
        'Start-Process -FilePath "C:\\Program Files\\ClaudeMnemos\\claude-mnemos.exe" '
        "-ArgumentList 'tray','run'" in outer
    )
    assert "http://127.0.0.1:5757/api/version" in outer
    assert "ConvertFrom-Json" in outer
    assert '-eq "0.9.0"' in outer
    assert "schtasks" not in outer


def test_outer_cleans_up_only_on_success(outer: str) -> None:
    assert "if ($ok)" in outer
    assert r'Remove-Item -LiteralPath "C:\Program Files\ClaudeMnemos.old"' in outer
    assert r'Remove-Item -LiteralPath "C:\Users\joe\.claude-mnemos\updates\swap.pending"' in outer


def test_outer_single_flight_lock(outer: str) -> None:
    # An exclusive (FileShare.None) handle next to the marker guards the whole
    # update, so a second relaunch bails (exit 0) instead of racing this swap on
    # the install dir. The acquire must come BEFORE the elevated swap so a loser
    # never kills/relaunches anything.
    assert r"C:\Users\joe\.claude-mnemos\updates\swap.lock" in outer
    assert "[IO.FileShare]::None" in outer
    lock_at = outer.index("swap.lock")
    swap_at = outer.index("Start-Process powershell -Verb RunAs -Wait")
    assert lock_at < swap_at, "the lock must be acquired before the swap is run"
    assert "$updLock.Close()" in outer


# --------------------------------------------------------------------------
# stage_update + spawn_updater
# --------------------------------------------------------------------------


def test_stage_update_writes_marker_and_scripts(monkeypatch) -> None:
    payload = _make_zip(["claude-mnemos.exe", "_internal/x"])
    monkeypatch.setattr(
        update_apply,
        "download_and_validate",
        lambda url, ver, *, opener=None: _zip_real(update_apply.updates_dir(), ver, payload),
    )
    work = update_apply.stage_update("https://example/portable.zip", "0.9.0")
    assert (work / "swap.ps1").read_text(encoding="utf-8")
    assert (work / "relaunch.ps1").read_text(encoding="utf-8")
    # The RM locker probe ships alongside so the inner swap can name a holder.
    assert "RmGetList" in (work / "lockcheck.ps1").read_text(encoding="utf-8")
    assert update_apply.pending_marker_path().exists()


def test_stage_update_refuses_when_in_progress(monkeypatch) -> None:
    monkeypatch.setattr(update_apply, "update_in_progress", lambda: True)
    with pytest.raises(UpdateApplyError):
        update_apply.stage_update("https://example/portable.zip", "0.9.0")


def test_stage_update_claims_marker_before_download(monkeypatch) -> None:
    order: list[str] = []
    monkeypatch.setattr(update_apply, "update_in_progress", lambda: False)

    def fake_marker(**kw):
        order.append("marker")
        return update_apply.pending_marker_path()

    def fake_download(asset_url, version):
        order.append("download")
        work = update_apply.updates_dir() / version
        work.mkdir(parents=True, exist_ok=True)
        return work / "portable.zip"

    monkeypatch.setattr(update_apply, "write_pending_marker", fake_marker)
    monkeypatch.setattr(update_apply, "download_and_validate", fake_download)
    monkeypatch.setattr(update_apply, "render_inner_script", lambda **k: "x")
    monkeypatch.setattr(update_apply, "render_outer_script", lambda **k: "x")
    update_apply.stage_update("https://example/p.zip", "0.0.99")
    assert order[0] == "marker", f"marker must be claimed before download, got {order}"


def test_stage_update_unlinks_marker_when_download_fails(monkeypatch) -> None:
    monkeypatch.setattr(update_apply, "update_in_progress", lambda: False)

    def fake_download(asset_url, version):
        raise UpdateApplyError("boom")

    monkeypatch.setattr(update_apply, "download_and_validate", fake_download)
    with pytest.raises(UpdateApplyError):
        update_apply.stage_update("https://example/p.zip", "0.0.99")
    # marker must NOT be left behind after a failed download
    assert not update_apply.pending_marker_path().exists()


def test_spawn_updater_direct_interactive(monkeypatch, tmp_path: Path) -> None:
    popen_calls: list[Any] = []
    run_calls: list[Any] = []

    monkeypatch.setattr(
        update_apply.subprocess,
        "Popen",
        lambda args, **kw: popen_calls.append((args, kw)),  # noqa: ANN001
    )
    monkeypatch.setattr(
        update_apply.subprocess,
        "run",
        lambda args, **kw: run_calls.append(args),  # noqa: ANN001
    )

    update_apply.spawn_updater(tmp_path)

    # Single direct child Popen of relaunch.ps1 — interactive session so the
    # outer's UAC prompt is visible. No WMI Win32_Process.Create wrapper.
    assert len(popen_calls) == 1
    args, _kw = popen_calls[0]
    cmd = " ".join(args)
    assert "relaunch.ps1" in cmd
    assert "-File" in args
    assert "Win32_Process" not in cmd
    assert run_calls == []


def _zip_real(updates: Path, version: str, payload: bytes) -> Path:
    work = updates / version
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / "portable.zip"
    zip_path.write_bytes(payload)
    return zip_path


# --------------------------------------------------------------------------
# _validate_version  (path-traversal hardening of the release tag)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["../evil", "a/b", "..\\x", "a b", "1.2/../3", ""])
def test_stage_update_rejects_unsafe_version(bad: str) -> None:
    with pytest.raises(update_apply.UpdateApplyError):
        update_apply._validate_version(bad)


@pytest.mark.parametrize("ok", ["0.0.56", "1.2.3", "0.0.56-rc1", "v0.0.1"])
def test_validate_version_accepts_normal_tags(ok: str) -> None:
    out = update_apply._validate_version(ok)
    assert out and "/" not in out and "\\" not in out and ".." not in out
