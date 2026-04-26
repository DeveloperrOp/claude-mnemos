# LLM Extraction Implementation Plan (Plan #2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Превратить raw JSONL transcript Claude Code в структурированные wiki-страницы (`wiki/entities/`, `wiki/concepts/`, `wiki/sources/`) через прямой `anthropic` SDK с tool use; добавить `.manifest.json` для идемпотентности; разделить `raw/chats/` (plain transcript) и `wiki/sources/` (наша structured page).

**Architecture:** См. design doc `docs/plans/2026-04-26-llm-extraction-design.md` (commit `95c64ef`). Прямой `anthropic.Anthropic` клиент с одним tool'ом и плоской JSON-схемой. Pydantic-валидация всех страниц до первой записи. Manifest-based dedup по SHA-256 транскрипта. Slug collision = skip-with-warning (merge придёт в #6 ontology). Staging/snapshots отложены в #3.

**Tech Stack:** Python 3.12, Pydantic v2, filelock, anthropic SDK, unidecode, pytest+ruff+mypy strict.

---

## Что НЕ делаем в этом плане

См. §2.2 design doc'а — staging, snapshots, lint, ontology, activity log, dashboard, daemon, MCP, hooks, AGENTS.md, inline `^[…]` маркеры, 4-factor confidence, lifecycle, `index.md`/`hot.md`. Все это последующие планы (#3, #4, #6, #5+).

---

## Files map

**Создаём:**

| Файл | Ответственность |
|---|---|
| `claude_mnemos/config.py` | Загрузка конфига из env + CLI override |
| `claude_mnemos/core/slug.py` | `make_slug(title) -> str` детерминированно |
| `claude_mnemos/state/__init__.py` | namespace |
| `claude_mnemos/state/manifest.py` | `Manifest` Pydantic + `load`/`save` через atomic_write |
| `claude_mnemos/ingest/llm.py` | `LLMClient` + tool schema + retry на ValidationError |
| `claude_mnemos/ingest/extraction.py` | `extract_wiki_pages` orchestration |
| `claude_mnemos/ingest/prompts/__init__.py` | namespace + helpers `load_system()`, `format_user()` |
| `claude_mnemos/ingest/prompts/system.md` | Системный prompt (en, статичный) |
| `claude_mnemos/ingest/prompts/extract_user.md` | User-prompt template |
| `tests/test_slug.py` | |
| `tests/test_manifest.py` | |
| `tests/test_config.py` | |
| `tests/test_llm.py` | |
| `tests/test_extraction.py` | |
| `tests/test_prompts.py` | |
| `tests/fixtures/llm_responses/single_entity.json` | замоканный tool input |
| `tests/fixtures/llm_responses/multi_pages.json` | |
| `tests/fixtures/llm_responses/empty_skipped.json` | |
| `tests/fixtures/llm_responses/invalid_then_valid.json` | пара: invalid и valid для retry |
| `tests/e2e/__init__.py` | |
| `tests/e2e/test_real_extraction.py` | optional, skipif no API key |

**Изменяем:**

| Файл | Что |
|---|---|
| `pyproject.toml` | Добавить `anthropic>=0.40`, `unidecode>=1.3` в deps; mypy override для `unidecode` |
| `claude_mnemos/core/models.py` | Добавить `ProvenanceCounts`, `ExtractedPage`, `ExtractionPayload`. Добавить опциональные поля `provenance`, `agent_written` в `WikiPageFrontmatter`. Добавить функцию `save_wiki_pages_tool_schema()` |
| `claude_mnemos/ingest/pipeline.py` | Переименовать `ingest_minimal` → `ingest`. Разделить запись `raw/chats/` (plain) vs `wiki/sources/` (structured). Интегрировать manifest. Параметры `extract`, `dry_run`, `llm_client`. Slug collision skip. |
| `claude_mnemos/cli.py` | Флаги `--model`, `--language-hint`, `--max-input-tokens`, `--dry-run`, `--no-llm`. Новые exit codes 66/70/71/74. |
| `tests/test_pipeline.py` | Заменить тесты под новое поведение (split raw/source, manifest, dry-run, no-llm, collision) |
| `tests/test_cli.py` | Обновить под новые флаги; убедиться что `--no-llm` не требует API key |
| `tests/test_models.py` | Добавить тесты для новых полей и для `ProvenanceCounts`/`ExtractedPage`/`ExtractionPayload` |

---

## Зависимости между задачами

```
Task 1 (deps)
    ↓
Task 2 (slug) ─────────────────────┐
                                   │
Task 3 (models extend) ────────────┼──┐
                                   │  │
Task 4 (manifest) ─────────────────┼──┼──┐
                                   │  │  │
Task 5 (config) ──────┐            │  │  │
                      ↓            │  │  │
Task 6 (llm.py) ──────┘            │  │  │
    ↓                              │  │  │
Task 7 (prompts) ─────┐            │  │  │
                      ↓            │  │  │
Task 8 (extraction) ←─┘ ←──────────┘  │  │
    ↓                                  │  │
Task 9 (pipeline rewrite) ←────────────┴──┘
    ↓
Task 10 (cli)
    ↓
Task 11 (optional real e2e)
```

Каждая задача — отдельный коммит, заканчивается зелёным `pytest -v` + `ruff` + `mypy`.

---

## Task 1: Add runtime deps (anthropic, unidecode)

**Files:**
- Modify: `pyproject.toml`

**Why:** Пакеты нужны Tasks 2 (`unidecode` для slug) и 6 (`anthropic` для LLM). Ставим заранее, чтобы каждая последующая задача стартовала на чистом окружении.

- [ ] **Step 1: Обновить `pyproject.toml`**

В секции `[project] dependencies` добавить:

```toml
dependencies = [
    "pydantic>=2.0",
    "filelock>=3.13",
    "pyyaml>=6.0",
    "anthropic>=0.40",
    "unidecode>=1.3",
]
```

В секции `[[tool.mypy.overrides]]` добавить блок (после существующего yaml override):

```toml
[[tool.mypy.overrides]]
module = "unidecode"
ignore_missing_imports = true
```

- [ ] **Step 2: Установить**

```bash
cd /d/code/claude-mnemos && .venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Ожидаем: успешная установка `anthropic`, `unidecode` без ошибок версий.

- [ ] **Step 3: Проверить, что текущие тесты не сломались**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: 32 passed, ruff clean, mypy clean.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add anthropic and unidecode for plan #2"
```

---

## Task 2: slug.py

**Files:**
- Create: `claude_mnemos/core/slug.py`
- Test: `tests/test_slug.py`

**Why:** Детерминированное преобразование `title` → файловое имя для wiki-страниц. UK/RU → ASCII через `unidecode`. Используется в pipeline (Task 9) для derive путей.

- [ ] **Step 1: Падающие тесты**

`tests/test_slug.py`:

```python
import re

import pytest

from claude_mnemos.core.slug import make_slug


def test_basic_ascii_lowercase():
    assert make_slug("Claude Code") == "claude-code"


def test_uppercase_normalized():
    assert make_slug("FOO BAR") == "foo-bar"


def test_punctuation_collapsed_to_dash():
    assert make_slug("Hello, World!") == "hello-world"


def test_multiple_spaces_collapsed():
    assert make_slug("a   b   c") == "a-b-c"


def test_leading_trailing_dashes_stripped():
    assert make_slug("---abc---") == "abc"


def test_unicode_transliterated_to_ascii():
    # Українська → unidecode → ascii. Не проверяем точную строку,
    # т.к. зависит от версии unidecode; проверяем инварианты.
    out = make_slug("Українська страница")
    assert out.isascii()
    assert re.fullmatch(r"[a-z0-9-]+", out)
    assert len(out) > 0


def test_russian_transliterated_to_ascii():
    out = make_slug("Атомарная запись")
    assert out.isascii()
    assert re.fullmatch(r"[a-z0-9-]+", out)


def test_truncates_to_60_chars_at_word_boundary():
    long_title = " ".join(["wordone"] * 20)  # > 60 chars
    out = make_slug(long_title)
    assert len(out) <= 60
    # Никаких leading/trailing dash после truncation
    assert not out.startswith("-")
    assert not out.endswith("-")


def test_empty_string_returns_untitled_with_hash():
    out = make_slug("")
    assert out.startswith("untitled-")
    assert len(out) == len("untitled-") + 8


def test_whitespace_only_returns_untitled():
    out = make_slug("   \t\n  ")
    assert out.startswith("untitled-")


def test_idempotent():
    s = make_slug("Some Title With Spaces")
    assert make_slug(s) == s


def test_pure_emoji_returns_untitled():
    out = make_slug("🎉🎊")
    assert out.startswith("untitled-")


def test_mixed_emoji_and_text_keeps_text():
    out = make_slug("Hello 🎉 World")
    assert "hello" in out
    assert "world" in out
    assert out.isascii()


def test_underscore_treated_as_separator():
    assert make_slug("snake_case_name") == "snake-case-name"


def test_numbers_preserved():
    assert make_slug("Plan 2 v3") == "plan-2-v3"


def test_untitled_hash_deterministic_per_input():
    # Empty hashes by content of the original (lower-case + stripped),
    # пустая строка всегда даёт один и тот же hash → стабильный fallback
    assert make_slug("") == make_slug("")
    assert make_slug("🎉") == make_slug("🎉")
```

- [ ] **Step 2: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_slug.py -v
```

Ожидаем: FAIL `ModuleNotFoundError: No module named 'claude_mnemos.core.slug'`.

- [ ] **Step 3: Реализовать `claude_mnemos/core/slug.py`**

```python
from __future__ import annotations

import hashlib
import re
import unicodedata

from unidecode import unidecode

