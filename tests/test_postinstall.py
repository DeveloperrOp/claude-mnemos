from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def state_path(tmp_path: Path, monkeypatch) -> Path:
    p = tmp_path / "install-state.json"
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        p,
    )
    return p


def test_first_launch_triggers_init(state_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("claude_mnemos.postinstall.runtime.is_frozen", lambda: True)
    calls = {"init": 0}
    monkeypatch.setattr(
        "claude_mnemos.postinstall.cli_init_run",
        lambda *, open_browser: calls.update({"init": calls["init"] + 1}) or 0,
    )

    from claude_mnemos.postinstall import maybe_run_first_time_init
    maybe_run_first_time_init()
    assert calls["init"] == 1


def test_subsequent_launches_skip_init(state_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("claude_mnemos.postinstall.runtime.is_frozen", lambda: True)
    monkeypatch.setattr(
        "claude_mnemos.postinstall.cli_init_run",
        lambda *, open_browser: 0,
    )

    from claude_mnemos.postinstall import maybe_run_first_time_init
    maybe_run_first_time_init()  # records first_run_ts

    calls = {"init": 0}
    monkeypatch.setattr(
        "claude_mnemos.postinstall.cli_init_run",
        lambda *, open_browser: calls.update({"init": calls["init"] + 1}) or 0,
    )
    maybe_run_first_time_init()
    assert calls["init"] == 0


def test_skipped_in_source_mode(state_path: Path, monkeypatch) -> None:
    """Source-mode (development via pipx) must NEVER auto-run init."""
    calls = {"init": 0}
    monkeypatch.setattr(
        "claude_mnemos.postinstall.cli_init_run",
        lambda *, open_browser: calls.update({"init": calls["init"] + 1}) or 0,
    )
    monkeypatch.setattr("claude_mnemos.postinstall.runtime.is_frozen", lambda: False)

    from claude_mnemos.postinstall import maybe_run_first_time_init
    maybe_run_first_time_init()
    assert calls["init"] == 0
