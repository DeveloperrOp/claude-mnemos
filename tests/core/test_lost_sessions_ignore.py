from __future__ import annotations

import json
from pathlib import Path

from claude_mnemos.core.lost_sessions import (
    IgnoredSessionDetails,
    LostSessionsIgnore,
    list_ignored_session_details,
    remove_from_ignore,
)


def _write_ignore(vault: Path, shas: list[str]) -> None:
    ignore_path = vault / ".lost-sessions-ignore.json"
    ignore_path.write_text(
        json.dumps({"version": 1, "ignored_shas": shas}), encoding="utf-8"
    )


def test_remove_from_ignore_removes_shas(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_ignore(vault, ["sha1", "sha2", "sha3"])
    updated, removed_count = remove_from_ignore(vault, ["sha1", "sha3"])
    assert removed_count == 2
    assert "sha1" not in updated.ignored_shas
    assert "sha3" not in updated.ignored_shas
    assert "sha2" in updated.ignored_shas


def test_remove_from_ignore_unknown_sha_is_noop(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_ignore(vault, ["sha1"])
    updated, removed_count = remove_from_ignore(vault, ["shaX"])
    assert removed_count == 0
    assert "sha1" in updated.ignored_shas


def test_remove_from_ignore_persists(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_ignore(vault, ["sha1", "sha2"])
    remove_from_ignore(vault, ["sha1"])
    reloaded = LostSessionsIgnore.load(vault)
    assert "sha1" not in reloaded.ignored_shas
    assert "sha2" in reloaded.ignored_shas


def test_remove_from_ignore_no_write_when_nothing_removed(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_ignore(vault, ["sha1"])
    ignore_path = vault / ".lost-sessions-ignore.json"
    mtime_before = ignore_path.stat().st_mtime
    remove_from_ignore(vault, ["nope"])
    mtime_after = ignore_path.stat().st_mtime
    assert mtime_before == mtime_after


def test_list_ignored_details_returns_sha(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_ignore(vault, ["aaabbbccc"])
    details = list_ignored_session_details(vault)
    assert len(details) == 1
    assert details[0].sha == "aaabbbccc"
    assert isinstance(details[0], IgnoredSessionDetails)


def test_list_ignored_details_empty(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    details = list_ignored_session_details(vault)
    assert details == []


def test_list_ignored_details_no_ignore_file(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    # No file at all — should return empty without error
    details = list_ignored_session_details(vault)
    assert details == []
