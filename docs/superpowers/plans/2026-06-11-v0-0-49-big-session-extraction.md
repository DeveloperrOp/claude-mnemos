# v0.0.49: Экстракция больших сессий — поднятый лимит + чанкинг + per-session выбор — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Большие сессии перестают молча падать в dead-letter. Фаза 1 поднимает лимит экстракции 150k→800k и оживляет настройку (была плацебо). Фаза 2 добавляет чанкинг (нарезка транскрипта на части, экстракция каждой, слияние страниц) и per-session выбор «попробовать целиком / обработать частями» с умной подсказкой.

**Architecture:** Контракт `LLMClient.extract()` НЕ трогаем — чанкинг живёт слоем выше в `extraction.py`. Лимит контролируется `GlobalSettings.default_max_input_tokens`, который наконец доходит до экстракции через `with_overrides`. Слияние страниц между чанками — чистая детерминированная функция поверх существующего `ontology_similarity` + `make_slug` (без LLM, без I/O). Per-session действия идут через тот же `POST /api/sessions/{project}/{session_id}/ingest` с новыми полями payload (`max_input_tokens` override, `chunk_extract` флаг).

**Tech Stack:** Python 3.12 / FastAPI / pydantic / tiktoken (count_tokens_local) / pytest; React 19 / TanStack Query / zod / Vitest.

**Операционные правила (из памяти):**
- Тесты: `D:\code\claude-mnemos\.venv\Scripts\python.exe -m pytest ...`. Frontend: `cd D:\code\claude-mnemos\frontend; npm test -- --run`; типы `npx tsc --noEmit`.
- Коммит-сообщения ТОЛЬКО `git commit -F <файл>`, файл писать python'ом (UTF-8 без BOM).
- Коммит только pathspec'ом (была гонка параллельных агентов на index).
- Деструктив только на claude-mnemos-dev. НЕ запускать второй frozen-демон против реального home.
- Дефолтный LLM-провайдер у Ярика — **CLI/подписка** (CliLLMClient, без ANTHROPIC_API_KEY). Экстракция не тарифицируется по токенам, ест лимиты подписки.

**База (снимок recon):**
- `config.py:12` `DEFAULT_MAX_INPUT_TOKENS=150000`; `Config.max_input_tokens`; env `MNEMOS_MAX_INPUT_TOKENS` (L84-93); `with_overrides(max_input_tokens=...)` (L122-148).
- `state/settings.py:143` `GlobalSettings.default_max_input_tokens` Field default=150000 ge=1024. Per-project override НЕТ.
- `ingest/llm/api.py:23` `TranscriptTooLargeError`; единственный enforcement L111-115 (только ApiLLMClient).
- `ingest/llm/cli.py` — НЕ проверяет лимит; `count_tokens_local` только для метрик (L215).
- `ingest/llm/__init__.py:51-70` `make_llm_client` — subscription default = Cli.
- `daemon/vault_runtime.py:241-242` `cfg_factory=Config.from_env()` БЕЗ overrides → **UI-настройка не доходит до экстракции (плацебо)**.
- `ingest/extraction.py` `extract_wiki_pages(*, messages, llm_client, cfg, today)` → `ExtractionResult(summary, skipped_reason, pages, input_tokens, output_tokens)`; `_render_transcript(messages)` (L75-82); `_render_page(page, today)`. Единственный вызов `llm_client.extract(system=, user=, tool=, validate=)`.
- `ingest/transcript.py` `parse_jsonl()` → `list[TranscriptMessage(role, text, session_id)]` (frozen dataclass) — единица нарезки.
- `ingest/llm/__init__.py` Protocol `LLMClient.extract(*, system, user, tool, validate=None) -> ExtractionRaw(payload, input_tokens, output_tokens)`.
- `core/models.py` `ExtractedPage(type, title, slug_hint, flavor, confidence, provenance, related, body)`, `ExtractionPayload(summary, skipped_reason, pages)`.
- `core/ontology_similarity.py` `body_hash`, `jaccard_similarity`, `tokenize_for_similarity` — чистые. `core/slug.py` `make_slug`.
- `ingest/pipeline.py` `ingest()` — extractor 1 раз, `StagingTransaction` + `Manifest` + `Activity`. Коллизии слугов ВНУТРИ результата НЕ ловятся (txn.write дважды).
- `ingest/prompts/__init__.py` `format_user(transcript=, language_hint=)` (replace); `extract_user.md`/`extract_system.md` рассчитаны на ПОЛНЫЙ транскрипт.
- `daemon/jobs/handlers.py` `IngestHandler.run()` ловит `EmptyTranscriptError`/`RateLimitError`; **TranscriptTooLargeError НЕ ловит** → generic except в `worker.py:142` → `mark_failed_with_retry` → 4 ретрая → dead_letter.
- `state/jobs.py:27` `MAX_ATTEMPTS=4`; `JobStatus` Literal (L30); payload `{transcript_path, project_name?, extract, raw_filename_suffix?}`.
- `daemon/routes/sessions.py:66-137` `POST .../ingest` создаёт ingest-джобу.
- Frontend: `components/widgets/SessionCard.tsx` (brainState extracted/raw_only/in_progress/failed/not_in_brain, кнопка «Сохранить как знания»), `pages/SessionDetail.tsx`, hooks `useReingestSession.ts`/`useSessionIngest.ts`, `api/sessions.api.ts` `ingestSession`, `types/Session.ts` (`raw_transcript_bytes` уже есть, в UI не используется), `pages/DeadLetter.tsx`/`components/widgets/DeadLetterRow.tsx`/`pages/DeadLetterDetail.tsx`.

