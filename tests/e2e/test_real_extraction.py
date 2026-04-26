"""Optional end-to-end test against the real Anthropic API.

Run with:
    pytest tests/e2e -v -m slow

Skipped automatically when ANTHROPIC_API_KEY is unset.
"""
from __future__ import annotations

import os
from datetime import date

import pytest

from claude_mnemos.config import Config
from claude_mnemos.ingest.extraction import extract_wiki_pages
from claude_mnemos.ingest.llm import LLMClient
from claude_mnemos.ingest.transcript import TranscriptMessage

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set",
    ),
]


def test_real_extraction_yields_at_least_one_page():
    cfg = Config.from_env()
    client = LLMClient(cfg)

    messages = [
        TranscriptMessage(
            role="user",
            text=(
                "Let's decide our error-handling policy: we should always wrap "
                "anthropic SDK calls in try/except APIError and log the request id. "
                "This is our team standard going forward."
            ),
        ),
        TranscriptMessage(
            role="assistant",
            text=(
                "Agreed. The decision is: wrap every anthropic.messages.create() call "
                "in try/except APIError, log the request id, and re-raise as our own "
                "LLMExtractionError. This is now our error-handling standard."
            ),
        ),
    ]

    result = extract_wiki_pages(
        messages=messages,
        cfg=cfg,
        llm_client=client,
        today=date(2026, 4, 26),
    )

    assert len(result.pages) >= 1, "expected at least one extracted page from a clear decision"

    p = result.pages[0]
    assert p.frontmatter.type in ("entity", "concept")
    assert p.frontmatter.provenance is not None
    total = (
        p.frontmatter.provenance.extracted_pct
        + p.frontmatter.provenance.inferred_pct
        + p.frontmatter.provenance.ambiguous_pct
    )
    assert 90 <= total <= 110, f"provenance percentages should sum ~100, got {total}"

    assert isinstance(result.summary, str) and len(result.summary) > 0
    assert result.input_tokens > 0
    assert result.output_tokens > 0

    rendered = p.serialize()
    assert rendered.startswith("---\n")
    assert "---\n" in rendered.split("---\n", 2)[1]  # closing fence exists
