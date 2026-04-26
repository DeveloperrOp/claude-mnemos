import json
import os
import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def _run(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Гарантируем что во всех тестах ANTHROPIC_API_KEY НЕ установлен по умолчанию.
    env.pop("ANTHROPIC_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "claude_mnemos", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_cli_no_llm_writes_raw_only(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    assert res.returncode == 0, res.stderr

    raw = vault / "raw" / "chats" / "abc-123.md"
    assert raw.exists()
    text = raw.read_text(encoding="utf-8")
    assert text.startswith("# Transcript")
    assert not (vault / "wiki").exists()
    assert (vault / ".manifest.json").exists()


def test_cli_no_llm_idempotent(tmp_path: Path):
    vault = tmp_path / "vault"
    first = _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    assert first.returncode == 0
    second = _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    assert second.returncode == 0
    assert "already_ingested" in (second.stdout + second.stderr).lower()


def test_cli_missing_jsonl_returns_nonzero(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(tmp_path / "does-not-exist.jsonl"), str(vault), "--no-llm")
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
    res = _run("ingest", str(empty), str(vault), "--no-llm")
    assert res.returncode == 65
    assert "empty transcript" in res.stderr.lower()


def test_cli_extract_without_api_key_returns_66(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(FIXTURE), str(vault))  # no --no-llm, no API key
    assert res.returncode == 66
    assert "api" in res.stderr.lower() or "anthropic_api_key" in res.stderr.lower()


def test_cli_unknown_language_hint_returns_2(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(FIXTURE), str(vault), "--no-llm", "--language-hint", "klingon")
    assert res.returncode == 2  # argparse choices reject


def test_main_module_safe_to_import():
    import importlib

    mod = importlib.import_module("claude_mnemos.__main__")
    assert hasattr(mod, "main")


def test_cli_no_llm_manifest_records_no_model(tmp_path: Path):
    vault = tmp_path / "vault"
    _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    m = json.loads((vault / ".manifest.json").read_text(encoding="utf-8"))
    rec = next(iter(m["ingested"].values()))
    assert rec["model"] is None
    assert rec["source_path"] is None


def test_cli_dry_run_writes_nothing(tmp_path: Path):
    """--dry-run with --no-llm should print 'dry_run' and write nothing to vault."""
    vault = tmp_path / "vault"
    res = _run("ingest", str(FIXTURE), str(vault), "--no-llm", "--dry-run")
    assert res.returncode == 0
    assert "dry_run" in res.stdout.lower()
    assert not (vault / "raw").exists()
    assert not (vault / "wiki").exists()
    assert not (vault / ".manifest.json").exists()


def test_cli_no_llm_prints_snapshot_line(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    assert res.returncode == 0, res.stderr
    assert "snapshot:" in res.stdout.lower()
    # Snapshot path should reference .backups directory
    assert ".backups" in res.stdout