---

## ФАЗА 1 — Поднять лимit + оживить настройку + структурный TooLarge (релиз-кандидат сам по себе)

### Task 1: Поднять дефолт 150k→800k синхронно в трёх местах

**Files:**
- Modify: `claude_mnemos/config.py:12`
- Modify: `claude_mnemos/state/settings.py:143`
- Modify: `frontend/src/types/Settings.ts:60`, `frontend/src/components/settings/globals/GlobalDefaultsSection.tsx:18`
- Test: `tests/test_config.py` (или ближайший — сверь), `tests/state/test_settings.py`

- [ ] **Step 1: failing test (backend).** В тесте конфига добавить:
```python
def test_default_max_input_tokens_is_800k():
    from claude_mnemos.config import DEFAULT_MAX_INPUT_TOKENS
    assert DEFAULT_MAX_INPUT_TOKENS == 800_000

def test_global_settings_default_max_input_tokens_is_800k():
    from claude_mnemos.state.settings import GlobalSettings
    assert GlobalSettings().default_max_input_tokens == 800_000
```
(сверь точные имена тест-файлов: `tests/test_config.py` / `tests/state/test_settings.py`; если конфиг-теста нет — добавь в ближайший по смыслу.)

- [ ] **Step 2:** прогнать → FAIL.
- [ ] **Step 3: implementation.** `config.py:12` `DEFAULT_MAX_INPUT_TOKENS = 800_000`. `state/settings.py:143` `default_max_input_tokens: int = Field(default=800_000, ge=1024)`. ВНИМАНИЕ: проверь, нет ли ещё мест с литералом 150000 (grep `150_000|150000` по claude_mnemos) — если дефолт дублируется, синхронизируй; env-парсинг и `with_overrides` НЕ трогать.
- [ ] **Step 4: frontend.** `frontend/src/types/Settings.ts:60` `z.number().int().min(1024).default(800_000)` (верхней границы нет — 800k валиден). `GlobalDefaultsSection.tsx:18` `useState(800_000)` (или как там инициализируется — сверь, чтобы плейсхолдер/дефолт совпал). Grep `150000|150_000` по frontend/src — синхронизируй все.
- [ ] **Step 5:** backend pytest затронутых + `cd frontend; npm test -- --run; npx tsc --noEmit`.
- [ ] **Step 6: commit** (pathspec): `feat: raise default extraction limit 150k → 800k (model context is 1M, cap was overcautious)`.

**Миграция:** не нужна. Сохранённый `global-settings.json` хранит явное значение → смена дефолта влияет только на новых/без-поля юзеров. У кого записано 150000 — поднимут вручную в UI (или см. Task 2, где UI-значение наконец заработает).

### Task 2: Оживить настройку — GlobalSettings.default_max_input_tokens доходит до экстракции

**Files:**
- Modify: `claude_mnemos/daemon/vault_runtime.py:241-242` (cfg_factory)
- Test: `tests/daemon/test_vault_runtime.py` (или где тестируется cfg_factory; сверь)

**Проблема (placebo):** сейчас `cfg_factory = Config.from_env()` — UI-значение `default_max_input_tokens` НЕ применяется, работает только env `MNEMOS_MAX_INPUT_TOKENS`. Чинимём: cfg_factory читает GlobalSettings и применяет `with_overrides(max_input_tokens=...)`.

