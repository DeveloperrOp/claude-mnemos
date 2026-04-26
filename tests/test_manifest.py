from datetime import datetime
from pathlib import Path

import pytest

from claude_mnemos.state.manifest import (
    IngestRecord,
    Manifest,
    ManifestCorruptError,
)


def _record(sid: str = "abc") -> IngestRecord:
    return IngestRecord(
        session_id=sid,
        ingested_at=datetime(2026, 4, 26, 14, 30, 0),
        raw_path=f"raw/chats/{sid}.md",
        source_path=f"wiki/sources/2026-04-26-{sid}.md",
        created_pages=[
            f"wiki/sources/2026-04-26-{sid}.md",
            "wiki/entities/foo.md",
        ],
        skipped_collisions=[],
        model="claude-sonnet-4-6",
        input_tokens=1234,
        output_tokens=456,
    )


def test_load_missing_file_returns_empty_manifest(tmp_path: Path):
    m = Manifest.load(tmp_path)
    assert m.version == 1
    assert m.ingested == {}


def test_save_then_load_roundtrip(tmp_path: Path):
    m = Manifest()
    m.add("sha-1", _record("sid-1"))
    m.save(tmp_path)

    assert (tmp_path / ".manifest.json").exists()

    loaded = Manifest.load(tmp_path)
    assert "sha-1" in loaded.ingested
    assert loaded.ingested["sha-1"].session_id == "sid-1"
    assert loaded.ingested["sha-1"].input_tokens == 1234


def test_load_corrupt_json_raises(tmp_path: Path):
    (tmp_path / ".manifest.json").write_text("not json {", encoding="utf-8")
    with pytest.raises(ManifestCorruptError):
        Manifest.load(tmp_path)


def test_load_invalid_schema_raises(tmp_path: Path):
    (tmp_path / ".manifest.json").write_text(
        '{"version": 1, "ingested": {"x": {"unknown_field": 1}}}',
        encoding="utf-8",
    )
    with pytest.raises(ManifestCorruptError):
        Manifest.load(tmp_path)


def test_load_unknown_top_level_field_raises(tmp_path: Path):
    (tmp_path / ".manifest.json").write_text(
        '{"version": 1, "ingested": {}, "unknown": 1}',
        encoding="utf-8",
    )
    with pytest.raises(ManifestCorruptError):
        Manifest.load(tmp_path)


def test_add_duplicate_sha_raises():
    m = Manifest()
    m.add("sha-1", _record())
    with pytest.raises(ValueError):
        m.add("sha-1", _record())


def test_save_uses_atomic_write_no_partial_file(tmp_path: Path, monkeypatch):
    m = Manifest()
    m.add("sha-1", _record())

    def boom(*args, **kwargs):
        raise RuntimeError("simulated mid-write crash")

    monkeypatch.setattr("claude_mnemos.core.atomic.os.replace", boom)
    with pytest.raises(RuntimeError):
        m.save(tmp_path)

    leftovers = list(tmp_path.glob(".manifest.json*"))
    assert leftovers == []


def test_record_with_none_for_no_llm_path(tmp_path: Path):
    rec = IngestRecord(
        session_id="sid-x",
        ingested_at=datetime(2026, 4, 26, 14, 30, 0),
        raw_path="raw/chats/sid-x.md",
        source_path=None,
        created_pages=["raw/chats/sid-x.md"],
        skipped_collisions=[],
        model=None,
        input_tokens=None,
        output_tokens=None,
    )
    m = Manifest()
    m.add("sha-x", rec)
    m.save(tmp_path)

    loaded = Manifest.load(tmp_path)
    assert loaded.ingested["sha-x"].source_path is None
    assert loaded.ingested["sha-x"].model is None


def test_serialize_to_string_matches_save_output(tmp_path: Path):
    """serialize_to_string() must produce identical bytes to save() writes to disk."""
    m = Manifest()
    m.add("sha-x", _record("sid-x"))

    serialized = m.serialize_to_string()

    m.save(tmp_path)
    on_disk = (tmp_path / ".manifest.json").read_text(encoding="utf-8")

    assert serialized == on_disk


def test_serialize_to_string_roundtrip_via_model_validate_json():
    import json as _json

    m = Manifest()
    m.add("sha-y", _record("sid-y"))

    out = m.serialize_to_string()
    parsed = _json.loads(out)
    reloaded = Manifest.model_validate(parsed)

    assert "sha-y" in reloaded.ingested
    assert reloaded.ingested["sha-y"].session_id == "sid-y"
