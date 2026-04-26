import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "claude_mnemos", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_ingest_writes_page(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(FIXTURE), str(vault))
    assert res.returncode == 0, res.stderr
    page = vault / "raw" / "chats" / "abc-123.md"
    assert page.exists()
    assert "type: source" in page.read_text(encoding="utf-8")


def test_cli_missing_jsonl_returns_nonzero(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(tmp_path / "does-not-exist.jsonl"), str(vault))
    assert res.returncode != 0
    assert "not found" in (res.stderr + res.stdout).lower()


def test_cli_no_command_shows_help():
    res = _run()
    assert res.returncode != 0
    assert "ingest" in (res.stderr + res.stdout).lower()


def test_cli_empty_jsonl_returns_data_error(tmp_path: Path):
    vault = tmp_path / "vault"
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    res = _run("ingest", str(empty), str(vault))
    assert res.returncode == 65
    assert "empty transcript" in res.stderr.lower()


def test_main_module_safe_to_import():
    # Importing __main__ should NOT execute the CLI (must be guarded by __name__).
    import importlib

    # Even if previously imported, reimport should not raise.
    mod = importlib.import_module("claude_mnemos.__main__")
    assert hasattr(mod, "main")
