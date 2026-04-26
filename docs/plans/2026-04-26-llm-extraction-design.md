# Design: LLM extraction (Plan #2)

**Status:** approved scope, ready for implementation-plan generation.
**Date:** 2026-04-26
**Author:** Claude (with Yarik approval).
**Predecessor:** `2026-04-26-minimal-e2e.md` (Plan #1, merged in `f753fbc`).
**Successor planned:** Plan #3 (StagingTransaction + Layer 4 snapshots).

---

## 1. Goal

Перейти от «vault содержит только `raw/chats/` с сырым транскриптом» к «vault содержит структурированные wiki-страницы, извлечённые LLM из транскрипта». После Plan #2:

```
<vault>/
├── .manifest.json                  # NEW: dedup-индекс по SHA-256 транскриптов
├── raw/
│   └── chats/
│       └── <sid>.md                # CHANGED: чистый транскрипт без Pydantic-frontmatter
└── wiki/
    ├── entities/<slug>.md          # NEW: вещи (модули, инструменты, баги)
    ├── concepts/<slug>.md          # NEW: идеи, паттерны, решения
    └── sources/<date>-<sid>.md     # NEW: одна страница = одна сессия, summary + ссылки
```

CLI остаётся `mnemos ingest <jsonl> <vault>` плюс новые опциональные флаги. Никакого dashboard, daemon, MCP, hooks, staging, snapshots, lint, ontology, activity log в этом плане — всё это последующие планы.

---

## 2. Scope

### 2.1 In scope

| Компонент | Где |
|---|---|
| Прямой `anthropic` SDK call с `tool_choice="tool"` | `ingest/llm.py` |
| Tool schema из расширенной Pydantic-модели страницы | `core/models.py` + `ingest/llm.py` |
| Pydantic-валидация **всех** возвращённых страниц до первой записи | `ingest/extraction.py` |
| Запись `wiki/entities/`, `wiki/concepts/`, `wiki/sources/` атомарно под общим pipeline FileLock | `ingest/pipeline.py` |
| Сохранение `raw/chats/<sid>.md` как чистого транскрипта (без Pydantic-frontmatter) | `ingest/pipeline.py` |
| Manifest `<vault>/.manifest.json` с SHA-256 транскрипта → `IngestRecord` | `state/manifest.py` |
| Идемпотентность: повторный ingest того же JSONL → no-op (по manifest) | `ingest/pipeline.py` |
| Slug-collision policy: skip-with-warning (existing wiki page не трогаем) | `ingest/pipeline.py` |
| Детерминированная нормализация title → slug (UK/RU транслит → ASCII) | `core/slug.py` |
| Конфиг через env + CLI flags | `config.py` + `cli.py` |
| `--dry-run`: всё прогоняется включая LLM, но не пишется | `cli.py` |
| `--no-llm`: пишется только `raw/chats/` (escape hatch без API key) | `cli.py` |
| Один auto-retry при невалидном tool input (system: «previous output failed validation») | `ingest/llm.py` |
| Token-budget guard: hard fail если транскрипт > `MNEMOS_MAX_INPUT_TOKENS` (default 150_000) | `ingest/llm.py` |
| Mock-based unit-тесты + опциональный реальный e2e (`@pytest.mark.skipif` без API key) | `tests/` |
| Структурные exit codes (66/70/71/74 — новые) | `cli.py` |

### 2.2 Out of scope (явно отложено)

| Компонент | План |
|---|---|
| `.staging/<sid>/` директория и pre-promote validation | #3 |
| `.backups/` snapshots | #3 |
| Lint check (broken wikilinks, frontmatter rules) | #3 |
| Ontology safety check / merge-on-collision | #6 |
| `.activity.json` + log_activity (Layer 5) | #4 |
| Inject-metrics / Token Metrics | позже |
| Dead-letter queue (Spec §8.9) | позже |
| Dashboard, daemon, MCP, hooks, watchdog | #5+ |
| AGENTS.md per-vault contract | отдельный план |
| Inline provenance markers `^[…]` (только aggregated в frontmatter) | позже |
| 4-factor confidence scoring | позже |
| Auto lifecycle transitions (draft → reviewed → stale) | позже |
| `index.md`, `log.md`, `hot.md`, `overview.md`, `_by_flavor/` | позже |
| `update_count`, `aliases`, `tags`, `last_human_edit`, `auto_stale_at`, `confidence_factors` поля frontmatter | позже |

---

## 3. Architecture

### 3.1 Data flow после #2

```
mnemos ingest <jsonl> <vault> [flags]
   │
   ▼
parse_jsonl(jsonl)                     ← существует, без изменений
   │
   ▼
Acquire pipeline_lock(vault)           ← существует, без изменений
   │
   ▼
manifest = Manifest.load(vault)        ← NEW
   │
   ▼
sha = sha256(raw_jsonl_bytes)
if sha in manifest.ingested:
    return IngestResult(status="already_ingested")
   │
   ▼
write raw/chats/<sid>.md (atomic)      ← всегда (даже для --no-llm). Plain markdown
                                          без YAML-frontmatter: "# Transcript\n\n
                                          ## user\n\n<text>\n\n## assistant\n\n..."
   │
   ▼
IF --no-llm:
    manifest.add(sha, ...); manifest.save(); return IngestResult(status="raw_only")
   │
   ▼
extracted = extract_wiki_pages(messages, config)   ← LLM call here
   │
   ▼
validate_all(extracted)                ← Pydantic, всё или ничего
   │
   ▼
build_source_page(sid, summary, extracted)   ← мы сами, не LLM
   │
   ▼
collisions = detect_collisions(extracted, vault)
   │
   ▼
write each non-colliding page (atomic) → wiki/entities|concepts/<slug>.md
write source page (atomic)              → wiki/sources/<date>-<sid>.md
   │
   ▼
manifest.add(sha, sid, created_paths, skipped_collisions); manifest.save()
   │
   ▼
return IngestResult(
    status="extracted",
    raw_path, source_path,
    created_pages=[...],
    skipped_collisions=[...],
    llm_model, input_tokens, output_tokens,
)
```

### 3.2 Module map

**Новые:**
| Файл | Ответственность |
|---|---|
| `claude_mnemos/config.py` | Загрузка конфига из env + CLI override (`MNEMOS_MODEL`, `MNEMOS_LANGUAGE_HINT`, `MNEMOS_MAX_INPUT_TOKENS`, `ANTHROPIC_API_KEY`, `MNEMOS_LOCK_TIMEOUT`) |
| `claude_mnemos/core/slug.py` | `make_slug(title: str) -> str` — детерминированно, UK/RU → en транслит, lowercase, `[^a-z0-9-]` → `-`, max 60 chars |
| `claude_mnemos/state/__init__.py` | namespace |
| `claude_mnemos/state/manifest.py` | `Manifest` Pydantic model + `Manifest.load(vault)` / `Manifest.save(vault)` через atomic_write |
| `claude_mnemos/ingest/llm.py` | `LLMClient` — обёртка над `anthropic.Anthropic`. Метод `extract(system, user, tool_schema)` возвращает `dict` (tool input). `MissingApiKeyError`, `LLMExtractionError`, `TranscriptTooLargeError` |
| `claude_mnemos/ingest/extraction.py` | `extract_wiki_pages(messages, vault, config) -> ExtractionResult` — собирает prompt, зовёт LLMClient, валидирует tool input через Pydantic, возвращает list[WikiPage] + summary + token-usage |
| `claude_mnemos/ingest/prompts/system.md` | Системный prompt (en, статичный, ~600 токенов) |
| `claude_mnemos/ingest/prompts/extract_user.md` | Шаблон user-сообщения с `{transcript}` placeholder'ом |

**Изменяемые:**
| Файл | Что |
|---|---|
| `claude_mnemos/core/models.py` | Добавить опциональные поля `provenance: dict[str, int] \| None`, `agent_written: bool = True`. Добавить `EntityPageFrontmatter`, `ConceptPageFrontmatter` (наследуют WikiPageFrontmatter с `type` фиксированным через Literal). Добавить `tool_schema()` фабрику для anthropic tool input_schema |
| `claude_mnemos/ingest/pipeline.py` | Переименовать `ingest_minimal` → `ingest`. Добавить параметры `extract: bool = True`, `dry_run: bool = False`. Разделить запись: `raw/chats/` теперь без frontmatter; `wiki/sources/` — отдельная страница с frontmatter |
| `claude_mnemos/cli.py` | Добавить флаги `--model`, `--language-hint`, `--dry-run`, `--no-llm`, `--max-input-tokens`. Маппинг новых exception'ов на exit codes (66/70/71/74) |
| `pyproject.toml` | Добавить в runtime deps: `anthropic>=0.40`, `unidecode>=1.3` (slug транслит). В dev-deps мокаем `unittest.mock` — никаких новых dev deps. |

### 3.3 Sequence: extract path

```
pipeline.ingest()
  ├─ acquire lock
  ├─ parse_jsonl()                              [existing]
  ├─ sha = sha256(jsonl bytes)
  ├─ Manifest.load() → check sha
  │   └─ if hit → return status="already_ingested", release lock
  ├─ atomic_write(raw/chats/<sid>.md, plain transcript)
  ├─ if --no-llm:
  │     manifest.add(sha, raw_only); manifest.save(); return
  ├─ extraction.extract_wiki_pages()
  │   ├─ build prompt (system from file, user with transcript inlined)
  │   ├─ token_count = client.messages.count_tokens(...)
  │   ├─ if token_count.input_tokens > max_input_tokens:
  │   │     raise TranscriptTooLargeError
  │   ├─ resp = client.messages.create(
  │   │     model=cfg.model,
  │   │     system=[{type:"text", text:SYSTEM, cache_control:{"type":"ephemeral"}}],
  │   │     tools=[SAVE_WIKI_PAGES_TOOL],
  │   │     tool_choice={"type":"tool", "name":"save_wiki_pages"},
  │   │     messages=[{role:"user", content:USER}],
  │   │     max_tokens=8000,
  │   │   )
  │   ├─ extract tool_use block → tool_input dict
  │   ├─ try Pydantic validate → ExtractionPayload
  │   ├─ on ValidationError: ONE retry with error injected as system addendum
  │   ├─ on second failure: raise LLMExtractionError(exit 70)
  │   └─ return ExtractionResult(pages=[WikiPage,...], summary, usage)
  ├─ build source page from summary + extracted page links
  ├─ for each page (extracted + source):
  │     target = vault / page.relative_path
  │     if target.exists():
  │         skipped_collisions.append((page, "exists"))
  │         continue
  │     atomic_write(target, page.serialize())
  ├─ manifest.add(sha, IngestRecord(sid, created_pages, skipped, model, usage, ts))
  ├─ manifest.save() (atomic_write)
  └─ release lock; return IngestResult
```

---

## 4. LLM contract

### 4.1 Single tool

LLM вынуждена вызвать ровно один tool — `save_wiki_pages`. Свободного текста на выходе нет (всё что в `text` блоках игнорируем, читаем только `tool_use`).

### 4.2 Tool input schema

Плоская schema — никаких `oneOf`/`anyOf`/`discriminator` (Anthropic Claude существенно стабильнее на плоской схеме):

```python
# Generated from Pydantic via .model_json_schema(), normalized to Anthropic dialect.
SAVE_WIKI_PAGES_TOOL = {
    "name": "save_wiki_pages",
    "description": (
        "Save extracted wiki pages from a Claude Code transcript. "
        "Call this exactly once. If the transcript contains nothing significant "
        "(greeting, ping, trivial question with no decision/insight), return "
        "an empty `pages` array and set `skipped_reason`."
    ),
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {
                "type": "string",
                "description": "1-3 sentence summary of the conversation, used in the source page.",
            },
            "skipped_reason": {
                "type": ["string", "null"],
                "description": "If pages is empty, brief reason. Otherwise null.",
            },
            "pages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "type": {"type": "string", "enum": ["entity", "concept"]},
                        "title": {"type": "string", "minLength": 1, "maxLength": 200},
                        "slug_hint": {
                            "type": ["string", "null"],
                            "description": "Optional explicit slug; if null, derived from title.",
                        },
                        "flavor": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["pattern", "mistake", "decision", "lesson", "reference"]},
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
                            "description": "Wikilinks like '[[other-page-slug]]' to other pages this references.",
                        },
                        "body": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Markdown body. No frontmatter — we add it.",
                        },
                    },
                    "required": ["type", "title", "flavor", "confidence", "provenance", "related", "body"],
                },
            },
        },
        "required": ["summary", "pages"],
    },
}
```

### 4.3 Pydantic mirror

```python
class ProvenanceCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extracted_pct: int = Field(ge=0, le=100)
    inferred_pct: int = Field(ge=0, le=100)
    ambiguous_pct: int = Field(ge=0, le=100)

class ExtractedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["entity", "concept"]
    title: str = Field(min_length=1, max_length=200)
    slug_hint: str | None = None
    flavor: list[PageFlavor] = []
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: ProvenanceCounts
    related: list[str] = []
    body: str = Field(min_length=1)

class ExtractionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    skipped_reason: str | None = None
    pages: list[ExtractedPage]
```

`provenance` percentages **не нормализуем** до 100 в Pydantic (LLM может ошибиться на 1-2%) — допустим сумма 95-105. Если вне диапазона — warning в логи, не reject.

### 4.4 Retry logic

```
try LLM call
try parse tool_use → Pydantic validate
if ValidationError:
    add system message: "Previous output failed schema validation: <err>. Try again."
    retry once
    if still ValidationError → raise LLMExtractionError
```

SDK-level retry на 429/5xx — встроенный (`anthropic.Anthropic(max_retries=2)`).

---

## 5. Frontmatter schema extensions

`WikiPageFrontmatter` остаётся минимальным, добавляем 2 опциональных поля:

```python
class WikiPageFrontmatter(BaseModel):
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
    # NEW
    provenance: ProvenanceCounts | None = None
    agent_written: bool = True
```

Поля spec'а 6.4 (`update_count`, `aliases`, `tags`, `last_human_edit`, `auto_stale_at`, `confidence_factors`) **не добавляем** — они нужны только когда есть lifecycle/lint/ontology, которые отложены.

`agent_written: True` для всех страниц #2 (мы ingest'им автоматом). Когда появится UI/MCP edit — переключим на False для тех страниц.

---

## 6. Manifest

### 6.1 Расположение

`<vault>/.manifest.json` — в корне vault (по spec'у §5.1). Не в `.mnemos/` поддиректории.

### 6.2 Schema

```python
class IngestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    ingested_at: datetime
    raw_path: str          # relative to vault root
    source_path: str | None  # relative; None for --no-llm
    created_pages: list[str]  # relative paths to entity/concept/source files
    skipped_collisions: list[str]  # relative paths LLM proposed but already existed
    model: str | None      # LLM model used; None for --no-llm
    input_tokens: int | None
    output_tokens: int | None

class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    ingested: dict[str, IngestRecord] = Field(default_factory=dict)  # key = sha256 hex
```

### 6.3 Operations

- `Manifest.load(vault)` — если файла нет, возвращает пустой `Manifest()`. Если файл есть и невалидный JSON / Pydantic не валидирует → `ManifestCorruptError` (exit 74). **Не** автопочиняем — ошибка говорит юзеру что что-то трогало vault руками.
- `Manifest.save(vault)` — `atomic_write(vault / ".manifest.json", json.dumps(model_dump(mode="json"), indent=2, ensure_ascii=False))`.
- Все операции под общим `pipeline_lock` — concurrent ingests никогда не пересекаются.
- `Manifest.add(sha, record)` — assert sha not in ingested (внутренняя инвариантная проверка); присваивает запись.

### 6.4 Что хранится / не хранится

Хранится: то что нужно для idempotency + минимальный аудит (когда, чем, что создалось/скипнулось, цена).
Не хранится: raw transcript hash separately, prompt version, vault state hash (это всё для будущих планов lint/ontology/migration).

---

## 7. Slug rules

`core/slug.py::make_slug(title: str) -> str`:

1. NFKD normalize → strip combining marks (`unicodedata.normalize("NFKD", s)`).
2. UK/RU → транслит через `unidecode` (новая dep, маленькая, MIT). Альтернатива — рукописная мапа, но `unidecode` стабильнее на edge cases.
3. lowercase.
4. `re.sub(r"[^a-z0-9]+", "-", s)`.
5. strip leading/trailing `-`.
6. truncate to 60 chars (по последнему `-` в пределах лимита, без обрыва слова).
7. если результат пустой → `"untitled-{8-hex-hash-of-title}"`.

Детерминированно: тот же input → тот же output (нужно для slug_hint validation и для будущих миграций).

`slug_hint` от LLM — если задан, пропускаем через `make_slug` (LLM может вернуть «Claude Code» — нормализуем). Если не задан — derive из title.

Финальный относительный путь:
- `wiki/entities/<slug>.md`
- `wiki/concepts/<slug>.md`
- `wiki/sources/<YYYY-MM-DD>-<short-sid>.md` где `short-sid = sid[:8]` (для читабельности)

---

## 8. Prompts

### 8.1 `prompts/system.md`

Жёстко en. Содержит:

- Role: «You extract structured knowledge pages from a Claude Code chat transcript for the user's per-project Obsidian vault.»
- Two page types:
  - **entity** — concrete things: modules, files, tools, libraries, services, people, projects, specific bugs.
  - **concept** — ideas, patterns, architectural decisions, lessons learned, principles.
- Closed flavor vocabulary: `pattern, mistake, decision, lesson, reference`. Pages may have any combination.
- Output language rule: **match the dominant language of the transcript** (UK/RU/EN). Headings and frontmatter values in same language. Slugs always ASCII (we'll derive — they should set `slug_hint` only if they want a specific one in english).
- Selectivity rules:
  - Skip greetings, pings, trivial Q&A.
  - One page per real concept, not per mention. If transcript discusses 3 facets of same thing → 1 page.
  - Body should be 80%+ grounded in transcript. No fabrication.
  - If unsure if something is significant → leave it out (low recall is better than noise; missing pages can be added later, wrong pages are pollution).
- Confidence rule: 0.7 default; 0.85 if explicit decision/conclusion; 0.5 if speculative/exploratory.
- Provenance rule: percentages of `extracted` (direct from transcript), `inferred` (synthesis/connection LLM made), `ambiguous` (sources conflict). Should sum to ~100.
- Related links: use `[[slug]]` for other pages in this batch or that probably exist already; if unsure, omit.
- If transcript is trivial → `pages: []` and `skipped_reason: "<short reason>"`.
- Hard rule: call `save_wiki_pages` exactly once. No text response.

### 8.2 `prompts/extract_user.md`

```
The transcript follows. Extract wiki pages per the system instructions and call save_wiki_pages.

<transcript language_hint="{language_hint}">
{transcript}
</transcript>
```

`{language_hint}` — `auto` (default) / `uk` / `ru` / `en`. Пробрасывается как hint, не как принуждение.

### 8.3 Prompt caching

System prompt — `cache_control: {"type": "ephemeral"}`. Экономит на повторных ингестах в пределах 5 минут. Не критично, добавляем потому что одна строка кода.

### 8.4 Token budget

- Default `max_input_tokens = 150_000` (Sonnet 4.6 200K окно, оставляем хвост на system+output).
- `client.messages.count_tokens()` для prompt **до** `messages.create()`. Если превышен — `TranscriptTooLargeError` (exit 71). Chunking откладываем; пока пользователь видит явную ошибку и может разрезать сессию руками.
- `max_tokens` на ответ — 8000 (пачка из 5-15 страниц легко в это влезает; если 20+ страниц нужно — это сигнал что транскрипт надо дробить).

---

## 9. Configuration & CLI

### 9.1 Env vars

| Var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required unless `--no-llm`. Empty → `MissingApiKeyError` (exit 66). |
| `MNEMOS_MODEL` | `claude-sonnet-4-6` | LLM model id. Aliases `sonnet`/`haiku`/`opus` маппятся на full id внутри `config.py`. |
| `MNEMOS_LANGUAGE_HINT` | `auto` | `auto`/`uk`/`ru`/`en`. |
| `MNEMOS_MAX_INPUT_TOKENS` | `150000` | Hard limit для prompt. |
| `MNEMOS_LOCK_TIMEOUT` | `60.0` | seconds, передаётся в `pipeline_lock`. |

### 9.2 CLI

```
mnemos ingest <jsonl> <vault>
    [--model <id-or-alias>]
    [--language-hint auto|uk|ru|en]
    [--max-input-tokens <int>]
    [--dry-run]            # everything including LLM call, but no file writes
    [--no-llm]             # write raw/chats/ only, skip LLM
```

CLI flags перебивают env. Order of precedence: CLI > env > default.

`--dry-run` поведение: parse, manifest check, **зовёт LLM** (чтобы поймать prompt issues), валидирует — но `atomic_write` подменяется на no-op + лог `would write: <path>`. Manifest не сохраняется. Это полезно для тестирования промптов на реальных сессиях без мутации vault.

`--no-llm` поведение: parse, manifest check, пишет `raw/chats/<sid>.md`, обновляет manifest с `IngestRecord(model=None, source_path=None, created_pages=[raw_path])`. LLM не зовётся. Полезно когда нет API key, но хочется сохранить чат для будущего разбора.

### 9.3 Exit codes

| Code | Cause | Source |
|---|---|---|
| 0 | OK (включая `already_ingested`, `raw_only`) | |
| 2 | Usage error / file not found | argparse / `cli.py` |
| 65 | EmptyTranscriptError | existing |
| 66 | MissingApiKeyError | NEW |
| 70 | LLMExtractionError (after retry) | NEW |
| 71 | TranscriptTooLargeError | NEW |
| 73 | LockTimeoutError | existing |
| 74 | ManifestCorruptError | NEW |
| 75 | FileBusyError | existing |

---

## 10. Idempotency & collisions

### 10.1 Идемпотентность по транскрипту

SHA-256 от **байтов JSONL** (не от парсенных messages). Если файл переименован — это новый ingest. Если содержимое идентично — no-op.

### 10.2 Slug-collision policy

Policy для #2: **skip-with-warning**.

Проверка: если `(vault / page.relative_path).exists()` → не пишем, добавляем в `skipped_collisions`. Manifest сохраняет skip'нутые — позже (#6 ontology) сможем сделать merge.

Никаких append/overwrite/diff в #2 — это ontology территория.

Source page (`wiki/sources/<date>-<short-sid>.md`) — путь содержит SID, коллизия возможна только если повторный ingest того же SID в тот же день, что отлавливается раньше через manifest. Если повторный ingest того же JSONL — отрабатывает manifest (status=already_ingested), до записи source page не доходим.

### 10.3 Partial-write риск

Между записью первой и последней страницы может упасть процесс/сеть/диск. Vault окажется в полу-собранном состоянии: часть страниц записана, manifest **не обновлён** (он пишется последним).

Поведение при повторном ingest того же JSONL после такого падения:
- manifest не содержит SHA (мы упали до save) → процесс начинается заново.
- `raw/chats/<sid>.md` уже есть → atomic_write перезаписывает = идемпотентно.
- LLM зовётся снова (платим деньги повторно — известная цена).
- На записи pages: уже существующие (от первой попытки) → skip-with-warning. Новые от второй попытки (если LLM вернул другие — non-determinism) → запишутся.
- Vault получит objединённый набор. Это **не** идеально, но **safe**: ничего не теряем, никаких половинных файлов (atomic_write garantees that).
- Manifest finally сохраняется → следующий ingest no-op.

Полноценная транзакционность придёт с Layer 2 (`.staging/`) в Plan #3 — там запись будет «всё или ничего».

---

## 11. Testing strategy

### 11.1 Уровни

1. **Unit (mocked LLM):**
   - `test_slug.py` — табличные тесты: en/uk/ru/edge cases (emoji, длинные titles, повторные дефисы, пустые строки).
   - `test_manifest.py` — load/save/load roundtrip, missing file, corrupt JSON, corrupt schema, atomicity (mock os.replace fail).
   - `test_llm.py` — мок `anthropic.Anthropic`, проверяем: tool_choice выставлен, tool schema корректна, retry на ValidationError, fail после 2 попыток, MissingApiKeyError, TranscriptTooLargeError.
   - `test_extraction.py` — мок LLMClient, фикстуры tool input в `tests/fixtures/llm_responses/*.json`. Кейсы: один entity, multi (entity+concept), пустой `pages` со `skipped_reason`, провалившаяся валидация → retry succeeds, retry fails.
   - `test_pipeline.py` — расширяем существующие тесты: проверка manifest, разделения raw/chats vs wiki/sources, idempotency, --no-llm path, --dry-run no writes, slug collision skip.
   - `test_cli.py` — расширяем: новые флаги, новые exit codes (mock LLM через monkeypatch на module-level).

2. **Integration без сети:**
   - Полный pipeline на fixture JSONL с моком LLM, проверяем что в vault'е появились правильные файлы со правильными relative paths.
   - Повторный ingest того же JSONL → status=already_ingested.
   - Параллельный ingest того же JSONL под общим lock → второй ждёт → читает manifest → no-op.

3. **Optional real e2e** (`tests/e2e/test_real_extraction.py`):
   - `@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="no API key")`.
   - `@pytest.mark.slow` (по умолчанию выключен; гоняется через `pytest -m slow`).
   - Использует мини-fixture (3-5 messages) с явным «decision» утверждением, проверяет что:
     - Хотя бы 1 page создана.
     - Frontmatter валиден.
     - `provenance` percentages ~100.
     - Source page существует с summary.
   - Стоимость: одна Sonnet 4.6 inference на ~2K tokens prompt + ~1K output ≈ копейки.
   - Не входит в обычный CI; ручной запуск.

### 11.2 Coverage targets

- 32 текущих теста остаются зелёными.
- +20-30 новых unit-тестов.
- mypy strict + ruff остаются чистыми.

---

## 12. Known limitations

1. **Slug collision = lost update.** Если на вторую сессию LLM решит уточнить уже существующую entity — обновление не запишется (skip). Эта инфа доступна в `raw/chats/` и `wiki/sources/`, восстановится при ontology pass (#6).
2. **Partial-write window.** Между записью первой страницы и сохранением manifest — небольшое окно. См. §10.3. Закрывается в #3.
3. **Non-determinism.** Один и тот же транскрипт в разные ingest'ы (после ошибки) может дать разный набор страниц. Manifest защищает от обычного двойного ingest'а; обходится только через крах посередине.
4. **Token waste при крашах.** Re-ingest после краха = повторный платный LLM call.
5. **Нет lint валидации** на broken wikilinks в `related`. LLM может ссылаться на `[[non-existent-page]]`. Это не блокирует ingest. Lint придёт в #3.
6. **Нет index.md update.** Файлы появляются «молча». Видны через файловую систему, но не в edit-friendly каталоге.
7. **Качество extraction зависит от языка** — Claude хорошо знает UK, но edge cases возможны. Mitigation — `MNEMOS_LANGUAGE_HINT=en` принудительно.
8. **Hard token limit** без chunking — большие сессии (>150K tokens) требуют ручного разбиения.

---

## 13. What this enables (и что после)

После Plan #2 vault уже **полезен** для запросов: пользователь (или другой Claude) может grep'ать `wiki/entities/`, `wiki/concepts/` чтобы найти что мы знаем по теме. Это первая реальная value milestone.

**Plan #3** (StagingTransaction + Layer 4 snapshots) — закрывает §10.3 и даёт rollback. Делается поверх #2 без переписывания pipeline'а: добавляется этап `.staging/` между Pydantic-validation и финальной записью.

**Plan #4** (Activity Center) — добавляет `.activity.json` log на каждый ingest, делает undo возможным.

**Plan #6** (Ontology) — закрывает slug-collision: вместо skip — proposal для merge/append.

---

## 14. Решения, которые я принял сам (для протокола)

| Решение | Альтернатива | Почему выбрал |
|---|---|---|
| `anthropic` SDK напрямую | `claude-agent-sdk` или `subprocess claude -p` | Нам не нужен agent loop — один structured-output call. Плоский SDK = тестируемее, без recursion-рисков (см. spec §5.5). |
| Default model `claude-sonnet-4-6` | Haiku 4.5 / Opus 4.7 | Sonnet — баланс цена/качество для extraction. Haiku может лажать на nuanced concepts; Opus — overkill и дорого. Configurable. |
| Tool use, плоская schema | JSON mode / `oneOf`/discriminator | Anthropic Claude стабильнее на плоской схеме с `enum` discriminator. Tool use надёжнее JSON mode. |
| `<vault>/.manifest.json` в корне | `<vault>/.mnemos/manifest.json` | Spec §5.1 указывает корень. Не плодим лишних директорий. |
| Один retry + provenance в frontmatter (но без inline `^[…]` маркеров) | Без retry / с inline markers | Retry стоит копейки и закрывает 80% LLM-флэйков (особенно при первой работе с моделью). Inline markers — много правил для LLM, риск что портит body; отложим. |
| Skip-with-warning на коллизии | Overwrite / merge / append | Safe: старая инфа цела. Merge — это ontology (#6), сложно делать without LLM second-pass. Overwrite — теряем данные. |
| `raw/chats/` без Pydantic-frontmatter | С frontmatter `type: source` (как сейчас) | Spec разделяет: `raw/` immutable transcript, `wiki/sources/` — наша structured page. Текущая слитная версия — артефакт минимального e2e. |
| Hard fail при `> max_input_tokens` | Auto-chunking / truncation | Chunking — отдельная фича со своими развилками (как клеить результаты), отложим. Truncation теряет данные молча. Hard fail с понятной ошибкой = честно. |
| Token-count call перед messages.create | Полагаться только на ответ API | Лучше дёшево узнать заранее чем платить за прерванный inference. |
| `MNEMOS_LANGUAGE_HINT=auto` default | Принудительно en | UK primary по решению Ярика (память, q1 closed). |
| Unit-тесты через `unittest.mock`, опциональный real e2e | VCR cassettes | Cassettes требуют initial запись с реальным API + хранение JSON на десятки KB; для 1-tool API mock'и проще. Real e2e даёт ground truth когда нужно. |

---

## 15. Open questions для имплементации (не блокеры)

Эти решения сделаю в плане / при кодинге, а не сейчас:

- Как именно генерируется system prompt: read at module import vs на каждый call (важно для тестов и hot-reload).
- Точный shape `prompts/system.md` (содержание написать при имплементации, чтобы не заморачиваться с draft'ом).
- Как именно мокать `anthropic.Anthropic` в тестах — через `monkeypatch.setattr` на module-level client vs DI через `LLMClient(client=...)` в production-коде. Склоняюсь к DI (тестируемее).
