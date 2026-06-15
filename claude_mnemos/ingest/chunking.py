"""Budget-bounded splitting of transcript messages into LLM-servable chunks.

A pure, side-effect-free helper used before handing a transcript to the LLM
extractor. It packs whole messages into chunks whose local token estimate
stays within a caller-supplied budget, so each chunk fits a single request.

Splitting boundaries fall ONLY between whole messages — a message is never
cut mid-text, since that would shred the role/turn structure the extractor
relies on. A single message that already exceeds the budget gets its own
(over-budget) chunk: the LLM client's own guard decides whether such a
genuinely unservable message is dropped or truncated. No I/O, no LLM calls.
"""

from __future__ import annotations

from claude_mnemos.ingest.llm.tokens import count_tokens_local
from claude_mnemos.ingest.transcript import TranscriptMessage

# Rough per-message framing overhead (role marker, separators) added on top
# of the body's token estimate so packing leaves headroom for the rendered
# prompt structure rather than just the raw concatenated text.
_HEADER_OVERHEAD_TOKENS = 8


def _msg_tokens(m: TranscriptMessage) -> int:
    """Approximate token cost of one message, body plus framing overhead."""
    return count_tokens_local(m.text) + _HEADER_OVERHEAD_TOKENS


def split_messages_for_budget(
    messages: list[TranscriptMessage], *, budget_tokens: int
) -> list[list[TranscriptMessage]]:
    """Greedily pack *messages* into chunks each within *budget_tokens*.

    Messages are kept in their original order and none are dropped: the
    concatenation of all returned chunks equals *messages*. A chunk's combined
    local token estimate stays at or below *budget_tokens*, except when a
    single message exceeds the budget on its own — that message is emitted as
    its own over-budget chunk rather than being split mid-text.

    Empty input returns an empty list.
    """
    if not messages:
        return []

    chunks: list[list[TranscriptMessage]] = []
    cur: list[TranscriptMessage] = []
    cur_tok = 0

    for m in messages:
        mt = _msg_tokens(m)
        # Close the current chunk before adding a message that would push it
        # over budget — but only if it already holds something, so an
        # oversized lone message still lands in a chunk of its own.
        if cur and cur_tok + mt > budget_tokens:
            chunks.append(cur)
            cur = []
            cur_tok = 0
        cur.append(m)
        cur_tok += mt

    if cur:
        chunks.append(cur)

    return chunks
