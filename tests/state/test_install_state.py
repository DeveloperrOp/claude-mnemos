import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.state.install_state import InstallState, load_install_state


@pytest.fixture
def state_path(tmp_path: Path, monkeypatch) -> Path:
    p = tmp_path / "install-state.json"
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        p,
    )
    return p


def test_load_returns_default_when_file_missing(state_path: Path) -> None:
    s = load_install_state()
    assert s.first_run_ts is None
    assert s.autostart_decision is None
    assert s.first_session_celebrated_for == []


def test_save_then_load_roundtrip(state_path: Path) -> None:
    s = InstallState(
        first_run_ts=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        autostart_decision="accepted",
        first_session_celebrated_for=["proj-a", "proj-b"],
    )
    s.save()
    loaded = load_install_state()
    assert loaded.first_run_ts == s.first_run_ts
    assert loaded.autostart_decision == "accepted"
    assert loaded.first_session_celebrated_for == ["proj-a", "proj-b"]


def test_mark_celebrated_is_idempotent(state_path: Path) -> None:
    s = load_install_state()
    s.mark_celebrated("proj-x")
    s.mark_celebrated("proj-x")  # second call must not duplicate
    assert s.first_session_celebrated_for == ["proj-x"]
