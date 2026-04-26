from pathlib import Path

import pytest

from claude_mnemos.ingest.transcript import (
    EmptyTranscriptError,
    TranscriptMessage,
    parse_jsonl,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def test_parse_returns_messages_in_order():
    messages: list[TranscriptMessage] = parse_jsonl(FIXTURE)
    assert len(messages) == 3
    assert [m.role for m in messages] == ["user", "assistant", "user"]


def test_parse_extracts_text_from_string_content():
    messages = parse_jsonl(FIXTURE)
    assert messages[0].text == "Hello, what is 2+2?"
    assert messages[2].text == "Thanks."


def test_parse_extracts_text_from_block_list_content():
    messages = parse_jsonl(FIXTURE)
    assert messages[1].text == "2+2 equals 4."


def test_parse_empty_file_raises(tmp_path: Path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(EmptyTranscriptError):
        parse_jsonl(empty)


def test_parse_skips_non_message_entries(tmp_path: Path):
    f = tmp_path / "mixed.jsonl"
    f.write_text(
        '{"type":"summary","summary":"x"}\n'
        '{"type":"user","message":{"role":"user","content":"hi"}}\n',
        encoding="utf-8",
    )
    messages = parse_jsonl(f)
    assert len(messages) == 1
    assert messages[0].text == "hi"


def test_parse_session_id_present_on_all_messages():
    messages = parse_jsonl(FIXTURE)
    assert all(m.session_id == "abc-123" for m in messages)


def test_parse_skips_malformed_json(tmp_path: Path):
    f = tmp_path / "bad.jsonl"
    f.write_text(
        '{invalid json}\n'
        '{"type":"user","message":{"role":"user","content":"ok"}}\n',
        encoding="utf-8",
    )
    messages = parse_jsonl(f)
    assert len(messages) == 1
    assert messages[0].text == "ok"