_MAX_LEN = 60
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def make_slug(title: str) -> str:
    """Deterministically turn a title into an ASCII filename slug.

    - NFKD normalize, drop combining marks
    - unidecode transliteration (UK/RU → ASCII)
    - lowercase
    - collapse non-alphanumerics into single dashes
    - strip leading/trailing dashes
    - truncate to 60 chars at last dash boundary
    - empty → "untitled-<8 hex of original>"
    """
    decomposed = unicodedata.normalize("NFKD", title)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    ascii_form = unidecode(stripped).lower()
    collapsed = _NON_ALNUM.sub("-", ascii_form).strip("-")

    if not collapsed:
        digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
        return f"untitled-{digest}"

    if len(collapsed) <= _MAX_LEN:
        return collapsed

    # Truncate at last dash within limit; if none, hard-cut.
    head = collapsed[:_MAX_LEN]
    last_dash = head.rfind("-")
    if last_dash > 0:
        head = head[:last_dash]
    return head.strip("-")
```

- [ ] **Step 4: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_slug.py -v
```

Ожидаем: 15 passed.

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/core/slug.py tests/test_slug.py
git commit -m "feat(core): deterministic slug normalization with unicode transliteration"
```

---

## Task 3: Extend models.py — provenance, ExtractedPage, ExtractionPayload, tool schema

**Files:**
- Modify: `claude_mnemos/core/models.py`
- Modify: `tests/test_models.py`

**Why:** Нужны Pydantic-зеркала структуры, которую LLM возвращает через tool input (§4.3 design'а). Расширяем `WikiPageFrontmatter` опциональными `provenance` и `agent_written` (§5 design'а). Добавляем фабрику `save_wiki_pages_tool_schema()` чтобы Task 6 мог импортировать готовую schema.

- [ ] **Step 1: Падающие тесты**

Дополнить `tests/test_models.py` (в конец файла):

```python
import pytest
from datetime import date

from claude_mnemos.core.models import (
    ExtractedPage,
    ExtractionPayload,
    ProvenanceCounts,
    WikiPageFrontmatter,
    save_wiki_pages_tool_schema,
)


def test_provenance_counts_valid():
    p = ProvenanceCounts(extracted_pct=70, inferred_pct=25, ambiguous_pct=5)
    assert p.extracted_pct == 70


def test_provenance_counts_rejects_negative():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ProvenanceCounts(extracted_pct=-1, inferred_pct=0, ambiguous_pct=0)


def test_provenance_counts_rejects_over_100():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ProvenanceCounts(extracted_pct=101, inferred_pct=0, ambiguous_pct=0)


def test_extracted_page_minimal_valid():
    page = ExtractedPage(
        type="entity",
        title="FastAPI",
        flavor=[],
        confidence=0.8,
        provenance=ProvenanceCounts(extracted_pct=80, inferred_pct=15, ambiguous_pct=5),
        related=[],
        body="FastAPI is a Python web framework.",
    )
    assert page.title == "FastAPI"
    assert page.slug_hint is None


def test_extracted_page_rejects_source_type():
    # source pages we generate ourselves; LLM only returns entity/concept
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtractedPage(
            type="source",
            title="X",
            flavor=[],
            confidence=0.7,
            provenance=ProvenanceCounts(extracted_pct=100, inferred_pct=0, ambiguous_pct=0),
            related=[],
            body="x",
        )


def test_extracted_page_rejects_extra_fields():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtractedPage(
            type="entity",
            title="X",
            flavor=[],
            confidence=0.7,
            provenance=ProvenanceCounts(extracted_pct=100, inferred_pct=0, ambiguous_pct=0),
            related=[],
            body="x",
            unknown="oops",
        )


def test_extracted_page_rejects_empty_body():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtractedPage(
            type="entity",
            title="X",
            flavor=[],
            confidence=0.7,
            provenance=ProvenanceCounts(extracted_pct=100, inferred_pct=0, ambiguous_pct=0),
            related=[],
            body="",
        )


def test_extraction_payload_with_pages():
    payload = ExtractionPayload(
        summary="A discussion about FastAPI.",
        pages=[
            ExtractedPage(
                type="entity",
                title="FastAPI",
                flavor=["reference"],
                confidence=0.9,
                provenance=ProvenanceCounts(extracted_pct=80, inferred_pct=15, ambiguous_pct=5),
                related=[],
                body="A Python framework.",
            )
        ],
    )
    assert len(payload.pages) == 1
    assert payload.skipped_reason is None


def test_extraction_payload_empty_pages_with_reason():
    payload = ExtractionPayload(
        summary="Just a greeting.",
        skipped_reason="trivial conversation",
        pages=[],
    )
    assert payload.pages == []
    assert payload.skipped_reason == "trivial conversation"


def test_frontmatter_accepts_provenance():
    p = ProvenanceCounts(extracted_pct=70, inferred_pct=25, ambiguous_pct=5)
    fm = WikiPageFrontmatter(
        title="X",
        type="entity",
        provenance=p,
        created=date(2026, 4, 26),
        updated=date(2026, 4, 26),
    )
    assert fm.provenance is not None
    assert fm.provenance.extracted_pct == 70


def test_frontmatter_agent_written_default_true():
    fm = WikiPageFrontmatter(
        title="X",
        type="entity",
        created=date(2026, 4, 26),
        updated=date(2026, 4, 26),
    )
    assert fm.agent_written is True


def test_frontmatter_provenance_serializes_as_dict():
    p = ProvenanceCounts(extracted_pct=70, inferred_pct=25, ambiguous_pct=5)
    fm = WikiPageFrontmatter(
        title="X",
        type="entity",
        provenance=p,
        created=date(2026, 4, 26),
        updated=date(2026, 4, 26),
    )
    dumped = fm.model_dump(mode="json")
    assert dumped["provenance"] == {"extracted_pct": 70, "inferred_pct": 25, "ambiguous_pct": 5}


def test_tool_schema_shape():
    schema = save_wiki_pages_tool_schema()
    assert schema["name"] == "save_wiki_pages"
    assert "input_schema" in schema
    inp = schema["input_schema"]
    assert inp["type"] == "object"
    assert "summary" in inp["properties"]
    assert "pages" in inp["properties"]
    assert inp["additionalProperties"] is False
    page_item = inp["properties"]["pages"]["items"]
    assert page_item["additionalProperties"] is False
    assert "type" in page_item["properties"]
    assert page_item["properties"]["type"]["enum"] == ["entity", "concept"]
```

- [ ] **Step 2: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_models.py -v
```

Ожидаем: ImportError.

- [ ] **Step 3: Расширить `claude_mnemos/core/models.py`**

Заменить существующий файл целиком:

```python
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
                                    "enum": ["pattern", "mistake", "decision", "lesson", "reference"],
                                },
                            },
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "provenance": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "extracted_pct": {"type": "integer", "minimum": 0, "maximum": 100},
                                    "inferred_pct": {"type": "integer", "minimum": 0, "maximum": 100},
                                    "ambiguous_pct": {"type": "integer", "minimum": 0, "maximum": 100},
                                },
                                "required": ["extracted_pct", "inferred_pct", "ambiguous_pct"],
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
```

- [ ] **Step 4: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_models.py -v
```

Ожидаем: все старые + 13 новых тестов проходят (≥19 total в этом файле).

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/core/models.py tests/test_models.py
git commit -m "feat(core): ExtractedPage/ExtractionPayload + tool schema for LLM extraction"
```

---

## Task 4: Manifest

**Files:**
- Create: `claude_mnemos/state/__init__.py`
- Create: `claude_mnemos/state/manifest.py`
- Test: `tests/test_manifest.py`

