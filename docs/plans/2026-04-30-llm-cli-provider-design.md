# LLM Provider Refactor — Design

**Date:** 2026-04-30
**Status:** Approved by Yarik (autonomous brainstorm)
**Goal:** Убрать жёсткую зависимость от `ANTHROPIC_API_KEY`. Использовать Claude Code subscription через CLI subprocess. **Сохранить контракт `LLMClient` 1:1** — никакие callers не меняются. Dual mode: новый CLI provider — default, старый API provider — opt-in для тех у кого есть ключ.

---

## 1. Why

claude-mnemos сейчас требует отдельный `ANTHROPIC_API_KEY` (отдельный billing на console.anthropic.com), хотя его целевая аудитория — Claude Code subscribers (Pro $20/мес или Max $100-200/мес). Это требует двойного billing'а и большинство пользователей не имеют API key вообще.

Решение — использовать `claude -p` CLI с user subscription через OAuth (`CLAUDE_CODE_OAUTH_TOKEN` или `claude login` flow). Анализ возможностей описан в research-брифе (см. `tasks/`).

**Главное правило:** «Не менять суть mnemos, подстроить ingest под него не потеряв суть и эффективность» (Yarik). Поэтому:
- Контракт `LLMClient.extract()` НЕ меняется.
- `extraction.py` НЕ меняется.
- Все callers (cli.py, vault_runtime.py, jobs/handlers.py) НЕ меняются.
- Только подменяется backend под капотом + добавляется factory для выбора.

## 2. Scope

### Включено

- Новый `CliLLMClient` через `claude -p --output-format json --json-schema <S> --system-prompt <T> --setting-sources ""` + stdin для prompt'а
- Dual-mode factory: `cli | api` provider, auto-detect по `ANTHROPIC_API_KEY` env
- Local approximate token counter (`tiktoken` как proxy для Claude tokens — точность ~85-95%)
- Smart pause queue при rate limit (45/5h Pro), auto-resume через 5h
- Onboarding wizard step «Check Claude CLI access» (preflight `claude --version` + dry test)
- Все 1404 существующих теста должны продолжать проходить

### Не включено (out of MVP)

- Claude Agent SDK — требует API key, не наша задача
- Multi-provider (OpenAI, Groq, Ollama)
- Streaming output (`stream-json`)
- Hide-user-CLAUDE.md трюк (как в Control Panel runner.py) — `--system-prompt` override достаточен
- Кэширование LLM ответов

## 3. Architecture

```
extraction.py (без изменений)
        │
        │ llm_client.extract(system, user, tool, validate)
        ↓
   LLMClient (Protocol — извлечён из текущего класса)
        │
   ┌────┴─────┐ ← factory(cfg)
   ↓          ↓
 ApiLLMClient    CliLLMClient
 (старый код,    (новый)
 переименован)        │
                      │ subprocess.run
                      ↓
              ┌─────────────────────┐
              │ claude -p           │
              │ --output-format json│
              │ --json-schema <S>   │
              │ --system-prompt <T> │
              │ --setting-sources ""│
              │ --max-turns 1       │
              └─────────────────────┘
```

### Принципы

- **Adapter pattern.** `LLMClient` Protocol с одним методом `extract()`. Два adapter'а под одним интерфейсом — `ApiLLMClient` (Anthropic SDK) и `CliLLMClient` (subprocess).
- **Phase-by-phase rollout.** Каждая фаза независимо тестируема, можно остановиться/откатиться без поломок.
- **Existing tests survive.** `tests/test_llm.py` мокает через `_client=...` DI keyword — продолжает работать после переименования в `tests/test_llm_api.py`.
- **Default behavior unchanged.** Auto-detect: если `ANTHROPIC_API_KEY` set → `ApiLLMClient`. Иначе → `CliLLMClient`. Существующие пользователи (с API key) продолжают на старом пути.

## 4. Components

### Новые файлы (~10)

```
claude_mnemos/ingest/llm/__init__.py        ← Protocol + exceptions + factory + ExtractionRaw
claude_mnemos/ingest/llm/api.py              ← ApiLLMClient (бывший llm.py)
claude_mnemos/ingest/llm/cli.py              ← CliLLMClient
claude_mnemos/ingest/llm/tokens.py           ← local token counter (tiktoken wrapper)
claude_mnemos/ingest/llm/auth.py             ← check_claude_cli_auth, find_claude_binary
claude_mnemos/ingest/llm/rate_limit.py       ← RateLimitError + parse_rate_limit_from_stderr

tests/test_llm_factory.py
tests/test_llm_cli.py                        ← мокает subprocess.run
tests/test_llm_tokens.py
tests/test_llm_auth.py
tests/test_jobs_pause_on_rate_limit.py
```