- [ ] **Step 1: failing test.** Замокать/выставить GlobalSettings.default_max_input_tokens=500000, получить cfg из cfg_factory соответствующего runtime, assert `cfg.max_input_tokens == 500000`. ВНИМАНИЕ: env `MNEMOS_MAX_INPUT_TOKENS`, если задан, должен иметь приоритет над UI (env — escape hatch); тест на оба порядка. Изучи, как cfg_factory вызывается и где взять SettingsStore (vault_runtime уже держит settings_store? сверь).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: implementation.** В vault_runtime cfg_factory: `cfg = Config.from_env()` (env берёт приоритет если задан); затем, если env НЕ задавал max_input_tokens явно, применить `cfg = cfg.with_overrides(max_input_tokens=global_settings.default_max_input_tokens)`. Точную форму подгони под то, как `from_env` отличает «явно задано» от дефолта (возможно надо читать `os.environ.get("MNEMOS_MAX_INPUT_TOKENS")` напрямую для приоритета). Реши консервативно: **UI-значение применяется всегда, КРОМЕ случая когда env-var выставлен** — env остаётся override для разработчика.
- [ ] **Step 4:** `pytest tests/daemon/test_vault_runtime.py -q` + смежные ingest-тесты (не сломал ли cfg-флоу).
- [ ] **Step 5: commit:** `fix: GlobalSettings.default_max_input_tokens now actually controls extraction (was a placebo; only env applied)`.

### Task 3: Структурный TranscriptTooLargeError + детект в CLI-режиме

**Files:**
- Modify: `claude_mnemos/ingest/llm/api.py:23-24,111-115`
- Modify: `claude_mnemos/ingest/llm/cli.py` (pre-count в extract())
- Test: `tests/ingest/test_llm_api.py`, `tests/ingest/test_llm_cli.py` (сверь имена)

**Проблема:** `TranscriptTooLargeError` несёт только строку. CLI-клиент (дефолт у Ярика) вообще не проверяет лимит → большая сессия = subprocess timeout 600s, а не структурная ошибка. Чинимём: добавляем поля и pre-count в CLI.

- [ ] **Step 1: failing tests.**
```python
# api: ошибка несёт числа
def test_too_large_error_carries_token_counts(...):
    with pytest.raises(TranscriptTooLargeError) as ei:
        client.extract(system="...", user=<huge>, tool=...)
    assert ei.value.input_tokens > ei.value.max_input_tokens
    assert ei.value.max_input_tokens == <cfg.max_input_tokens>

# cli: pre-count райзит ДО subprocess
def test_cli_raises_too_large_before_subprocess(monkeypatch, ...):
    # cfg.max_input_tokens маленький; user большой; subprocess.run замокать и assert НЕ вызван
    with pytest.raises(TranscriptTooLargeError) as ei:
        cli_client.extract(system="s", user=<big>, tool=...)
    assert ei.value.input_tokens > ei.value.max_input_tokens
    # subprocess.run not called
```
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: implementation.**
  - `api.py`: `class TranscriptTooLargeError(Exception):` → добавить `def __init__(self, message: str, *, input_tokens: int, max_input_tokens: int): super().__init__(message); self.input_tokens = input_tokens; self.max_input_tokens = max_input_tokens`. На строках 111-115 передавать поля.
  - `cli.py`: в начале `extract()` (до subprocess): `est = count_tokens_local(system) + count_tokens_local(user)`; `if est > self.cfg.max_input_tokens: raise TranscriptTooLargeError(f"prompt would be ~{est} tokens; max_input_tokens={self.cfg.max_input_tokens}", input_tokens=est, max_input_tokens=self.cfg.max_input_tokens)`. Импортировать `TranscriptTooLargeError` из api (или вынести в общий `llm/errors.py` если так чище — реши по месту; не плоди циклов импорта).
- [ ] **Step 4:** `pytest tests/ingest/ -q` → все зелёные (старые тесты api не сломаны — добавление kwargs к __init__ совместимо, проверь что старые места вызова обновлены).
- [ ] **Step 5: commit:** `feat: structured TranscriptTooLargeError (token counts) + CLI-mode pre-count detection`.

### Task 4: Handler ловит TooLarge — fail-fast, без 4 пустых ретраев, с машинным кодом

**Files:**
- Modify: `claude_mnemos/daemon/jobs/handlers.py` (IngestHandler.run try/except)
- Test: `tests/daemon/jobs/test_handlers.py` (или где тестируется IngestHandler; сверь)

**Проблема:** TooLarge сейчас проваливается в generic except → 4 ретрая (30s/120s/1200s) → молчаливый dead_letter. Чинимём: ловим явно, помечаем терминально СРАЗУ, с распознаваемым кодом и числами, чтобы UI (Task 8/9) показал выбор.

