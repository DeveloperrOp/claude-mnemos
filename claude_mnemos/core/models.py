from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

PageType = Literal["entity", "concept", "source"]
PageStatus = Literal["draft", "reviewed", "verified", "stale", "archived"]
PageFlavor = Literal["pattern", "mistake", "decision", "lesson", "reference"]


class WikiPageFrontmatter(BaseModel):
    """Minimal frontmatter schema. Spec: section 6.4."""

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


@dataclass(frozen=True)
class WikiPage:
    relative_path: Path
    frontmatter: WikiPageFrontmatter
    body: str

    def serialize(self) -> str:
        """Serialize the page to a markdown string with YAML frontmatter.

        Output always ends with exactly one newline regardless of trailing
        whitespace in ``body``.
        """
        fm_dict = self.frontmatter.model_dump(mode="json", exclude_defaults=False)
        yaml_block = yaml.safe_dump(
            fm_dict,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
        return f"---\n{yaml_block}---\n{self.body.rstrip(chr(10))}\n"