### Modified files

```
claude_mnemos/config.py                      ← +ingest_provider: Literal["cli","api"] | None
claude_mnemos/state/jobs.py                  ← +paused_until: datetime | None
claude_mnemos/daemon/jobs/handlers.py        ← catch RateLimitError → JobStore.pause_queue
claude_mnemos/daemon/routes/health.py        ← +cli auth status в /health
frontend/src/pages/Onboarding.tsx            ← +«Check Claude CLI» step
pyproject.toml                               ← +tiktoken>=0.7

tests/test_llm.py → tests/test_llm_api.py    ← переименование, без изменений в логике
```

### Что критически НЕ трогаем (zero-diff)

- `claude_mnemos/ingest/extraction.py` — pipeline парсинга
- `claude_mnemos/ingest/parser.py` — JSONL parser
- `claude_mnemos/state/manifest.py` — IngestRecord, метаданные
- `claude_mnemos/core/metrics.py` — compression_ratio считается из ExtractionRaw как было
- Все hooks (SessionStart inject, PostToolUse), watchdog
- Frontend кроме Onboarding шага

## 5. Detailed Behavior

### `LLMClient` Protocol (Phase 1)

```python
class LLMClient(Protocol):
    def extract(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        validate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> ExtractionRaw: ...
```

`ExtractionRaw` тот же dataclass что и сейчас (`payload: dict`, `input_tokens: int`, `output_tokens: int`).