- [ ] **Step 1: failing test.** Замокать ingest() так, чтобы он райзил `TranscriptTooLargeError(input_tokens=900000, max_input_tokens=800000)`. Прогнать handler.run(job). Assert: джоба помечена терминально БЕЗ ретраев (attempt не растёт до 4 через паузы; статус сразу dead_letter/failed-terminal), и error содержит распознаваемый префикс с числами (например `error.startswith("too_large:")` и `"900000"`/`"800000"` в нём). Изучи, как handler сообщает worker'у «не ретраить» — есть ли в репо паттерн терминальной ошибки (например EmptyTranscriptError = success-return; RateLimitError = pause+raise). Возможно нужен спец-возврат или спец-исключение, которое worker переведёт в dead_letter сразу (attempt=MAX). Выбери минимальный механизм, согласованный с worker.py:142-152.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: implementation.** В `IngestHandler.run()` добавить `except TranscriptTooLargeError as exc:` ПЕРЕД тем как оно дойдёт до generic. Внутри — пометить джобу терминально без ретраев: записать `error = f"too_large:needs={exc.input_tokens}:max={exc.max_input_tokens}"` (машинный код, парсится фронтом) и перевести в dead_letter немедленно (attempt=MAX_ATTEMPTS). Реализуй через существующий механизм терминальной отметки (или добавь `JobStore.mark_dead_letter_now(job_id, error)` если нет — минимальный метод без схема-миграции: ставит status='dead_letter', attempt=MAX_ATTEMPTS, error=...). НЕ вызывать pause_queue (это не rate-limit).
- [ ] **Step 4:** `pytest tests/daemon/jobs/ -q` + полный прогон ingest.
- [ ] **Step 5: commit:** `fix: oversized-session ingest fails fast with machine-readable too_large code (was 4 silent retries → dead-letter)`.

### Task 5: Релиз-гейт Фазы 1 + промежуточная проверка

- [ ] **Step 1:** Полный `pytest -q` (exit 0, база 0 failed / 6 skipped), `ruff check claude_mnemos` clean, `mypy claude_mnemos` Success, `npm test -- --run` + `npx tsc --noEmit`.
- [ ] **Step 2:** Живая проверка на dev-демоне (НЕ frozen): выставить через UI default_max_input_tokens=500000, рестартнуть, проверить через `/api/settings/global` что значение применилось; (опц.) проверить на claude-mnemos-dev что ingest большой тестовой сессии теперь упирается в новый лимит, а не в 150k.
- [ ] **Step 3:** Зафиксировать: Фаза 1 — самостоятельный релиз-кандидат (можно выпустить v0.0.49 здесь, Фазу 2 — v0.0.50), ИЛИ продолжить и выпустить обе фазы одним релизом. Решение при сборке (Task 16). По умолчанию — копим обе фазы в один релиз v0.0.49.

---

## ФАЗА 2 — Чанкинг + per-session выбор «целиком / частями» + smart hint

### Task 6: Модуль нарезки `chunking.py` (чистая функция, TDD)

**Files:**
- Create: `claude_mnemos/ingest/chunking.py`
- Test: `tests/ingest/test_chunking.py`

- [ ] **Step 1: failing tests.**
```python
from claude_mnemos.ingest.chunking import split_messages_for_budget
from claude_mnemos.ingest.transcript import TranscriptMessage  # сверь конструктор

def _msg(role, text): return TranscriptMessage(role=role, text=text, session_id="s")  # сверь поля

def test_small_transcript_one_chunk():
    msgs = [_msg("user", "hi"), _msg("assistant", "hello")]
    chunks = split_messages_for_budget(msgs, budget_tokens=10_000)
    assert len(chunks) == 1 and chunks[0] == msgs

def test_splits_on_message_boundary_by_budget():
    msgs = [_msg("user", "x" * 4000) for _ in range(10)]  # каждое ~1000 ток
    chunks = split_messages_for_budget(msgs, budget_tokens=2500)
    assert len(chunks) > 1
    # каждый чанк ≤ budget (по count_tokens_local рендера), границы только между сообщениями
    flat = [m for c in chunks for m in c]
    assert flat == msgs  # ничего не потеряно, порядок сохранён

def test_single_message_over_budget_gets_own_chunk():
    msgs = [_msg("user", "x" * 40000)]  # одно сообщение больше бюджета
    chunks = split_messages_for_budget(msgs, budget_tokens=2500)
    assert len(chunks) == 1 and chunks[0] == msgs  # не теряем, отдаём как есть (API-guard решит)

def test_empty():
    assert split_messages_for_budget([], budget_tokens=1000) == []
```
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: implementation.**
```python
"""Split a transcript's messages into budget-bounded chunks for chunked extraction."""
from __future__ import annotations
from claude_mnemos.ingest.transcript import TranscriptMessage
from claude_mnemos.ingest.llm.tokens import count_tokens_local


def _msg_tokens(m: TranscriptMessage) -> int:
    # role header + text; cheap local estimate (cl100k proxy), never raises
    return count_tokens_local(m.text) + 8


def split_messages_for_budget(
    messages: list[TranscriptMessage], *, budget_tokens: int
) -> list[list[TranscriptMessage]]:
    """Greedily pack messages into chunks each within budget_tokens. Boundaries
    only between whole messages. A single message larger than the budget gets
    its own (over-budget) chunk — never split mid-message, never dropped; the
    LLM-client's own guard handles a genuinely unservable single message."""
    if not messages:
        return []
    chunks: list[list[TranscriptMessage]] = []
    cur: list[TranscriptMessage] = []
    cur_tok = 0
    for m in messages:
        mt = _msg_tokens(m)
        if cur and cur_tok + mt > budget_tokens:
            chunks.append(cur)
            cur, cur_tok = [], 0
        cur.append(m)
        cur_tok += mt
    if cur:
        chunks.append(cur)
    return chunks
```
(Сверь точную сигнатуру `TranscriptMessage` и `count_tokens_local`. Если рендер сообщения сложнее, оцени через `_render_transcript([m])`, но _msg_tokens дешевле и достаточно для жадной упаковки + headroom задаётся вызывающим.)
- [ ] **Step 4:** `pytest tests/ingest/test_chunking.py -v` → PASS.
- [ ] **Step 5: commit:** `feat: chunking.split_messages_for_budget — budget-bounded transcript splitting`.

