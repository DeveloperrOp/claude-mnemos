import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_mnemos.config import Config
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
