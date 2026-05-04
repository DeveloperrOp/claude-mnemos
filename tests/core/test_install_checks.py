from pathlib import Path

import pytest

from claude_mnemos.core.install_checks import (
    check_claude_cli_installed,
    check_hooks_present,
    check_vault_writable,
)


def test_claude_cli_installed_when_present(monkeypatch) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.install_checks._which",
        lambda name: "/usr/bin/claude",
    )
    alert = check_claude_cli_installed()
    assert alert is None


def test_claude_cli_installed_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.install_checks._which",
        lambda name: None,
    )
    alert = check_claude_cli_installed()
    assert alert is not None
    assert alert.id == "claude_cli_not_installed"
    assert alert.severity == "critical"


def test_hooks_present_when_settings_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.install_checks.CLAUDE_SETTINGS",
        tmp_path / "missing.json",
    )
    alert = check_hooks_present()
    assert alert is not None
    assert alert.id == "hooks_not_installed"


def test_hooks_present_when_all_three_present(tmp_path: Path, monkeypatch) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(
        '{"hooks": {"SessionStart": [{"hooks":[{"command":"py claude_mnemos/hooks/session_start.py"}]}],'
        '          "SessionEnd":   [{"hooks":[{"command":"py claude_mnemos/hooks/session_end.py"}]}],'
        '          "PreCompact":   [{"hooks":[{"command":"py claude_mnemos/hooks/pre_compact.py"}]}]}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "claude_mnemos.core.install_checks.CLAUDE_SETTINGS",
        settings,
    )
    alert = check_hooks_present()
    assert alert is None


def test_hooks_present_when_partial(tmp_path: Path, monkeypatch) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(
        '{"hooks": {"SessionStart": [{"hooks":[{"command":"py claude_mnemos/hooks/session_start.py"}]}]}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "claude_mnemos.core.install_checks.CLAUDE_SETTINGS",
        settings,
    )
    alert = check_hooks_present()
    assert alert is not None
    assert alert.id == "hooks_partial"
    assert "SessionEnd" in alert.message
    assert "PreCompact" in alert.message


def test_vault_writable_when_writable(tmp_path: Path) -> None:
    alert = check_vault_writable([tmp_path])
    assert alert is None


def test_vault_writable_when_not_writable(tmp_path: Path, monkeypatch) -> None:
    bad = tmp_path / "bad"

    original_mkdir = Path.mkdir

    def fake_mkdir(self, *args, **kwargs):
        if self == bad:
            raise OSError("simulated permission denied")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)

    alert = check_vault_writable([bad])
    assert alert is not None
    assert alert.id == "vault_not_writable"
