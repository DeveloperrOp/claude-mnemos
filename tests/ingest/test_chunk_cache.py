from __future__ import annotations

import os
import time
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from claude_mnemos.config import Config
from claude_mnemos.core.models import (
    ExtractedPage,
    ExtractionPayload,
    ProvenanceCounts,
)
from claude_mnemos.ingest.chunk_cache import (
    CHUNK_CACHE_DIRNAME,
    ChunkCache,
    hash_chunk_text,
)
from claude_mnemos.ingest.extraction import _render_transcript, extract_wiki_pages
from claude_mnemos.ingest.llm import ExtractionRaw
from claude_mnemos.ingest.transcript import TranscriptMessage

_PROV = ProvenanceCounts(extracted_pct=100, inferred_pct=0, ambiguous_pct=0)
FIXED_TODAY = date(2026, 4, 26)


def _payload(*, title: str, body: str, related: list[str] | None = None) -> ExtractionPayload:
    return ExtractionPayload(
        summary=f"summary for {title}",
        skipped_reason=None,
        pages=[
            ExtractedPage(
                type="entity",
                title=title,
                confidence=0.8,
                provenance=_PROV,
                related=related or [],
                body=body,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def test_hash_chunk_text_deterministic_and_distinct() -> None:
    assert hash_chunk_text("hello") == hash_chunk_text("hello")
    assert hash_chunk_text("hello") != hash_chunk_text("world")
    # sha256 hexdigest is 64 chars
    assert len(hash_chunk_text("x")) == 64


# ---------------------------------------------------------------------------
# ChunkCache get/put/clear
# ---------------------------------------------------------------------------


def test_put_then_get_roundtrip(tmp_path: Path) -> None:
    cache = ChunkCache(tmp_path, "sess-1")
    payload = _payload(title="FastAPI", body="A framework.", related=["[[x]]"])
    h = hash_chunk_text("chunk text")

    cache.put(h, payload)
    got = cache.get(h)

    assert got is not None
    assert got.pages[0].title == "FastAPI"
    assert got.pages[0].body == "A framework."
    assert got.pages[0].related == ["[[x]]"]
    assert got.summary == "summary for FastAPI"


def test_get_missing_hash_returns_none(tmp_path: Path) -> None:
    cache = ChunkCache(tmp_path, "sess-1")
    assert cache.get(hash_chunk_text("never written")) is None


def test_get_corrupt_file_returns_none(tmp_path: Path) -> None:
    cache = ChunkCache(tmp_path, "sess-1")
    h = hash_chunk_text("chunk")
    cache.dir.mkdir(parents=True, exist_ok=True)
    (cache.dir / f"{h}.json").write_text("{not json", encoding="utf-8")

    assert cache.get(h) is None


def test_get_schema_mismatch_returns_none(tmp_path: Path) -> None:
    cache = ChunkCache(tmp_path, "sess-1")
    h = hash_chunk_text("chunk")
    cache.dir.mkdir(parents=True, exist_ok=True)
    # Valid JSON but not an ExtractionPayload.
    (cache.dir / f"{h}.json").write_text('{"unexpected": true}', encoding="utf-8")

    assert cache.get(h) is None


def test_clear_removes_dir(tmp_path: Path) -> None:
    cache = ChunkCache(tmp_path, "sess-1")
    cache.put(hash_chunk_text("a"), _payload(title="A", body="b"))
    assert cache.dir.exists()

    cache.clear()
    assert not cache.dir.exists()


def test_clear_on_missing_dir_is_noop(tmp_path: Path) -> None:
    cache = ChunkCache(tmp_path, "never-created")
    cache.clear()  # must not raise
    assert not cache.dir.exists()


def test_put_write_failure_is_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cache write failure must never abort extraction — put() is best-effort.

    Caching is an optimization; if the disk is full / read-only, the chunk is
    simply re-extracted on a later retry rather than crashing a good job.
    """
    cache = ChunkCache(tmp_path, "sess-1")

    def _boom(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("claude_mnemos.ingest.chunk_cache.atomic_write", _boom)
    h = hash_chunk_text("chunk")
    cache.put(h, _payload(title="A", body="b"))  # must not raise
    assert cache.get(h) is None  # nothing persisted, no crash


# ---------------------------------------------------------------------------
# sweep_stale
# ---------------------------------------------------------------------------


def test_sweep_stale_removes_old_keeps_fresh(tmp_path: Path) -> None:
    old = ChunkCache(tmp_path, "old-session")
    fresh = ChunkCache(tmp_path, "fresh-session")
    old.put(hash_chunk_text("a"), _payload(title="A", body="b"))
    fresh.put(hash_chunk_text("c"), _payload(title="C", body="d"))

    # Age the old session dir well beyond the 7-day window.
    old_ts = time.time() - 30 * 24 * 3600
    os.utime(old.dir, (old_ts, old_ts))

    removed = ChunkCache.sweep_stale(tmp_path)

    assert removed == 1
    assert not old.dir.exists()
    assert fresh.dir.exists()


def test_sweep_stale_no_cache_dir_returns_zero(tmp_path: Path) -> None:
    assert ChunkCache.sweep_stale(tmp_path) == 0


# ---------------------------------------------------------------------------
# Resume behavior (the key test)
# ---------------------------------------------------------------------------


def _cfg() -> Config:
    # Tiny budget so split_messages_for_budget yields multiple chunks.
    return Config(
        api_key="sk-test",
        model="claude-sonnet-4-6",
        language_hint="auto",
        max_input_tokens=200,
        lock_timeout=60.0,
    )


def _big_messages() -> list[TranscriptMessage]:
    """Two distinct, fat messages that will land in separate chunks."""
    return [
        TranscriptMessage(role="user", text="alpha " * 200),
        TranscriptMessage(role="assistant", text="bravo " * 200),
    ]


class _ScriptedClient:
    """Fake LLMClient driven by a dict mapping a substring of the user prompt
    to either an ExtractionRaw or an Exception to raise."""

    def __init__(self, rules: list[tuple[str, Any]]) -> None:
        self.rules = rules
        self.calls: list[str] = []

    def extract(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        validate: Any = None,
    ) -> ExtractionRaw:
        self.calls.append(user)
        for needle, outcome in self.rules:
            if needle in user:
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome
        raise AssertionError(f"no scripted rule matched user prompt: {user[:60]!r}")


def _raw(title: str, body: str) -> ExtractionRaw:
    return ExtractionRaw(
        payload=_payload(title=title, body=body).model_dump(),
        input_tokens=100,
        output_tokens=20,
    )


def test_chunk_extract_persists_payload_before_later_chunk_fails(tmp_path: Path) -> None:
    cfg = _cfg()
    messages = _big_messages()
    cache = ChunkCache(tmp_path, "sess-resume")

    # chunk 1 (contains "alpha") succeeds; chunk 2 (contains "bravo") raises.
    client = _ScriptedClient(
        [
            ("alpha", _raw("Alpha Page", "Alpha body.")),
            ("bravo", RuntimeError("rate limited on chunk 2")),
        ]
    )

    with pytest.raises(RuntimeError):
        extract_wiki_pages(
            messages=messages,
            cfg=cfg,
            llm_client=client,  # type: ignore[arg-type]
            today=FIXED_TODAY,
            chunk_extract=True,
            chunk_cache=cache,
        )

    # Chunk 1's payload is now cached: exactly one file present.
    files = list(cache.dir.glob("*.json"))
    assert len(files) == 1


def test_chunk_extract_resumes_from_cache_on_retry(tmp_path: Path) -> None:
    cfg = _cfg()
    messages = _big_messages()
    cache = ChunkCache(tmp_path, "sess-resume")

    # First run: chunk 1 cached, chunk 2 fails.
    first = _ScriptedClient(
        [
            ("alpha", _raw("Alpha Page", "Alpha body.")),
            ("bravo", RuntimeError("rate limited")),
        ]
    )
    with pytest.raises(RuntimeError):
        extract_wiki_pages(
            messages=messages,
            cfg=cfg,
            llm_client=first,
            today=FIXED_TODAY,
            chunk_extract=True,
            chunk_cache=cache,
        )

    # Pre-compute chunk-1's content hash so we can assert it is never re-requested.
    from claude_mnemos.ingest.chunking import split_messages_for_budget

    budget = int(cfg.max_input_tokens * 0.75)
    chunks = split_messages_for_budget(messages, budget_tokens=budget)
    assert len(chunks) >= 2
    chunk1_hash = hash_chunk_text(_render_transcript(chunks[0]))
    assert cache.get(chunk1_hash) is not None  # chunk 1 was cached

    # Second run: a client that would FAIL if asked for chunk-1 content, but
    # succeeds for chunk 2. Resume must serve chunk 1 from cache.
    second = _ScriptedClient(
        [
            ("alpha", AssertionError("chunk 1 must come from cache, not the LLM")),
            ("bravo", _raw("Bravo Page", "Bravo body.")),
        ]
    )
    result = extract_wiki_pages(
        messages=messages,
        cfg=cfg,
        llm_client=second,
        today=FIXED_TODAY,
        chunk_extract=True,
        chunk_cache=cache,
    )

    # The chunk-1 client method was NOT called for the cached hash.
    assert not any("alpha" in u for u in second.calls)
    # Merged pages include both chunks.
    titles = {p.frontmatter.title for p in result.pages}
    assert titles == {"Alpha Page", "Bravo Page"}
    # Tokens accumulate only from the live chunk-2 call (cached chunk = 0).
    assert result.input_tokens == 100
    assert result.output_tokens == 20


# ---------------------------------------------------------------------------
# Single-call path must not touch the cache
# ---------------------------------------------------------------------------


def test_single_call_path_does_not_touch_cache(tmp_path: Path) -> None:
    cfg = Config(
        api_key="sk-test",
        model="claude-sonnet-4-6",
        language_hint="auto",
        max_input_tokens=150_000,  # huge budget => single call
        lock_timeout=60.0,
    )
    messages = [TranscriptMessage(role="user", text="short message")]
    cache = ChunkCache(tmp_path, "sess-single")

    client = _ScriptedClient([("short message", _raw("Solo", "Solo body."))])
    result = extract_wiki_pages(
        messages=messages,
        cfg=cfg,
        llm_client=client,
        today=FIXED_TODAY,
        chunk_extract=True,
        chunk_cache=cache,
    )

    assert len(client.calls) == 1  # exactly one extract call
    assert not cache.dir.exists()  # cache untouched on the fits path
    assert {p.frontmatter.title for p in result.pages} == {"Solo"}


def test_chunk_cache_dirname_constant() -> None:
    assert CHUNK_CACHE_DIRNAME == ".chunk-cache"