**Why:** SHA-256-based dedup для idempotency. Pydantic-валидируемая schema, atomic load/save (§6 design'а).

- [ ] **Step 1: Падающие тесты**

`tests/test_manifest.py`:

```python
from datetime import datetime
from pathlib import Path

import pytest

from claude_mnemos.state.manifest import (
    IngestRecord,
    Manifest,
    ManifestCorruptError,
)


def _record(sid: str = "abc") -> IngestRecord:
    return IngestRecord(
        session_id=sid,
        ingested_at=datetime(2026, 4, 26, 14, 30, 0),
        raw_path=f"raw/chats/{sid}.md",
        source_path=f"wiki/sources/2026-04-26-{sid}.md",
        created_pages=[
            f"wiki/sources/2026-04-26-{sid}.md",
            "wiki/entities/foo.md",
        ],
        skipped_collisions=[],
        model="claude-sonnet-4-6",
        input_tokens=1234,
        output_tokens=456,
    )


def test_load_missing_file_returns_empty_manifest(tmp_path: Path):
    m = Manifest.load(tmp_path)
    assert m.version == 1
    assert m.ingested == {}


def test_save_then_load_roundtrip(tmp_path: Path):
    m = Manifest()
    m.add("sha-1", _record("sid-1"))
    m.save(tmp_path)

    assert (tmp_path / ".manifest.json").exists()

    loaded = Manifest.load(tmp_path)
    assert "sha-1" in loaded.ingested
    assert loaded.ingested["sha-1"].session_id == "sid-1"
    assert loaded.ingested["sha-1"].input_tokens == 1234


def test_load_corrupt_json_raises(tmp_path: Path):
    (tmp_path / ".manifest.json").write_text("not json {", encoding="utf-8")
    with pytest.raises(ManifestCorruptError):
        Manifest.load(tmp_path)


def test_load_invalid_schema_raises(tmp_path: Path):
    # Valid JSON but wrong shape
    (tmp_path / ".manifest.json").write_text(
        '{"version": 1, "ingested": {"x": {"unknown_field": 1}}}',
        encoding="utf-8",
    )
    with pytest.raises(ManifestCorruptError):
        Manifest.load(tmp_path)


def test_load_unknown_top_level_field_raises(tmp_path: Path):
    (tmp_path / ".manifest.json").write_text(
        '{"version": 1, "ingested": {}, "unknown": 1}',
        encoding="utf-8",
    )
    with pytest.raises(ManifestCorruptError):
        Manifest.load(tmp_path)


def test_add_duplicate_sha_raises():
    m = Manifest()
    m.add("sha-1", _record())
    with pytest.raises(ValueError):
        m.add("sha-1", _record())


def test_save_uses_atomic_write_no_partial_file(tmp_path: Path, monkeypatch):
    m = Manifest()
    m.add("sha-1", _record())

    def boom(*args, **kwargs):
        raise RuntimeError("simulated mid-write crash")

    monkeypatch.setattr("claude_mnemos.state.manifest.os.replace", boom)
    with pytest.raises(RuntimeError):
        m.save(tmp_path)

    # Никаких .tmp обломков
    leftovers = list(tmp_path.glob(".manifest.json*"))
    assert leftovers == []


def test_record_with_none_for_no_llm_path(tmp_path: Path):
    rec = IngestRecord(
        session_id="sid-x",
        ingested_at=datetime(2026, 4, 26, 14, 30, 0),
        raw_path="raw/chats/sid-x.md",
        source_path=None,
        created_pages=["raw/chats/sid-x.md"],
        skipped_collisions=[],
        model=None,
        input_tokens=None,
        output_tokens=None,
    )
    m = Manifest()
    m.add("sha-x", rec)
    m.save(tmp_path)

    loaded = Manifest.load(tmp_path)
    assert loaded.ingested["sha-x"].source_path is None
    assert loaded.ingested["sha-x"].model is None
```

- [ ] **Step 2: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_manifest.py -v
```

Ожидаем: ImportError.

- [ ] **Step 3: Создать namespace `claude_mnemos/state/__init__.py`**

```python
```

(пустой файл)

- [ ] **Step 4: Реализовать `claude_mnemos/state/manifest.py`**

```python
from __future__ import annotations

import json
import os  # noqa: F401  # re-exported for monkeypatch in tests
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


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    ingested: dict[str, IngestRecord] = Field(default_factory=dict)

    @classmethod
    def load(cls, vault_root: Path) -> Manifest:
        path = vault_root / MANIFEST_FILENAME
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ManifestCorruptError(f"manifest at {path} is not valid JSON: {exc}") from exc
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ManifestCorruptError(f"manifest at {path} fails schema: {exc}") from exc

    def save(self, vault_root: Path) -> None:
        path = vault_root / MANIFEST_FILENAME
        payload = json.dumps(
            self.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
            sort_keys=False,
        )
        atomic_write(path, payload + "\n")

    def add(self, sha: str, record: IngestRecord) -> None:
        if sha in self.ingested:
            raise ValueError(f"manifest already contains record for sha {sha}")
        self.ingested[sha] = record
```

- [ ] **Step 5: Прогнать тесты**

Тест `test_save_uses_atomic_write_no_partial_file` патчит `os.replace` в module-неймспейсе — для этого `atomic_write` должен использовать `os.replace` через прямой `import os` в `core/atomic.py` (он так и делает). Но monkeypatch указывает на `claude_mnemos.state.manifest.os.replace` — это работает только если `manifest.py` импортирует `os` сам. Поэтому в файле `import os` оставлено с `# noqa: F401` именно ради этого хука. Альтернативно — перепатчить на `claude_mnemos.core.atomic.os.replace`. Изменить тест если нужно:

Если `monkeypatch.setattr("claude_mnemos.state.manifest.os.replace", boom)` не срабатывает (atomic_write импортирует свой os), переписать строку на:
```python
monkeypatch.setattr("claude_mnemos.core.atomic.os.replace", boom)
```
И убрать `import os` из manifest.py (оставить чисто).

```bash
.venv/Scripts/python.exe -m pytest tests/test_manifest.py -v
```

Ожидаем: 8 passed.

- [ ] **Step 6: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное.

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/state/__init__.py claude_mnemos/state/manifest.py tests/test_manifest.py
git commit -m "feat(state): manifest with sha-256 dedup and atomic save"
```

---

## Task 5: Config loader

**Files:**
- Create: `claude_mnemos/config.py`
- Test: `tests/test_config.py`

**Why:** Централизованный source-of-truth конфигурации (env + override). Используется LLMClient (Task 6) и pipeline (Task 9).

- [ ] **Step 1: Падающие тесты**

`tests/test_config.py`:

```python
import pytest

from claude_mnemos.config import (
    DEFAULT_MAX_INPUT_TOKENS,
    DEFAULT_MODEL,
    Config,
    UnknownLanguageHintError,
    resolve_model_id,
)


def test_default_config(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MNEMOS_MODEL", raising=False)
    monkeypatch.delenv("MNEMOS_LANGUAGE_HINT", raising=False)
    monkeypatch.delenv("MNEMOS_MAX_INPUT_TOKENS", raising=False)
    monkeypatch.delenv("MNEMOS_LOCK_TIMEOUT", raising=False)

    cfg = Config.from_env()
    assert cfg.api_key is None
    assert cfg.model == DEFAULT_MODEL
    assert cfg.language_hint == "auto"
    assert cfg.max_input_tokens == DEFAULT_MAX_INPUT_TOKENS
    assert cfg.lock_timeout == 60.0


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("MNEMOS_MODEL", "haiku")
    monkeypatch.setenv("MNEMOS_LANGUAGE_HINT", "uk")
    monkeypatch.setenv("MNEMOS_MAX_INPUT_TOKENS", "50000")
    monkeypatch.setenv("MNEMOS_LOCK_TIMEOUT", "10.5")

    cfg = Config.from_env()
    assert cfg.api_key == "sk-test"
    # haiku alias resolved to full id
    assert cfg.model.startswith("claude-haiku-")
    assert cfg.language_hint == "uk"
    assert cfg.max_input_tokens == 50000
    assert cfg.lock_timeout == 10.5


def test_with_overrides_keeps_unset_from_env(monkeypatch):
    monkeypatch.setenv("MNEMOS_MODEL", "sonnet")
    cfg = Config.from_env().with_overrides(language_hint="en")
    assert cfg.model.startswith("claude-sonnet-")
    assert cfg.language_hint == "en"


def test_with_overrides_explicit_full_id_passes_through():
    cfg = Config.from_env().with_overrides(model="claude-opus-4-7")
    assert cfg.model == "claude-opus-4-7"


def test_resolve_model_id_aliases():
    assert resolve_model_id("sonnet") == "claude-sonnet-4-6"
    assert resolve_model_id("haiku") == "claude-haiku-4-5-20251001"
    assert resolve_model_id("opus") == "claude-opus-4-7"


def test_resolve_model_id_pass_through():
    assert resolve_model_id("claude-something-custom") == "claude-something-custom"


def test_invalid_language_hint_raises(monkeypatch):
    monkeypatch.setenv("MNEMOS_LANGUAGE_HINT", "klingon")
    with pytest.raises(UnknownLanguageHintError):
        Config.from_env()


def test_invalid_max_input_tokens_raises(monkeypatch):
    monkeypatch.setenv("MNEMOS_MAX_INPUT_TOKENS", "not-a-number")
    with pytest.raises(ValueError):
        Config.from_env()
```

- [ ] **Step 2: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_config.py -v
```

Ожидаем: ImportError.

- [ ] **Step 3: Реализовать `claude_mnemos/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Literal

LanguageHint = Literal["auto", "uk", "ru", "en"]

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_INPUT_TOKENS = 150_000
DEFAULT_LOCK_TIMEOUT = 60.0
DEFAULT_LANGUAGE_HINT: LanguageHint = "auto"

_MODEL_ALIASES = {
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
    "opus": "claude-opus-4-7",
}

_VALID_HINTS: set[str] = {"auto", "uk", "ru", "en"}


class UnknownLanguageHintError(ValueError):
    """Raised when MNEMOS_LANGUAGE_HINT is not in {auto, uk, ru, en}."""


def resolve_model_id(model_or_alias: str) -> str:
    """Map sonnet/haiku/opus aliases to full model ids; pass through others."""
    return _MODEL_ALIASES.get(model_or_alias, model_or_alias)


@dataclass(frozen=True)
class Config:
    api_key: str | None
    model: str
    language_hint: LanguageHint
    max_input_tokens: int
    lock_timeout: float

    @classmethod
    def from_env(cls) -> Config:
        api_key = os.environ.get("ANTHROPIC_API_KEY") or None

        model_raw = os.environ.get("MNEMOS_MODEL", DEFAULT_MODEL)
        model = resolve_model_id(model_raw)

        hint_raw = os.environ.get("MNEMOS_LANGUAGE_HINT", DEFAULT_LANGUAGE_HINT)
        if hint_raw not in _VALID_HINTS:
            raise UnknownLanguageHintError(
                f"MNEMOS_LANGUAGE_HINT={hint_raw!r}; expected one of {sorted(_VALID_HINTS)}"
            )

        max_tokens_raw = os.environ.get("MNEMOS_MAX_INPUT_TOKENS")
        max_tokens = int(max_tokens_raw) if max_tokens_raw else DEFAULT_MAX_INPUT_TOKENS

        lock_raw = os.environ.get("MNEMOS_LOCK_TIMEOUT")
        lock = float(lock_raw) if lock_raw else DEFAULT_LOCK_TIMEOUT

        return cls(
            api_key=api_key,
            model=model,
            language_hint=hint_raw,  # type: ignore[arg-type]
            max_input_tokens=max_tokens,
            lock_timeout=lock,
        )

    def with_overrides(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        language_hint: LanguageHint | None = None,
        max_input_tokens: int | None = None,
        lock_timeout: float | None = None,
    ) -> Config:
        return replace(
            self,
            api_key=api_key if api_key is not None else self.api_key,
            model=resolve_model_id(model) if model is not None else self.model,
            language_hint=language_hint if language_hint is not None else self.language_hint,
            max_input_tokens=(
                max_input_tokens if max_input_tokens is not None else self.max_input_tokens
            ),
            lock_timeout=lock_timeout if lock_timeout is not None else self.lock_timeout,
        )
```

- [ ] **Step 4: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_config.py -v
```

Ожидаем: 8 passed.

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/config.py tests/test_config.py
git commit -m "feat(config): env-based config with model aliases and language hints"
```

---

## Task 6: LLM client (anthropic SDK wrapper)

**Files:**
- Create: `claude_mnemos/ingest/llm.py`
- Test: `tests/test_llm.py`

**Why:** Тонкая обёртка над `anthropic.Anthropic` с принуждением tool use, retry на ValidationError, token-budget guard. DI-friendly: pipeline создаёт `LLMClient` и передаёт его в extraction (для лёгкого мока).

- [ ] **Step 1: Падающие тесты**

`tests/test_llm.py`:

```python
from unittest.mock import MagicMock

import pytest

from claude_mnemos.config import Config
from claude_mnemos.ingest.llm import (
    LLMClient,
    LLMExtractionError,
    MissingApiKeyError,
    TranscriptTooLargeError,
)


def _cfg(**overrides) -> Config:
    base = Config(
        api_key="sk-test",
        model="claude-sonnet-4-6",
        language_hint="auto",
        max_input_tokens=10_000,
        lock_timeout=60.0,
    )
    return base.with_overrides(**overrides) if overrides else base


def _make_response_with_tool_use(payload: dict):
    """Construct a minimal anthropic Message-like object with one tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "save_wiki_pages"
    block.input = payload

    resp = MagicMock()
    resp.content = [block]
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    resp.usage = usage
    return resp


def _make_token_count(input_tokens: int):
    tc = MagicMock()
    tc.input_tokens = input_tokens
    return tc


def test_missing_api_key_raises():
    cfg = _cfg(api_key=None)
    with pytest.raises(MissingApiKeyError):
        LLMClient(cfg)


def test_transcript_too_large_raises():
    cfg = _cfg(max_input_tokens=1000)
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(2000)

    client = LLMClient(cfg, _client=inner)
    with pytest.raises(TranscriptTooLargeError):
        client.extract(system="sys", user="usr", tool=_dummy_tool())

    inner.messages.create.assert_not_called()


def test_successful_extract_returns_payload_and_usage():
    cfg = _cfg()
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(500)

    valid_payload = {
        "summary": "ok",
        "skipped_reason": None,
        "pages": [
            {
                "type": "entity",
                "title": "X",
                "slug_hint": None,
                "flavor": [],
                "confidence": 0.7,
                "provenance": {"extracted_pct": 100, "inferred_pct": 0, "ambiguous_pct": 0},
                "related": [],
                "body": "body",
            }
        ],
    }
    inner.messages.create.return_value = _make_response_with_tool_use(valid_payload)

    client = LLMClient(cfg, _client=inner)
    result = client.extract(system="sys", user="usr", tool=_dummy_tool())

    assert result.payload == valid_payload
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    inner.messages.create.assert_called_once()


def test_tool_choice_forces_tool():
    cfg = _cfg()
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(500)
    inner.messages.create.return_value = _make_response_with_tool_use({"summary": "x", "pages": []})

    client = LLMClient(cfg, _client=inner)
    client.extract(system="sys", user="usr", tool=_dummy_tool())

    kwargs = inner.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "save_wiki_pages"}
    assert kwargs["model"] == "claude-sonnet-4-6"
    # System sent with cache_control
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_retries_once_on_validation_error_then_succeeds():
    cfg = _cfg()
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(500)

    invalid = {"summary": "x"}  # missing required "pages"
    valid = {"summary": "x", "pages": []}
    inner.messages.create.side_effect = [
        _make_response_with_tool_use(invalid),
        _make_response_with_tool_use(valid),
    ]

    client = LLMClient(cfg, _client=inner)

    def validate_payload(p):
        if "pages" not in p:
            raise ValueError("missing pages")
        return p

    result = client.extract(
        system="sys", user="usr", tool=_dummy_tool(), validate=validate_payload
    )

    assert result.payload == valid
    assert inner.messages.create.call_count == 2


def test_raises_after_two_validation_failures():
    cfg = _cfg()
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(500)

    bad = {"summary": "x"}
    inner.messages.create.return_value = _make_response_with_tool_use(bad)

    client = LLMClient(cfg, _client=inner)

    def validate_payload(p):
        raise ValueError("always fails")

    with pytest.raises(LLMExtractionError):
        client.extract(
            system="sys", user="usr", tool=_dummy_tool(), validate=validate_payload
        )

    assert inner.messages.create.call_count == 2


def test_response_without_tool_use_block_raises():
    cfg = _cfg()
    inner = MagicMock()
    inner.messages.count_tokens.return_value = _make_token_count(500)

    bad_resp = MagicMock()
    block = MagicMock()
    block.type = "text"
    bad_resp.content = [block]
    inner.messages.create.return_value = bad_resp

    client = LLMClient(cfg, _client=inner)

    with pytest.raises(LLMExtractionError):
        client.extract(system="sys", user="usr", tool=_dummy_tool())


def _dummy_tool() -> dict:
    return {
        "name": "save_wiki_pages",
        "description": "test",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }
```

- [ ] **Step 2: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_llm.py -v
```

Ожидаем: ImportError.

- [ ] **Step 3: Реализовать `claude_mnemos/ingest/llm.py`**

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import anthropic

from claude_mnemos.config import Config

DEFAULT_MAX_TOKENS = 8000
DEFAULT_TIMEOUT_SEC = 120.0


class MissingApiKeyError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is not set and LLM extraction is required."""


class TranscriptTooLargeError(RuntimeError):
    """Raised when prompt token count exceeds configured max_input_tokens."""


class LLMExtractionError(RuntimeError):
    """Raised when LLM call fails to produce a valid tool_use payload after retry."""


@dataclass(frozen=True)
class ExtractionRaw:
    payload: dict[str, Any]
    input_tokens: int
    output_tokens: int


class LLMClient:
    """Thin wrapper around anthropic.Anthropic enforcing single-tool-use extraction.

    Pass `_client` only in tests (DI for mocking).
    """

    def __init__(self, cfg: Config, *, _client: Any | None = None) -> None:
        if _client is None and not cfg.api_key:
            raise MissingApiKeyError(
                "ANTHROPIC_API_KEY is not set. Use --no-llm to skip extraction."
            )
        self.cfg = cfg
        self._client = _client or anthropic.Anthropic(
            api_key=cfg.api_key,
            max_retries=2,  # SDK-level retry on 429/5xx
            timeout=DEFAULT_TIMEOUT_SEC,
        )

    def extract(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        validate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> ExtractionRaw:
        """Single tool-use call. If `validate` raises, retry once with the error
        appended as a user message; if retry also fails, raise LLMExtractionError.
        """
        system_blocks = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        user_messages: list[dict[str, Any]] = [{"role": "user", "content": user}]

        # Token budget check
        try:
            tc = self._client.messages.count_tokens(
                model=self.cfg.model,
                system=system_blocks,
                tools=[tool],
                messages=user_messages,
            )
            input_tokens = int(tc.input_tokens)
        except (AttributeError, TypeError):  # pragma: no cover — defensive
            input_tokens = 0

        if input_tokens > self.cfg.max_input_tokens:
            raise TranscriptTooLargeError(
                f"prompt would be {input_tokens} tokens; "
                f"max_input_tokens={self.cfg.max_input_tokens}"
            )

        # First attempt
        payload = self._call_once(system_blocks, user_messages, tool)
        first_validation_error: Exception | None = None
        if validate is not None:
            try:
                validate(payload)
                return self._build_result(payload)
            except Exception as exc:  # noqa: BLE001
                first_validation_error = exc

        # Retry once with error message
        retry_messages = list(user_messages)
        retry_messages.append(
            {
                "role": "user",
                "content": (
                    "The previous tool call failed schema validation: "
                    f"{first_validation_error}. Please call save_wiki_pages "
                    "again with a corrected payload."
                ),
            }
        )
        try:
            payload2 = self._call_once(system_blocks, retry_messages, tool)
        except LLMExtractionError as exc:
            raise LLMExtractionError(
                f"retry after validation failure also failed: {exc}"
            ) from exc

        if validate is not None:
            try:
                validate(payload2)
            except Exception as exc:  # noqa: BLE001
                raise LLMExtractionError(
                    f"LLM tool input failed validation twice: first={first_validation_error}, "
                    f"second={exc}"
                ) from exc
        return self._build_result(payload2)

    def _call_once(
        self,
        system_blocks: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tool: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            resp = self._client.messages.create(
                model=self.cfg.model,
                system=system_blocks,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=messages,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
        except anthropic.APIError as exc:
            raise LLMExtractionError(f"anthropic API error: {exc}") from exc

        self._last_input_tokens = int(getattr(resp.usage, "input_tokens", 0))
        self._last_output_tokens = int(getattr(resp.usage, "output_tokens", 0))

        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise LLMExtractionError(
            "LLM response contained no tool_use block — extraction failed."
        )

    def _build_result(self, payload: dict[str, Any]) -> ExtractionRaw:
        return ExtractionRaw(
            payload=payload,
            input_tokens=getattr(self, "_last_input_tokens", 0),
            output_tokens=getattr(self, "_last_output_tokens", 0),
        )
```

- [ ] **Step 4: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_llm.py -v
```

Ожидаем: 8 passed.

- [ ] **Step 5: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Если mypy ругается на `anthropic` types — добавить в `pyproject.toml`:
```toml
[[tool.mypy.overrides]]
module = "anthropic"
ignore_missing_imports = true
```

Ожидаем: всё зелёное.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/ingest/llm.py tests/test_llm.py pyproject.toml
git commit -m "feat(ingest): LLMClient wrapper with tool use, retry on validation, token budget"
```

---

## Task 7: Prompts (system + user)

**Files:**
- Create: `claude_mnemos/ingest/prompts/__init__.py`
- Create: `claude_mnemos/ingest/prompts/system.md`
- Create: `claude_mnemos/ingest/prompts/extract_user.md`
- Test: `tests/test_prompts.py`
- Modify: `pyproject.toml` (включить markdown в package data, чтобы prompts попадали в wheel)

**Why:** Хранение промптов в .md-файлах рядом с кодом. `__init__.py` даёт `load_system()` и `format_user(transcript, language_hint)` хелперы.

- [ ] **Step 1: Падающие тесты**

`tests/test_prompts.py`:

```python
import re

from claude_mnemos.ingest.prompts import format_user, load_system


def test_load_system_returns_non_empty_string():
    s = load_system()
    assert isinstance(s, str)
    assert len(s) > 100
    # Sanity content checks — these strings must remain in the prompt.
    assert "save_wiki_pages" in s
    assert "entity" in s.lower()
    assert "concept" in s.lower()


def test_load_system_cached():
    # Two calls return the exact same object (or at least equal content).
    assert load_system() == load_system()


def test_format_user_inlines_transcript():
    transcript = "## user\n\nhello\n\n## assistant\n\nhi back"
    out = format_user(transcript=transcript, language_hint="auto")
    assert "hello" in out
    assert "hi back" in out


def test_format_user_inlines_language_hint():
    out = format_user(transcript="x", language_hint="uk")
    assert 'language_hint="uk"' in out


def test_format_user_no_unsubstituted_placeholders():
    out = format_user(transcript="x", language_hint="auto")
    # Шаблон не должен оставлять незаменённые {transcript} / {language_hint}
    assert not re.search(r"\{transcript\}|\{language_hint\}", out)
```

- [ ] **Step 2: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_prompts.py -v
```

Ожидаем: ImportError.

- [ ] **Step 3: Создать `claude_mnemos/ingest/prompts/system.md`**

```markdown
You extract structured knowledge pages from a Claude Code chat transcript for the user's per-project Obsidian vault. You are called once per session via the `save_wiki_pages` tool. You MUST call `save_wiki_pages` exactly once and produce no free text.

# Page types

- **entity**: a concrete thing — a module, file, library, tool, service, person, project, or specific bug. Examples of slugs: `fastapi`, `claude-runner`, `file-lock-bug`.
- **concept**: an idea, pattern, architectural decision, lesson learned, or principle. Examples: `atomic-writes`, `5-layer-defense`, `prefer-fastapi-over-flask`.

If unsure whether something is an entity or concept, prefer **concept** for ideas/patterns and **entity** for nameable things.

# Flavor (closed vocabulary)

A page may have any combination of: `pattern`, `mistake`, `decision`, `lesson`, `reference`. Use empty array if none apply.

# Output language

Match the dominant language of the transcript (Ukrainian, Russian, English). Headings and frontmatter values in the same language. Slugs are always ASCII — set `slug_hint` only if you want a specific English slug; otherwise we will derive it from the title.

# Selectivity

- Skip greetings, pings, and trivial Q&A. Return `pages: []` and a brief `skipped_reason`.
- One page per real concept, not per mention. If the transcript discusses three facets of the same thing, produce one page.
- Body must be 80%+ grounded in the transcript. Do not fabricate.
- Low recall is better than noise. If unsure that something is significant, leave it out — wrong pages are pollution; missing pages can be added next time.

# Confidence

- Default `0.7`.
- Raise to `0.85` when the transcript contains an explicit decision, conclusion, or clear consensus.
- Lower to `0.5` for speculative or exploratory material.

# Provenance percentages

Set `provenance` for every page:
- `extracted_pct`: percentage of body content that is direct quote/restatement of the transcript.
- `inferred_pct`: percentage that is your synthesis or connection not stated explicitly.
- `ambiguous_pct`: percentage where sources within the transcript conflict.

Should sum to roughly 100 (±5 acceptable).

# Related links

Use `[[slug]]` syntax for wikilinks to other pages in this batch or pages you believe already exist. If unsure, omit. Do not invent links.

# Body

Markdown only. Do not include YAML frontmatter — we add it. Use H2 (`##`) for section headings; the title is implicit.

# Hard rules

- Call `save_wiki_pages` exactly once.
- Empty `pages` array is valid; pair it with `skipped_reason`.
- Do not produce any text response outside the tool call.
```

- [ ] **Step 4: Создать `claude_mnemos/ingest/prompts/extract_user.md`**

```markdown
The transcript follows. Extract wiki pages per the system instructions and call save_wiki_pages.

<transcript language_hint="{language_hint}">
{transcript}
</transcript>
```

- [ ] **Step 5: Реализовать `claude_mnemos/ingest/prompts/__init__.py`**

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=1)
def load_system() -> str:
    return (_PROMPTS_DIR / "system.md").read_text(encoding="utf-8")


def format_user(*, transcript: str, language_hint: str) -> str:
    template = (_PROMPTS_DIR / "extract_user.md").read_text(encoding="utf-8")
    return template.format(transcript=transcript, language_hint=language_hint)
```

- [ ] **Step 6: Включить .md файлы в wheel**

В `pyproject.toml` после `[tool.hatch.build.targets.wheel]`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["claude_mnemos"]

[tool.hatch.build.targets.wheel.force-include]
"claude_mnemos/ingest/prompts/system.md" = "claude_mnemos/ingest/prompts/system.md"
"claude_mnemos/ingest/prompts/extract_user.md" = "claude_mnemos/ingest/prompts/extract_user.md"
```

(Опционально, для editable install это не критично — файлы и так читаются из исходников. Включаем для будущей wheel-публикации.)

- [ ] **Step 7: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_prompts.py -v
```

Ожидаем: 5 passed.

- [ ] **Step 8: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное.

- [ ] **Step 9: Commit**

```bash
git add claude_mnemos/ingest/prompts/ tests/test_prompts.py pyproject.toml
git commit -m "feat(ingest): system and user prompts as markdown files"
```

---

## Task 8: Extraction orchestration

**Files:**
- Create: `claude_mnemos/ingest/extraction.py`
- Test: `tests/test_extraction.py`
- Create: `tests/fixtures/llm_responses/single_entity.json`
- Create: `tests/fixtures/llm_responses/multi_pages.json`
- Create: `tests/fixtures/llm_responses/empty_skipped.json`

**Why:** Связка LLMClient + prompts + Pydantic-валидация + рендер каждой `ExtractedPage` в `WikiPage` со slug-derivation. На вход — список TranscriptMessage + Config + LLMClient (DI), на выход — `ExtractionResult(pages, summary, usage)`.

- [ ] **Step 1: Создать fixture-файлы**

`tests/fixtures/llm_responses/single_entity.json`:

```json
{
  "summary": "User asked about FastAPI; we discussed its async support.",
  "skipped_reason": null,
  "pages": [
    {
      "type": "entity",
      "title": "FastAPI",
      "slug_hint": null,
      "flavor": ["reference"],
      "confidence": 0.85,
      "provenance": {"extracted_pct": 80, "inferred_pct": 15, "ambiguous_pct": 5},
      "related": [],
      "body": "FastAPI is a Python web framework with first-class async support."
    }
  ]
}
```

`tests/fixtures/llm_responses/multi_pages.json`:

```json
{
  "summary": "Discussed FastAPI vs Flask, decided to prefer FastAPI for async.",
  "skipped_reason": null,
  "pages": [
    {
      "type": "entity",
      "title": "FastAPI",
      "slug_hint": null,
      "flavor": ["reference"],
      "confidence": 0.9,
      "provenance": {"extracted_pct": 85, "inferred_pct": 10, "ambiguous_pct": 5},
      "related": ["[[prefer-fastapi-over-flask]]"],
      "body": "FastAPI: async-native, type hints, OpenAPI built-in."
    },
    {
      "type": "entity",
      "title": "Flask",
      "slug_hint": null,
      "flavor": ["reference"],
      "confidence": 0.8,
      "provenance": {"extracted_pct": 75, "inferred_pct": 20, "ambiguous_pct": 5},
      "related": [],
      "body": "Flask: minimal, sync-default, large ecosystem."
    },
    {
      "type": "concept",
      "title": "Prefer FastAPI over Flask",
      "slug_hint": "prefer-fastapi-over-flask",
      "flavor": ["decision"],
      "confidence": 0.9,
      "provenance": {"extracted_pct": 70, "inferred_pct": 25, "ambiguous_pct": 5},
      "related": ["[[fastapi]]", "[[flask]]"],
      "body": "When async is required and we have a clean slate, prefer FastAPI."
    }
  ]
}
```

`tests/fixtures/llm_responses/empty_skipped.json`:

```json
{
  "summary": "Ping conversation, no substance.",
  "skipped_reason": "trivial greeting and ping; no decisions or insights.",
  "pages": []
}
```

- [ ] **Step 2: Падающие тесты**

`tests/test_extraction.py`:

```python
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
    # slug_hint was "prefer-fastapi-over-flask"; make_slug normalizes but keeps shape
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
    # validate is callable that runs ExtractionPayload.model_validate
    validate = kwargs["validate"]
    validate(payload)  # should not raise
    with pytest.raises(Exception):
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
```

- [ ] **Step 3: Запустить — упадут**

```bash
.venv/Scripts/python.exe -m pytest tests/test_extraction.py -v
```

Ожидаем: ImportError.

- [ ] **Step 4: Реализовать `claude_mnemos/ingest/extraction.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from claude_mnemos.config import Config
from claude_mnemos.core.models import (
    ExtractedPage,
    ExtractionPayload,
    WikiPage,
    WikiPageFrontmatter,
    save_wiki_pages_tool_schema,
)
from claude_mnemos.core.slug import make_slug
from claude_mnemos.ingest.llm import LLMClient
from claude_mnemos.ingest.prompts import format_user, load_system
from claude_mnemos.ingest.transcript import TranscriptMessage


@dataclass(frozen=True)
class ExtractionResult:
    summary: str
    skipped_reason: str | None
    pages: list[WikiPage]
    input_tokens: int
    output_tokens: int


def extract_wiki_pages(
    *,
    messages: list[TranscriptMessage],
    cfg: Config,
    llm_client: LLMClient,
    today: date,
) -> ExtractionResult:
    """Run the LLM extraction over a parsed transcript and return wiki pages.

    `today` is injected for testability (deterministic created/updated).
    """
    transcript_text = _render_transcript(messages)
    system = load_system()
    user = format_user(transcript=transcript_text, language_hint=cfg.language_hint)

    raw = llm_client.extract(
        system=system,
        user=user,
        tool=save_wiki_pages_tool_schema(),
        validate=_validate_payload,
    )

    payload = ExtractionPayload.model_validate(raw.payload)

    pages = [_render_page(p, today) for p in payload.pages]

    return ExtractionResult(
        summary=payload.summary,
        skipped_reason=payload.skipped_reason,
        pages=pages,
        input_tokens=raw.input_tokens,
        output_tokens=raw.output_tokens,
    )


def _validate_payload(payload: dict) -> ExtractionPayload:
    return ExtractionPayload.model_validate(payload)


def _render_transcript(messages: list[TranscriptMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        lines.append(f"## {m.role}")
        lines.append("")
        lines.append(m.text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_page(p: ExtractedPage, today: date) -> WikiPage:
    slug = make_slug(p.slug_hint) if p.slug_hint else make_slug(p.title)
    folder = "entities" if p.type == "entity" else "concepts"
    rel = Path(f"wiki/{folder}/{slug}.md")

    fm = WikiPageFrontmatter(
        title=p.title,
        type=p.type,
        confidence=p.confidence,
        flavor=p.flavor,
        related=p.related,
        provenance=p.provenance,
        created=today,
        updated=today,
        agent_written=True,
    )
    return WikiPage(relative_path=rel, frontmatter=fm, body=p.body)
```

- [ ] **Step 5: Прогнать тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_extraction.py -v
```

Ожидаем: 7 passed.

- [ ] **Step 6: ruff + mypy + полный pytest**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное.

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/ingest/extraction.py tests/test_extraction.py tests/fixtures/llm_responses/
git commit -m "feat(ingest): orchestrate LLM extraction into validated WikiPages"
```

---

## Task 9: Pipeline rewrite — split raw/source, manifest, dry-run, no-llm, slug-collision

**Files:**
- Modify: `claude_mnemos/ingest/pipeline.py` (полная замена)
- Modify: `tests/test_pipeline.py` (полная замена под новое поведение)

**Why:** Связка всех модулей. Это самая большая задача плана. Меняется поведение: `raw/chats/` теперь без frontmatter, `wiki/sources/` — отдельная страница; добавляется manifest dedup; flags `extract`/`dry_run`; slug collision = skip.

- [ ] **Step 1: Заменить `tests/test_pipeline.py` целиком**

```python
import hashlib
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_mnemos.config import Config
from claude_mnemos.core.models import (
    ExtractionPayload,
    WikiPage,
    WikiPageFrontmatter,
)
from claude_mnemos.ingest.extraction import ExtractionResult
from claude_mnemos.ingest.pipeline import IngestResult, ingest
from claude_mnemos.state.manifest import MANIFEST_FILENAME, Manifest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def _cfg() -> Config:
    return Config(
        api_key="sk-test",
        model="claude-sonnet-4-6",
        language_hint="auto",
        max_input_tokens=150_000,
        lock_timeout=60.0,
    )


def _stub_extraction(today: date) -> ExtractionResult:
    fm = WikiPageFrontmatter(
        title="FastAPI",
        type="entity",
        flavor=[],
        confidence=0.8,
        related=[],
        created=today,
        updated=today,
    )
    page = WikiPage(
        relative_path=Path("wiki/entities/fastapi.md"),
        frontmatter=fm,
        body="FastAPI is a framework.",
    )
    return ExtractionResult(
        summary="Talked about FastAPI.",
        skipped_reason=None,
        pages=[page],
        input_tokens=1000,
        output_tokens=200,
    )


FIXED_TODAY = date(2026, 4, 26)


def _stub_extractor():
    """Returns a callable matching extract_wiki_pages signature."""
    def _extract(*, messages, cfg, llm_client, today):  # noqa: ARG001
        return _stub_extraction(today)
    return _extract


def test_ingest_writes_plain_raw_chat(tmp_path: Path):
    vault = tmp_path / "vault"
    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    raw = vault / "raw" / "chats" / "abc-123.md"
    assert raw.exists()
    text = raw.read_text(encoding="utf-8")
    # Plain transcript: no YAML frontmatter
    assert not text.startswith("---")
    assert text.startswith("# Transcript")
    assert "## user" in text
    assert "Hello, what is 2+2?" in text


def test_ingest_writes_source_page(tmp_path: Path):
    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    assert res.source_path is not None
    assert res.source_path.name == "2026-04-26-abc-123.md"
    assert res.source_path.parent == vault / "wiki" / "sources"
    text = res.source_path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "type: source" in text
    assert "Talked about FastAPI." in text  # summary in body
    assert "[[wiki/entities/fastapi]]" in text


def test_ingest_writes_extracted_pages(tmp_path: Path):
    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    page = vault / "wiki" / "entities" / "fastapi.md"
    assert page.exists()
    assert "type: entity" in page.read_text(encoding="utf-8")
    assert page.as_posix().endswith("wiki/entities/fastapi.md")
    assert any("wiki/entities/fastapi.md" in p.as_posix() for p in res.created_pages)


def test_ingest_creates_manifest_entry(tmp_path: Path):
    vault = tmp_path / "vault"
    ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    m = Manifest.load(vault)
    expected_sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert expected_sha in m.ingested
    rec = m.ingested[expected_sha]
    assert rec.session_id == "abc-123"
    assert rec.source_path is not None
    assert rec.input_tokens == 1000


def test_ingest_idempotent_on_repeat(tmp_path: Path):
    vault = tmp_path / "vault"
    extractor = MagicMock(side_effect=_stub_extractor())

    first = ingest(
        FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor,
        today=FIXED_TODAY,
    )
    assert first.status == "extracted"

    second = ingest(
        FIXTURE, vault, cfg=_cfg(), llm_client=MagicMock(), extractor=extractor,
        today=FIXED_TODAY,
    )
    assert second.status == "already_ingested"
    # Extractor called only once — second was a no-op
    assert extractor.call_count == 1


def test_ingest_dry_run_writes_nothing(tmp_path: Path):
    vault = tmp_path / "vault"
    extractor = MagicMock(side_effect=_stub_extractor())

    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=extractor,
        dry_run=True,
        today=FIXED_TODAY,
    )
    assert res.status == "dry_run"
    # Extractor was called (we exercise the prompt path)
    assert extractor.call_count == 1
    # No files written (vault dir itself may exist from mkdir, but no content)
    assert not (vault / "raw").exists()
    assert not (vault / "wiki").exists()
    assert not (vault / MANIFEST_FILENAME).exists()


def test_ingest_no_llm_writes_only_raw_and_manifest(tmp_path: Path):
    vault = tmp_path / "vault"
    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=None,
        extractor=None,
        extract=False,
        today=FIXED_TODAY,
    )
    assert res.status == "raw_only"
    assert res.source_path is None
    assert (vault / "raw" / "chats" / "abc-123.md").exists()
    assert not (vault / "wiki").exists()

    m = Manifest.load(vault)
    sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert m.ingested[sha].source_path is None
    assert m.ingested[sha].model is None


def test_ingest_skips_existing_extracted_page(tmp_path: Path):
    vault = tmp_path / "vault"
    # Pre-create the file the stub extractor wants to write
    target = vault / "wiki" / "entities" / "fastapi.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("---\ntitle: existing\n---\nbody", encoding="utf-8")

    res = ingest(
        FIXTURE,
        vault,
        cfg=_cfg(),
        llm_client=MagicMock(),
        extractor=_stub_extractor(),
        today=FIXED_TODAY,
    )
    # Existing file is preserved
    assert "existing" in target.read_text(encoding="utf-8")
    # And it's reported as a collision
    assert any("wiki/entities/fastapi.md" in p for p in res.skipped_collisions)


def test_ingest_under_lock_blocks_concurrent(tmp_path: Path):
    from claude_mnemos.core.locks import LockTimeoutError, pipeline_lock

    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = _cfg().with_overrides(lock_timeout=0.2)
    with pipeline_lock(vault, timeout=1.0), pytest.raises(LockTimeoutError):
        ingest(
            FIXTURE,
            vault,
            cfg=cfg,
            llm_client=MagicMock(),
            extractor=_stub_extractor(),
            today=FIXED_TODAY,
        )


def test_ingest_empty_jsonl_does_not_create_vault(tmp_path: Path):
    from claude_mnemos.ingest.transcript import EmptyTranscriptError

    vault = tmp_path / "vault"
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(EmptyTranscriptError):
        ingest(
            empty,
            vault,
            cfg=_cfg(),
            llm_client=MagicMock(),
            extractor=_stub_extractor(),
            today=FIXED_TODAY,
        )
    assert not vault.exists()
```

- [ ] **Step 2: Запустить — упадут (старая `ingest_minimal` не имеет нужной сигнатуры)**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -v
```

Ожидаем: ImportError или AttributeError.

- [ ] **Step 3: Полностью заменить `claude_mnemos/ingest/pipeline.py`**

```python
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from claude_mnemos.config import Config
from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.core.locks import pipeline_lock
from claude_mnemos.core.models import WikiPage, WikiPageFrontmatter
from claude_mnemos.ingest.extraction import ExtractionResult, extract_wiki_pages
from claude_mnemos.ingest.llm import LLMClient
from claude_mnemos.ingest.transcript import TranscriptMessage, parse_jsonl
from claude_mnemos.state.manifest import IngestRecord, Manifest

IngestStatus = Literal["extracted", "raw_only", "already_ingested", "dry_run"]

Extractor = Callable[..., ExtractionResult]


@dataclass(frozen=True)
class IngestResult:
    status: IngestStatus
    session_id: str
    raw_path: Path | None
    source_path: Path | None = None
    created_pages: list[Path] = field(default_factory=list)
    skipped_collisions: list[str] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None


def ingest(
    jsonl_path: Path,
    vault_root: Path,
    *,
    cfg: Config,
    llm_client: LLMClient | None,
    extractor: Extractor | None = extract_wiki_pages,
    extract: bool = True,
    dry_run: bool = False,
    today: date | None = None,
) -> IngestResult:
    """Full ingest pipeline.

    - Parse JSONL (raises EmptyTranscriptError before any side effects).
    - Acquire pipeline lock.
    - Compute SHA-256, check manifest → no-op if seen.
    - Write raw/chats/<sid>.md (plain).
    - If `extract` and not dry_run: call extractor (LLM), write wiki pages, source page.
    - Update and save manifest.

    Pass `extractor` to inject a stub in tests; default uses real extract_wiki_pages.
    Pass `llm_client=None` only when `extract=False` (no-llm path).
    """
    messages = parse_jsonl(jsonl_path)  # may raise EmptyTranscriptError
    session_id = _resolve_session_id(messages, jsonl_path)
    today_d = today or date.today()
    raw_bytes = jsonl_path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()

    vault_root.mkdir(parents=True, exist_ok=True)

    with pipeline_lock(vault_root, timeout=cfg.lock_timeout):
        manifest = Manifest.load(vault_root)
        if sha in manifest.ingested:
            existing = manifest.ingested[sha]
            return IngestResult(
                status="already_ingested",
                session_id=existing.session_id,
                raw_path=vault_root / existing.raw_path,
                source_path=(
                    vault_root / existing.source_path if existing.source_path else None
                ),
                created_pages=[vault_root / p for p in existing.created_pages],
                skipped_collisions=existing.skipped_collisions,
                model=existing.model,
                input_tokens=existing.input_tokens,
                output_tokens=existing.output_tokens,
            )

        raw_relative = Path("raw/chats") / f"{session_id}.md"
        raw_target = vault_root / raw_relative
        raw_body = _render_raw_transcript(messages)

        # No-LLM path: plain raw chat + manifest, done.
        if not extract:
            if not dry_run:
                atomic_write(raw_target, raw_body)
                manifest.add(
                    sha,
                    IngestRecord(
                        session_id=session_id,
                        ingested_at=datetime.now(),
                        raw_path=raw_relative.as_posix(),
                        source_path=None,
                        created_pages=[raw_relative.as_posix()],
                        skipped_collisions=[],
                        model=None,
                        input_tokens=None,
                        output_tokens=None,
                    ),
                )
                manifest.save(vault_root)
            return IngestResult(
                status="raw_only" if not dry_run else "dry_run",
                session_id=session_id,
                raw_path=raw_target if not dry_run else None,
            )

        # LLM extraction required from here on.
        if extractor is None:
            raise ValueError("extractor cannot be None when extract=True")
        if llm_client is None:
            raise ValueError("llm_client cannot be None when extract=True")

        extraction = extractor(
            messages=messages,
            cfg=cfg,
            llm_client=llm_client,
            today=today_d,
        )

        # Build the source page (we generate this, not the LLM)
        source_relative = Path("wiki/sources") / f"{today_d.isoformat()}-{session_id}.md"
        source_page = _build_source_page(
            session_id=session_id,
            summary=extraction.summary,
            skipped_reason=extraction.skipped_reason,
            extracted_pages=extraction.pages,
            today=today_d,
            relative_path=source_relative,
        )

        all_pages = [*extraction.pages, source_page]

        # Detect collisions
        to_write: list[WikiPage] = []
        skipped: list[str] = []
        for p in all_pages:
            if (vault_root / p.relative_path).exists():
                skipped.append(p.relative_path.as_posix())
            else:
                to_write.append(p)

        if dry_run:
            return IngestResult(
                status="dry_run",
                session_id=session_id,
                raw_path=None,
                source_path=None,
                created_pages=[vault_root / p.relative_path for p in to_write],
                skipped_collisions=skipped,
                input_tokens=extraction.input_tokens,
                output_tokens=extraction.output_tokens,
                model=cfg.model,
            )

        # Real writes
        atomic_write(raw_target, raw_body)
        created_paths: list[Path] = []
        for p in to_write:
            target = vault_root / p.relative_path
            atomic_write(target, p.serialize())
            created_paths.append(target)

        manifest.add(
            sha,
            IngestRecord(
                session_id=session_id,
                ingested_at=datetime.now(),
                raw_path=raw_relative.as_posix(),
                source_path=source_relative.as_posix(),
                created_pages=[p.relative_path.as_posix() for p in to_write],
                skipped_collisions=skipped,
                model=cfg.model,
                input_tokens=extraction.input_tokens,
                output_tokens=extraction.output_tokens,
            ),
        )
        manifest.save(vault_root)

        return IngestResult(
            status="extracted",
            session_id=session_id,
            raw_path=raw_target,
            source_path=vault_root / source_relative,
            created_pages=created_paths,
            skipped_collisions=skipped,
            input_tokens=extraction.input_tokens,
            output_tokens=extraction.output_tokens,
            model=cfg.model,
        )


def _resolve_session_id(messages: list[TranscriptMessage], jsonl_path: Path) -> str:
    for m in messages:
        if m.session_id:
            return m.session_id
    return jsonl_path.stem


def _render_raw_transcript(messages: list[TranscriptMessage]) -> str:
    lines = ["# Transcript", ""]
    for m in messages:
        lines.append(f"## {m.role}")
        lines.append("")
        lines.append(m.text)
        lines.append("")
    return "\n".join(lines)


def _build_source_page(
    *,
    session_id: str,
    summary: str,
    skipped_reason: str | None,
    extracted_pages: list[WikiPage],
    today: date,
    relative_path: Path,
) -> WikiPage:
    title = f"Session {session_id} ({today.isoformat()})"
    related = [_to_wikilink(p.relative_path) for p in extracted_pages]
    body_lines = ["## Summary", "", summary, ""]
    if skipped_reason:
        body_lines.extend(["## Skipped", "", skipped_reason, ""])
    if extracted_pages:
        body_lines.append("## Extracted pages")
        body_lines.append("")
        for p in extracted_pages:
            body_lines.append(f"- {_to_wikilink(p.relative_path)}")
        body_lines.append("")
    body_lines.extend(["## Original", "", f"[[raw/chats/{session_id}|Open transcript]]"])
    body = "\n".join(body_lines)

    fm = WikiPageFrontmatter(
        title=title,
        type="source",
        sources=[f"raw/chats/{session_id}.md"],
        related=related,
        created=today,
        updated=today,
        agent_written=True,
    )
    return WikiPage(relative_path=relative_path, frontmatter=fm, body=body)


def _to_wikilink(rel: Path) -> str:
    return f"[[{rel.with_suffix('').as_posix()}]]"
```

- [ ] **Step 4: Прогнать новые pipeline-тесты**

```bash
.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -v
```

Ожидаем: 10 passed.

- [ ] **Step 5: Прогнать ВСЕ тесты — старый `test_cli.py` упадёт**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Ожидаем: tests/test_cli.py FAIL — потому что CLI ещё на `ingest_minimal` и не знает про новые exit-codes/`--no-llm`. Это ожидаемо — починим в Task 10.

- [ ] **Step 6: ruff + mypy**

```bash
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: clean (если mypy ругается на pipeline.py — починить аннотации, в первую очередь Optional[Path]).

- [ ] **Step 7: Commit (с пометкой что CLI временно сломан, починим в следующей задаче)**

```bash
git add claude_mnemos/ingest/pipeline.py tests/test_pipeline.py
git commit -m "refactor(ingest): split raw/chats and wiki/sources, add manifest, dry-run, no-llm

CLI tests intentionally red here; Task 10 (cli rewrite) restores them."
```

---

## Task 10: CLI rewrite — flags, exit codes, plumbing config + LLM client

**Files:**
- Modify: `claude_mnemos/cli.py` (полная замена)
- Modify: `tests/test_cli.py` (расширить под новые флаги/exit codes)

**Why:** Прокинуть Config, LLMClient в новый `pipeline.ingest`. Добавить флаги `--model`, `--language-hint`, `--max-input-tokens`, `--dry-run`, `--no-llm`. Маппинг новых exception'ов на exit codes 66/70/71/74.

- [ ] **Step 1: Заменить `tests/test_cli.py` целиком**

```python
import json
import os
import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def _run(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Гарантируем что во всех тестах ANTHROPIC_API_KEY НЕ установлен по умолчанию.
    env.pop("ANTHROPIC_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "claude_mnemos", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_cli_no_llm_writes_raw_only(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    assert res.returncode == 0, res.stderr

    raw = vault / "raw" / "chats" / "abc-123.md"
    assert raw.exists()
    text = raw.read_text(encoding="utf-8")
    assert text.startswith("# Transcript")
    # Не должно быть wiki/
    assert not (vault / "wiki").exists()
    # Manifest есть
    assert (vault / ".manifest.json").exists()


def test_cli_no_llm_idempotent(tmp_path: Path):
    vault = tmp_path / "vault"
    first = _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    assert first.returncode == 0
    second = _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    assert second.returncode == 0
    assert "already_ingested" in (second.stdout + second.stderr).lower()


def test_cli_missing_jsonl_returns_nonzero(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(tmp_path / "does-not-exist.jsonl"), str(vault), "--no-llm")
    assert res.returncode != 0
    assert "not found" in (res.stderr + res.stdout).lower()


def test_cli_no_command_shows_help():
    res = _run()
    assert res.returncode != 0
    assert "ingest" in (res.stderr + res.stdout).lower()


def test_cli_empty_jsonl_returns_data_error(tmp_path: Path):
    vault = tmp_path / "vault"
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    res = _run("ingest", str(empty), str(vault), "--no-llm")
    assert res.returncode == 65
    assert "empty transcript" in res.stderr.lower()


def test_cli_extract_without_api_key_returns_66(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(FIXTURE), str(vault))  # no --no-llm, no API key
    assert res.returncode == 66
    assert "api" in res.stderr.lower() or "anthropic_api_key" in res.stderr.lower()


def test_cli_unknown_language_hint_returns_2(tmp_path: Path):
    vault = tmp_path / "vault"
    res = _run("ingest", str(FIXTURE), str(vault), "--no-llm", "--language-hint", "klingon")
    assert res.returncode == 2  # argparse choices reject


def test_main_module_safe_to_import():
    import importlib

    mod = importlib.import_module("claude_mnemos.__main__")
    assert hasattr(mod, "main")


def test_cli_no_llm_manifest_records_no_model(tmp_path: Path):
    vault = tmp_path / "vault"
    _run("ingest", str(FIXTURE), str(vault), "--no-llm")
    m = json.loads((vault / ".manifest.json").read_text(encoding="utf-8"))
    rec = next(iter(m["ingested"].values()))
    assert rec["model"] is None
    assert rec["source_path"] is None
```

- [ ] **Step 2: Заменить `claude_mnemos/cli.py` целиком**

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from claude_mnemos.config import Config, UnknownLanguageHintError
from claude_mnemos.core.atomic import FileBusyError
from claude_mnemos.core.locks import LockTimeoutError
from claude_mnemos.ingest.llm import (
    LLMClient,
    LLMExtractionError,
    MissingApiKeyError,
    TranscriptTooLargeError,
)
from claude_mnemos.ingest.pipeline import ingest
from claude_mnemos.ingest.transcript import EmptyTranscriptError
from claude_mnemos.state.manifest import ManifestCorruptError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude_mnemos")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="Ingest a Claude Code JSONL session into a vault")
    p.add_argument("jsonl", type=Path, help="Path to the session JSONL file")
    p.add_argument("vault", type=Path, help="Path to the vault root")
    p.add_argument("--model", type=str, default=None, help="Model id or alias (sonnet/haiku/opus)")
    p.add_argument(
        "--language-hint",
        type=str,
        default=None,
        choices=["auto", "uk", "ru", "en"],
        help="Language hint for the extraction prompt",
    )
    p.add_argument(
        "--max-input-tokens",
        type=int,
        default=None,
        help="Hard upper bound on prompt tokens",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Run extraction but write nothing to the vault",
    )
    p.add_argument(
        "--no-llm",
        action="store_true",
        help="Write raw/chats only; skip LLM extraction (no API key required)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "ingest":
        parser.error(f"unknown command: {args.command}")
        return 2

    if not args.jsonl.exists():
        print(f"error: jsonl not found: {args.jsonl}", file=sys.stderr)
        return 2

    try:
        cfg = Config.from_env().with_overrides(
            model=args.model,
            language_hint=args.language_hint,
            max_input_tokens=args.max_input_tokens,
        )
    except UnknownLanguageHintError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    extract = not args.no_llm
    llm_client: LLMClient | None = None

    try:
        if extract:
            llm_client = LLMClient(cfg)

        result = ingest(
            args.jsonl,
            args.vault,
            cfg=cfg,
            llm_client=llm_client,
            extract=extract,
            dry_run=args.dry_run,
        )
    except EmptyTranscriptError as exc:
        print(f"error: empty transcript: {exc}", file=sys.stderr)
        return 65
    except MissingApiKeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 66
    except LLMExtractionError as exc:
        print(f"error: LLM extraction failed: {exc}", file=sys.stderr)
        return 70
    except TranscriptTooLargeError as exc:
        print(f"error: transcript too large: {exc}", file=sys.stderr)
        return 71
    except LockTimeoutError as exc:
        print(f"error: another ingest is running: {exc}", file=sys.stderr)
        return 73
    except ManifestCorruptError as exc:
        print(f"error: manifest corrupt: {exc}", file=sys.stderr)
        return 74
    except FileBusyError as exc:
        print(f"error: vault file busy after retries: {exc}", file=sys.stderr)
        return 75

    if result.status == "already_ingested":
        print(f"already_ingested: session_id={result.session_id}")
        return 0
    if result.status == "dry_run":
        print(
            f"dry_run: would write {len(result.created_pages)} pages, "
            f"{len(result.skipped_collisions)} collisions"
        )
        return 0
    if result.status == "raw_only":
        print(f"raw_only: wrote {result.raw_path}")
        return 0
    # extracted
    print(
        f"extracted: session_id={result.session_id} "
        f"pages={len(result.created_pages)} skipped={len(result.skipped_collisions)} "
        f"tokens_in={result.input_tokens} tokens_out={result.output_tokens}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Прогнать тесты CLI**

```bash
.venv/Scripts/python.exe -m pytest tests/test_cli.py -v
```

Ожидаем: 9 passed.

- [ ] **Step 4: Прогнать всё**

```bash
.venv/Scripts/python.exe -m pytest -v
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos
```

Ожидаем: всё зелёное.

- [ ] **Step 5: Ручной smoke `--no-llm`**

```bash
rm -rf tmp/smoke-vault
.venv/Scripts/python.exe -m claude_mnemos ingest tests/fixtures/sample_session.jsonl tmp/smoke-vault --no-llm
ls tmp/smoke-vault/
cat tmp/smoke-vault/.manifest.json
cat tmp/smoke-vault/raw/chats/abc-123.md
```

Ожидаем: `raw/chats/abc-123.md` начинается с `# Transcript`, `.manifest.json` содержит запись с `model: null`. Никакой `wiki/`.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/cli.py tests/test_cli.py
git commit -m "feat(cli): full plan #2 flags, new exit codes (66/70/71/74), LLM client plumbing"
```

---

## Task 11: Optional real e2e (skipped without API key)

**Files:**
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/test_real_extraction.py`
- Modify: `pyproject.toml` (зарегистрировать marker `slow`)

**Why:** Один тест против реального Anthropic API на маленькой sample-сессии. По умолчанию пропускается; гоняется руками когда нужен sanity check на реальной модели. Без него мы не знаем работает ли `tool_use` end-to-end на живой Sonnet.

- [ ] **Step 1: Зарегистрировать marker в `pyproject.toml`**

В секцию `[tool.pytest.ini_options]` добавить:

```toml
markers = [
    "slow: tests that hit external services or take >1s",
]
```

- [ ] **Step 2: Создать `tests/e2e/__init__.py`**

(пустой файл)

- [ ] **Step 3: Реализовать `tests/e2e/test_real_extraction.py`**

```python
"""Optional end-to-end test against the real Anthropic API.

Run with:
    pytest tests/e2e -v -m slow

Skipped automatically when ANTHROPIC_API_KEY is unset.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

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

    # Sanity: page can be serialized
    rendered = p.serialize()
    assert rendered.startswith("---\n")
    assert "---\n" in rendered.split("---\n", 2)[1]  # closing fence exists
```

- [ ] **Step 4: Локально проверить, что без API key тест skip'ается**

```bash
.venv/Scripts/python.exe -m pytest tests/e2e/ -v
```

Ожидаем: 1 skipped (reason: `ANTHROPIC_API_KEY not set`).

- [ ] **Step 5: Опционально — если есть API key, прогнать вручную**

```bash
ANTHROPIC_API_KEY=sk-... .venv/Scripts/python.exe -m pytest tests/e2e -v -m slow
```

Ожидаем: 1 passed (потратит ~$0.01 на Sonnet).

- [ ] **Step 6: Прогнать полный pytest без e2e (default)**

```bash
.venv/Scripts/python.exe -m pytest -v
```

Ожидаем: e2e тест в выводе показан как skipped, остальные passed.

- [ ] **Step 7: ruff + mypy**

```bash
.venv/Scripts/python.exe -m ruff check claude_mnemos tests
.venv/Scripts/python.exe -m mypy claude_mnemos tests
```

Ожидаем: всё зелёное.

- [ ] **Step 8: Commit**

```bash
git add tests/e2e/ pyproject.toml
git commit -m "test(e2e): optional real anthropic API extraction test (skipped without API key)"
```

---

## Definition of Done

- [ ] Все 11 задач закоммичены отдельно (11 коммитов поверх `95c64ef` design doc).
- [ ] `pytest -v` зелёный, e2e-тест skipped (без API key).
- [ ] `ruff check claude_mnemos tests` чистый.
- [ ] `mypy claude_mnemos` чистый под strict.
- [ ] Ручной smoke `python -m claude_mnemos ingest <fixture> <vault> --no-llm` работает; `--dry-run` тоже работает (если есть API key — экспериментально).
- [ ] `<vault>/.manifest.json` создаётся, повторный ингест говорит `already_ingested`.
- [ ] Slug коллизии не теряют существующие файлы и попадают в `skipped_collisions`.
- [ ] Все exit codes как в design doc §9.3 (66/70/71/74 — новые).

---

## После плана #2

- **Plan #3** (StagingTransaction + Layer 4 snapshots) — закрывает partial-write window §10.3 design doc'а; добавляет `.staging/` между Pydantic-validation и финальной записью + snapshots в `.backups/`.
- **Plan #4** (Activity Center / Layer 5) — `.activity.json` + log_activity, делает undo возможным.
- **Plan #6** (Ontology) — заменяет skip-with-warning на ontology suggestions для merge.
- **Plan #5+** — daemon, dashboard, MCP, hooks, watchdog.