### Task 7: Чистое слияние страниц между чанками `merge_extraction_payloads`

**Files:**
- Modify: `claude_mnemos/ingest/extraction.py` (добавить чистую `_merge_payloads`)
- Test: `tests/ingest/test_extraction_merge.py`

- [ ] **Step 1: failing tests.** Слияние списка `ExtractionPayload` в один с дедупом по slug:
```python
def test_merge_dedups_same_slug_keeps_higher_confidence(): ...
def test_merge_identical_body_collapses_to_one(): ...
def test_merge_unions_related_links(): ...
def test_merge_concatenates_nonempty_summaries(): ...
def test_merge_single_payload_is_identity(): ...
```
Ключ дедупа: `make_slug(page.slug_hint or page.title)` (тот же rel-path). Совпал slug: если `body_hash` равны → одна; разные → берём с большим `confidence` (при равенстве — первую); `related` и `flavor` — union; summary непустых склеить через `\n\n`; `skipped_reason=None` если есть хоть одна page.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: implementation.** Добавить в `extraction.py` чистую функцию (без I/O, без LLM):
```python
from claude_mnemos.core.slug import make_slug
from claude_mnemos.core.ontology_similarity import body_hash

def _merge_payloads(payloads: list[ExtractionPayload]) -> ExtractionPayload:
    by_slug: dict[str, ExtractedPage] = {}
    for p in payloads:
        for page in p.pages:
            key = make_slug(page.slug_hint or page.title)
            existing = by_slug.get(key)
            if existing is None:
                by_slug[key] = page
                continue
            if body_hash(existing.body) == body_hash(page.body):
                merged = existing  # identical → keep, just union links below
            else:
                merged = page if page.confidence > existing.confidence else existing
            # union related + flavor regardless
            related = list(dict.fromkeys([*existing.related, *page.related]))
            # rebuild with unioned related (ExtractedPage likely frozen — use dataclasses.replace / model_copy)
            by_slug[key] = merged.model_copy(update={"related": related})  # сверь: pydantic vs dataclass
    summaries = [p.summary for p in payloads if p.summary]
    return ExtractionPayload(
        summary="\n\n".join(summaries),
        skipped_reason=None if by_slug else (payloads[0].skipped_reason if payloads else "no pages"),
        pages=list(by_slug.values()),
    )
```
(Сверь: `ExtractedPage`/`ExtractionPayload` — pydantic BaseModel или dataclass? Используй `model_copy(update=...)` для pydantic или `dataclasses.replace` для dataclass. `body_hash` сигнатура.)
- [ ] **Step 4:** `pytest tests/ingest/test_extraction_merge.py -v` → PASS.
- [ ] **Step 5: commit:** `feat: deterministic merge_payloads for chunked extraction (slug dedup, body-hash collapse, related union)`.

### Task 8: Встроить чанкинг в `extract_wiki_pages` + промпт chunk_note

**Files:**
- Modify: `claude_mnemos/ingest/extraction.py` (`extract_wiki_pages`)
- Modify: `claude_mnemos/ingest/prompts/__init__.py` (`format_user` слот chunk_note), `ingest/prompts/extract_user.md`, `ingest/prompts/extract_system.md`
- Test: `tests/test_extraction.py` (расширить)

