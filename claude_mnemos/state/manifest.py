from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_mnemos.core.atomic import atomic_write

MANIFEST_FILENAME = ".manifest.json"


class ManifestCorruptError(ValueError):
    """Raised when manifest file is unreadable or fails schema validation."""


class IngestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    ingested_at: datetime
    raw_path: str
    source_path: str | None
    created_pages: list[str] = Field(default_factory=list)
    skipped_collisions: list[str] = Field(default_factory=list)
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    transcript_path: str | None = None
    raw_transcript_bytes: int | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    ingested: dict[str, IngestRecord] = Field(default_factory=dict)

    @classmethod
    def load(cls, vault_root: Path) -> Manifest:
        path = vault_root / MANIFEST_FILENAME
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ManifestCorruptError(
                f"manifest at {path} is not valid JSON: {exc}"
            ) from exc
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ManifestCorruptError(
                f"manifest at {path} fails schema: {exc}"
            ) from exc

    def serialize_to_string(self) -> str:
        """Serialize manifest to the exact JSON string we'd write to disk.

        Used by pipeline to put manifest content into the staging area before promote.
        """
        return (
            json.dumps(
                self.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=False,
            )
            + "\n"
        )

    def save(self, vault_root: Path) -> None:
        path = vault_root / MANIFEST_FILENAME
        atomic_write(path, self.serialize_to_string())

    def add(self, sha: str, record: IngestRecord) -> None:
        if sha in self.ingested:
            raise ValueError(f"manifest already contains record for sha {sha}")
        self.ingested[sha] = record
