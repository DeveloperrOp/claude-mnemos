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


def test_main_only_runs_postinstall_for_tray_run(monkeypatch) -> None:
    """cli.main() must NOT call maybe_run_first_time_init for diagnostic
    subcommands (doctor, hook, hooks status, ingest, etc) — only for the
    primary `tray run` entry. Otherwise smoke tests / hook invocations
    spawn rogue tray processes before they can save first_run_ts.

    Regression: the bundled exe being invoked with `doctor` (e.g. by the
    PyInstaller smoke test) used to trigger the full init flow which
    spawned a detached tray subprocess that never got cleaned up,
    leaving ghost tray icons in the Windows notification area.
    """
    calls = {"postinstall": 0}

    def fake_postinstall():
        calls["postinstall"] += 1

    monkeypatch.setattr(
        "claude_mnemos.postinstall.maybe_run_first_time_init",
        fake_postinstall,
    )
    # Mock all command implementations so the test verifies ONLY the postinstall
    # gate, not actual command execution. Without this, `doctor` makes a live
    # HTTP request to the daemon and `tray run` would spawn real subprocesses.
    monkeypatch.setattr("claude_mnemos.cli_doctor._cmd_doctor", lambda args: 0)
    monkeypatch.setattr("claude_mnemos.cli_hook._cmd_hook", lambda args: 0)
    monkeypatch.setattr("claude_mnemos.cli_hooks._cmd_status", lambda args: 0)

    from claude_mnemos.cli import main

    # Diagnostic / non-app commands MUST NOT trigger postinstall.
    for argv in (["doctor"], ["hook", "session-start"], ["hooks", "status"]):
        try:
            main(argv)
        except SystemExit:
            pass
        except Exception:
            pass
    assert calls["postinstall"] == 0


def test_main_skips_postinstall_when_env_var_set(monkeypatch) -> None:
    """MNEMOS_SKIP_POSTINSTALL=1 disables the call even on `tray run`.

    CRITICAL: this test must NOT actually run the tray supervisor — it would
    spawn detached daemon + tray subprocesses that survive pytest exit and
    accumulate every time the suite runs. Mock cli_tray.run to a no-op.
    """
    calls = {"postinstall": 0}

    def fake_postinstall():
        calls["postinstall"] += 1

    monkeypatch.setattr(
        "claude_mnemos.postinstall.maybe_run_first_time_init",
        fake_postinstall,
    )
    monkeypatch.setattr("claude_mnemos.cli_tray.run", lambda argv: 0)
    monkeypatch.setenv("MNEMOS_SKIP_POSTINSTALL", "1")

    from claude_mnemos.cli import main
    try:
        main(["tray", "run"])
    except SystemExit:
        pass
    except Exception:
        pass
    assert calls["postinstall"] == 0