- [ ] **Step 1: failing tests.** В `tests/test_extraction.py` (MagicMock LLMClient):
```python
def test_small_transcript_calls_extract_once(...):
    # регрессия: маленький транскрипт → llm.extract вызван РОВНО 1 раз (старое поведение)
    assert llm.extract.call_count == 1

def test_oversized_transcript_chunks_and_merges(...):
    # cfg.max_input_tokens маленький; транскрипт большой; chunk_extract=True
    llm.extract.side_effect = [ExtractionRaw(payload=chunk1, ...), ExtractionRaw(payload=chunk2, ...)]
    result = extract_wiki_pages(messages=big, llm_client=llm, cfg=small_cfg, today=..., chunk_extract=True)
    assert llm.extract.call_count == 2
    # страницы дедуплицированы, токены = сумма по чанкам
    assert result.input_tokens == chunk1_tok + chunk2_tok
```
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: implementation.**
  - Сигнатуру `extract_wiki_pages` расширить параметром `chunk_extract: bool = False`.
  - Логика: `full = _render_transcript(messages)`. Если `not chunk_extract` ИЛИ `count_tokens_local(full) + HEADROOM <= cfg.max_input_tokens` → текущий путь без изменений (один вызов; **регрессия зелёная**). Иначе:
    ```python
    budget = int(cfg.max_input_tokens * 0.75)  # headroom под system+шаблон+tool-schema
    chunks = split_messages_for_budget(messages, budget_tokens=budget)
    payloads, in_tok, out_tok = [], 0, 0
    for i, chunk in enumerate(chunks, 1):
        user = format_user(transcript=_render_transcript(chunk), language_hint=cfg.language_hint,
                           chunk_note=f"(Это часть {i} из {len(chunks)} большого транскрипта.)")
        raw = llm_client.extract(system=load_system(), user=user, tool=..., validate=...)
        payloads.append(raw.payload); in_tok += raw.input_tokens; out_tok += raw.output_tokens
    merged = _merge_payloads(payloads)
    pages = [_render_page(pg, today) for pg in merged.pages]
    return ExtractionResult(summary=merged.summary, skipped_reason=merged.skipped_reason,
                            pages=pages, input_tokens=in_tok, output_tokens=out_tok)
    ```
  - `format_user`: добавить необязательный `chunk_note: str = ""` → replace слота `{chunk_note}` (пустой для single-chunk = ноль изменений). `extract_user.md`: вставить `{chunk_note}` строку. `extract_system.md`: ослабить «exactly once per session» формулировкой «если транскрипт пришёл частями — извлекай из этой части; дубли сущностей между частями будут слиты автоматически».
- [ ] **Step 4:** `pytest tests/test_extraction.py tests/ingest/ -v` → все 16+ зелёные, новые PASS.
- [ ] **Step 5: commit:** `feat: chunked extraction in extract_wiki_pages (split → extract per chunk → merge) + chunk_note prompt slot`.

### Task 9: Payload-флаги `chunk_extract` + `max_input_tokens` через endpoint и handler

**Files:**
- Modify: `claude_mnemos/daemon/routes/sessions.py` (ingest_session_route)
- Modify: `claude_mnemos/daemon/jobs/handlers.py` (применить override + флаг)
- Modify: `claude_mnemos/ingest/pipeline.py` (прокинуть chunk_extract в extract_wiki_pages)
- Test: `tests/daemon/test_app_sessions.py` (или где роут тестируется), `tests/daemon/jobs/test_handlers.py`

- [ ] **Step 1: failing tests.** (а) POST .../ingest с body `{transcript_path, extract: true, max_input_tokens: 1200000, chunk_extract: true}` → джоба создана с этими полями в payload. (б) handler с payload.chunk_extract=true и max_input_tokens override → cfg.with_overrides применён, chunk_extract проброшен в pipeline/extract_wiki_pages.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: implementation.**
  - `sessions.py` ingest_session_route: читать опц. `body.get("max_input_tokens")` (int|None) и `body.get("chunk_extract", False)`; класть в payload джобы (валидация: max_input_tokens >= 1024 если задан).
  - `handlers.py`: если `payload.get("max_input_tokens")` → `cfg = cfg.with_overrides(max_input_tokens=...)`; прокинуть `chunk_extract=payload.get("chunk_extract", False)` в `ingest()`.
  - `pipeline.py` `ingest()`: пробросить `chunk_extract` в `extract_wiki_pages(..., chunk_extract=chunk_extract)`.
- [ ] **Step 4:** `pytest tests/daemon/ tests/ingest/ -q` → PASS.
- [ ] **Step 5: commit:** `feat: per-session ingest accepts max_input_tokens override + chunk_extract flag`.

### Task 10: Frontend — api/hooks принимают режим

**Files:**
- Modify: `frontend/src/api/sessions.api.ts` (`ingestSession`)
- Modify: `frontend/src/hooks/useReingestSession.ts`, `frontend/src/hooks/useSessionIngest.ts`
- Test: `frontend/src/__tests__/api-sessions.test.ts` (или ближайший; сверь)

