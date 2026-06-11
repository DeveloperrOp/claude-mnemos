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
        "claude_mnemos.postinstall._silent_init",
        lambda: calls.update({"init": calls["init"] + 1}),
    )

    from claude_mnemos.postinstall import maybe_run_first_time_init
    maybe_run_first_time_init()
    assert calls["init"] == 1


def test_subsequent_launches_skip_init(state_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("claude_mnemos.postinstall.runtime.is_frozen", lambda: True)
    monkeypatch.setattr("claude_mnemos.postinstall._silent_init", lambda: None)

    from claude_mnemos.postinstall import maybe_run_first_time_init
    maybe_run_first_time_init()  # records first_run_ts

    calls = {"init": 0}
    monkeypatch.setattr(
        "claude_mnemos.postinstall._silent_init",
        lambda: calls.update({"init": calls["init"] + 1}),
    )
    maybe_run_first_time_init()
    assert calls["init"] == 0


def test_skipped_in_source_mode(state_path: Path, monkeypatch) -> None:
    """Source-mode (development via pipx) must NEVER auto-run init."""
    calls = {"init": 0}
    monkeypatch.setattr(
        "claude_mnemos.postinstall._silent_init",
        lambda: calls.update({"init": calls["init"] + 1}),
    )
    monkeypatch.setattr("claude_mnemos.postinstall.runtime.is_frozen", lambda: False)

    from claude_mnemos.postinstall import maybe_run_first_time_init
    maybe_run_first_time_init()
    assert calls["init"] == 0


def test_silent_init_does_not_open_browser_or_wait_for_daemon(
    state_path: Path, monkeypatch
) -> None:
    """Regression: the old impl called cli_init_run which spent up to 30s
    waiting for daemon health and then opened a browser. _silent_init must
    NOT do either — launcher's splash window handles both.
    """
    # Stub the two installs to no-ops — we only care whether the forbidden
    # side-effects fire. Stubbing _cmd_install is MANDATORY, not an
    # optimization: the real one reaches WindowsAutostart.install(), which
    # rewrites the user's REAL Startup\Mnemos.lnk to the current python on
    # every pytest run (the "dev-venv hijack" incident).
    hook_calls = {"n": 0}

    def _hook_install():
        hook_calls["n"] += 1
        return {"installed": []}

    monkeypatch.setattr("claude_mnemos.cli_hooks.install", _hook_install)

    tray_calls: list[bool] = []

    def _tray_install(*, spawn_tray: bool = True) -> int:
        tray_calls.append(spawn_tray)
        return 0

    monkeypatch.setattr("claude_mnemos.tray.__main__._cmd_install", _tray_install)

    # These must NOT be reached.
    def _boom_browser(*a, **kw):
        raise AssertionError("postinstall must not open a browser")

    def _boom_wait(*a, **kw):
        raise AssertionError("postinstall must not block on daemon health")

    monkeypatch.setattr("webbrowser.open", _boom_browser)
    monkeypatch.setattr("claude_mnemos.cli_init._wait_daemon_health", _boom_wait)

    from claude_mnemos.postinstall import _silent_init
    _silent_init()
    assert hook_calls["n"] == 1
    # Autostart was attempted (fresh state ⇒ not declined) — via the stub,
    # never the real Startup folder — and without spawning a second tray.
    assert tray_calls == [False]


def test_silent_init_skips_autostart_when_declined(state_path: Path, monkeypatch) -> None:
    """If the installer recorded autostart_decision='declined' (the "Start
    when I sign in" checkbox was unticked), first-run must NOT install
    autostart. Hooks are still installed as before."""
    from claude_mnemos.state.install_state import load_install_state

    state = load_install_state()
    state.autostart_decision = "declined"
    state.save()

    calls = []
    monkeypatch.setattr(
        "claude_mnemos.cli_hooks.install", lambda: calls.append("hooks"))
    monkeypatch.setattr(
        "claude_mnemos.tray.__main__._cmd_install",
        lambda spawn_tray: calls.append("tray") or 0)

    from claude_mnemos import postinstall
    errors = postinstall._silent_init()

    assert errors == []
    assert "hooks" in calls          # hooks are always installed
    assert "tray" not in calls       # autostart is not
    assert load_install_state().autostart_decision == "declined"  # not overwritten


def test_main_only_runs_postinstall_for_tray_run(monkeypatch) -> None:
    """cli.main() must NOT call maybe_run_first_time_init for diagnostic
    subcommands (doctor, hook, hooks status, ingest, etc) — only for the
    primary `tray run` / `launcher` entries. Otherwise smoke tests / hook
    invocations spawn rogue tray processes before they can save first_run_ts.
    """
    calls = {"postinstall": 0}

    def fake_postinstall():
        calls["postinstall"] += 1

    monkeypatch.setattr(
        "claude_mnemos.postinstall.maybe_run_first_time_init",
        fake_postinstall,
    )
    monkeypatch.setattr("claude_mnemos.cli_doctor._cmd_doctor", lambda args: 0)
    monkeypatch.setattr("claude_mnemos.cli_hook._cmd_hook", lambda args: 0)
    monkeypatch.setattr("claude_mnemos.cli_hooks._cmd_status", lambda args: 0)

    from claude_mnemos.cli import main

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


def test_main_runs_postinstall_for_launcher_command(monkeypatch) -> None:
    """`mnemos launcher` should also trigger postinstall (it's the new primary entry)."""
    calls = {"postinstall": 0}

    def fake_postinstall():
        calls["postinstall"] += 1

    monkeypatch.setattr(
        "claude_mnemos.postinstall.maybe_run_first_time_init",
        fake_postinstall,
    )
    monkeypatch.setattr("claude_mnemos.cli_launcher.run", lambda argv: 0)
    monkeypatch.delenv("MNEMOS_SKIP_POSTINSTALL", raising=False)

    from claude_mnemos.cli import main
    try:
        main(["launcher"])
    except SystemExit:
        pass
    except Exception:
        pass
    assert calls["postinstall"] == 1
