from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_mnemos.core.atomic import atomic_write

SUGGESTIONS_DIRNAME = ".ontology-suggestions"
ARCHIVE_DIRNAME = "archive"
SUGGESTION_ID_RE = re.compile(r"^ont-\d{4}-\d{2}-\d{2}-[0-9a-f]{6}$")

logger = logging.getLogger(__name__)

SuggestionStatus = Literal["pending", "approved", "rejected", "deferred"]
SuggestionOperation = Literal["merge_entities", "rename_entity", "delete_page"]


class OntologyCorruptError(ValueError):
    """Raised when a suggestion file is unreadable or fails schema validation."""


def generate_suggestion_id(today: datetime | None = None) -> str:
    today = today or datetime.utcnow()
    return f"ont-{today.strftime('%Y-%m-%d')}-{uuid4().hex[:6]}"


class SuggestionFrontmatter(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(pattern=SUGGESTION_ID_RE.pattern)
    created: datetime
    operation: SuggestionOperation
    status: SuggestionStatus = "pending"
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    affected_pages: list[str] = Field(min_length=1)
    proposed_target: str | None = None
    reason: str = ""
    applied_at: datetime | None = None
    applied_op_id: str | None = None


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frontmatter: SuggestionFrontmatter
    body: str = ""

    def serialize(self) -> str:
        fm_dict = self.frontmatter.model_dump(mode="json", exclude_none=False)
        yaml_text = yaml.safe_dump(
            fm_dict, sort_keys=False, allow_unicode=True, default_flow_style=False
        )
        return f"---\n{yaml_text}---\n\n{self.body}".rstrip() + "\n"

    @classmethod
    def parse(cls, text: str) -> Suggestion:
        if not text.startswith("---\n"):
            raise OntologyCorruptError("suggestion must start with '---' frontmatter")
        end_marker = "\n---\n"
        end = text.find(end_marker, 4)
        if end < 0:
            raise OntologyCorruptError("suggestion missing closing '---' delimiter")
        yaml_block = text[4:end]
        body = text[end + len(end_marker) :]
        try:
            data = yaml.safe_load(yaml_block) or {}
        except yaml.YAMLError as exc:
            raise OntologyCorruptError(f"invalid YAML frontmatter: {exc}") from exc
        if not isinstance(data, dict):
            raise OntologyCorruptError("frontmatter must be a YAML mapping")
        try:
            fm = SuggestionFrontmatter.model_validate(data)
        except ValidationError as exc:
            raise OntologyCorruptError(f"frontmatter schema mismatch: {exc}") from exc
        return cls(frontmatter=fm, body=body)


class SuggestionStore:
    def __init__(self, vault_root: Path) -> None:
        self.vault = vault_root

    @property
    def root(self) -> Path:
        return self.vault / SUGGESTIONS_DIRNAME

    @property
    def archive(self) -> Path:
        return self.root / ARCHIVE_DIRNAME

    def _file_for(self, suggestion_id: str) -> Path:
        return self.root / f"{suggestion_id}.md"

    def _archive_file_for(self, suggestion_id: str) -> Path:
        return self.archive / f"{suggestion_id}.md"

    def list(self, *, include_archive: bool = False) -> list[Suggestion]:
        results: list[Suggestion] = []
        if not self.root.is_dir():
            return results

        def _safe_load(path: Path) -> Suggestion | None:
            try:
                return Suggestion.parse(path.read_text(encoding="utf-8-sig"))  # tolerate BOM
            except OntologyCorruptError as exc:
                logger.warning("skipping corrupt suggestion %s: %s", path.name, exc)
                return None
            except OSError as exc:
                logger.warning("cannot read suggestion %s: %s", path.name, exc)
                return None

        for entry in sorted(self.root.glob("*.md")):
            if entry.is_file():
                s = _safe_load(entry)
                if s is not None:
                    results.append(s)

        if include_archive and self.archive.is_dir():
            for entry in sorted(self.archive.glob("*.md")):
                if entry.is_file():
                    s = _safe_load(entry)
                    if s is not None:
                        results.append(s)

        return results

    def get(self, suggestion_id: str) -> Suggestion | None:
        for candidate in (self._file_for(suggestion_id), self._archive_file_for(suggestion_id)):
            if candidate.is_file():
                try:
                    return Suggestion.parse(candidate.read_text(encoding="utf-8-sig"))
                except OntologyCorruptError:
                    raise
        return None

    def create(self, suggestion: Suggestion) -> Path:
        target = self._file_for(suggestion.frontmatter.id)
        if target.exists() or self._archive_file_for(suggestion.frontmatter.id).exists():
            raise ValueError(
                f"suggestion already exists: {suggestion.frontmatter.id}"
            )
        atomic_write(target, suggestion.serialize())
        return target

    def update_status(
        self,
        suggestion_id: str,
        status: SuggestionStatus,
        *,
        applied_at: datetime | None = None,
        applied_op_id: str | None = None,
    ) -> Suggestion:
        existing = self.get(suggestion_id)
        if existing is None:
            raise ValueError(f"suggestion not found: {suggestion_id}")
        updates: dict[str, object] = {"status": status}
        if applied_at is not None:
            updates["applied_at"] = applied_at
        if applied_op_id is not None:
            updates["applied_op_id"] = applied_op_id
        new_fm = existing.frontmatter.model_copy(update=updates)
        new_suggestion = Suggestion(frontmatter=new_fm, body=existing.body)

        # Determine current location
        target = self._file_for(suggestion_id)
        if not target.is_file():
            target = self._archive_file_for(suggestion_id)
        atomic_write(target, new_suggestion.serialize())
        return new_suggestion

    def archive_suggestion(self, suggestion_id: str) -> Path:
        src = self._file_for(suggestion_id)
        if not src.is_file():
            raise ValueError(f"suggestion not in pending area: {suggestion_id}")
        self.archive.mkdir(parents=True, exist_ok=True)
        dst = self._archive_file_for(suggestion_id)
        if dst.exists():
            raise ValueError(f"suggestion already archived: {suggestion_id}")
        shutil.move(str(src), str(dst))
        return dst