- [ ] **Step 1: failing test.** `ingestSession(project, sid, transcript_path, {extract:true, maxInputTokens: 1200000})` шлёт body с `max_input_tokens`; `{extract:true, chunked:true}` шлёт `chunk_extract:true`.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: implementation.** Расширить сигнатуру `ingestSession` опц. объектом `opts?: { extract: boolean; maxInputTokens?: number; chunked?: boolean }` (или добавить поля, сохранив обратную совместимость вызовов — сверь текущую сигнатуру и не сломай существующие). Положить в body `max_input_tokens`/`chunk_extract` когда заданы. В обоих хуках (`useReingestSession`, `useSessionIngest`) добавить опц. `mode`/`maxInputTokens` в Args и пробросить. ВНИМАНИЕ: хуки почти дублируются — правь оба синхронно (или вынеси общий core, если дёшево).
- [ ] **Step 4:** `cd frontend; npm test -- --run; npx tsc --noEmit`.
- [ ] **Step 5: commit:** `feat: frontend ingest api/hooks accept maxInputTokens override + chunked mode`.

### Task 11: Frontend — smart hint + две кнопки на SessionCard/SessionDetail

**Files:**
- Create: `frontend/src/lib/tooLarge.ts` (парсер кода `too_large:needs=N:max=M` + helper)
- Modify: `frontend/src/components/widgets/SessionCard.tsx`, `frontend/src/pages/SessionDetail.tsx`
- Modify: локали ru/uk/en
- Test: `frontend/src/__tests__/tooLarge.test.ts`, расширить SessionCard-тест

- [ ] **Step 1: failing tests.**
```ts
// tooLarge.ts
parseTooLarge("too_large:needs=900000:max=800000") // => {needs:900000, max:800000}
parseTooLarge("some other error") // => null
recommendMode(900000, 800000) // => "whole"  (≤ ~1.5× лимита → целиком на повышенном бюджете)
recommendMode(5_000_000, 800000) // => "chunked"  (сильно за лимитом → частями)
```
Плюс компонентный: когда `session.error` содержит too_large-код, SessionCard показывает бейдж «Слишком большая для одного захода» + ДВЕ кнопки («Попробовать целиком», «Обработать частями»), и подсвечивает рекомендованную.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: implementation.**
  - `tooLarge.ts`: `parseTooLarge(error?: string|null): {needs:number; max:number} | null` (regex `^too_large:needs=(\d+):max=(\d+)$`); `recommendMode(needs:number, max:number): "whole"|"chunked"` (порог: `needs <= max * 1.5` → whole, иначе chunked).
  - SessionCard/SessionDetail: если сессия в too-large состоянии (распознали по `parseTooLarge(s.error)`), вместо одной кнопки extract — бейдж + две кнопки: «Попробовать целиком» → `ingest({extract:true, maxInputTokens: needs + headroom})` (headroom напр. +10% или до следующей круглой), «Обработать частями» → `ingest({extract:true, chunked:true})`. Рекомендованную (по `recommendMode`) выделить (primary), вторую — outline. Когда НЕ too-large — поведение как сейчас (одна кнопка).
  - Локали: `sessions.too_large_badge` «Слишком большая для одного захода», `sessions.too_large_hint` (с числами), `sessions.extract_whole_button` «Попробовать целиком», `sessions.extract_chunked_button` «Обработать частями». ru/uk/en. Сверь точные ключи `sessions.*` в локалях (extract_button ~409).
- [ ] **Step 4:** `npm test -- --run; npx tsc --noEmit`.
- [ ] **Step 5: commit:** `feat: per-session too-large badge + whole/chunked choice with smart recommendation`.

### Task 12: Frontend — те же действия в Dead-letter UI

**Files:**
- Modify: `frontend/src/components/widgets/DeadLetterRow.tsx`, `frontend/src/pages/DeadLetterDetail.tsx`
- Modify: локали dead_letter.*
- Test: расширить dead-letter тест(ы)

- [ ] **Step 1: failing test.** Когда dead-letter джоба несёт too_large-код в error, рядом с Retry/Dismiss появляется «Обработать частями» (и/или «Попробовать целиком»), дёргающая ingest с нужным режимом для этой сессии.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: implementation.** В `DeadLetterRow`/`DeadLetterDetail`: `parseTooLarge(job.error)` → если не null, показать action-кнопки (переиспользовать helper из Task 11; project/session_id извлечь из payload.transcript_path как делает существующий код — сверь `_sid_from_job` аналог на фронте, либо payload содержит project). Локали `dead_letter.process_in_chunks` и т.п. (ru/uk/en).
- [ ] **Step 4:** `npm test -- --run; npx tsc --noEmit`.
- [ ] **Step 5: commit:** `feat: dead-letter rows offer chunked/whole re-extraction for too-large jobs`.

