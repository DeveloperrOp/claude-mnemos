import pytest


def test_doctor_prints_ok_lines_when_all_pass(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "claude_mnemos.cli_doctor.check_claude_cli_installed",
        lambda: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.cli_doctor.check_hooks_present",
        lambda: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.cli_doctor._fetch_setup_status",
        lambda: {
            "all_ok": True,
            "claude_cli": {"status": "ok", "message": "ok"},
            "hooks": {"status": "ok", "message": "ok"},
            "vaults": {"status": "ok", "message": "ok"},
            "projects": {"status": "ok", "message": "ok", "count": 1},
        },
    )

    from claude_mnemos.cli_doctor import run

    rc = run()
    out = capsys.readouterr().out
    assert rc == 0
    assert "[OK]" in out
    assert "claude_cli" in out
    assert "hooks" in out


def test_doctor_returns_nonzero_when_any_fail(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "claude_mnemos.cli_doctor._fetch_setup_status",
        lambda: {
            "all_ok": False,
            "claude_cli": {"status": "critical", "message": "not installed"},
            "hooks": {"status": "ok", "message": "ok"},
            "vaults": {"status": "ok", "message": "ok"},
            "projects": {"status": "ok", "message": "ok", "count": 1},
        },
    )

    from claude_mnemos.cli_doctor import run

    rc = run()
    out = capsys.readouterr().out
    assert rc != 0
    assert "[FAIL]" in out or "[WARN]" in out
    assert "not installed" in out
