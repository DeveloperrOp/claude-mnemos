from pathlib import Path

import pytest

from claude_mnemos.ingest.pipeline import IngestResult, ingest_minimal

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def test_ingest_creates_source_page(tmp_path: Path):
    vault = tmp_path / "vault"
    result = ingest_minimal(FIXTURE, vault)

    assert isinstance(result, IngestResult)
    assert result.page_path.exists()
    assert result.page_path.is_relative_to(vault)
    assert result.page_path.name == "abc-123.md"
    assert result.page_path.parent == vault / "raw" / "chats"


def test_ingest_page_has_valid_frontmatter(tmp_path: Path):
    vault = tmp_path / "vault"
    result = ingest_minimal(FIXTURE, vault)
    text = result.page_path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "type: source" in text
    assert "title: " in text
    assert "Hello, what is 2+2?" in text  # body содержит транскрипт
    assert "2+2 equals 4." in text


def test_ingest_idempotent_overwrite(tmp_path: Path):
    vault = tmp_path / "vault"
    first = ingest_minimal(FIXTURE, vault)
    first_mtime = first.page_path.stat().st_mtime
    second = ingest_minimal(FIXTURE, vault)
    assert second.page_path == first.page_path
    assert second.page_path.stat().st_mtime >= first_mtime


def test_ingest_under_lock_blocks_concurrent(tmp_path: Path):
    # Если в этом vault уже стоит pipeline lock — ingest_minimal падает с LockTimeoutError.
    from claude_mnemos.core.locks import LockTimeoutError, pipeline_lock

    vault = tmp_path / "vault"
    vault.mkdir()
    with pipeline_lock(vault, timeout=1.0), pytest.raises(LockTimeoutError):
        ingest_minimal(FIXTURE, vault, lock_timeout=0.2)


def test_ingest_empty_jsonl_does_not_create_page(tmp_path: Path):
    from claude_mnemos.ingest.transcript import EmptyTranscriptError

    vault = tmp_path / "vault"
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(EmptyTranscriptError):
        ingest_minimal(empty, vault)
    # Vault не должен содержать никаких файлов кроме .pipeline.lock
    files = [p for p in vault.rglob("*") if p.is_file() and p.name != ".pipeline.lock"]
    assert files == []
