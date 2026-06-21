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
