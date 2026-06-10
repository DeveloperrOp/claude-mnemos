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


def test_iss_snapshots_lnk_before_old_uninstall_runs() -> None:
    """The old version's uninstaller deletes the .lnk (`tray uninstall` in its
    [UninstallRun]) — the existence check must happen in InitializeSetup,
    before UnInstallOldVersion."""
    text = _text()
    init_setup = text[text.index("function InitializeSetup")]
    assert "HadAutostartLnk" in text
    init_body = text[text.index("function InitializeSetup"):]
    assert init_body.index("HadAutostartLnk := FileExists") < init_body.index(
        "UnInstallOldVersion"
    ), "snapshot must precede the old-version uninstall"
    assert init_setup is not None


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
