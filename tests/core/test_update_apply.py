"""Tests for core.update_apply — the one-click portable-zip self-updater.

ALL mocked. We never download, never spawn powershell, never taskkill.
The real end-to-end swap needs a live frozen install; here we assert on the
generated PowerShell TEXT to prove the safety invariant (backup-before-swap,
restore-on-failure) holds.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from claude_mnemos.core import update_apply
from claude_mnemos.core.update_apply import UpdateApplyError


def _make_zip(names: list[str]) -> bytes:
    """Build a real in-memory zip containing the given member names."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, b"x")
    return buf.getvalue()


class _FakeResponse:
    """A minimal file-like + context-manager standing in for urlopen()."""

    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    def __enter__(self) -> io.BytesIO:
        return self._buf

    def __exit__(self, *exc: object) -> None:
        self._buf.close()

    # Some callers use the response directly without a with-block.
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
    # Runs in the dev venv where runtime.is_frozen() is False.
    ok, reason = update_apply.can_apply()
    assert ok is False
    assert reason  # non-empty human-readable reason
    assert isinstance(reason, str)


# --------------------------------------------------------------------------
# download_and_stage
# --------------------------------------------------------------------------


def test_download_and_stage_valid_zip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(update_apply, "updates_dir", lambda: tmp_path / "updates")
    payload = _make_zip(["claude-mnemos.exe", "_internal/x"])

    zip_path = update_apply.download_and_stage(
        "https://example/portable.zip",
        "0.9.0",
        opener=_opener_for(payload),
    )

    assert zip_path.exists()
    assert zip_path.name == "portable.zip"
    assert zipfile.is_zipfile(zip_path)
    # Staged under updates_dir()/version/
    assert zip_path.parent.name == "0.9.0"


def test_download_and_stage_rejects_non_zip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(update_apply, "updates_dir", lambda: tmp_path / "updates")
    with pytest.raises(UpdateApplyError):
        update_apply.download_and_stage(
            "https://example/portable.zip",
            "0.9.0",
            opener=_opener_for(b"not a zip at all"),
        )


def test_download_and_stage_rejects_zip_without_exe(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(update_apply, "updates_dir", lambda: tmp_path / "updates")
    payload = _make_zip(["_internal/x", "readme.txt"])
    with pytest.raises(UpdateApplyError):
        update_apply.download_and_stage(
            "https://example/portable.zip",
            "0.9.0",
            opener=_opener_for(payload),
        )


# --------------------------------------------------------------------------
# render_updater_script
# --------------------------------------------------------------------------


@pytest.fixture
def rendered_script() -> str:
    return update_apply.render_updater_script(
        install_dir=Path(r"C:\Program Files\ClaudeMnemos"),
        work_dir=Path(r"C:\Users\joe\.claude-mnemos\updates\0.9.0"),
        zip_path=Path(r"C:\Users\joe\.claude-mnemos\updates\0.9.0\portable.zip"),
        username="joe",
        version="0.9.0",
        daemon_url="http://127.0.0.1:5757",
    )


def test_script_kills_both_exes(rendered_script: str) -> None:
    assert "taskkill /F /IM claude-mnemos.exe /T" in rendered_script
    assert "taskkill /F /IM claude-mnemos-cli.exe /T" in rendered_script


def test_script_backup_before_swap(rendered_script: str) -> None:
    # The backup robocopy must appear BEFORE the swap robocopy.
    backup_idx = rendered_script.index(r"\backup")
    extract_idx = rendered_script.index("Expand-Archive")
    swap_idx = rendered_script.index(r"\extract")
    assert backup_idx < extract_idx, "backup must precede extract/swap"
    # robocopy backup target
    assert r'robocopy "C:\Program Files\ClaudeMnemos"' in rendered_script
    assert r'\backup" /E' in rendered_script
    # The swap copies extract -> install dir
    assert swap_idx > backup_idx


def test_script_expand_archive(rendered_script: str) -> None:
    assert "Expand-Archive" in rendered_script
    assert r"portable.zip" in rendered_script
    assert r"\extract" in rendered_script


def test_script_sanity_gate(rendered_script: str) -> None:
    assert r"Test-Path" in rendered_script
    assert r"\extract\claude-mnemos.exe" in rendered_script
    assert "throw" in rendered_script


def test_script_swap_no_mirror(rendered_script: str) -> None:
    # robocopy extract -> install (the swap). Must NOT purge with /MIR.
    assert r'robocopy "C:\Users\joe\.claude-mnemos\updates\0.9.0\extract"' in rendered_script
    assert r'"C:\Program Files\ClaudeMnemos"' in rendered_script
    assert "/MIR" not in rendered_script


def test_script_relaunch_as_user(rendered_script: str) -> None:
    assert "schtasks /Create" in rendered_script
    assert "ClaudeMnemosRelaunch" in rendered_script
    assert "tray run" in rendered_script
    # Relaunched as the interactive user, not elevated.
    assert '/RU "joe"' in rendered_script
    assert "schtasks /Run" in rendered_script
    assert "schtasks /Delete" in rendered_script


def test_script_verify_version_endpoint(rendered_script: str) -> None:
    assert "Invoke-WebRequest" in rendered_script
    assert "http://127.0.0.1:5757/api/version" in rendered_script


def test_script_restore_in_catch(rendered_script: str) -> None:
    # The catch block restores backup -> install dir (the safety invariant).
    assert "catch" in rendered_script
    # restore robocopy: backup -> install
    assert r'robocopy "C:\Users\joe\.claude-mnemos\updates\0.9.0\backup"' in rendered_script
    restore_marker = r'\updates\0.9.0\backup" "C:\Program Files\ClaudeMnemos"'
    assert restore_marker in rendered_script
    # result.txt written on both paths
    assert "result.txt" in rendered_script
    assert "FAILED:" in rendered_script
    assert "OK 0.9.0" in rendered_script


def test_script_error_action_stop(rendered_script: str) -> None:
    assert '$ErrorActionPreference = "Stop"' in rendered_script


def test_script_interpolates_install_dir_and_username(rendered_script: str) -> None:
    assert r"C:\Program Files\ClaudeMnemos" in rendered_script
    assert "joe" in rendered_script


# --------------------------------------------------------------------------
# stage_update — writes updater.ps1 next to the staged zip
# --------------------------------------------------------------------------


def test_stage_update_writes_script(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(update_apply, "updates_dir", lambda: tmp_path / "updates")
    monkeypatch.setattr(
        update_apply, "current_install_dir", lambda: Path(r"C:\Install")
    )
    monkeypatch.setattr(update_apply, "current_username", lambda: "joe")
    payload = _make_zip(["claude-mnemos.exe", "_internal/x"])
    monkeypatch.setattr(
        update_apply,
        "download_and_stage",
        lambda url, ver, *, opener=None: _stage_real(
            tmp_path, ver, payload
        ),
    )

    work = update_apply.stage_update("https://example/portable.zip", "0.9.0")
    assert work.is_dir()
    script = (work / "updater.ps1").read_text(encoding="utf-8")
    assert "Expand-Archive" in script
    assert "joe" in script


def _stage_real(tmp_path: Path, version: str, payload: bytes) -> Path:
    work = tmp_path / "updates" / version
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / "portable.zip"
    zip_path.write_bytes(payload)
    return zip_path
