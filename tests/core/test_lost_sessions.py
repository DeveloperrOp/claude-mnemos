"""Tests for `claude_mnemos.core.lost_sessions` — scanner + ignore list + cache."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.core.lost_sessions import (
    LOST_SESSIONS_IGNORE_FILENAME,
    LostSession,
    LostSessionsCache,
    LostSessionsIgnore,
    add_to_ignore,
    scan_lost_sessions,
)
from claude_mnemos.core.transcript_helpers import _extract_cwd_and_preview
from claude_mnemos.state.manifest import IngestRecord, Manifest


def _write_jsonl(root: Path, name: str, content: bytes) -> tuple[Path, str]:
    """Write a jsonl file under ``root`` and return (path, sha256_hex)."""
    path = root / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    return path, sha


def _ingest_record(sid: str) -> IngestRecord:
    return IngestRecord(
        session_id=sid,
        ingested_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
        raw_path=f"raw/chats/{sid}.md",
        source_path=None,
        created_pages=[],
        skipped_collisions=[],
        model=None,
        input_tokens=None,
        output_tokens=None,
    )


def test_scan_empty_transcripts_root_returns_empty(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()

    assert scan_lost_sessions(vault, transcripts_root=transcripts_root) == []


def test_scan_nonexistent_transcripts_root_returns_empty(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    missing_root = tmp_path / "does-not-exist"

    assert scan_lost_sessions(vault, transcripts_root=missing_root) == []


def test_scan_all_in_manifest_returns_empty(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()

    manifest = Manifest()
    for i, content in enumerate([b"alpha-content\n", b"beta-content\n", b"gamma\n"]):
        _, sha = _write_jsonl(transcripts_root / f"proj-{i}", f"sess-{i}", content)
        manifest.add(sha, _ingest_record(f"sess-{i}"))
    manifest.save(vault)

    assert scan_lost_sessions(vault, transcripts_root=transcripts_root) == []


def test_scan_one_lost_returns_single_entry(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()

    payload_a = b"already-ingested-a\n"
    payload_b = b"already-ingested-b\n"
    payload_lost = b"lost-content-blob\n"

    path_a, sha_a = _write_jsonl(transcripts_root / "proj-a", "sess-a", payload_a)
    path_b, sha_b = _write_jsonl(transcripts_root / "proj-b", "sess-b", payload_b)
    path_lost, sha_lost = _write_jsonl(
        transcripts_root / "proj-lost", "sess-lost", payload_lost
    )

    manifest = Manifest()
    manifest.add(sha_a, _ingest_record("sess-a"))
    manifest.add(sha_b, _ingest_record("sess-b"))
    manifest.save(vault)

    result = scan_lost_sessions(vault, transcripts_root=transcripts_root)
    assert len(result) == 1
    entry = result[0]
    assert isinstance(entry, LostSession)
    assert entry.session_id == "sess-lost"
    assert entry.sha == sha_lost
    assert entry.transcript_path == str(path_lost.resolve())
    assert entry.size_bytes == len(payload_lost)
    assert entry.mtime.tzinfo is not None
    # Path/sha are unrelated to ingested ones.
    assert entry.sha != sha_a
    assert entry.sha != sha_b
    # Make sure ignored ones not present.
    assert path_a.exists() and path_b.exists()


def test_scan_respects_ignore_list(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()

    payload_lost = b"lost-content-blob\n"
    payload_ignored = b"some-ignored-blob\n"

    _write_jsonl(transcripts_root / "proj-lost", "sess-lost", payload_lost)
    _, sha_ignored = _write_jsonl(
        transcripts_root / "proj-ignored", "sess-ignored", payload_ignored
    )

    Manifest().save(vault)

    ignore = LostSessionsIgnore(ignored_shas={sha_ignored})
    ignore.save(vault)

    result = scan_lost_sessions(vault, transcripts_root=transcripts_root)
    assert len(result) == 1
    assert result[0].session_id == "sess-lost"


def test_ignore_save_load_round_trip_and_corrupt_raises(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    # Empty default when file missing.
    loaded = LostSessionsIgnore.load(vault)
    assert loaded.version == 1
    assert loaded.ignored_shas == set()

    # Round trip with content.
    original = LostSessionsIgnore(ignored_shas={"sha-aaa", "sha-bbb"})
    original.save(vault)

    path = vault / LOST_SESSIONS_IGNORE_FILENAME
    assert path.is_file()
    # File contains a sane JSON representation (sets serialized as lists).
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert sorted(payload["ignored_shas"]) == ["sha-aaa", "sha-bbb"]

    reloaded = LostSessionsIgnore.load(vault)
    assert reloaded.version == 1
    assert reloaded.ignored_shas == {"sha-aaa", "sha-bbb"}

    # Corrupt JSON → ValueError.
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        LostSessionsIgnore.load(vault)

    # Schema-violating JSON → ValueError as well.
    path.write_text(json.dumps({"version": 1, "ignored_shas": "not-a-list"}), encoding="utf-8")
    with pytest.raises(ValueError):
        LostSessionsIgnore.load(vault)


def test_add_to_ignore_appends_and_persists(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    first = add_to_ignore(vault, "sha-aaa")
    assert first.ignored_shas == {"sha-aaa"}

    second = add_to_ignore(vault, "sha-bbb")
    assert second.ignored_shas == {"sha-aaa", "sha-bbb"}

    reloaded = LostSessionsIgnore.load(vault)
    assert reloaded.ignored_shas == {"sha-aaa", "sha-bbb"}


def test_lost_sessions_cache_ttl_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()

    _write_jsonl(transcripts_root / "proj-lost", "sess-lost", b"lost-content\n")
    Manifest().save(vault)

    fake_now = {"t": 1000.0}

    def _monotonic() -> float:
        return fake_now["t"]

    monkeypatch.setattr("claude_mnemos.core.lost_sessions.time.monotonic", _monotonic)

    cache = LostSessionsCache(ttl_s=60.0)
    first = cache.get_or_scan(vault, transcripts_root=transcripts_root)
    assert len(first) == 1

    # Add a second lost session — without TTL expiry the cache should hide it.
    _write_jsonl(transcripts_root / "proj-lost-2", "sess-lost-2", b"lost-2\n")
    fake_now["t"] = 1030.0  # within TTL
    cached = cache.get_or_scan(vault, transcripts_root=transcripts_root)
    assert len(cached) == 1, "cache should not rescan within TTL window"

    # Advance past TTL → fresh scan.
    fake_now["t"] = 1100.0
    fresh = cache.get_or_scan(vault, transcripts_root=transcripts_root)
    assert len(fresh) == 2

    # invalidate() forces a rescan even within the TTL window.
    fake_now["t"] = 1110.0
    _write_jsonl(transcripts_root / "proj-lost-3", "sess-lost-3", b"lost-3\n")
    cache.invalidate()
    after_invalidate = cache.get_or_scan(vault, transcripts_root=transcripts_root)
    assert len(after_invalidate) == 3


def test_scan_resolves_transcripts_root_from_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    transcripts_root = tmp_path / "from-env"
    transcripts_root.mkdir()

    _write_jsonl(transcripts_root / "proj", "via-env", b"env-payload\n")
    Manifest().save(vault)

    monkeypatch.setenv("MNEMOS_TRANSCRIPTS_ROOT", str(transcripts_root))

    result = scan_lost_sessions(vault)
    assert len(result) == 1
    assert result[0].session_id == "via-env"


def test_scan_sorted_by_mtime_desc(tmp_path: Path) -> None:
    import os

    vault = tmp_path / "vault"
    vault.mkdir()
    transcripts_root = tmp_path / "transcripts"
    transcripts_root.mkdir()

    Manifest().save(vault)

    path_old, _ = _write_jsonl(transcripts_root / "p-old", "old-sid", b"old\n")
    path_new, _ = _write_jsonl(transcripts_root / "p-new", "new-sid", b"new\n")

    os.utime(path_old, (1_700_000_000, 1_700_000_000))
    os.utime(path_new, (1_800_000_000, 1_800_000_000))

    result = scan_lost_sessions(vault, transcripts_root=transcripts_root)
    ids = [item.session_id for item in result]
    assert ids == ["new-sid", "old-sid"]


def test_extract_cwd_and_preview_finds_both(tmp_path: Path) -> None:
    """First user event with content + first event with cwd are extracted."""

    jsonl = tmp_path / "test.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                '{"type":"queue-operation","cwd":"D:\\\\code\\\\foo"}',
                '{"type":"user","content":"hello mnemos"}',
                '{"type":"assistant","content":"hi"}',
            ]
        ),
        encoding="utf-8",
    )
    cwd, preview = _extract_cwd_and_preview(jsonl)
    assert cwd == "D:\\code\\foo"
    assert preview == "hello mnemos"


def test_extract_preview_truncates_long_message(tmp_path: Path) -> None:
    """Preview cuts at 200 chars and adds ellipsis."""
    from claude_mnemos.core.transcript_helpers import PREVIEW_MAX_CHARS

    long_msg = "lorem ipsum " * 50  # ~600 chars
    jsonl = tmp_path / "long.jsonl"
    jsonl.write_text(
        json.dumps({"type": "user", "content": long_msg}) + "\n",
        encoding="utf-8",
    )
    _cwd, preview = _extract_cwd_and_preview(jsonl)
    assert preview is not None
    assert len(preview) <= PREVIEW_MAX_CHARS + 1  # +1 for ellipsis
    assert preview.endswith("…")


def test_extract_preview_handles_anthropic_content_blocks(tmp_path: Path) -> None:
    """User content can be a list of {type: text, text: ...} blocks (Anthropic API style)."""

    jsonl = tmp_path / "blocks.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "type": "user",
                "content": [{"type": "text", "text": "from blocks"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _cwd, preview = _extract_cwd_and_preview(jsonl)
    assert preview == "from blocks"


def test_extract_handles_no_cwd_no_user(tmp_path: Path) -> None:
    """File with neither cwd nor user events → both None."""

    jsonl = tmp_path / "empty.jsonl"
    jsonl.write_text(
        json.dumps({"type": "queue-operation", "operation": "add"}) + "\n",
        encoding="utf-8",
    )
    cwd, preview = _extract_cwd_and_preview(jsonl)
    assert cwd is None
    assert preview is None


def test_extract_tolerates_malformed_lines(tmp_path: Path) -> None:
    """A bad JSON line in the middle doesn't break the scan; valid lines after still work."""

    jsonl = tmp_path / "messy.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                "{not valid json",
                json.dumps({"type": "user", "content": "good"}),
            ]
        ),
        encoding="utf-8",
    )
    _cwd, preview = _extract_cwd_and_preview(jsonl)
    assert preview == "good"


