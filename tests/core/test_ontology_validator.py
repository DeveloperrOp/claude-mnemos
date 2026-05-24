"""Tests for OntologyLLMValidator (Phase B3c).

Uses a FakeLLMClient that satisfies the LLMClient protocol — no real subprocess
or API calls. The validator's job is to take a candidate pair (already
short-listed by heuristics), send the bodies to the LLM with a strict tool
schema, and return a structured verdict.

The strict-validator rule (per design): if the LLM emits ``verdict == "merge"``
or ``verdict == "duplicate"`` without a ``target_slug``, the inner schema
validation must reject and the validator must surface the error — never silently
return half-filled data that the apply pipeline would crash on later.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from claude_mnemos.core.ontology_validator import (
    OntologyLLMValidator,
    ValidationVerdict,
    VerdictKind,
)
from claude_mnemos.ingest.llm import ExtractionRaw, LLMExtractionError


class FakeLLMClient:
    """Stub LLMClient that returns a fixed payload (or raises a fixed error).

    Captures the system/user/tool args so tests can inspect what was sent.
    """

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        raise_error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.raise_error = raise_error
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def extract(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        validate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> ExtractionRaw:
        self.calls.append((system, user, tool))
        if self.raise_error is not None:
            raise self.raise_error
        assert self.payload is not None
        if validate is not None:
            validate(self.payload)  # mirrors real client semantics
        return ExtractionRaw(payload=self.payload, input_tokens=0, output_tokens=0)


def _make_validator(client: FakeLLMClient) -> OntologyLLMValidator:
    return OntologyLLMValidator(llm=client)


class TestVerdict:
    def test_returns_duplicate_with_target(self) -> None:
        client = FakeLLMClient(
            payload={
                "verdict": "duplicate",
                "target_slug": "auth-jwt-pattern",
                "merged_title": "Auth JWT Pattern",
                "reason": "Identical content; second is a copy.",
            }
        )
        v = _make_validator(client)
        verdict = v.validate_pair(
            page_a="wiki/concepts/foo.md",
            body_a="same content",
            page_b="wiki/concepts/bar.md",
            body_b="same content",
            similarity=1.0,
        )
        assert isinstance(verdict, ValidationVerdict)
        assert verdict.verdict == "duplicate"
        assert verdict.target_slug == "auth-jwt-pattern"
        assert verdict.merged_title == "Auth JWT Pattern"
        assert "Identical" in verdict.reason

    def test_returns_merge_with_target(self) -> None:
        client = FakeLLMClient(
            payload={
                "verdict": "merge",
                "target_slug": "auth-overview",
                "merged_title": "Auth Overview",
                "reason": "Overlapping topics; combine to preserve both.",
            }
        )
        v = _make_validator(client)
        verdict = v.validate_pair(
            page_a="wiki/concepts/auth-a.md",
            body_a="JWT tokens and refresh logic",
            page_b="wiki/concepts/auth-b.md",
            body_b="Token refresh handling for JWT",
            similarity=0.6,
        )
        assert verdict.verdict == "merge"
        assert verdict.target_slug == "auth-overview"

    def test_returns_distinct_without_target(self) -> None:
        client = FakeLLMClient(
            payload={
                "verdict": "distinct",
                "reason": "Different scopes despite surface similarity.",
            }
        )
        v = _make_validator(client)
        verdict = v.validate_pair(
            page_a="wiki/concepts/auth.md",
            body_a="auth logic",
            page_b="wiki/concepts/db.md",
            body_b="auth column in database",
            similarity=0.3,
        )
        assert verdict.verdict == "distinct"
        assert verdict.target_slug is None
        assert verdict.merged_title is None


class TestStrictValidation:
    def test_rejects_merge_without_target_slug(self) -> None:
        # LLM returns merge but forgot target_slug. Strict validator must
        # reject — the apply pipeline requires proposed_target for merge.
        # FakeLLMClient delegates to the `validate` callback when wired,
        # so this should surface as LLMExtractionError.
        client = FakeLLMClient(
            payload={
                "verdict": "merge",
                "reason": "Should merge but no target slug provided.",
            }
        )
        v = _make_validator(client)
        with pytest.raises(LLMExtractionError, match="target_slug"):
            v.validate_pair(
                page_a="wiki/concepts/a.md",
                body_a="x",
                page_b="wiki/concepts/b.md",
                body_b="y",
                similarity=0.6,
            )

    def test_rejects_duplicate_without_target_slug(self) -> None:
        client = FakeLLMClient(
            payload={
                "verdict": "duplicate",
                "reason": "Same content but no target named.",
            }
        )
        v = _make_validator(client)
        with pytest.raises(LLMExtractionError, match="target_slug"):
            v.validate_pair(
                page_a="wiki/concepts/a.md",
                body_a="x",
                page_b="wiki/concepts/b.md",
                body_b="x",
                similarity=1.0,
            )

    def test_distinct_does_not_require_target_slug(self) -> None:
        client = FakeLLMClient(
            payload={"verdict": "distinct", "reason": "Different topics."}
        )
        v = _make_validator(client)
        # Must not raise.
        verdict = v.validate_pair(
            page_a="a.md", body_a="x", page_b="b.md", body_b="y", similarity=0.1
        )
        assert verdict.verdict == "distinct"

    def test_surfaces_llm_runtime_error(self) -> None:
        client = FakeLLMClient(raise_error=LLMExtractionError("rate limit"))
        v = _make_validator(client)
        with pytest.raises(LLMExtractionError, match="rate limit"):
            v.validate_pair(
                page_a="a.md", body_a="x", page_b="b.md", body_b="x", similarity=1.0
            )


class TestPromptStructure:
    def test_user_prompt_includes_both_paths_and_bodies(self) -> None:
        client = FakeLLMClient(
            payload={
                "verdict": "distinct",
                "reason": "Different topics.",
            }
        )
        v = _make_validator(client)
        v.validate_pair(
            page_a="wiki/concepts/alpha.md",
            body_a="alpha alpha alpha",
            page_b="wiki/concepts/beta.md",
            body_b="beta beta beta",
            similarity=0.4,
        )
        assert len(client.calls) == 1
        _, user, tool = client.calls[0]
        assert "wiki/concepts/alpha.md" in user
        assert "wiki/concepts/beta.md" in user
        assert "alpha alpha" in user
        assert "beta beta" in user
        # Similarity is mentioned so the LLM has context.
        assert "40%" in user or "0.4" in user

    def test_tool_schema_includes_required_fields(self) -> None:
        client = FakeLLMClient(
            payload={"verdict": "distinct", "reason": "x"}
        )
        v = _make_validator(client)
        v.validate_pair(
            page_a="a.md", body_a="x", page_b="b.md", body_b="y", similarity=0.5
        )
        _, _, tool = client.calls[0]
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        # verdict and reason always required; target_slug enforced by inner validator
        assert "verdict" in schema["required"]
        assert "reason" in schema["required"]
        # Verdict enum is the canonical three values.
        enum = schema["properties"]["verdict"]["enum"]
        assert set(enum) == {"duplicate", "merge", "distinct"}


class TestVerdictKind:
    def test_kind_constants_match_pydantic_operations(self) -> None:
        # The VerdictKind literals must align with what the apply pipeline
        # expects (apply_merge_entities, apply_delete_page).
        assert VerdictKind.DUPLICATE == "duplicate"
        assert VerdictKind.MERGE == "merge"
        assert VerdictKind.DISTINCT == "distinct"
