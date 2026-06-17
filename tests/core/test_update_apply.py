"""Tests for core.update_apply (V2) — the one-click portable-zip self-updater.

ALL mocked. We never download, never spawn powershell, never taskkill. The real
end-to-end swap needs a live frozen install; here we assert on the generated
PowerShell TEXT to prove the safety design: validate+extract BEFORE any kill, an
atomic rename-based swap (never a per-file merge), a rename-back restore on
failure, a two-process model whose outer (non-elevated) relaunch + version-
checked verify removes the backup + clears the marker only on success.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

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


# --------------------------------------------------------------------------
# can_apply
# --------------------------------------------------------------------------


def test_can_apply_false_in_dev() -> None:
    ok, reason = update_apply.can_apply()
    assert ok is False
    assert isinstance(reason, str) and reason


# --------------------------------------------------------------------------
# download_and_extract  (validate + extract BEFORE anything is killed)
# --------------------------------------------------------------------------


def test_download_and_extract_valid_zip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(update_apply, "updates_dir", lambda: tmp_path / "updates")
    monkeypatch.setattr(update_apply, "current_install_dir", lambda: tmp_path / "Install")
    payload = _make_zip(["claude-mnemos.exe", "_internal/x"])

    work = update_apply.download_and_extract(
        "https://example/portable.zip", "0.9.0", opener=_opener_for(payload)
    )

    assert work.is_dir() and work.name == "0.9.0"
    assert (work / "portable.zip").exists()
    # The new build is extracted + validated up front.
    assert (work / "extract" / "claude-mnemos.exe").is_file()


def test_download_and_extract_rejects_non_zip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(update_apply, "updates_dir", lambda: tmp_path / "updates")
    monkeypatch.setattr(update_apply, "current_install_dir", lambda: tmp_path / "Install")
    with pytest.raises(UpdateApplyError):
        update_apply.download_and_extract(
            "https://example/portable.zip", "0.9.0", opener=_opener_for(b"nope")
        )


def test_download_and_extract_rejects_zip_without_exe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(update_apply, "updates_dir", lambda: tmp_path / "updates")
    monkeypatch.setattr(update_apply, "current_install_dir", lambda: tmp_path / "Install")
    payload = _make_zip(["_internal/x", "readme.txt"])
    with pytest.raises(UpdateApplyError):
        update_apply.download_and_extract(
            "https://example/portable.zip", "0.9.0", opener=_opener_for(payload)
        )


def test_download_and_extract_rejects_low_disk(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(update_apply, "updates_dir", lambda: tmp_path / "updates")
    monkeypatch.setattr(update_apply, "current_install_dir", lambda: tmp_path / "Install")

    class _Usage:
        free = 1  # 1 byte free -> always insufficient

    monkeypatch.setattr(update_apply.shutil, "disk_usage", lambda _p: _Usage())
    payload = _make_zip(["claude-mnemos.exe", "_internal/x"])
    with pytest.raises(UpdateApplyError):
        update_apply.download_and_extract(
            "https://example/portable.zip", "0.9.0", opener=_opener_for(payload)
        )


# --------------------------------------------------------------------------
# write_pending_marker
# --------------------------------------------------------------------------


def test_write_pending_marker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(update_apply, "updates_dir", lambda: tmp_path / "updates")
    marker = update_apply.write_pending_marker(
        version="0.9.0",
        install_dir=Path(r"C:\Install"),
        old_dir=Path(r"C:\Install.old"),
    )
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["version"] == "0.9.0"
    assert data["install_dir"] == r"C:\Install"
    assert data["old_dir"] == r"C:\Install.old"
    assert "started_at" in data


# --------------------------------------------------------------------------
# render_inner_script  (elevated: kill -> atomic rename swap -> restore-on-fail)
# --------------------------------------------------------------------------


@pytest.fixture
def inner() -> str:
    return update_apply.render_inner_script(
        install_dir=Path(r"C:\Program Files\ClaudeMnemos"),
        old_dir=Path(r"C:\Program Files\ClaudeMnemos.old"),
        extract_dir=Path(r"C:\Users\joe\.claude-mnemos\updates\0.9.0\extract"),
        result_path=Path(r"C:\Users\joe\.claude-mnemos\updates\0.9.0\result.txt"),
        version="0.9.0",
    )


def test_inner_error_action_stop(inner: str) -> None:
    assert '$ErrorActionPreference = "Stop"' in inner


def test_inner_kills_both_exes_with_wildcard_poll(inner: str) -> None:
    assert "taskkill /F /IM claude-mnemos.exe /T" in inner
    assert "taskkill /F /IM claude-mnemos-cli.exe /T" in inner
    # Wildcard poll matches BOTH claude-mnemos.exe and claude-mnemos-cli.exe.
    assert "Get-Process claude-mnemos*" in inner


def test_inner_atomic_rename_swap(inner: str) -> None:
    # Move the live install aside, then move the new build into place — renames,
    # not a per-file merge (so an interruption can't leave a frankenbuild).
    assert (
        'Move-Item -LiteralPath "C:\\Program Files\\ClaudeMnemos" '
        '-Destination "C:\\Program Files\\ClaudeMnemos.old"' in inner
    )
    assert (
        'Move-Item -LiteralPath "C:\\Users\\joe\\.claude-mnemos\\updates\\0.9.0\\extract" '
        '-Destination "C:\\Program Files\\ClaudeMnemos"' in inner
    )
    # No per-file copy tools for the swap.
    assert "robocopy" not in inner
    assert "/MIR" not in inner
    assert "/E " not in inner


def test_inner_sanity_gate(inner: str) -> None:
    assert r'Test-Path -LiteralPath "C:\Program Files\ClaudeMnemos\claude-mnemos.exe"' in inner
    assert "throw" in inner


def test_inner_restore_in_catch_is_rename_back(inner: str) -> None:
    assert "catch" in inner
    # Restore = rename the backed-up old tree back over the install path.
    assert (
        'Move-Item -LiteralPath "C:\\Program Files\\ClaudeMnemos.old" '
        '-Destination "C:\\Program Files\\ClaudeMnemos"' in inner
    )
    assert "OK 0.9.0" in inner
    assert "FAILED:" in inner
    assert "result.txt" in inner


def test_inner_has_no_scheduled_task(inner: str) -> None:
    # The relaunch lives in the outer (non-elevated) script, never via schtasks.
    assert "schtasks" not in inner


# --------------------------------------------------------------------------
# render_outer_script  (non-elevated: elevate+wait -> relaunch -> verify version)
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


def test_outer_elevates_and_waits_for_inner(outer: str) -> None:
    assert "Start-Process powershell -Verb RunAs -Wait" in outer
    assert r"C:\Users\joe\.claude-mnemos\updates\0.9.0\swap.ps1" in outer


def test_outer_relaunches_tray_as_user(outer: str) -> None:
    # Plain Start-Process as THIS (non-elevated) user — array ArgumentList, no
    # nested quoting, no scheduled task.
    assert (
        'Start-Process -FilePath "C:\\Program Files\\ClaudeMnemos\\claude-mnemos.exe" '
        "-ArgumentList 'tray','run'" in outer
    )
    assert "schtasks" not in outer


def test_outer_verifies_target_version(outer: str) -> None:
    assert "http://127.0.0.1:5757/api/version" in outer
    assert "ConvertFrom-Json" in outer
    assert '-eq "0.9.0"' in outer  # must match the TARGET version, not any 200


def test_outer_cleans_up_only_on_success(outer: str) -> None:
    # On success: drop the backup + clear the pending marker.
    assert r'Remove-Item -LiteralPath "C:\Program Files\ClaudeMnemos.old"' in outer
    assert r'Remove-Item -LiteralPath "C:\Users\joe\.claude-mnemos\updates\swap.pending"' in outer
    # Guarded by the $ok flag.
    assert "if ($ok)" in outer


# --------------------------------------------------------------------------
# stage_update  (writes marker + swap.ps1 + relaunch.ps1)
# --------------------------------------------------------------------------


def test_stage_update_writes_marker_and_both_scripts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(update_apply, "updates_dir", lambda: tmp_path / "updates")
    monkeypatch.setattr(update_apply, "current_install_dir", lambda: tmp_path / "Install")
    monkeypatch.setattr(update_apply, "current_username", lambda: "joe")
    payload = _make_zip(["claude-mnemos.exe", "_internal/x"])
    monkeypatch.setattr(
        update_apply,
        "download_and_extract",
        lambda url, ver, *, opener=None: _extract_real(tmp_path, ver, payload),
    )

    work = update_apply.stage_update("https://example/portable.zip", "0.9.0")

    assert work.is_dir()
    assert (work / "swap.ps1").read_text(encoding="utf-8")
    assert (work / "relaunch.ps1").read_text(encoding="utf-8")
    assert update_apply.pending_marker_path().exists()


def _extract_real(tmp_path: Path, version: str, payload: bytes) -> Path:
    work = tmp_path / "updates" / version
    (work / "extract").mkdir(parents=True, exist_ok=True)
    (work / "portable.zip").write_bytes(payload)
    (work / "extract" / "claude-mnemos.exe").write_bytes(b"x")
    return work
