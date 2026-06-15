import hashlib
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_mnemos.config import Config
from claude_mnemos.core.models import (
    WikiPage,
    WikiPageFrontmatter,
)
from claude_mnemos.ingest.extraction import ExtractionResult
from claude_mnemos.ingest.pipeline import ingest
from claude_mnemos.state.manifest import MANIFEST_FILENAME, Manifest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"
FIXED_TODAY = date(2026, 4, 26)


def _cfg() -> Config:
    return Config(
        api_key="sk-test",
        model="claude-sonnet-4-6",
        language_hint="auto",
        max_input_tokens=150_000,
        lock_timeout=60.0,
    )


def _stub_extraction(today: date) -> ExtractionResult:
    fm = WikiPageFrontmatter(
        title="FastAPI",
        type="entity",
        flavor=[],
        confidence=0.8,
        related=[],
        created=today,
        updated=today,
    )
    page = WikiPage(
        relative_path=Path("wiki/entities/fastapi.md"),
        frontmatter=fm,
        body="FastAPI is a framework.",
    )
    return ExtractionResult(
        summary="Talked about FastAPI.",
        skipped_reason=None,
        pages=[page],
        input_tokens=1000,
        output_tokens=200,
    )


def _stub_extractor():
    """Returns a callable matching extract_wiki_pages signature."""
    def _extract(*, messages, cfg, llm_client, today, chunk_extract=False):  # noqa: ARG001
        return _stub_extraction(today)
    return _extract


def test_ingest_writes_plain_raw_chat(tmp_path: Path):
    vault = tmp_path / "vault"
    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    raw = vault / "raw" / "chats" / "abc-123.md"
    assert raw.exists()
    text = raw.read_text(encoding="utf-8")
    # Plain transcript: no YAML frontmatter
    assert not text.startswith("---")
    assert text.startswith("# Transcript")
    assert "## user" in text
    assert "Hello, what is 2+2?" in text


def test_ingest_writes_source_page(tmp_path: Path):
    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    assert res.source_path is not None
    assert res.source_path.name == "2026-04-26-abc-123.md"
    assert res.source_path.parent == vault / "wiki" / "sources"
    text = res.source_path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "type: source" in text
    assert "Talked about FastAPI." in text  # summary in body
    assert "[[fastapi]]" in text


def test_ingest_writes_extracted_pages(tmp_path: Path):
    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    page = vault / "wiki" / "entities" / "fastapi.md"
    assert page.exists()
    assert "type: entity" in page.read_text(encoding="utf-8")
    assert page.as_posix().endswith("wiki/entities/fastapi.md")
    assert any("wiki/entities/fastapi.md" in p.as_posix() for p in res.created_pages)


def test_ingest_creates_manifest_entry(tmp_path: Path):
    vault = tmp_path / "vault"
    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    m = Manifest.load(vault)
    expected_sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert expected_sha in m.ingested
    rec = m.ingested[expected_sha]
    assert rec.session_id == "abc-123"
    assert rec.source_path is not None
    assert rec.input_tokens == 1000


def test_ingest_idempotent_on_repeat(tmp_path: Path):
    vault = tmp_path / "vault"
    extractor = MagicMock(side_effect=_stub_extractor())

    first = ingest(
        FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor,
        today=FIXED_TODAY,
    )
    assert first.status == "extracted"

    second = ingest(
        FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor,
        today=FIXED_TODAY,
    )
    assert second.status == "already_ingested"
    # Extractor called only once — second was a no-op
    assert extractor.call_count == 1


def test_ingest_dry_run_writes_nothing(tmp_path: Path):
    vault = tmp_path / "vault"
    extractor = MagicMock(side_effect=_stub_extractor())

    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=extractor,
        dry_run=True,
        today=FIXED_TODAY,
    )
    assert res.status == "dry_run"
    # Extractor was called (we exercise the prompt path)
    assert extractor.call_count == 1
    # No files written (vault dir itself may exist from mkdir, but no content)
    assert not (vault / "raw").exists()
    assert not (vault / "wiki").exists()
    assert not (vault / MANIFEST_FILENAME).exists()