Exceptions: `MissingApiKeyError`, `LLMExtractionError`, `TranscriptTooLargeError` — те же. Новый — `RateLimitError(reset_at: datetime)` (специально для CLI provider'а, но поднимается как `LLMExtractionError` subclass).

### `CliLLMClient.extract()` flow

1. Render JSON schema из `tool["input_schema"]`.
2. Build command:
   ```
   claude -p
     --output-format json
     --json-schema <serialized_schema>
     --system-prompt <system_text>
     --setting-sources ""
     --no-session-persistence
     --max-turns 1
   ```
3. Build env:
   - Copy `os.environ`
   - Drop `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT` (recursion guard)
   - Drop `ANTHROPIC_API_KEY` (force subscription path; иначе CLI пойдёт через API billing!)
   - Keep `CLAUDE_CODE_OAUTH_TOKEN` if set
4. Run via `subprocess.run(cmd, input=user_prompt_text, capture_output=True, text=True, encoding="utf-8", timeout=120, env=env)`.
   - Promпт через **stdin**, не argv (Windows CMD режет multiline на первом LF).
5. If `returncode != 0`:
   - Parse stderr на rate_limit / HTTP 429 → `RateLimitError`
   - Иначе → `LLMExtractionError(stderr)`
6. Parse stdout как JSON envelope: `{"result": ..., "structured_output": {...}, ...}`.
7. Extract `structured_output` field → use as payload.
8. Token counting:
   - `input_tokens = count_tokens_local(system + user)` через tiktoken
   - `output_tokens = count_tokens_local(json.dumps(structured_output))`
9. If `validate(payload)` raises → retry once with error appended (mirror existing `ApiLLMClient` retry logic).
10. Return `ExtractionRaw(payload, input_tokens, output_tokens)`.

### Factory resolution

```python
def make_llm_client(cfg: Config) -> LLMClient:
    explicit = cfg.ingest_provider  # Literal["cli","api"] | None
    if explicit == "api":
        return ApiLLMClient(cfg)
    if explicit == "cli":
        return CliLLMClient(cfg)
    # auto-detect
    if cfg.api_key:
        return ApiLLMClient(cfg)
    return CliLLMClient(cfg)
```

`ingest_provider` — поле в global settings (`~/.claude-mnemos/global-settings.json`), с возможностью per-project override через `~/.claude-mnemos/settings/<project>.json` (используя существующий settings overlay механизм из Plan #13b-α).

Factory создаёт client **lazy** — без auth-check на этапе создания. `CliLLMClient.__init__` тоже не делает sync subprocess вызовов. Auth-check выполняется только при первом `extract()` или явно через `check_claude_cli_auth()`. Это позволяет dashboard'у иметь живой client который может ругаться на missing binary позже, без блокировки startup.

### Recursion guard

`CLAUDECODE=1` и `CLAUDE_CODE_ENTRYPOINT` устанавливаются Claude Code когда mnemos запущен изнутри его сессии. `claude -p` отказывается работать в таком env (issue #32618). Решение — чистим env подпроцесса. Это standard pattern, описан в research.

### CLAUDE.md contamination

`--system-prompt <T>` полностью заменяет системный prompt (включая user's `~/.claude/CLAUDE.md`). `--setting-sources ""` отключает loading настроек из файлов. Этого достаточно — без костылей с переименованием user файлов (как в Control Panel runner.py).

### Rate limit pause

`RateLimitError` — это `LLMExtractionError` subclass с полем `reset_at: datetime`. Handler различает через `isinstance(exc, RateLimitError)`:

```python
try:
    result = llm_client.extract(...)
except RateLimitError as exc:
    job_store.pause_queue(until=exc.reset_at)
    raise  # job re-queued, not dead-lettered
except LLMExtractionError:
    # обычный fail → dead-letter после retry attempts
    ...
```

В `JobStore` добавляется поле `paused_until: datetime | None`. При `RateLimitError` от любого provider:
- `IngestHandler` ловит → `JobStore.pause_queue(until=datetime.now(UTC) + timedelta(hours=5))`
- Job re-queued (retry потом), не уходит в dead-letter сразу
- При следующем dequeue если `paused_until > now` → skip iteration, daemon ждёт
- `/health` endpoint показывает `queue_paused_until: ISO timestamp`
- Frontend dashboard читает и показывает «Rate limited — resumes at HH:MM»

### Token counting (local approximate)

`tiktoken` — официальная OpenAI tokenizer library. Использует BPE (Byte Pair Encoding). Claude использует свой собственный BPE (близкий, но не идентичный). `tiktoken.get_encoding("cl100k_base")` даёт стабильную оценку с точностью ~85-95% для типичного Claude content.

```python
def count_tokens_local(text: str) -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))
```

Альтернатива (если `tiktoken` не доступен) — character-based heuristic (4 char/token English, 2 char/token Russian). Но `tiktoken` стандартно работает на всех платформах.

В UI metrics для CLI ingests добавляется префикс `~` чтобы было видно что approximate (e.g. `~5.2× compression` vs `5.2× compression`).

### Auth preflight

`check_claude_cli_auth() -> AuthStatus` запускает:
1. `claude --version` → проверка установки. Если binary не найден → `AuthStatus(installed=False)`.
2. `claude -p "ok"` → dry test (минимальный prompt). Если успех → `AuthStatus(installed=True, authenticated=True)`. Если fail с auth-related error → `AuthStatus(installed=True, authenticated=False)`.

Endpoint `/health/claude-cli` exposes этот статус в дашборде.

### Onboarding шаг

После шага «Создать проект» (если выбран CLI provider или auto-detect → CLI):
- Wizard вызывает `/health/claude-cli`
- Если `installed=False` → показывает инструкцию «Install Claude Code from https://claude.ai/download»
- Если `authenticated=False` → показывает инструкцию «Run `claude login` in terminal»
- Если ok → green checkmark, можно идти дальше

## 6. Backward Compatibility

- **Existing tests:** `tests/test_llm.py` тестирует через `_client=...` DI. Переименовываем в `tests/test_llm_api.py`, **код тестов unchanged**, только импорты (`from claude_mnemos.ingest.llm.api import ApiLLMClient` вместо `from claude_mnemos.ingest.llm import LLMClient`).
- **Existing users with API key:** auto-detect → `ApiLLMClient` → старый flow без изменений.
- **Existing vaults:** на диске ничего не меняется.
- **Existing manifest:** `tokens_full`, `tokens_actual` остаются точными для старых ingests (через API). Новые ingests (через CLI) — approximate, но schema unchanged.
- **Existing config files:** новое поле `ingest_provider` опционально (default None = auto). Existing configs без него работают.

## 7. Risks / Edge cases

| Риск | Mitigation |
|---|---|
| `tiktoken` несовместим с какой-то платформой | tiktoken работает на Win/Mac/Linux. Pure Python fallback в случае import error — character heuristic. |
| User has `ANTHROPIC_API_KEY` set but wants CLI mode | `cfg.ingest_provider = "cli"` явно. Subprocess env очищается от `ANTHROPIC_API_KEY`. |
| `claude` binary не в PATH (Windows) | `find_claude_binary()` проверяет `%APPDATA%/npm/claude.cmd` / `.bat`. |
| `--system-prompt` будет deprecated в будущем | Маловероятно, это документированный flag. Если — patch upgrade. |
| User CLAUDE.md всё равно подмешивается (несмотря на `--system-prompt`) | `--setting-sources ""` отключает all settings. Если этого недостаточно — phase 6 добавит fallback на rename-файлы (костыль из Control Panel). |
| Claude Code session подвисла, claude -p не отвечает | Timeout 120s + kill_proc_tree (на Win убивает дерево процессов, не просто claude). |
| Rate limit reset_at undeterminable | Default к 5h pause если parse failed. Пользователь видит «paused, retry manually» через UI. |
| Pro подписка не доходит для bulk ingest | Self-throttling out of scope. Юзер ждёт rate limit pause. Документация рекомендует Max $100+ для heavy use. |
| Mnemos запущен в headless server (CI, docker) без `claude login` | `check_claude_cli_auth` → `authenticated=False`. Юзер должен один раз сделать `claude setup-token` локально + передать `CLAUDE_CODE_OAUTH_TOKEN` env var в server. |

## 8. Phase-by-phase plan

Каждая фаза заканчивается зелёным test suite, можно ship/revert независимо.

| Phase | What | Behavior change | Tests |
|---|---|---|---|
| 1 | Extract `LLMClient` Protocol; rename existing class to `ApiLLMClient`; reorganize files | NONE | All existing tests pass with renamed import paths |
| 2 | Add `CliLLMClient` + `tokens.py` + `auth.py` + `rate_limit.py` modules + their tests | NONE (никто не использует) | New unit tests, all existing tests still pass |
| 3 | Add factory `make_llm_client` + config field `ingest_provider`. Wire factory into `vault_runtime.py` and `cli.py` | NONE in default behavior (auto-detect → existing flow) | Factory resolution tests |
| 4 | Rate-limit pause logic в `JobStore` + `IngestHandler` | Universal — works for both providers (если будут rate limit errors) | Pause tests |
| 5 | Onboarding wizard «Check Claude CLI» step + `/health/claude-cli` endpoint | UI-only | Frontend tests |
| 6 | Final: end-to-end проверка на Yarik's машине (без API key) + ручной checklist + merge to main | Confirmation only — default уже включён auto-detect'ом в Phase 3 | Manual smoke test |

## 9. Tests

### Unit (CI):
- `test_llm_factory.py` — provider resolution (explicit/env/auto cases)
- `test_llm_cli.py` — `CliLLMClient.extract()` с моком `subprocess.run`. Verify command line args, env cleaning, stdin content, parsing, retry, error mapping
- `test_llm_tokens.py` — local counter sanity (length monotonic, character→token ratio)
- `test_llm_auth.py` — `check_claude_cli_auth` с моком subprocess + cross-platform binary discovery
- `test_jobs_pause_on_rate_limit.py` — JobStore pause/resume mechanics
- `test_llm_api.py` (renamed) — все existing assertions, без изменений в коде тестов

### Integration (manual / behind `MNEMOS_REAL_CLAUDE_CLI=1` env):
- `tests/e2e/test_real_extraction_cli.py` — реальный вызов `claude -p` с минимальным prompt'ом, validate basic shape. Skip on CI.

## 10. Success Criteria

1. У Yarik (без `ANTHROPIC_API_KEY`) ingest заработал через `claude` subscription
2. Все 1404 backend pytest + 188 frontend Vitest теста зелёные после refactor'а
3. Существующая ingest pipeline (`extraction.py`, jobs queue, hooks, manifest) — diff = 0 строк
4. Compression metrics показывают approximate цифры в CLI mode (с `~` префиксом)
5. Onboarding wizard детектирует если `claude` не установлен / не залогинен → показывает инструкцию
6. Rate limit hit → queue paused, auto-resume через 5h без потери данных
7. User с API key (legacy) — продолжает работать через `ApiLLMClient` без изменений в его flow

## 11. Размер

~600-800 LOC Python (большая часть — тесты), ~100 LOC frontend, ~10 новых файлов, 6 фаз. **5-7 рабочих дней**.

## 12. Future work (out of scope)

- Multi-provider adapter (OpenAI / Groq / Ollama)
- Streaming output для UI прогресса при больших ingest'ах
- Self-throttling под Pro plan (avoid rate limits proactively)
- Кэширование identical extraction prompts
- Anthropic count_tokens API для точных счётчиков в CLI mode (если у юзера есть API key для side-channel only)
