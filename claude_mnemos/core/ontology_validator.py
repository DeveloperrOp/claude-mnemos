"""LLM validator for ontology candidate pairs (Phase B3c).

Takes a pair of pages already short-listed by heuristics (B3b) and asks the
LLM to classify the relationship as ``duplicate`` / ``merge`` / ``distinct``,
with a target slug + merged title for the first two verdicts.

Uses the existing :class:`LLMClient` protocol — works with both ``CliLLMClient``
(Claude Code subscription via ``claude -p``) and ``ApiLLMClient`` (legacy API
key). Selection is the orchestrator's job (Phase B3d): it constructs the
client via :func:`make_llm_client` and passes it in.

Strict-validator rule (per Yarik's design directive):
    "verdict == merge" or "verdict == duplicate" without ``target_slug`` is
    a contract violation — the apply pipeline crashes on missing proposed_target.
    We catch this in the schema's inner ``validate`` callback and raise
    :class:`LLMExtractionError` so the orchestrator can skip the pair instead
    of silently creating a broken Suggestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from claude_mnemos.ingest.llm import LLMClient, LLMExtractionError


class VerdictKind:
    """String constants for the three legal verdicts.

    Aligns with ``state.ontology.SuggestionOperation`` semantics:
    - DUPLICATE → emits ``delete_page`` suggestion (one of the two)
    - MERGE     → emits ``merge_entities`` suggestion (combine both)
    - DISTINCT  → no suggestion (false positive caught by LLM)
    """

    DUPLICATE: Literal["duplicate"] = "duplicate"
    MERGE: Literal["merge"] = "merge"
    DISTINCT: Literal["distinct"] = "distinct"


VerdictLiteral = Literal["duplicate", "merge", "distinct"]


@dataclass(frozen=True, slots=True)
class ValidationVerdict:
    verdict: VerdictLiteral
    reason: str
    target_slug: str | None = None
    merged_title: str | None = None


_SYSTEM_PROMPT = """You are an ontology validator for a personal wiki knowledge base.

Your job: given two pages with similar content, decide whether they are:
- "duplicate" — same information, one can be safely deleted (only if texts are essentially identical and no information is lost)
- "merge" — overlapping but each has unique parts; combine into one page (preserves all unique content)
- "distinct" — they cover different topics or contexts despite surface similarity

Conservative bias: when in doubt, choose "distinct". A false-negative wastes
nothing; a false-positive wastes the user's review time and risks
information loss.

For "duplicate" or "merge":
- target_slug: kebab-case identifier for the kept/merged page (lowercase
  letters/digits/hyphens only, no slashes, no `.md` extension, ≤60 chars)
- merged_title: human-readable title for the kept/merged page

For "distinct": only "reason" is required.

Always include "reason" — one to two sentences explaining the verdict."""  # noqa: E501 — LLM prompt; rewrapping would change the prompt content


_TOOL_NAME = "submit_ontology_verdict"

_TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "verdict": {
                "type": "string",
                "enum": [VerdictKind.DUPLICATE, VerdictKind.MERGE, VerdictKind.DISTINCT],
            },
            "target_slug": {
                "type": "string",
                "pattern": r"^[a-z0-9]+(-[a-z0-9]+)*$",
                "maxLength": 60,
            },
            "merged_title": {"type": "string", "maxLength": 200},
            "reason": {"type": "string", "minLength": 1, "maxLength": 1000},
        },
        "required": ["verdict", "reason"],
    },
}


def _validate_payload(payload: dict[str, Any]) -> None:
    """Inner validator passed to ``LLMClient.extract(validate=...)``.

    The JSON-schema-level validator already enforces field shapes; this
    handles cross-field invariants the schema can't express:

    - "merge" and "duplicate" verdicts MUST carry a ``target_slug``.
    - "merge" SHOULD carry a ``merged_title`` (we accept its absence —
      apply pipeline falls back to title-cased slug — but log it).
    """
    verdict = payload.get("verdict")
    if verdict in (VerdictKind.MERGE, VerdictKind.DUPLICATE) and not payload.get("target_slug"):
        raise LLMExtractionError(
            f"verdict={verdict!r} requires target_slug; got payload={payload}"
        )


class OntologyLLMValidator:
    """Wraps an :class:`LLMClient` and exposes a single ``validate_pair``
    method that classifies a candidate pair.
    """

    def __init__(self, *, llm: LLMClient) -> None:
        self.llm = llm

    def validate_pair(
        self,
        *,
        page_a: str,
        body_a: str,
        page_b: str,
        body_b: str,
        similarity: float,
    ) -> ValidationVerdict:
        """Ask the LLM to classify the relationship between two pages.

        Bodies are sent verbatim (no truncation) — caller is responsible for
        ensuring they fit within the model's context window.
        """
        similarity_pct = int(round(similarity * 100))
        user = (
            f"Path A: {page_a}\n"
            f"---\n"
            f"{body_a}\n\n"
            f"Path B: {page_b}\n"
            f"---\n"
            f"{body_b}\n\n"
            f"These pages have {similarity_pct}% text similarity. "
            f"Classify their relationship."
        )

        result = self.llm.extract(
            system=_SYSTEM_PROMPT,
            user=user,
            tool=_TOOL_SCHEMA,
            validate=_validate_payload,
        )
        payload = result.payload
        return ValidationVerdict(
            verdict=payload["verdict"],
            reason=payload["reason"],
            target_slug=payload.get("target_slug"),
            merged_title=payload.get("merged_title"),
        )
