from __future__ import annotations

from claude_mnemos.ingest.chunking import split_messages_for_budget
from claude_mnemos.ingest.transcript import TranscriptMessage


def _msg(text: str, role: str = "user") -> TranscriptMessage:
    return TranscriptMessage(role=role, text=text)


def test_small_transcript_one_chunk() -> None:
    m1 = _msg("hello there")
    m2 = _msg("general kenobi")
    chunks = split_messages_for_budget([m1, m2], budget_tokens=10_000)
    assert chunks == [[m1, m2]]


def test_splits_on_message_boundary_by_budget() -> None:
    # ~1000 tokens each (one token per word-ish; 1000 words comfortably > 1000 tok).
    messages = [_msg(("word " * 1000).strip()) for _ in range(10)]
    chunks = split_messages_for_budget(messages, budget_tokens=2500)

    # More than one chunk because the total greatly exceeds the budget.
    assert len(chunks) > 1
    # Nothing dropped, order preserved.
    flat = [m for chunk in chunks for m in chunk]
    assert flat == messages
    # Every multi-message chunk stays within budget by local estimate.
    from claude_mnemos.ingest.llm.tokens import count_tokens_local

    for chunk in chunks:
        if len(chunk) > 1:
            total = sum(count_tokens_local(m.text) + 8 for m in chunk)
            assert total <= 2500


def test_single_message_over_budget_gets_own_chunk() -> None:
    big = _msg("x " * 20_000)  # ~40000 chars -> far over budget
    small_before = _msg("before")
    small_after = _msg("after")
    chunks = split_messages_for_budget(
        [small_before, big, small_after], budget_tokens=2500
    )

    # The oversized message is never split and never dropped.
    flat = [m for chunk in chunks for m in chunk]
    assert flat == [small_before, big, small_after]
    # The big message lives in a chunk of its own.
    assert [big] in chunks


def test_single_message_over_budget_alone() -> None:
    big = _msg("x " * 20_000)
    chunks = split_messages_for_budget([big], budget_tokens=2500)
    assert chunks == [[big]]


def test_empty() -> None:
    assert split_messages_for_budget([], budget_tokens=1000) == []
