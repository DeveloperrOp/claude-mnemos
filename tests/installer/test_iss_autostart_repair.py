"""Text-level guards on installer/windows/mnemos.iss autostart repair.

The .iss is compiled by ISCC on CI only — these guards pin the [Code]
contracts that are invisible until a user upgrades with a stale Startup
shortcut (2026-06-10 incident: dev-venv .lnk held the single-instance
mutex, the installed exe exited silently).
"""

from __future__ import annotations

import re
from pathlib import Path

ISS = Path(__file__).resolve().parents[2] / "installer" / "windows" / "mnemos.iss"


def _text() -> str:
    return ISS.read_text(encoding="utf-8")


def test_iss_autostart_task_is_authoritative() -> None:
    """v0.0.48: the [Tasks] "autostart" checkbox is consumed in both
    directions — checked rewrites the .lnk in [Code], unchecked runs
    `tray uninstall` in [Run]. The old HadAutostartLnk "restore only if it
    existed" snapshot is gone (subsumed by checkedonce + the checkbox)."""
    text = _text()
    assert "HadAutostartLnk" not in text
    assert "WizardIsTaskSelected('autostart')" in text


def test_iss_run_tray_uninstall_precedes_launcher() -> None:
    """The unchecked-task `tray uninstall` [Run] entry must have NO
    postinstall flag (plain [Run] entries execute at end of install, before
    ssPostInstall; postinstall-flagged ones only after the Finish page) and
    must precede the launcher entry — the launcher triggers the exe's
    first-run postinstall, which must already see autostart_decision="declined"."""
    text = _text()
    uninstall_entry = re.search(
        r'^Filename: "\{app\}\\\{#MyAppExeName\}"; Parameters: "tray uninstall"; '
        r"Tasks: not autostart; Flags: runhidden\s*$",
        text,
        re.MULTILINE,
    )
    assert uninstall_entry is not None, "[Run] must consume the unchecked autostart task"
    launcher = text.index('Parameters: "launcher"; Description: "Start claude-mnemos now"')
    assert uninstall_entry.start() < launcher, "tray uninstall must precede the launcher"


def test_iss_rewrites_lnk_with_bare_subcommand() -> None:
    """The rewritten shortcut must use `tray run` — the bundled exe rejects
    the legacy `-m claude_mnemos.tray run` arguments with exit 2."""
    text = _text()
    assert re.search(r"Arguments\s*:=\s*'tray run'", text)
    assert "CurStep = ssPostInstall" in text


def test_iss_rewrite_failure_deletes_stale_lnk() -> None:
    """If WScript.Shell fails, the stale shortcut must be deleted — better no
    autostart than one that hijacks the single-instance mutex."""
    text = _text()
    rewrite = text[text.index("procedure RewriteAutostartLnk"):]
    body = rewrite[: rewrite.index("procedure CurStepChanged")]
    assert "except" in body
    assert "DeleteFile" in body


def test_iss_initialize_wizard_pre_unchecks_persisted_decline() -> None:
    """checkedonce task memory lives in the {AppId}_is1 registry key, which the
    recommended IDYES upgrade path wipes — UnInstallOldVersion runs the old
    uninstaller from InitializeSetup, BEFORE the wizard reads prior selections.
    InitializeWizard must therefore re-read the decline persisted in
    install-state.json and deselect the autostart task, otherwise a user who
    declined autostart silently gets it back on every recommended upgrade."""
    text = _text()
    assert "function AutostartPreviouslyDeclined" in text
    assert r"\.claude-mnemos\install-state.json" in text
    body = text[text.index("procedure InitializeWizard"):]
    body = body[: body.index("function InitializeSetup")]
    assert "AutostartPreviouslyDeclined" in body
    assert "WizardSelectTasks('!autostart')" in body


def test_iss_decline_probe_matches_real_serialization() -> None:
    """AutostartPreviouslyDeclined probes install-state.json with plain Pos()
    substring literals — pin them to what InstallState.save() actually writes
    (pydantic model_dump_json), so a serializer change (separator, key rename,
    enum value) can't silently disarm the pre-uncheck."""
    from claude_mnemos.state.install_state import InstallState

    serialized = InstallState(autostart_decision="declined").model_dump_json(indent=2)
    patterns = re.findall(r"Pos\('([^']*autostart_decision[^']*)'", _text())
    assert patterns, "AutostartPreviouslyDeclined must probe autostart_decision via Pos()"
    assert any(p in serialized for p in patterns), (
        f"no .iss Pos() literal matches the real serializer output:\n{serialized}"
    )