def test_extract_preview_from_real_claude_code_shape(tmp_path: Path) -> None:
    """Real Claude Code transcripts wrap user content in event.message.content,
    not event.content. Helper must dig one level deeper."""

    jsonl = tmp_path / "real.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "type": "user",
                "cwd": "/home/me/project",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "fix the failing test"},
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cwd, preview = _extract_cwd_and_preview(jsonl)
    assert cwd == "/home/me/project"
    assert preview == "fix the failing test"


def test_extract_preview_skips_ide_opened_file_wrapper(tmp_path: Path) -> None:
    """A first user event that's just an IDE notification should be skipped
    in favour of the next real user message."""

    jsonl = tmp_path / "ide.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "<ide_opened_file>The user opened foo.py</ide_opened_file>",
                                }
                            ],
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "content": [{"type": "text", "text": "real prompt here"}],
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    _cwd, preview = _extract_cwd_and_preview(jsonl)
    assert preview == "real prompt here"


def test_scan_lost_sessions_populates_cwd_and_preview(tmp_path: Path) -> None:
    """End-to-end: scan_lost_sessions() returns LostSession with cwd + preview filled."""
    vault = tmp_path / "vault"
    vault.mkdir()
    transcripts_root = tmp_path / "transcripts"
    proj = transcripts_root / "myproj"
    proj.mkdir(parents=True)
    payload = (
        json.dumps({"type": "queue-operation", "cwd": r"C:\Users\test\code"})
        + "\n"
        + json.dumps({"type": "user", "content": "ingest me"})
        + "\n"
    )
    (proj / "abc123.jsonl").write_text(payload, encoding="utf-8")

    results = scan_lost_sessions(vault, transcripts_root=transcripts_root)
    assert len(results) == 1
    entry = results[0]
    assert entry.session_id == "abc123"
    assert entry.cwd == r"C:\Users\test\code"
    assert entry.preview == "ingest me"


