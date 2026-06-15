import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_mnemos.config import Config
from claude_mnemos.core.models import ExtractedPage, ExtractionPayload, ProvenanceCounts
from claude_mnemos.ingest.extraction import ExtractionResult, extract_wiki_pages
from claude_mnemos.ingest.llm import ExtractionRaw
from claude_mnemos.ingest.transcript import TranscriptMessage

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "llm_responses"


def _load(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _cfg() -> Config:
    return Config(
        api_key="sk-test",
        model="claude-sonnet-4-6",
        language_hint="auto",
        max_input_tokens=150_000,
        lock_timeout=60.0,
    )


def _messages() -> list[TranscriptMessage]:
    return [
        TranscriptMessage(role="user", text="Tell me about FastAPI."),
        TranscriptMessage(role="assistant", text="FastAPI is a Python web framework..."),
    ]


def test_extract_returns_extraction_result_for_single_entity():
    payload = _load("single_entity.json")
    fake_client = MagicMock()
    fake_client.extract.return_value = ExtractionRaw(
        payload=payload, input_tokens=1000, output_tokens=200
    )

    result = extract_wiki_pages(
        messages=_messages(),
        cfg=_cfg(),
        llm_client=fake_client,
        today=date(2026, 4, 26),
    )

    assert isinstance(result, ExtractionResult)
    assert result.summary == payload["summary"]
    assert result.skipped_reason is None
    assert len(result.pages) == 1
    page = result.pages[0]
    assert page.frontmatter.title == "FastAPI"
    assert page.frontmatter.type == "entity"
    assert page.relative_path == Path("wiki/entities/fastapi.md")
    assert result.input_tokens == 1000
    assert result.output_tokens == 200


def test_extract_handles_multi_page_payload():
    payload = _load("multi_pages.json")
    fake_client = MagicMock()
    fake_client.extract.return_value = ExtractionRaw(
        payload=payload, input_tokens=2000, output_tokens=500
    )

    result = extract_wiki_pages(
        messages=_messages(),
        cfg=_cfg(),
        llm_client=fake_client,
        today=date(2026, 4, 26),
    )

    assert len(result.pages) == 3
    paths = {p.relative_path for p in result.pages}
    assert Path("wiki/entities/fastapi.md") in paths
    assert Path("wiki/entities/flask.md") in paths
    assert Path("wiki/concepts/prefer-fastapi-over-flask.md") in paths


def test_extract_uses_slug_hint_when_provided():
    payload = _load("multi_pages.json")
    fake_client = MagicMock()
    fake_client.extract.return_value = ExtractionRaw(
        payload=payload, input_tokens=1, output_tokens=1
    )

    result = extract_wiki_pages(
        messages=_messages(),
        cfg=_cfg(),
        llm_client=fake_client,
        today=date(2026, 4, 26),
    )

    concept = next(p for p in result.pages if p.frontmatter.type == "concept")
    assert concept.relative_path.name == "prefer-fastapi-over-flask.md"


def test_extract_empty_payload_with_skipped_reason():
    payload = _load("empty_skipped.json")
    fake_client = MagicMock()
    fake_client.extract.return_value = ExtractionRaw(
        payload=payload, input_tokens=300, output_tokens=50
    )

    result = extract_wiki_pages(
        messages=_messages(),
        cfg=_cfg(),
        llm_client=fake_client,
        today=date(2026, 4, 26),
    )

    assert result.pages == []
    assert result.skipped_reason == payload["skipped_reason"]


def test_extract_passes_validate_callback_to_client():
    payload = _load("single_entity.json")
    fake_client = MagicMock()
    fake_client.extract.return_value = ExtractionRaw(
        payload=payload, input_tokens=1, output_tokens=1
    )

    extract_wiki_pages(
        messages=_messages(),
        cfg=_cfg(),
        llm_client=fake_client,
        today=date(2026, 4, 26),
    )

    kwargs = fake_client.extract.call_args.kwargs
    assert "validate" in kwargs
    validate = kwargs["validate"]
    validate(payload)  # should not raise
    with pytest.raises(Exception):  # noqa: B017
        validate({"summary": "x"})  # missing pages


def test_extract_pages_have_provenance_in_frontmatter():
    payload = _load("single_entity.json")
    fake_client = MagicMock()
    fake_client.extract.return_value = ExtractionRaw(
        payload=payload, input_tokens=1, output_tokens=1
    )
    result = extract_wiki_pages(
        messages=_messages(),
        cfg=_cfg(),
        llm_client=fake_client,
        today=date(2026, 4, 26),
    )
    p = result.pages[0]
    assert p.frontmatter.provenance is not None
    assert p.frontmatter.provenance.extracted_pct == 80


def test_extract_renders_transcript_into_user_prompt():
    payload = _load("empty_skipped.json")
    fake_client = MagicMock()
    fake_client.extract.return_value = ExtractionRaw(
        payload=payload, input_tokens=1, output_tokens=1
    )
    extract_wiki_pages(
        messages=[
            TranscriptMessage(role="user", text="UNIQUE_TRANSCRIPT_MARKER"),
            TranscriptMessage(role="assistant", text="ok"),
        ],
        cfg=_cfg(),
        llm_client=fake_client,
        today=date(2026, 4, 26),
    )

    user_arg = fake_client.extract.call_args.kwargs["user"]
    assert "UNIQUE_TRANSCRIPT_MARKER" in user_arg
    assert 'language_hint="auto"' in user_arg


def test_extract_unknown_page_type_raises_key_error(monkeypatch):
    """If ExtractedPageType is widened later, _render_page must reject unmapped types."""
    from claude_mnemos.ingest import extraction as extraction_mod

    payload = _load("single_entity.json")
    fake_client = MagicMock()
    fake_client.extract.return_value = ExtractionRaw(
        payload=payload, input_tokens=1, output_tokens=1
    )

    # Inject a foreign type into the validated ExtractedPage by patching the folder map.
    # This simulates "someone added a new ExtractedPageType variant but forgot to update the map".
    monkeypatch.setattr(extraction_mod, "_FOLDER_BY_TYPE", {"concept": "concepts"})

    with pytest.raises(KeyError):
        extraction_mod.extract_wiki_pages(
            messages=_messages(),
            cfg=_cfg(),
            llm_client=fake_client,
            today=date(2026, 4, 26),
        )


# --- chunked extraction (Task 8) -------------------------------------------

_PROV = ProvenanceCounts(extracted_pct=100, inferred_pct=0, ambiguous_pct=0)


def _extracted_page(
    *,
    title: str,
    body: str,
    confidence: float = 0.7,
    slug_hint: str | None = None,
) -> ExtractedPage:
    return ExtractedPage(
        type="entity",
        title=title,
        slug_hint=slug_hint,
        confidence=confidence,
        provenance=_PROV,
        body=body,
    )


def _raw_for(*pages: ExtractedPage, input_tokens: int, output_tokens: int) -> ExtractionRaw:
    payload = ExtractionPayload(summary="part", skipped_reason=None, pages=list(pages))
    return ExtractionRaw(
        payload=payload.model_dump(mode="json"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def test_small_transcript_calls_extract_once():
    """REGRESSION: a small transcript with chunk_extract defaulted is one extract call."""
    payload = _load("single_entity.json")
    fake_client = MagicMock()
    fake_client.extract.return_value = ExtractionRaw(
        payload=payload, input_tokens=1000, output_tokens=200
    )

    result = extract_wiki_pages(
        messages=_messages(),
        cfg=_cfg(),
        llm_client=fake_client,
        today=date(2026, 4, 26),
    )

    assert fake_client.extract.call_count == 1
    assert len(result.pages) == 1


def test_small_transcript_with_chunk_extract_still_one_call():
    """chunk_extract=True but transcript fits the budget → still a single call."""
    payload = _load("single_entity.json")
    fake_client = MagicMock()
    fake_client.extract.return_value = ExtractionRaw(
        payload=payload, input_tokens=1000, output_tokens=200
    )

    extract_wiki_pages(
        messages=_messages(),
        cfg=_cfg(),  # 150k budget — tiny transcript fits
        llm_client=fake_client,
        today=date(2026, 4, 26),
        chunk_extract=True,
    )

    assert fake_client.extract.call_count == 1


def test_oversized_transcript_chunks_and_merges():
    """Oversized transcript + chunk_extract → split, per-chunk extract, merged result."""
    # Many sizable messages so the rendered transcript blows past a tiny budget.
    messages = [
        TranscriptMessage(role="user", text=f"Message number {i}: " + ("lorem ipsum " * 40))
        for i in range(12)
    ]
    # budget = 800 * 0.75 = 600 → packs ~6 of these ~94-token messages per chunk
    # → exactly two chunks for twelve messages.
    cfg = _cfg().with_overrides(max_input_tokens=800)

    # Two chunks share the FastAPI slug (deduped on merge); chunk 2 adds Flask.
    chunk1 = _raw_for(
        _extracted_page(title="FastAPI", body="FastAPI body v1.", confidence=0.6),
        input_tokens=120,
        output_tokens=40,
    )
    chunk2 = _raw_for(
        _extracted_page(title="FastAPI", body="FastAPI body v2 better.", confidence=0.9),
        _extracted_page(title="Flask", body="Flask body."),
        input_tokens=130,
        output_tokens=55,
    )
    fake_client = MagicMock()
    fake_client.extract.side_effect = [chunk1, chunk2]

    from claude_mnemos.ingest.chunking import split_messages_for_budget

    expected_chunks = split_messages_for_budget(messages, budget_tokens=int(800 * 0.75))
    assert len(expected_chunks) == 2  # guard: the fixture splits into exactly two

    result = extract_wiki_pages(
        messages=messages,
        cfg=cfg,
        llm_client=fake_client,
        today=date(2026, 4, 26),
        chunk_extract=True,
    )

    assert fake_client.extract.call_count == len(expected_chunks)
    # FastAPI deduped across the two chunks, Flask survives → 2 unique pages.
    paths = {p.relative_path for p in result.pages}
    assert Path("wiki/entities/fastapi.md") in paths
    assert Path("wiki/entities/flask.md") in paths
    assert len(result.pages) == 2
    # Higher-confidence FastAPI body wins the merge.
    fastapi = next(p for p in result.pages if p.relative_path.name == "fastapi.md")
    assert fastapi.body == "FastAPI body v2 better."
    # Token totals are summed across chunks.
    assert result.input_tokens == 250
    assert result.output_tokens == 95


def test_chunked_extract_passes_chunk_note_in_user_prompt():
    """Each chunked call carries a 'part N of M' note in the user prompt."""
    messages = [
        TranscriptMessage(role="user", text=f"Msg {i}: " + ("alpha beta gamma " * 40))
        for i in range(10)
    ]
    cfg = _cfg().with_overrides(max_input_tokens=200)
    raw = _raw_for(
        _extracted_page(title="Topic", body="Body."), input_tokens=10, output_tokens=5
    )
    fake_client = MagicMock()
    fake_client.extract.return_value = raw

    extract_wiki_pages(
        messages=messages,
        cfg=cfg,
        llm_client=fake_client,
        today=date(2026, 4, 26),
        chunk_extract=True,
    )

    user_args = [c.kwargs["user"] for c in fake_client.extract.call_args_list]
    assert any("част" in u.lower() or "part" in u.lower() for u in user_args)


def test_chunk_note_empty_for_single_chunk():
    """format_user without chunk_note is byte-identical to the chunk_note='' call."""
    from claude_mnemos.ingest.prompts import format_user

    base = format_user(transcript="T", language_hint="auto")
    empty = format_user(transcript="T", language_hint="auto", chunk_note="")
    assert base == empty
    # And a non-empty note actually changes the prompt.
    noted = format_user(transcript="T", language_hint="auto", chunk_note="(часть 1 из 2)")
    assert noted != base
    assert "часть 1 из 2" in noted
