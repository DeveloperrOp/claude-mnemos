from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

PageType = Literal["entity", "concept", "source"]
PageStatus = Literal["draft", "reviewed", "verified", "stale", "archived"]
PageFlavor = Literal["pattern", "mistake", "decision", "lesson", "reference"]
ExtractedPageType = Literal["entity", "concept"]


class ProvenanceCounts(BaseModel):
    """Aggregated provenance percentages for a page (spec §6.5)."""

    model_config = ConfigDict(extra="forbid")

    extracted_pct: int = Field(ge=0, le=100)
    inferred_pct: int = Field(ge=0, le=100)
    ambiguous_pct: int = Field(ge=0, le=100)


class WikiPageFrontmatter(BaseModel):
    """Minimal frontmatter schema (spec §6.4)."""

    model_config = ConfigDict(extra="forbid")

    title: str
    type: PageType
    status: PageStatus = "draft"
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    flavor: list[PageFlavor] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    created: date
    updated: date
    provenance: ProvenanceCounts | None = None
    agent_written: bool = True


@dataclass(frozen=True)
class WikiPage:
    relative_path: Path
    frontmatter: WikiPageFrontmatter
    body: str

    def serialize(self) -> str:
        """Serialize the page to a markdown string with YAML frontmatter."""
        fm_dict = self.frontmatter.model_dump(mode="json", exclude_defaults=False)
        yaml_block = yaml.safe_dump(
            fm_dict,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
        return f"---\n{yaml_block}---\n{self.body.rstrip(chr(10))}\n"


class ExtractedPage(BaseModel):
    """One page returned by LLM via tool use. Mirror of input_schema page item."""

    model_config = ConfigDict(extra="forbid")

    type: ExtractedPageType
    title: str = Field(min_length=1, max_length=200)
    slug_hint: str | None = None
    flavor: list[PageFlavor] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: ProvenanceCounts
    related: list[str] = Field(default_factory=list)
    body: str = Field(min_length=1)


class ExtractionPayload(BaseModel):
    """Top-level structure of save_wiki_pages tool input."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    skipped_reason: str | None = None
    pages: list[ExtractedPage] = Field(default_factory=list)


def save_wiki_pages_tool_schema() -> dict[str, Any]:
    """Return the Anthropic tool definition for save_wiki_pages.

    Flat JSON schema (no oneOf/anyOf) — Claude is more reliable on flat schemas
    with enum discriminators.
    """
    return {
        "name": "save_wiki_pages",
        "description": (
            "Save extracted wiki pages from a Claude Code transcript. "
            "Call this exactly once. If the transcript contains nothing significant "
            "(greeting, ping, trivial Q&A with no decision/insight), return an empty "
            "`pages` array and set `skipped_reason`."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "1-3 sentence summary used in the source page.",
                },
                "skipped_reason": {
                    "type": ["string", "null"],
                    "description": "Reason if pages is empty; null otherwise.",
                },
                "pages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["entity", "concept"],
                            },
                            "title": {"type": "string", "minLength": 1, "maxLength": 200},
                            "slug_hint": {
                                "type": ["string", "null"],
                                "description": "Optional explicit slug; null = derive from title.",
                            },
                            "flavor": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": [
                                        "pattern",
                                        "mistake",
                                        "decision",
                                        "lesson",
                                        "reference",
                                    ],
                                },
                            },
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "provenance": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "extracted_pct": {
                                        "type": "integer",
                                        "minimum": 0,
                                        "maximum": 100,
                                    },
                                    "inferred_pct": {
                                        "type": "integer",
                                        "minimum": 0,
                                        "maximum": 100,
                                    },
                                    "ambiguous_pct": {
                                        "type": "integer",
                                        "minimum": 0,
                                        "maximum": 100,
                                    },
                                },
                                "required": [
                                    "extracted_pct",
                                    "inferred_pct",
                                    "ambiguous_pct",
                                ],
                            },
                            "related": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Wikilinks like '[[other-slug]]'.",
                            },
                            "body": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Markdown body. We add the frontmatter.",
                            },
                        },
                        "required": [
                            "type",
                            "title",
                            "flavor",
                            "confidence",
                            "provenance",
                            "related",
                            "body",
                        ],
                    },
                },
            },
            "required": ["summary", "pages"],
        },
    }