# ---------------------------------------------------------------------------
# read_transcript_messages — parse JSONL → role-tagged messages for the
# inline transcript reader on the dashboard.
# ---------------------------------------------------------------------------


def test_read_transcript_returns_user_assistant_messages(tmp_path: Path) -> None:
    from claude_mnemos.core.lost_sessions import read_transcript_messages

    jsonl = tmp_path / "t.jsonl"
    jsonl.write_text(
        "\n".join([
            json.dumps({"type": "user", "content": "hello"}),
            json.dumps({"type": "assistant", "content": "hi back"}),
            json.dumps({"type": "queue-operation", "op": "x"}),  # skipped
        ]),
        encoding="utf-8",
    )
    msgs, total, trunc = read_transcript_messages(jsonl)
    assert total == 2
    assert trunc is False
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "hello"


def test_read_transcript_truncates_long_message(tmp_path: Path) -> None:
    from claude_mnemos.core.lost_sessions import (
        TRANSCRIPT_MESSAGE_MAX_CHARS,
        read_transcript_messages,
    )

    long_text = "x" * (TRANSCRIPT_MESSAGE_MAX_CHARS + 100)
    jsonl = tmp_path / "long.jsonl"
    jsonl.write_text(
        json.dumps({"type": "user", "content": long_text}) + "\n",
        encoding="utf-8",
    )
    msgs, _total, _trunc = read_transcript_messages(jsonl)
    assert msgs[0].truncated is True
    assert len(msgs[0].content) <= TRANSCRIPT_MESSAGE_MAX_CHARS + 1


