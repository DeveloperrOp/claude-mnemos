import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


@pytest.fixture
def project_env(tmp_path: Path) -> tuple[Path, dict]:
    """Set up an isolated ~/.claude-mnemos/ via HOME/USERPROFILE override and
    pre-register a project named "p" pointing at ``tmp_path / "vault"``.

    Returns (vault_path, env_dict) where env_dict is suitable for passing as
    the ``env=`` kwarg to subprocess.run().
    """
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("MNEMOS_VAULT_ROOT", None)
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)

    # Register the project via the CLI itself so the subprocess and the test
    # share the same on-disk project-map.
    res = subprocess.run(
        [
            sys.executable, "-m", "claude_mnemos",
            "project", "add", "--name", "p", "--vault", str(vault),
        ],
        capture_output=True, text=True, env=env, check=False,
    )
    assert res.returncode == 0, f"project add failed: {res.stderr}"
    return vault, env


def _run(*args: str, env: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "claude_mnemos", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_cli_no_llm_writes_raw_only(project_env):
    vault, env = project_env
    res = _run("ingest", str(FIXTURE), "--project", "p", "--no-llm", env=env)
    assert res.returncode == 0, res.stderr

    raw = vault / "raw" / "chats" / "abc-123.md"
    assert raw.exists()
    text = raw.read_text(encoding="utf-8")
    assert text.startswith("# Transcript")
    assert not (vault / "wiki").exists()
    assert (vault / ".manifest.json").exists()


def test_cli_no_llm_idempotent(project_env):
    vault, env = project_env
    first = _run("ingest", str(FIXTURE), "--project", "p", "--no-llm", env=env)
    assert first.returncode == 0
    second = _run("ingest", str(FIXTURE), "--project", "p", "--no-llm", env=env)
    assert second.returncode == 0
    assert "already_ingested" in (second.stdout + second.stderr).lower()


def test_cli_missing_jsonl_returns_nonzero(project_env, tmp_path):
    vault, env = project_env
    res = _run(
        "ingest", str(tmp_path / "does-not-exist.jsonl"),
        "--project", "p", "--no-llm",
        env=env,
    )
    assert res.returncode != 0
    assert "not found" in (res.stderr + res.stdout).lower()


def test_cli_no_command_shows_help():
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    res = subprocess.run(
        [sys.executable, "-m", "claude_mnemos"],
        capture_output=True, text=True, check=False, env=env,
    )
    assert res.returncode != 0
    assert "ingest" in (res.stderr + res.stdout).lower()


def test_cli_empty_jsonl_returns_data_error(project_env, tmp_path):
    vault, env = project_env
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    res = _run("ingest", str(empty), "--project", "p", "--no-llm", env=env)
    assert res.returncode == 65
    assert "empty transcript" in res.stderr.lower()


def test_cli_extract_without_api_key_returns_66(project_env):
    vault, env = project_env
    res = _run("ingest", str(FIXTURE), "--project", "p", env=env)
    assert res.returncode == 66
    assert "api" in res.stderr.lower() or "anthropic_api_key" in res.stderr.lower()


def test_cli_unknown_language_hint_returns_2(project_env):
    vault, env = project_env
    res = _run(
        "ingest", str(FIXTURE), "--project", "p",
        "--no-llm", "--language-hint", "klingon",
        env=env,
    )
    assert res.returncode == 2  # argparse choices reject


def test_main_module_safe_to_import():
    import importlib

    mod = importlib.import_module("claude_mnemos.__main__")
    assert hasattr(mod, "main")


def test_cli_no_llm_manifest_records_no_model(project_env):
    vault, env = project_env
    _run("ingest", str(FIXTURE), "--project", "p", "--no-llm", env=env)
    m = json.loads((vault / ".manifest.json").read_text(encoding="utf-8"))
    rec = next(iter(m["ingested"].values()))
    assert rec["model"] is None
    assert rec["source_path"] is None


def test_cli_dry_run_writes_nothing(project_env):
    """--dry-run with --no-llm should print 'dry_run' and write nothing to vault."""
    vault, env = project_env
    res = _run(
        "ingest", str(FIXTURE), "--project", "p", "--no-llm", "--dry-run",
        env=env,
    )
    assert res.returncode == 0
    assert "dry_run" in res.stdout.lower()
    assert not (vault / "raw").exists()
    assert not (vault / "wiki").exists()
    assert not (vault / ".manifest.json").exists()


def test_cli_no_llm_prints_snapshot_line(project_env):
    vault, env = project_env
    res = _run("ingest", str(FIXTURE), "--project", "p", "--no-llm", env=env)
    assert res.returncode == 0, res.stderr
    assert "snapshot:" in res.stdout.lower()
    # Snapshot path should reference .backups directory
    assert ".backups" in res.stdout


def test_cli_activity_lists_recent_entries(project_env):
    vault, env = project_env
    res_ingest = _run("ingest", str(FIXTURE), "--project", "p", "--no-llm", env=env)
    assert res_ingest.returncode == 0

    res_activity = _run("activity", "--project", "p", env=env)
    assert res_activity.returncode == 0, res_activity.stderr
    assert "ingest_raw_only" in res_activity.stdout


def test_cli_activity_limit(project_env):
    vault, env = project_env
    _run("ingest", str(FIXTURE), "--project", "p", "--no-llm", env=env)
    res = _run("activity", "--project", "p", "--limit", "0", env=env)
    assert res.returncode == 0
    assert "ingest_raw_only" in res.stdout


def test_cli_activity_empty_vault(project_env):
    vault, env = project_env
    res = _run("activity", "--project", "p", env=env)
    assert res.returncode == 0
    assert "no activity" in res.stdout.lower() or res.stdout.strip() == ""


def test_cli_undo_unknown_id_returns_77(project_env):
    vault, env = project_env
    _run("ingest", str(FIXTURE), "--project", "p", "--no-llm", env=env)

    res = _run("undo", "fake-id-doesnotexist", "--project", "p", env=env)
    assert res.returncode == 77
    assert "not found" in res.stderr.lower()


def test_cli_undo_last_no_undoable_returns_77(project_env):
    vault, env = project_env
    res = _run("undo", "--last", "--project", "p", env=env)
    assert res.returncode == 77
    assert "no undoable" in res.stderr.lower()


def test_cli_undo_last_succeeds_after_ingest(project_env):
    vault, env = project_env
    res_ingest = _run("ingest", str(FIXTURE), "--project", "p", "--no-llm", env=env)
    assert res_ingest.returncode == 0

    res_undo = _run("undo", "--last", "--project", "p", env=env)
    assert res_undo.returncode == 0, res_undo.stderr
    assert "undone" in res_undo.stdout.lower() or "restored" in res_undo.stdout.lower()

    log_text = (vault / ".activity.json").read_text(encoding="utf-8")
    log = json.loads(log_text)
    assert len(log["entries"]) == 2
    types = [e["operation_type"] for e in log["entries"]]
    assert "ingest_raw_only" in types
    assert "manual_restore" in types
    ingest_entry = next(e for e in log["entries"] if e["operation_type"] == "ingest_raw_only")
    assert ingest_entry["undone"] is True


def test_cli_undo_id_prefix_match(project_env):
    vault, env = project_env
    res_ingest = _run("ingest", str(FIXTURE), "--project", "p", "--no-llm", env=env)
    assert res_ingest.returncode == 0

    log = json.loads((vault / ".activity.json").read_text(encoding="utf-8"))
    full_id = log["entries"][0]["id"]
    short_prefix = full_id[:8]

    res_undo = _run("undo", short_prefix, "--project", "p", env=env)
    assert res_undo.returncode == 0, res_undo.stderr
