"""Source-mode (git checkout) self-update detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos import runtime
from claude_mnemos.core import update_git


def test_repo_root_none_when_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "is_frozen", lambda: True)
    assert update_git.repo_root() is None
    assert update_git.can_git_pull() is False


def test_repo_root_when_source_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(runtime, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime, "bundle_root", lambda: tmp_path)
    assert update_git.repo_root() == tmp_path
    assert update_git.can_git_pull() is True


def test_repo_root_none_without_git_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runtime, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime, "bundle_root", lambda: tmp_path)
    assert update_git.repo_root() is None
    assert update_git.can_git_pull() is False


def test_git_pull_refuses_when_not_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(update_git, "repo_root", lambda: None)
    ok, msg = update_git.git_pull()
    assert ok is False
    assert "not a git checkout" in msg


def test_current_branch_falls_back_to_main(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(update_git, "_run", lambda *a, **k: (False, ""))
    assert update_git.current_branch(tmp_path) == "main"


def test_git_pull_targets_origin_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # No upstream needed: pull origin <branch> explicitly.
    monkeypatch.setattr(update_git, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(update_git, "current_branch", lambda root: "dev")
    seen: list[list[str]] = []

    def _fake(cmd: list[str], cwd: Path, timeout: float) -> tuple[bool, str]:
        seen.append(cmd)
        return True, "Already up to date."

    monkeypatch.setattr(update_git, "_run", _fake)
    ok, _ = update_git.git_pull()
    assert ok is True
    assert seen[-1] == ["git", "pull", "--ff-only", "origin", "dev"]


def test_display_version_uses_git_describe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(update_git, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(update_git, "_run", lambda *a, **k: (True, "v0.0.70-3-gabc\n"))
    assert update_git.display_version() == "v0.0.70-3-gabc"


def test_display_version_falls_back_when_not_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from claude_mnemos import __version__

    monkeypatch.setattr(update_git, "repo_root", lambda: None)
    assert update_git.display_version() == __version__