def test_read_transcript_handles_anthropic_message_shape(tmp_path: Path) -> None:
    """event.message.content = [{type: text, text: ...}]."""
    from claude_mnemos.core.lost_sessions import read_transcript_messages

    jsonl = tmp_path / "ant.jsonl"
    jsonl.write_text(
        json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "from anthropic"}]},
        }) + "\n",
        encoding="utf-8",
    )
    msgs, _, _ = read_transcript_messages(jsonl)
    assert len(msgs) == 1
    assert msgs[0].role == "assistant"
    assert msgs[0].content == "from anthropic"


def test_read_transcript_extracts_tool_use_block(tmp_path: Path) -> None:
    from claude_mnemos.core.lost_sessions import read_transcript_messages

    jsonl = tmp_path / "tool.jsonl"
    jsonl.write_text(
        json.dumps({
            "type": "assistant",
            "content": [
                {"type": "text", "text": "let me check"},
                {"type": "tool_use", "name": "bash", "input": {"command": "ls"}},
            ],
        }) + "\n",
        encoding="utf-8",
    )
    msgs, _, _ = read_transcript_messages(jsonl)
    content = msgs[0].content
    assert "let me check" in content
    assert "<tool: bash>" in content
    assert "ls" in content


def test_read_transcript_limit_clamp(tmp_path: Path) -> None:
    from claude_mnemos.core.lost_sessions import read_transcript_messages

    jsonl = tmp_path / "many.jsonl"
    lines = [json.dumps({"type": "user", "content": f"msg{i}"}) for i in range(50)]
    jsonl.write_text("\n".join(lines), encoding="utf-8")
    msgs, total, trunc = read_transcript_messages(jsonl, limit=5)
    assert len(msgs) == 5
    assert total == 50
    assert trunc is True


def test_read_transcript_classifies_system_metadata(tmp_path: Path) -> None:
    """User content with <ide_opened_file> / <system-reminder> prefix is reclassified as 'system'."""
    from claude_mnemos.core.lost_sessions import read_transcript_messages

    jsonl = tmp_path / "sys.jsonl"
    jsonl.write_text(
        "\n".join([
            json.dumps({"type": "user", "content": "<ide_opened_file>foo.py</ide_opened_file>"}),
            json.dumps({"type": "user", "content": "real prompt"}),
        ]),
        encoding="utf-8",
    )
    msgs, _, _ = read_transcript_messages(jsonl)
    assert msgs[0].role == "system"
    assert msgs[1].role == "user"