def test_ingest_no_llm_writes_only_raw_and_manifest(tmp_path: Path):
    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=None,
        extractor=None,
        extract=False,
        today=FIXED_TODAY,
    )
    assert res.status == "raw_only"
    assert res.source_path is None
    assert (vault / "raw" / "chats" / "abc-123.md").exists()
    assert not (vault / "wiki").exists()

    m = Manifest.load(vault)
    sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert m.ingested[sha].source_path is None
    assert m.ingested[sha].model is None


def test_ingest_raw_only_populates_transcript_path_and_bytes(tmp_path: Path):
    """raw_only ingest must populate transcript_path + raw_transcript_bytes in manifest."""
    vault = tmp_path / "vault"
    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=None,
        extractor=None,
        extract=False,
        today=FIXED_TODAY,
    )
    m = Manifest.load(vault)
    sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    rec = m.ingested[sha]
    assert rec.transcript_path == str(FIXTURE.resolve())
    assert rec.raw_transcript_bytes == FIXTURE.stat().st_size


def test_ingest_extracted_populates_transcript_path_and_bytes(tmp_path: Path):
    """LLM-extract ingest must populate transcript_path + raw_transcript_bytes in manifest."""
    vault = tmp_path / "vault"
    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    m = Manifest.load(vault)
    sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    rec = m.ingested[sha]
    assert rec.transcript_path == str(FIXTURE.resolve())
    assert rec.raw_transcript_bytes == FIXTURE.stat().st_size


def test_ingest_skips_existing_extracted_page(tmp_path: Path):
    vault = tmp_path / "vault"
    # Pre-create the file the stub extractor wants to write
    target = vault / "wiki" / "entities" / "fastapi.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("---\ntitle: existing\n---\nbody", encoding="utf-8")

    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    # Existing file is preserved
    assert "existing" in target.read_text(encoding="utf-8")
    # And it's reported as a collision
    assert any("wiki/entities/fastapi.md" in p for p in res.skipped_collisions)


def test_ingest_under_lock_blocks_concurrent(tmp_path: Path):
    from claude_mnemos.core.locks import LockTimeoutError, pipeline_lock

    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = _cfg().with_overrides(lock_timeout=0.2)
    with pipeline_lock(vault, timeout=1.0), pytest.raises(LockTimeoutError):
        ingest(
            FIXTURE,
            vault,
            cfg=cfg,
            llm_client=MagicMock(),
            extractor=_stub_extractor(),
            today=FIXED_TODAY,
        )


def test_ingest_source_page_collision_hard_fails(tmp_path: Path):
    """Stale source-page file at target must not be silently overwritten/skipped — fail loud."""
    vault = tmp_path / "vault"
    target = vault / "wiki" / "sources" / "2026-04-26-abc-123.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("---\ntitle: stale\n---\nold body", encoding="utf-8")

    with pytest.raises(FileExistsError):
        ingest(
            FIXTURE,
            vault,
            cfg=_cfg(),
            llm_client=MagicMock(),
            extractor=_stub_extractor(),
            today=FIXED_TODAY,
        )

    # Stale file must be preserved
    assert "stale" in target.read_text(encoding="utf-8")
    # Manifest must NOT contain a record for this sha (we failed before saving)
    assert not (vault / ".manifest.json").exists()


def test_ingest_source_page_wikilinks_use_shortest_slug(tmp_path: Path):
    """Source page wikilinks must match the shortest-slug style used by LLM-extracted pages."""
    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    text = res.source_path.read_text(encoding="utf-8")
    # Stem-style:
    assert "[[fastapi]]" in text
    # Old full-path style must be gone:
    assert "[[wiki/entities/fastapi]]" not in text
    # Backlink to raw uses session_id stem with alias:
    assert "[[abc-123|Open transcript]]" in text


