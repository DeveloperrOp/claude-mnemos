from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from claude_mnemos.ingest.llm.auth import (
    AuthStatus,
    check_claude_cli_auth,
    find_claude_binary,
)


def _stub_completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_auth_status_dataclass() -> None:
    s = AuthStatus(installed=True, authenticated=True, binary_path="/usr/bin/claude")
    assert s.installed is True
    assert s.authenticated is True
    assert s.binary_path == "/usr/bin/claude"


def test_find_claude_binary_uses_shutil_which_first() -> None:
    with patch("claude_mnemos.ingest.llm.auth.shutil.which", return_value="/usr/bin/claude"):
        assert find_claude_binary() == Path("/usr/bin/claude")


def test_find_claude_binary_fallback_to_npm_global_on_windows(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    npm = tmp_path / "npm"
    npm.mkdir()
    fake = npm / "claude.cmd"
    fake.write_text("@echo fake\n")
    with patch("claude_mnemos.ingest.llm.auth.shutil.which", return_value=None), \
         patch("claude_mnemos.ingest.llm.auth.sys.platform", "win32"):
        result = find_claude_binary()
    assert result == fake


def test_find_claude_binary_returns_none_when_missing() -> None:
    with patch("claude_mnemos.ingest.llm.auth.shutil.which", return_value=None), \
         patch("claude_mnemos.ingest.llm.auth.sys.platform", "linux"):
        assert find_claude_binary() is None


def test_check_auth_when_binary_missing() -> None:
    with patch("claude_mnemos.ingest.llm.auth.find_claude_binary", return_value=None):
        s = check_claude_cli_auth()
    assert s.installed is False
    assert s.authenticated is False
    assert s.binary_path is None


def test_check_auth_version_succeeds_dry_run_succeeds() -> None:
    with patch("claude_mnemos.ingest.llm.auth.find_claude_binary",
               return_value=Path("/usr/bin/claude")), \
         patch("claude_mnemos.ingest.llm.auth.subprocess.run") as run:
        run.side_effect = [
            _stub_completed(0, stdout="2.1.0"),  # --version
            _stub_completed(0, stdout="ok"),     # dry test
        ]
        s = check_claude_cli_auth()
    assert s.installed is True
    assert s.authenticated is True


def test_check_auth_version_succeeds_dry_run_fails_with_auth_error() -> None:
    with patch("claude_mnemos.ingest.llm.auth.find_claude_binary",
               return_value=Path("/usr/bin/claude")), \
         patch("claude_mnemos.ingest.llm.auth.subprocess.run") as run:
        run.side_effect = [
            _stub_completed(0, stdout="2.1.0"),
            _stub_completed(1, stderr="not authenticated; run claude login"),
        ]
        s = check_claude_cli_auth()
    assert s.installed is True
    assert s.authenticated is False


def test_check_auth_version_fails() -> None:
    with patch("claude_mnemos.ingest.llm.auth.find_claude_binary",
               return_value=Path("/usr/bin/claude")), \
         patch("claude_mnemos.ingest.llm.auth.subprocess.run") as run:
        run.return_value = _stub_completed(1, stderr="binary corrupt")
        s = check_claude_cli_auth()
    assert s.installed is False
    assert s.authenticated is False