### Task 13: Живая проверка фичи на claude-mnemos-dev

- [ ] **Step 1:** `cd frontend; npm run build`; рестарт dev-демона (НЕ frozen).
- [ ] **Step 2:** На claude-mnemos-dev взять заведомо большую тестовую сессию (или искусственно занизить лимит через UI до ~2000, чтобы любая сессия стала «слишком большой»). Прогнать extract → убедиться: джоба НЕ висит 4 ретрая, а сразу помечается too_large; на SessionCard появились бейдж + две кнопки.
- [ ] **Step 3:** Нажать «Обработать частями» → убедиться, что экстракция идёт чанками и страницы создаются (проверить vault: wiki-страницы появились, дублей слугов нет). Нажать «Попробовать целиком» на другой → один заход на повышенном бюджете.
- [ ] **Step 4:** Консоль браузера 0 errors. Восстановить лимит в UI обратно (800000).

---

## ФАЗА 3 — Скептик + релиз v0.0.49

### Task 14: Полные гейты

- [ ] `pytest -q` exit 0 (база 0 failed / 6 skipped), `ruff check claude_mnemos` clean, `mypy claude_mnemos` Success (помни про `platform=win32` пин), `npm test -- --run` all pass, `npx tsc --noEmit` clean, `npm run build` ok.

### Task 15: Adversarial скептик-ревью критичных путей

- [ ] Скептик (как на v0.0.43/44/48 — ловил реальные баги): (а) **слияние чанков** — теряются ли страницы при коллизии слугов; что если два чанка дают конфликтующие body одной сущности (берём по confidence — не теряем ли важное); related-ссылки на страницы из другого чанка (битый wikilink?). (б) **CLI pre-count** — count_tokens_local занижает (cl100k ≠ реальный токенайзер Claude) → можем пропустить чуть-большую сессию в `claude -p`, она упадёт по таймауту 600s; достаточен ли headroom 0.75. (в) **частичный фейл чанкинга** — 2-й чанк падает (RateLimit/CLI-ошибка) → теряем результат 1-го (job retry с нуля); приемлемо ли, или нужна устойчивость. (г) **placebo-фикс vault_runtime** — env-приоритет не сломал ли существующие env-override юзеров. (д) **миграции нет** — у кого записано 150000, UI-значение теперь реально режет на 150k (а не плацебо) — это улучшение или регрессия для тех, кто думал что у них больше?

### Task 16: Релиз

- [ ] Решить упаковку: обе фазы → один тег `v0.0.49` (рекомендация), или Фаза 1 → v0.0.49 / Фаза 2 → v0.0.50. По умолчанию обе в v0.0.49.
- [ ] Тег `v0.0.49` → push → CI (release.yml) 3 платформы → опубликовать (версия из тега, set_version.py).
- [ ] Установка у Ярика: WDAC → portable zip + elevated robocopy в `C:\Program Files\claude-mnemos`. Проверить `Mnemos.lnk` → установленный exe.
- [ ] Живое доказательство на установленной версии: лимит 800k применяется; большая сессия экстрактится (целиком или частями); too-large даёт выбор, а не молчаливый dead-letter.

---

## Self-review notes

- **Главный placebo-фикс (Task 2)** — настройка лимита была мёртвой; теперь UI-значение реально управляет экстракцией. Это сам по себе ценный фикс из класса «мёртвые контролы».
- **Контракт LLMClient.extract НЕ меняется** — чанкинг слоем выше, риск регрессии минимален; «маленький транскрипт = ровно 1 вызов» закреплён тестом-регрессией.
- **Слияние без LLM** — детерминированное, через существующий ontology_similarity; кросс-чанковые related-ссылки и умный merge оставлены post-hoc ontology-скану (не раздуваем scope).
- **Машинный код `too_large:needs=N:max=M`** в error джобы — без схема-миграции БД; фронт парсит. Если позже захотим чистый статус — отдельная задача.
- **CLI pre-count приблизителен** (cl100k ≠ Claude-токенайзер) — headroom 0.75 + skeptic Task 15(б) это проверяет; на API-режиме точный count страхует.
- **Известные pre-existing failing tests** (Windows PID + env, ~3-5) не чинятся; критерий exit 0 = «не хуже базовой линии».
- **Phasing**: Tasks 1-5 (Фаза 1) самодостаточны и могли бы выйти отдельным релизом; держим в одном v0.0.49 ради цельности, но если Фаза 2 затянется — Фаза 1 готова к выпуску в любой момент.