def test_ingest_empty_jsonl_does_not_create_vault(tmp_path: Path):
    from claude_mnemos.ingest.transcript import EmptyTranscriptError

    vault = tmp_path / "vault"
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(EmptyTranscriptError):
        ingest(
            empty,
            vault,
            cfg=_cfg(),
            llm_client=MagicMock(),
            extractor=_stub_extractor(),
            today=FIXED_TODAY,
        )
    assert not vault.exists()


def test_ingest_extracted_returns_snapshot_path(tmp_path: Path):
    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    assert res.snapshot_path is not None
    assert res.snapshot_path.exists()
    assert res.snapshot_path.is_dir()
    assert res.snapshot_path.parent == vault / ".backups"


def test_ingest_no_llm_returns_snapshot_path(tmp_path: Path):
    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=None,
        extractor=None,
        extract=False,
        today=FIXED_TODAY,
    )
    assert res.snapshot_path is not None
    assert res.snapshot_path.exists()


def test_ingest_dry_run_no_snapshot(tmp_path: Path):
    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        dry_run=True,
        today=FIXED_TODAY,
    )
    assert res.snapshot_path is None
    # Dry run rejects staging → goes to .trash
    rejected = list((vault / ".trash").glob("rejected-abc-123-*"))
    assert len(rejected) == 1


def test_ingest_already_ingested_no_snapshot(tmp_path: Path):
    vault = tmp_path / "vault"
    extractor = MagicMock(side_effect=_stub_extractor())
    first = ingest(
        FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor,
        today=FIXED_TODAY,
    )
    assert first.snapshot_path is not None

    second = ingest(
        FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor,
        today=FIXED_TODAY,
    )
    assert second.status == "already_ingested"
    assert second.snapshot_path is None  # no new snapshot for no-op


def test_ingest_cleans_up_staging_on_success(tmp_path: Path):
    vault = tmp_path / "vault"
    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    # .staging/ должен быть либо удалён целиком, либо пуст
    staging = vault / ".staging"
    if staging.exists():
        assert list(staging.iterdir()) == []


def test_ingest_promote_failure_restores_vault(tmp_path: Path, monkeypatch):
    vault = tmp_path / "vault"
    # Pre-populate vault with one extracted page
    vault.mkdir()
    (vault / "wiki" / "concepts").mkdir(parents=True)
    (vault / "wiki" / "concepts" / "preserved.md").write_text("survives", encoding="utf-8")

    import shutil as _shutil
    real_move = _shutil.move
    calls = {"n": 0}

    def flaky_move(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("simulated mid-promote failure")
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr("claude_mnemos.core.staging.shutil.move", flaky_move)

    from claude_mnemos.core.staging import StagingPromoteError

    with pytest.raises(StagingPromoteError):
        ingest(
            FIXTURE,
            vault,
            cfg=_cfg(),
            llm_client=MagicMock(),
            extractor=_stub_extractor(),
            today=FIXED_TODAY,
        )

    # Pre-existing file must survive
    assert (vault / "wiki" / "concepts" / "preserved.md").read_text(encoding="utf-8") == "survives"
    # No partially-written ingest pages in vault
    assert not (vault / "raw" / "chats" / "abc-123.md").exists()
    assert not (vault / "wiki" / "entities" / "fastapi.md").exists()
    # Manifest must NOT be updated (we rolled back)
    if (vault / ".manifest.json").exists():
        import json as _json
        m = _json.loads((vault / ".manifest.json").read_text(encoding="utf-8"))
        assert m["ingested"] == {}


def test_ingest_extracted_writes_activity_entry(tmp_path: Path):
    from claude_mnemos.state.activity import ActivityLog

    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )

    assert res.activity_id is not None

    log = ActivityLog.load(vault)
    assert len(log.entries) == 1
    entry = log.entries[0]
    assert entry.id == res.activity_id
    assert entry.operation_type == "ingest_extracted"
    assert entry.can_undo is True
    assert entry.snapshot_path is not None
    assert (vault / entry.snapshot_path).is_dir()
    assert (vault / entry.snapshot_path) == res.snapshot_path
    assert any("wiki/entities/fastapi.md" in p for p in entry.affected_pages)
    assert entry.metadata.get("session_id") == "abc-123"


