from unittest.mock import MagicMock

import pytest


def test_autostart_attempted_on_first_run_when_decision_none(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )

    attempts = {"count": 0}
    monkeypatch.setattr(
        "claude_mnemos.daemon.process._attempt_autostart_install",
        lambda: attempts.update({"count": attempts["count"] + 1}) or True,
    )

    from claude_mnemos.daemon.process import maybe_install_autostart_default

    maybe_install_autostart_default()
    assert attempts["count"] == 1

    # Re-run — decision now stored as "accepted", should NOT re-attempt.
    maybe_install_autostart_default()
    assert attempts["count"] == 1


def test_autostart_skipped_if_already_declined(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )
    from claude_mnemos.state.install_state import InstallState
    InstallState(autostart_decision="declined").save()

    attempts = {"count": 0}
    monkeypatch.setattr(
        "claude_mnemos.daemon.process._attempt_autostart_install",
        lambda: attempts.update({"count": attempts["count"] + 1}) or True,
    )

    from claude_mnemos.daemon.process import maybe_install_autostart_default
    maybe_install_autostart_default()
    assert attempts["count"] == 0