def test_ingest_no_llm_writes_activity_entry(tmp_path: Path):
    from claude_mnemos.state.activity import ActivityLog

    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=None,
        extractor=None,
        extract=False,
        today=FIXED_TODAY,
    )

    assert res.activity_id is not None
    log = ActivityLog.load(vault)
    assert len(log.entries) == 1
    entry = log.entries[0]
    assert entry.operation_type == "ingest_raw_only"
    assert entry.can_undo is True
    assert entry.snapshot_path is not None


def test_ingest_already_ingested_no_activity_entry(tmp_path: Path):
    """Re-ingesting same JSONL must not append a duplicate activity entry."""
    from claude_mnemos.state.activity import ActivityLog

    vault = tmp_path / "vault"
    extractor = MagicMock(side_effect=_stub_extractor())
    ingest(
        FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor,
        today=FIXED_TODAY,
    )
    second = ingest(
        FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor,
        today=FIXED_TODAY,
    )

    assert second.status == "already_ingested"
    assert second.activity_id is None

    log = ActivityLog.load(vault)
    assert len(log.entries) == 1


def test_ingest_dry_run_no_activity_entry(tmp_path: Path):
    """Dry-run must not append a permanent activity entry (staging gets rejected)."""
    from claude_mnemos.state.activity import ACTIVITY_FILENAME

    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        dry_run=True,
        today=FIXED_TODAY,
    )

    assert res.activity_id is None
    assert not (vault / ACTIVITY_FILENAME).exists()


def test_ingest_promote_failure_no_activity_entry(tmp_path: Path, monkeypatch):
    """Failed promote leaves vault unchanged AND no activity entry."""
    from claude_mnemos.state.activity import ACTIVITY_FILENAME

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "preexisting.md").write_text("survives", encoding="utf-8")

    import shutil as _shutil
    real_move = _shutil.move
    calls = {"n": 0}

    def flaky_move(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("simulated mid-promote failure")
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr("claude_mnemos.core.staging.shutil.move", flaky_move)

    from claude_mnemos.core.staging import StagingPromoteError

    with pytest.raises(StagingPromoteError):
        ingest(
            FIXTURE,
            vault,
            cfg=_cfg(),
            llm_client=MagicMock(),
            extractor=_stub_extractor(),
            today=FIXED_TODAY,
        )

    assert (vault / "preexisting.md").read_text(encoding="utf-8") == "survives"
    assert not (vault / ACTIVITY_FILENAME).exists()


def test_ingest_forwards_chunk_extract_to_extractor(tmp_path: Path):
    """``chunk_extract`` must be forwarded into the extractor call (Task 9)."""
    vault = tmp_path / "vault"
    seen: dict = {}

    def _extract(*, messages, cfg, llm_client, today, chunk_extract=False):  # noqa: ARG001
        seen["chunk_extract"] = chunk_extract
        return _stub_extraction(today)

    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_extract,
        today=FIXED_TODAY,
        chunk_extract=True,
    )
    assert seen["chunk_extract"] is True


def test_ingest_defaults_chunk_extract_false(tmp_path: Path):
    """Default forwards chunk_extract=False — backward compatible (Task 9)."""
    vault = tmp_path / "vault"
    seen: dict = {}

    def _extract(*, messages, cfg, llm_client, today, chunk_extract=False):  # noqa: ARG001
        seen["chunk_extract"] = chunk_extract
        return _stub_extraction(today)

    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_extract,
        today=FIXED_TODAY,
    )
    assert seen["chunk_extract"] is False
