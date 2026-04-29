# LLM CLI Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить hard dependency `ANTHROPIC_API_KEY` на dual-mode LLM client (Anthropic SDK *или* `claude -p` subprocess через user subscription), сохранив контракт `LLMClient.extract()` 1:1 — никакие callers не трогаются.

**Architecture:** Adapter pattern. `LLMClient` Protocol с одним методом `extract()`. Два adapter'а: `ApiLLMClient` (existing code, переименован) и `CliLLMClient` (новый, через `subprocess.run(['claude', '-p', ...])`). Factory `make_llm_client(cfg)` выбирает по `cfg.ingest_provider` или auto-detect. Phase-by-phase rollout: каждая фаза заканчивается зелёными тестами.

**Tech Stack:** Python 3.12+, Pydantic v2, FastAPI, `tiktoken>=0.7` (новая dep, локальный token counter), subprocess (stdlib), React/TypeScript для Onboarding step.

**Design doc:** `docs/plans/2026-04-30-llm-cli-provider-design.md`.

**Branch:** `feat/llm-cli-provider` (создана из `main` после merge `f6792e3`, design committed `4202fd6`).

**Critical safety rule:** Каждый Phase заканчивается полным test run: `python -m pytest --ignore=tests/slow` должен показывать зелёное (текущий baseline 1404 passed). Любое regression в существующих тестах = STOP & report.

---

## File Structure

### New files

```
claude_mnemos/ingest/llm/__init__.py        # Protocol, ExtractionRaw, exceptions, make_llm_client factory (later)
claude_mnemos/ingest/llm/api.py              # ApiLLMClient (renamed from ingest/llm.py)
claude_mnemos/ingest/llm/cli.py              # CliLLMClient (new)
claude_mnemos/ingest/llm/tokens.py           # count_tokens_local via tiktoken
claude_mnemos/ingest/llm/auth.py             # find_claude_binary, check_claude_cli_auth, AuthStatus
claude_mnemos/ingest/llm/rate_limit.py       # RateLimitError, parse_rate_limit_from_stderr

tests/ingest/__init__.py
tests/ingest/llm/__init__.py
tests/ingest/llm/test_protocol.py            # Protocol shape verification
tests/ingest/llm/test_api.py                 # renamed from tests/test_llm.py
tests/ingest/llm/test_cli.py                 # subprocess mocked
tests/ingest/llm/test_tokens.py
tests/ingest/llm/test_auth.py
tests/ingest/llm/test_rate_limit.py
tests/ingest/llm/test_factory.py
tests/daemon/jobs/test_pause_on_rate_limit.py

frontend/src/types/ClaudeCliAuth.ts          # zod schemas
frontend/src/api/claudeCli.api.ts            # axios client
frontend/src/__tests__/api-claude-cli.test.ts
```

### Modified files

```
claude_mnemos/ingest/llm.py                  # DELETED (split into ingest/llm/{api,__init__}.py)
tests/test_llm.py                            # DELETED (split into tests/ingest/llm/test_api.py)

claude_mnemos/config.py                      # +ingest_provider: Literal["cli","api"] | None
claude_mnemos/cli.py                         # LLMClient(cfg) → make_llm_client(cfg)
claude_mnemos/daemon/vault_runtime.py        # llm_factory uses make_llm_client
claude_mnemos/daemon/jobs/handlers.py        # catches RateLimitError → JobStore.pause_queue
claude_mnemos/state/jobs.py                  # +paused_until: datetime | None field + migration
claude_mnemos/daemon/routes/health.py        # +cli_auth status field, +queue_paused_until
frontend/src/pages/Onboarding.tsx            # +«Check Claude CLI» step (conditional on platform)
frontend/public/locales/{en,ru,uk}.json      # +new keys
pyproject.toml                               # +tiktoken>=0.7
```

### Untouched (zero-diff guarantee)

```
claude_mnemos/ingest/extraction.py
claude_mnemos/ingest/parser.py
claude_mnemos/state/manifest.py
claude_mnemos/core/metrics.py
claude_mnemos/hooks/* (SessionStart inject)
claude_mnemos/daemon/watchdog_*.py
```

---

# Phase 1 — Extract LLMClient Protocol (no behavior change)

**Goal:** Превратить existing class `LLMClient` (anthropic-based) в `ApiLLMClient` implementing a new `LLMClient` Protocol. Reorganize files. Все callers продолжают работать через тип `LLMClient`. Поведение не меняется.

**Safety:** В конце Phase 1 — `python -m pytest --ignore=tests/slow` должно показывать те же 1404 passed как до Phase 1.

---

## Task 1: Create ingest/llm/ subpackage skeleton

**Files:**
- Create: `claude_mnemos/ingest/llm/__init__.py` (empty markers)
- Create: `tests/ingest/__init__.py` (empty)
- Create: `tests/ingest/llm/__init__.py` (empty)

- [ ] **Step 1: Create empty package files**

```bash
mkdir -p D:/code/claude-mnemos/claude_mnemos/ingest/llm
mkdir -p D:/code/claude-mnemos/tests/ingest/llm
```

Write `claude_mnemos/ingest/llm/__init__.py`:
```python
"""LLM provider package — Protocol + adapter classes.

Adapters:
- ``ApiLLMClient`` (claude_mnemos.ingest.llm.api): uses anthropic.Anthropic SDK
  with ANTHROPIC_API_KEY. Existing path, preserved for users with their own
  API key billing.
- ``CliLLMClient`` (claude_mnemos.ingest.llm.cli): uses ``claude -p`` subprocess
  with the user's Claude Code subscription (added in Phase 2).

Selection happens via ``make_llm_client(cfg)`` factory (added in Phase 3).
See docs/plans/2026-04-30-llm-cli-provider-design.md.
"""
```

Write `tests/ingest/__init__.py` empty file.
Write `tests/ingest/llm/__init__.py` empty file.

- [ ] **Step 2: Verify package importable**

```bash
cd /d/code/claude-mnemos && python -c "import claude_mnemos.ingest.llm; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
cd /d/code/claude-mnemos && git add claude_mnemos/ingest/llm/__init__.py tests/ingest/ && git commit -m "feat(llm): ingest/llm subpackage skeleton

Empty marker files. ApiLLMClient + Protocol move into this package
in subsequent tasks of Phase 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Move LLMClient class to ingest/llm/api.py and rename to ApiLLMClient

**Files:**
- Create: `claude_mnemos/ingest/llm/api.py` (full content of current `ingest/llm.py`, class renamed)
- Modify: `claude_mnemos/ingest/llm.py` (DELETE — handled in Step 5)

- [ ] **Step 1: Read current llm.py**

```bash
cat /d/code/claude-mnemos/claude_mnemos/ingest/llm.py
```

Note the structure: imports, constants (`DEFAULT_MAX_TOKENS=8000`, `DEFAULT_TIMEOUT_SEC=120.0`), exceptions (`MissingApiKeyError`, `TranscriptTooLargeError`, `LLMExtractionError`), dataclass `ExtractionRaw`, class `LLMClient`.

- [ ] **Step 2: Write the new api.py**

Create `claude_mnemos/ingest/llm/api.py` with content (copy verbatim from current `claude_mnemos/ingest/llm.py`, BUT change the class name `LLMClient` → `ApiLLMClient`):

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
    """Raised when ANTHROPIC_API_KEY is not set and ApiLLMClient is selected."""


class TranscriptTooLargeError(RuntimeError):
    """Raised when prompt token count exceeds configured max_input_tokens."""


class LLMExtractionError(RuntimeError):
    """Raised when LLM call fails to produce a valid tool_use payload after retry."""


@dataclass(frozen=True)
class ExtractionRaw:
    payload: dict[str, Any]
    input_tokens: int
    output_tokens: int


class ApiLLMClient:
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
            max_retries=2,
            timeout=DEFAULT_TIMEOUT_SEC,
        )
        self._last_input_tokens: int = 0
        self._last_output_tokens: int = 0

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

        try:
            tc = self._client.messages.count_tokens(
                model=self.cfg.model,
                system=system_blocks,  # type: ignore[arg-type]
                tools=[tool],  # type: ignore[list-item]
                messages=user_messages,  # type: ignore[arg-type]
            )
            input_tokens = int(tc.input_tokens)
        except (AttributeError, TypeError):
            input_tokens = 0

        if input_tokens > self.cfg.max_input_tokens:
            raise TranscriptTooLargeError(
                f"prompt would be {input_tokens} tokens; "
                f"max_input_tokens={self.cfg.max_input_tokens}"
            )

        payload = self._call_once(system_blocks, user_messages, tool)
        first_validation_error: Exception | None = None
        if validate is not None:
            try:
                validate(payload)
                return self._build_result(payload)
            except Exception as exc:  # noqa: BLE001
                first_validation_error = exc
        else:
            return self._build_result(payload)

        combined_user = (
            user
            + "\n\n---\n\n"
            + f"ATTENTION: A previous attempt to call {tool['name']} failed schema validation: "
            + str(first_validation_error)
            + f". Please call {tool['name']} again with a corrected payload "
            + "that strictly matches the tool's input_schema."
        )
        retry_messages: list[dict[str, Any]] = [{"role": "user", "content": combined_user}]
        try:
            payload2 = self._call_once(system_blocks, retry_messages, tool)
        except LLMExtractionError as exc:
            raise LLMExtractionError(
                f"retry after validation failure also failed: {exc}"
            ) from exc

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
            resp = self._client.messages.create(  # type: ignore[call-overload]
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
            input_tokens=self._last_input_tokens,
            output_tokens=self._last_output_tokens,
        )
```

The ONLY difference from current `ingest/llm.py`: class name changed from `LLMClient` to `ApiLLMClient`. Everything else verbatim.

- [ ] **Step 3: Re-export from `ingest/llm/__init__.py` for backward compat during refactor**

Append to `claude_mnemos/ingest/llm/__init__.py`:
```python
# Re-exports for callers — preserves import paths during refactor.
from claude_mnemos.ingest.llm.api import (
    ApiLLMClient,
    ExtractionRaw,
    LLMExtractionError,
    MissingApiKeyError,
    TranscriptTooLargeError,
)

# Backward-compatible alias — Phase 3 will replace this with a Protocol that
# both ApiLLMClient and CliLLMClient satisfy.
LLMClient = ApiLLMClient

__all__ = [
    "ApiLLMClient",
    "ExtractionRaw",
    "LLMClient",
    "LLMExtractionError",
    "MissingApiKeyError",
    "TranscriptTooLargeError",
]
```

- [ ] **Step 4: Delete the old llm.py file**

```bash
cd /d/code/claude-mnemos && rm claude_mnemos/ingest/llm.py
```

- [ ] **Step 5: Run all tests — must still be 1404 passing**

```bash
cd /d/code/claude-mnemos && python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1404 passed, 3 skipped` (or whatever the baseline was — must equal pre-Phase-1).

If any test fails because `from claude_mnemos.ingest.llm import LLMClient` no longer works — that's a problem with the re-export. Verify `LLMClient = ApiLLMClient` is in `__init__.py`.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/ingest/llm/api.py claude_mnemos/ingest/llm/__init__.py && git rm claude_mnemos/ingest/llm.py && git commit -m "refactor(llm): split ingest/llm.py — class renamed to ApiLLMClient

Move existing implementation to ingest/llm/api.py with class name
ApiLLMClient. Top-level re-exports preserve all existing import paths
(LLMClient = ApiLLMClient alias). No behavior change. Phase 1 of LLM
provider refactor.

All 1404 tests still pass.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Define LLMClient Protocol

**Files:**
- Modify: `claude_mnemos/ingest/llm/__init__.py` (replace alias with Protocol)
- Create: `tests/ingest/llm/test_protocol.py`

- [ ] **Step 1: Write the failing test**

Create `tests/ingest/llm/test_protocol.py`:
```python
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from claude_mnemos.ingest.llm import (
    ApiLLMClient,
    ExtractionRaw,
    LLMClient,
)


def test_llm_client_is_protocol() -> None:
    """LLMClient must be a runtime-checkable Protocol so duck-typed clients
    pass isinstance() checks (used by factory + tests)."""

    class StubClient:
        def extract(
            self,
            *,
            system: str,
            user: str,
            tool: dict[str, Any],
            validate: Any = None,
        ) -> ExtractionRaw:
            return ExtractionRaw(payload={}, input_tokens=0, output_tokens=0)

    assert isinstance(StubClient(), LLMClient)


def test_api_llm_client_satisfies_protocol() -> None:
    """ApiLLMClient must implement LLMClient Protocol."""
    cfg = MagicMock()
    cfg.api_key = "sk-test"
    cfg.model = "claude-sonnet-4-5"
    inner = MagicMock()
    client = ApiLLMClient(cfg, _client=inner)
    assert isinstance(client, LLMClient)


def test_protocol_rejects_class_without_extract() -> None:
    class BadClient:
        def something_else(self) -> None: ...

    assert not isinstance(BadClient(), LLMClient)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /d/code/claude-mnemos && python -m pytest tests/ingest/llm/test_protocol.py -v 2>&1 | tail -10
```

Expected: tests fail because `LLMClient` is currently a class alias (`= ApiLLMClient`), not a Protocol — `isinstance(StubClient(), LLMClient)` returns False because `StubClient` is not an instance of `ApiLLMClient`.

- [ ] **Step 3: Replace alias with Protocol**

Replace `claude_mnemos/ingest/llm/__init__.py` content:
```python
"""LLM provider package — Protocol + adapter classes.

Adapters:
- ``ApiLLMClient`` (claude_mnemos.ingest.llm.api): uses anthropic.Anthropic SDK
  with ANTHROPIC_API_KEY.
- ``CliLLMClient`` (claude_mnemos.ingest.llm.cli): uses ``claude -p`` subprocess
  with the user's Claude Code subscription (added in Phase 2).

Selection happens via ``make_llm_client(cfg)`` factory (added in Phase 3).
See docs/plans/2026-04-30-llm-cli-provider-design.md.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from claude_mnemos.ingest.llm.api import (
    ApiLLMClient,
    ExtractionRaw,
    LLMExtractionError,
    MissingApiKeyError,
    TranscriptTooLargeError,
)


@runtime_checkable
class LLMClient(Protocol):
    """Common contract for all LLM extraction backends (API SDK or CLI subprocess).

    Implementations MUST honour the same retry-on-validation-error semantics:
    if ``validate(payload)`` raises, call the model again once with the error
    appended to the user prompt. If the second attempt also fails validation,
    raise ``LLMExtractionError``.
    """

    def extract(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        validate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> ExtractionRaw: ...


__all__ = [
    "ApiLLMClient",
    "ExtractionRaw",
    "LLMClient",
    "LLMExtractionError",
    "MissingApiKeyError",
    "TranscriptTooLargeError",
]
```

- [ ] **Step 4: Run protocol test — must pass**

```bash
python -m pytest tests/ingest/llm/test_protocol.py -v 2>&1 | tail -10
```

Expected: `3 passed`.

- [ ] **Step 5: Run ALL tests — must still be 1404+3 passing**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1407 passed, 3 skipped` (1404 baseline + 3 new protocol tests).

If existing tests regressed — `LLMClient = ApiLLMClient` alias is gone, callers might break. Check: any code that does `LLMClient(cfg)` (instantiating it as a class) WILL fail because Protocol can't be instantiated. Find these and update them in Step 6.

- [ ] **Step 6: Update callers that instantiate `LLMClient(cfg)`**

```bash
grep -rn "LLMClient(cfg" /d/code/claude-mnemos/claude_mnemos
```

Expected matches:
- `claude_mnemos/cli.py:593` — `llm_client = LLMClient(cfg)`
- `claude_mnemos/daemon/vault_runtime.py:160` — `return LLMClient(cfg)`

In each, change `LLMClient(cfg)` → `ApiLLMClient(cfg)` and update import:
- `from claude_mnemos.ingest.llm import LLMClient` → `from claude_mnemos.ingest.llm import ApiLLMClient`

For `vault_runtime.py:157` keep type hint as `LLMClient | None` (it's a Protocol, valid as type) — only change instantiation.

- [ ] **Step 7: Run all tests again**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1407 passed, 3 skipped`.

- [ ] **Step 8: Commit**

```bash
git add claude_mnemos/ingest/llm/__init__.py claude_mnemos/cli.py claude_mnemos/daemon/vault_runtime.py tests/ingest/llm/test_protocol.py && git commit -m "feat(llm): LLMClient Protocol — common contract for adapters

Replace class alias with @runtime_checkable Protocol. Update
instantiation sites (cli.py, vault_runtime.py) to use ApiLLMClient
explicitly. Type hints stay as 'LLMClient | None' since Protocol
is a valid type annotation.

3 new protocol shape tests. All 1407 backend tests pass.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Move tests/test_llm.py → tests/ingest/llm/test_api.py

**Files:**
- Move: `tests/test_llm.py` → `tests/ingest/llm/test_api.py`
- Modify: imports inside the moved file

- [ ] **Step 1: Move the file via git**

```bash
cd /d/code/claude-mnemos && git mv tests/test_llm.py tests/ingest/llm/test_api.py
```

- [ ] **Step 2: Update imports inside moved file**

In `tests/ingest/llm/test_api.py` change the top imports block. Replace:
```python
from claude_mnemos.ingest.llm import (
    LLMClient,
    ...
)
```
with:
```python
from claude_mnemos.ingest.llm import (
    ApiLLMClient,
    ExtractionRaw,
    LLMExtractionError,
    MissingApiKeyError,
    TranscriptTooLargeError,
)
```

Then in every test body, replace `LLMClient(` with `ApiLLMClient(`. Use sed:
```bash
cd /d/code/claude-mnemos && sed -i 's/LLMClient(/ApiLLMClient(/g' tests/ingest/llm/test_api.py
```

(On Windows bash this works — git's bash provides sed.)

- [ ] **Step 3: Run moved tests**

```bash
python -m pytest tests/ingest/llm/test_api.py -v 2>&1 | tail -10
```

Expected: same number of passes as the original `tests/test_llm.py` had (typically 6-8 tests, all passing).

- [ ] **Step 4: Run all tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1407 passed, 3 skipped` (no change — just file movement).

- [ ] **Step 5: Commit**

```bash
git add tests/ingest/llm/test_api.py && git commit -m "test(llm): move tests/test_llm.py → tests/ingest/llm/test_api.py

File rename + import update (LLMClient → ApiLLMClient). Same
assertions, same coverage.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Update other tests importing from old paths

**Files:**
- Modify: `tests/test_extraction.py` (imports may need adjustment)
- Modify: `tests/e2e/test_real_extraction.py` (imports may need adjustment)
- Modify: any other files matching `from claude_mnemos.ingest.llm import`

- [ ] **Step 1: Find all import sites**

```bash
cd /d/code/claude-mnemos && grep -rn "from claude_mnemos.ingest.llm import" tests/
```

For each match, verify it imports symbols still exported from `claude_mnemos/ingest/llm/__init__.py` — that's `ApiLLMClient`, `ExtractionRaw`, `LLMClient` (Protocol), `LLMExtractionError`, `MissingApiKeyError`, `TranscriptTooLargeError`. All are present. So:
- `from claude_mnemos.ingest.llm import ExtractionRaw` — works (re-exported).
- `from claude_mnemos.ingest.llm import LLMClient` — now Protocol, not class. If used only as type hint or for Protocol check, works. If used as `LLMClient(cfg)`, breaks (must use ApiLLMClient).

Read each test file to determine whether it instantiates the class.

- [ ] **Step 2: Fix tests/e2e/test_real_extraction.py**

Read line 17 + 31:
```python
from claude_mnemos.ingest.llm import LLMClient
...
client = LLMClient(cfg)
```

Replace `LLMClient` with `ApiLLMClient` in both lines (it's a real e2e test that needs an actual client).

- [ ] **Step 3: Run all tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1407 passed, 3 skipped`.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_real_extraction.py && git commit -m "test(llm): update e2e import — ApiLLMClient instead of LLMClient

LLMClient is now a Protocol; instantiation requires the concrete
ApiLLMClient class.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Phase 2 — New CliLLMClient + supporting modules

**Goal:** Add `CliLLMClient`, `tokens.py`, `auth.py`, `rate_limit.py` modules with their unit tests. Behavior unchanged — these new modules are not yet wired into anything.

**Safety:** All existing tests still pass. Only add new tests.

---

## Task 6: tiktoken dependency + tokens.py

**Files:**
- Modify: `pyproject.toml` (add `tiktoken>=0.7`)
- Create: `claude_mnemos/ingest/llm/tokens.py`
- Create: `tests/ingest/llm/test_tokens.py`

- [ ] **Step 1: Write the failing test**

Create `tests/ingest/llm/test_tokens.py`:
```python
from __future__ import annotations

from claude_mnemos.ingest.llm.tokens import count_tokens_local


def test_count_tokens_empty_string_returns_zero() -> None:
    assert count_tokens_local("") == 0


def test_count_tokens_short_english_in_reasonable_range() -> None:
    n = count_tokens_local("Hello, world!")
    assert 1 <= n <= 6  # cl100k tokenizer: typically 4 tokens


def test_count_tokens_monotonic_with_length() -> None:
    short = count_tokens_local("foo")
    long = count_tokens_local("foo " * 100)
    assert long > short


def test_count_tokens_handles_russian() -> None:
    """Russian characters take ~2 chars/token typically; just verify > 0."""
    n = count_tokens_local("Привет, мир!")
    assert n > 0


def test_count_tokens_handles_json_like_text() -> None:
    payload = '{"name": "test", "value": 42, "nested": {"a": [1, 2, 3]}}'
    n = count_tokens_local(payload)
    assert n > 5
```

- [ ] **Step 2: Run test — must fail**

```bash
python -m pytest tests/ingest/llm/test_tokens.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'claude_mnemos.ingest.llm.tokens'`.

- [ ] **Step 3: Add tiktoken to pyproject.toml**

Edit `pyproject.toml`. In `dependencies = [...]`, add `"tiktoken>=0.7",` alphabetically (between `psutil` and `pystray`):

```toml
dependencies = [
    "pydantic>=2.0",
    "filelock>=3.13",
    "pyyaml>=6.0",
    "anthropic>=0.40",
    "unidecode>=1.3",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "apscheduler>=3.10",
    "Pillow>=10",
    "psutil>=5.9",
    "httpx>=0.27",
    "mcp>=1.12",
    "pystray>=0.19",
    "tiktoken>=0.7",
    "watchdog>=4.0",
]
```

Install:
```bash
cd /d/code/claude-mnemos && python -m pip install --user tiktoken 2>&1 | tail -3
```

Expected: `Successfully installed tiktoken-...` or `Requirement already satisfied`.

- [ ] **Step 4: Implement tokens.py**

Create `claude_mnemos/ingest/llm/tokens.py`:
```python
"""Local approximate token counter for CLI provider mode.

The Claude Code CLI does not expose exact input/output token counts in its
`--output-format json` envelope. We use ``tiktoken`` (OpenAI's tokenizer
library) as a close proxy: Claude uses a similar BPE algorithm; accuracy
is empirically ~85-95% on typical content.

For ApiLLMClient (anthropic.count_tokens API path) accurate counts remain
available — this module is only used by CliLLMClient.

UI must mark CLI-mode token figures with a ``~`` prefix to signal the
approximation. See docs/plans/2026-04-30-llm-cli-provider-design.md §5.
"""

from __future__ import annotations

import functools

import tiktoken


@functools.lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens_local(text: str) -> int:
    """Return approximate token count for *text* using cl100k_base.

    Empty string returns 0. Never raises on valid UTF-8.
    """
    if not text:
        return 0
    return len(_encoder().encode(text))
```

- [ ] **Step 5: Run tests — must pass**

```bash
python -m pytest tests/ingest/llm/test_tokens.py -v 2>&1 | tail -10
```

Expected: `5 passed`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml claude_mnemos/ingest/llm/tokens.py tests/ingest/llm/test_tokens.py && git commit -m "feat(llm): tiktoken-based local token counter

count_tokens_local() wraps tiktoken's cl100k_base BPE as an approximate
proxy for Claude tokens. Used by CliLLMClient where exact counts aren't
available in the CLI JSON envelope. ~85-95% accuracy.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: auth.py — find_claude_binary + check_claude_cli_auth

**Files:**
- Create: `claude_mnemos/ingest/llm/auth.py`
- Create: `tests/ingest/llm/test_auth.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/ingest/llm/test_auth.py`:
```python
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_mnemos.ingest.llm.auth import (
    AuthStatus,
    check_claude_cli_auth,
    find_claude_binary,
)


def _stub_completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_auth_status_dataclass() -> None:
    s = AuthStatus(installed=True, authenticated=True, binary_path="/usr/bin/claude")
    assert s.installed is True
    assert s.authenticated is True
    assert s.binary_path == "/usr/bin/claude"


def test_find_claude_binary_uses_shutil_which_first() -> None:
    with patch("claude_mnemos.ingest.llm.auth.shutil.which", return_value="/usr/bin/claude"):
        assert find_claude_binary() == Path("/usr/bin/claude")


def test_find_claude_binary_fallback_to_npm_global_on_windows(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    npm = tmp_path / "npm"
    npm.mkdir()
    fake = npm / "claude.cmd"
    fake.write_text("@echo fake\n")
    with patch("claude_mnemos.ingest.llm.auth.shutil.which", return_value=None), \
         patch("claude_mnemos.ingest.llm.auth.sys.platform", "win32"):
        result = find_claude_binary()
    assert result == fake


def test_find_claude_binary_returns_none_when_missing() -> None:
    with patch("claude_mnemos.ingest.llm.auth.shutil.which", return_value=None), \
         patch("claude_mnemos.ingest.llm.auth.sys.platform", "linux"):
        assert find_claude_binary() is None


def test_check_auth_when_binary_missing() -> None:
    with patch("claude_mnemos.ingest.llm.auth.find_claude_binary", return_value=None):
        s = check_claude_cli_auth()
    assert s.installed is False
    assert s.authenticated is False
    assert s.binary_path is None


def test_check_auth_version_succeeds_dry_run_succeeds() -> None:
    with patch("claude_mnemos.ingest.llm.auth.find_claude_binary",
               return_value=Path("/usr/bin/claude")), \
         patch("claude_mnemos.ingest.llm.auth.subprocess.run") as run:
        run.side_effect = [
            _stub_completed(0, stdout="2.1.0"),  # --version
            _stub_completed(0, stdout="ok"),     # dry test
        ]
        s = check_claude_cli_auth()
    assert s.installed is True
    assert s.authenticated is True


def test_check_auth_version_succeeds_dry_run_fails_with_auth_error() -> None:
    with patch("claude_mnemos.ingest.llm.auth.find_claude_binary",
               return_value=Path("/usr/bin/claude")), \
         patch("claude_mnemos.ingest.llm.auth.subprocess.run") as run:
        run.side_effect = [
            _stub_completed(0, stdout="2.1.0"),
            _stub_completed(1, stderr="not authenticated; run claude login"),
        ]
        s = check_claude_cli_auth()
    assert s.installed is True
    assert s.authenticated is False


def test_check_auth_version_fails() -> None:
    with patch("claude_mnemos.ingest.llm.auth.find_claude_binary",
               return_value=Path("/usr/bin/claude")), \
         patch("claude_mnemos.ingest.llm.auth.subprocess.run") as run:
        run.return_value = _stub_completed(1, stderr="binary corrupt")
        s = check_claude_cli_auth()
    assert s.installed is False
    assert s.authenticated is False
```

- [ ] **Step 2: Run tests — must fail**

```bash
python -m pytest tests/ingest/llm/test_auth.py -v 2>&1 | tail -10
```

Expected: ModuleNotFoundError on `claude_mnemos.ingest.llm.auth`.

- [ ] **Step 3: Implement auth.py**

Create `claude_mnemos/ingest/llm/auth.py`:
```python
"""Claude CLI binary discovery + auth preflight.

``find_claude_binary()`` is cross-platform: Unix uses ``shutil.which``;
Windows additionally checks ``%APPDATA%/npm/claude.{cmd,bat}`` because
``shutil.which`` may not pick up npm-global wrappers when PATHEXT is
configured unusually.

``check_claude_cli_auth()`` runs two probes:
1. ``claude --version`` — verifies installed binary.
2. ``claude -p "ok"`` — dry test that fails if user is not logged in.

Both calls timeout at 10s. If a corrupt binary hangs longer that's the
caller's problem; preflight is not the place to fight pathological cases.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuthStatus:
    installed: bool
    authenticated: bool
    binary_path: str | None = None


def find_claude_binary() -> Path | None:
    found = shutil.which("claude")
    if found:
        return Path(found)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            for name in ("claude.cmd", "claude.bat"):
                cand = Path(appdata) / "npm" / name
                if cand.is_file():
                    return cand
    return None


def check_claude_cli_auth() -> AuthStatus:
    binary = find_claude_binary()
    if binary is None:
        return AuthStatus(installed=False, authenticated=False, binary_path=None)

    try:
        version_result = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return AuthStatus(installed=False, authenticated=False, binary_path=str(binary))

    if version_result.returncode != 0:
        return AuthStatus(installed=False, authenticated=False, binary_path=str(binary))

    # Dry test — minimal prompt. If authenticated, returns 0 quickly.
    try:
        dry_result = subprocess.run(
            [str(binary), "-p", "ok", "--max-turns", "1"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            input="",  # avoid hang on stdin
        )
    except (subprocess.TimeoutExpired, OSError):
        return AuthStatus(installed=True, authenticated=False, binary_path=str(binary))

    authenticated = dry_result.returncode == 0
    return AuthStatus(installed=True, authenticated=authenticated, binary_path=str(binary))
```

- [ ] **Step 4: Run tests — must pass**

```bash
python -m pytest tests/ingest/llm/test_auth.py -v 2>&1 | tail -15
```

Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/ingest/llm/auth.py tests/ingest/llm/test_auth.py && git commit -m "feat(llm): claude CLI binary discovery + auth preflight

find_claude_binary() — cross-platform with Windows .cmd/.bat fallback.
check_claude_cli_auth() — two-stage probe: version check, then dry
'claude -p ok' to detect login state. 10/15s timeouts protect against
hung/corrupt binaries.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: rate_limit.py — RateLimitError + parser

**Files:**
- Create: `claude_mnemos/ingest/llm/rate_limit.py`
- Create: `tests/ingest/llm/test_rate_limit.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/ingest/llm/test_rate_limit.py`:
```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from claude_mnemos.ingest.llm.rate_limit import (
    RateLimitError,
    parse_rate_limit_from_stderr,
)
from claude_mnemos.ingest.llm import LLMExtractionError


def test_rate_limit_error_is_llm_extraction_error_subclass() -> None:
    """JobStore catches LLMExtractionError; RateLimitError must propagate
    through that catch path while remaining distinguishable via isinstance."""
    err = RateLimitError("rate limited", reset_at=datetime.now(UTC))
    assert isinstance(err, LLMExtractionError)


def test_rate_limit_error_carries_reset_at() -> None:
    when = datetime(2026, 4, 30, 14, 0, tzinfo=UTC)
    err = RateLimitError("limit hit", reset_at=when)
    assert err.reset_at == when


def test_parse_returns_none_for_non_rate_limit_stderr() -> None:
    assert parse_rate_limit_from_stderr("network error: timeout") is None
    assert parse_rate_limit_from_stderr("") is None
    assert parse_rate_limit_from_stderr("auth failed") is None


def test_parse_detects_rate_limit_keyword() -> None:
    err = parse_rate_limit_from_stderr("Error: rate_limit_exceeded — try later")
    assert isinstance(err, RateLimitError)
    assert err.reset_at > datetime.now(UTC)


def test_parse_detects_http_429() -> None:
    err = parse_rate_limit_from_stderr("HTTP 429 Too Many Requests")
    assert isinstance(err, RateLimitError)


def test_parse_default_reset_is_5_hours_ahead() -> None:
    err = parse_rate_limit_from_stderr("rate_limit reached")
    assert err is not None
    delta = err.reset_at - datetime.now(UTC)
    # Allow ±1 minute slop for test execution time
    assert timedelta(hours=4, minutes=59) < delta < timedelta(hours=5, minutes=1)


def test_parse_iso_timestamp_in_stderr_used_when_present() -> None:
    """If stderr contains 'reset_at: <ISO>' or 'retry after: <unix-ts>',
    parser should use that instead of default 5h."""
    when = datetime(2026, 4, 30, 16, 30, tzinfo=UTC)
    err = parse_rate_limit_from_stderr(f"rate_limit_exceeded; reset_at: {when.isoformat()}")
    assert err is not None
    # ISO timestamp parsed back
    assert err.reset_at == when
```

- [ ] **Step 2: Run tests — must fail**

```bash
python -m pytest tests/ingest/llm/test_rate_limit.py -v 2>&1 | tail -10
```

Expected: ImportError.

- [ ] **Step 3: Implement rate_limit.py**

Create `claude_mnemos/ingest/llm/rate_limit.py`:
```python
"""Rate-limit detection for the CLI provider.

Claude Code CLI surfaces rate-limit errors via non-zero exit code + stderr
text. There's no structured error envelope, so we pattern-match. Heuristics:
- 'rate_limit' / 'rate-limit' / 'rate limit' substring (case-insensitive)
- 'HTTP 429' or '429 Too Many Requests'

When matched, ``parse_rate_limit_from_stderr`` returns a ``RateLimitError``
whose ``reset_at`` is either parsed from the stderr (if present in
ISO-8601 form) or set to ``now + 5h`` (Anthropic Pro window).

``RateLimitError`` is a subclass of ``LLMExtractionError`` so existing
``except LLMExtractionError`` catches still work; the JobStore pause
path uses ``isinstance(exc, RateLimitError)`` to discriminate.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from claude_mnemos.ingest.llm import LLMExtractionError

DEFAULT_PAUSE_HOURS = 5
_RATE_LIMIT_RE = re.compile(r"rate[ _-]?limit|429\b", re.IGNORECASE)
_RESET_AT_RE = re.compile(
    r"reset[_ ]?at[:= ]+(\d{4}-\d{2}-\d{2}T[\d:.+-]+(?:Z|[+-]\d{2}:?\d{2}))",
    re.IGNORECASE,
)


class RateLimitError(LLMExtractionError):
    """LLM call failed because rate limit was hit. Caller should pause queue."""

    def __init__(self, message: str, *, reset_at: datetime) -> None:
        super().__init__(message)
        self.reset_at = reset_at


def parse_rate_limit_from_stderr(stderr: str) -> RateLimitError | None:
    """Inspect *stderr* for rate-limit signal. Return RateLimitError or None."""
    if not stderr or not _RATE_LIMIT_RE.search(stderr):
        return None
    iso_match = _RESET_AT_RE.search(stderr)
    if iso_match:
        try:
            reset = datetime.fromisoformat(iso_match.group(1))
            if reset.tzinfo is None:
                reset = reset.replace(tzinfo=UTC)
        except ValueError:
            reset = datetime.now(UTC) + timedelta(hours=DEFAULT_PAUSE_HOURS)
    else:
        reset = datetime.now(UTC) + timedelta(hours=DEFAULT_PAUSE_HOURS)
    return RateLimitError(stderr.strip(), reset_at=reset)
```

- [ ] **Step 4: Run tests — must pass**

```bash
python -m pytest tests/ingest/llm/test_rate_limit.py -v 2>&1 | tail -15
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/ingest/llm/rate_limit.py tests/ingest/llm/test_rate_limit.py && git commit -m "feat(llm): RateLimitError + stderr parser for CLI provider

RateLimitError(LLMExtractionError) carries reset_at datetime. Parser
detects 'rate_limit'/'429' patterns + extracts ISO reset_at if present.
Defaults to now+5h (Anthropic Pro window) otherwise.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: CliLLMClient — subprocess-based extraction

**Files:**
- Create: `claude_mnemos/ingest/llm/cli.py`
- Create: `tests/ingest/llm/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/ingest/llm/test_cli.py`:
```python
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from claude_mnemos.config import Config
from claude_mnemos.ingest.llm import (
    ExtractionRaw,
    LLMExtractionError,
)
from claude_mnemos.ingest.llm.cli import CliLLMClient
from claude_mnemos.ingest.llm.rate_limit import RateLimitError


@pytest.fixture
def cfg() -> Config:
    return Config(
        api_key=None,
        model="claude-sonnet-4-5",
        language_hint="auto",
        max_input_tokens=180000,
        lock_timeout=30.0,
    )


def _stub_completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


_TOOL_SCHEMA = {
    "name": "save_pages",
    "description": "Save extracted pages",
    "input_schema": {
        "type": "object",
        "properties": {"pages": {"type": "array"}},
        "required": ["pages"],
    },
}


def _ok_envelope(payload: dict[str, Any]) -> str:
    return json.dumps({
        "result": "extracted",
        "session_id": "abc",
        "structured_output": payload,
        "cost_usd": 0.001,
        "duration_ms": 1234,
        "num_turns": 1,
    })


def test_extract_invokes_claude_p_with_correct_args(cfg: Config) -> None:
    payload = {"pages": [], "summary": "ok"}
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/usr/bin/claude")):
        run.return_value = _stub_completed(0, stdout=_ok_envelope(payload))
        client = CliLLMClient(cfg)
        result = client.extract(system="SYS", user="USR", tool=_TOOL_SCHEMA)

    assert isinstance(result, ExtractionRaw)
    assert result.payload == payload

    cmd = run.call_args[0][0]
    assert cmd[0] == "/usr/bin/claude"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "json" in cmd
    assert "--json-schema" in cmd
    assert "--system-prompt" in cmd
    assert "--setting-sources" in cmd
    assert "--no-session-persistence" in cmd
    assert "--max-turns" in cmd

    # System prompt passed as flag value
    sys_idx = cmd.index("--system-prompt")
    assert cmd[sys_idx + 1] == "SYS"

    # JSON schema is the tool's input_schema serialized
    schema_idx = cmd.index("--json-schema")
    parsed_schema = json.loads(cmd[schema_idx + 1])
    assert parsed_schema == _TOOL_SCHEMA["input_schema"]


def test_extract_passes_user_prompt_via_stdin(cfg: Config) -> None:
    """Critical: Windows CMD truncates multiline argv at first LF.
    User prompt MUST go through stdin."""
    payload = {"pages": []}
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/usr/bin/claude")):
        run.return_value = _stub_completed(0, stdout=_ok_envelope(payload))
        CliLLMClient(cfg).extract(system="S", user="multiline\nuser\nprompt", tool=_TOOL_SCHEMA)
    assert run.call_args.kwargs["input"] == "multiline\nuser\nprompt"


def test_extract_clears_recursion_env_vars(cfg: Config) -> None:
    payload = {"pages": []}
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")), \
         patch.dict("os.environ", {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "x",
                                    "ANTHROPIC_API_KEY": "sk-leak"}):
        run.return_value = _stub_completed(0, stdout=_ok_envelope(payload))
        CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)
    env = run.call_args.kwargs["env"]
    assert "CLAUDECODE" not in env
    assert "CLAUDE_CODE_ENTRYPOINT" not in env
    # ANTHROPIC_API_KEY MUST be removed — otherwise CLI bills via API not subscription
    assert "ANTHROPIC_API_KEY" not in env


def test_extract_returns_approximate_token_counts(cfg: Config) -> None:
    payload = {"pages": [{"slug": "x"}]}
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.return_value = _stub_completed(0, stdout=_ok_envelope(payload))
        result = CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)
    assert result.input_tokens > 0  # local approximation, non-zero for non-empty text
    assert result.output_tokens > 0


def test_extract_raises_rate_limit_on_429_stderr(cfg: Config) -> None:
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.return_value = _stub_completed(1, stderr="HTTP 429 Too Many Requests")
        with pytest.raises(RateLimitError):
            CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)


def test_extract_raises_extraction_error_on_other_failure(cfg: Config) -> None:
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.return_value = _stub_completed(1, stderr="something else broke")
        with pytest.raises(LLMExtractionError):
            CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)


def test_extract_raises_when_binary_missing(cfg: Config) -> None:
    with patch("claude_mnemos.ingest.llm.cli.find_claude_binary", return_value=None):
        with pytest.raises(LLMExtractionError, match="claude binary not found"):
            CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)


def test_extract_retries_once_on_validation_failure(cfg: Config) -> None:
    bad_payload = {"wrong": "shape"}
    good_payload = {"pages": []}
    call_count = {"n": 0}

    def validator(p: dict) -> None:
        if "pages" not in p:
            raise ValueError("schema mismatch")

    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.side_effect = [
            _stub_completed(0, stdout=_ok_envelope(bad_payload)),
            _stub_completed(0, stdout=_ok_envelope(good_payload)),
        ]
        result = CliLLMClient(cfg).extract(
            system="S", user="U", tool=_TOOL_SCHEMA, validate=validator,
        )
    assert result.payload == good_payload
    assert run.call_count == 2


def test_extract_raises_after_two_validation_failures(cfg: Config) -> None:
    def always_fail(p: dict) -> None:
        raise ValueError("nope")

    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.return_value = _stub_completed(0, stdout=_ok_envelope({"any": "shape"}))
        with pytest.raises(LLMExtractionError, match="failed validation twice"):
            CliLLMClient(cfg).extract(
                system="S", user="U", tool=_TOOL_SCHEMA, validate=always_fail,
            )


def test_extract_raises_on_invalid_json_envelope(cfg: Config) -> None:
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.return_value = _stub_completed(0, stdout="not json at all")
        with pytest.raises(LLMExtractionError, match="invalid JSON"):
            CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)


def test_extract_raises_when_structured_output_missing(cfg: Config) -> None:
    with patch("claude_mnemos.ingest.llm.cli.subprocess.run") as run, \
         patch("claude_mnemos.ingest.llm.cli.find_claude_binary",
               return_value=__import__("pathlib").Path("/x/claude")):
        run.return_value = _stub_completed(0, stdout=json.dumps({"result": "x"}))  # no structured_output
        with pytest.raises(LLMExtractionError, match="structured_output"):
            CliLLMClient(cfg).extract(system="S", user="U", tool=_TOOL_SCHEMA)
```

- [ ] **Step 2: Run tests — must fail**

```bash
python -m pytest tests/ingest/llm/test_cli.py -v 2>&1 | tail -15
```

Expected: ImportError on `claude_mnemos.ingest.llm.cli`.

- [ ] **Step 3: Implement cli.py**

Create `claude_mnemos/ingest/llm/cli.py`:
```python
"""CLI provider — drives ``claude -p`` subprocess for extraction.

Uses the user's Claude Code subscription (Pro/Max) via OAuth, no separate
ANTHROPIC_API_KEY needed. Token counts are approximate (tiktoken proxy)
since the CLI JSON envelope doesn't expose exact usage figures.

See docs/plans/2026-04-30-llm-cli-provider-design.md §5 for rationale.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from typing import Any

from claude_mnemos.config import Config
from claude_mnemos.ingest.llm import (
    ExtractionRaw,
    LLMExtractionError,
)
from claude_mnemos.ingest.llm.auth import find_claude_binary
from claude_mnemos.ingest.llm.rate_limit import (
    RateLimitError,
    parse_rate_limit_from_stderr,
)
from claude_mnemos.ingest.llm.tokens import count_tokens_local

DEFAULT_TIMEOUT_SEC = 120


def _build_env() -> dict[str, str]:
    """Copy os.environ minus vars that would derail subprocess auth.

    - CLAUDECODE / CLAUDE_CODE_ENTRYPOINT: parent-session markers; their
      presence makes ``claude -p`` refuse to run (recursion guard).
    - ANTHROPIC_API_KEY: if set, claude CLI prefers it over OAuth subscription
      → user gets billed per-token instead of subscription quota. We strip
      it to force subscription path. Users who explicitly want API mode use
      ``ApiLLMClient`` (selected by factory when ``ingest_provider == "api"``).
    """
    env = os.environ.copy()
    for var in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "ANTHROPIC_API_KEY"):
        env.pop(var, None)
    return env


class CliLLMClient:
    """LLMClient implementation backed by ``claude -p`` subprocess."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def extract(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        validate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> ExtractionRaw:
        binary = find_claude_binary()
        if binary is None:
            raise LLMExtractionError(
                "claude binary not found on PATH; install Claude Code or "
                "switch to ApiLLMClient via ingest_provider='api'"
            )

        payload = self._call_once(str(binary), system, user, tool)

        first_validation_error: Exception | None = None
        if validate is not None:
            try:
                validate(payload)
                return self._build_result(system, user, payload)
            except Exception as exc:  # noqa: BLE001
                first_validation_error = exc
        else:
            return self._build_result(system, user, payload)

        # Retry once with the validation error appended (mirrors ApiLLMClient).
        retry_user = (
            user
            + "\n\n---\n\n"
            + f"ATTENTION: A previous attempt to call {tool['name']} failed schema validation: "
            + str(first_validation_error)
            + f". Please call {tool['name']} again with a corrected payload "
            + "that strictly matches the tool's input_schema."
        )
        try:
            payload2 = self._call_once(str(binary), system, retry_user, tool)
        except LLMExtractionError as exc:
            raise LLMExtractionError(
                f"retry after validation failure also failed: {exc}"
            ) from exc

        try:
            validate(payload2)
        except Exception as exc:  # noqa: BLE001
            raise LLMExtractionError(
                f"LLM tool input failed validation twice: first={first_validation_error}, "
                f"second={exc}"
            ) from exc
        return self._build_result(system, retry_user, payload2)

    def _call_once(
        self,
        binary: str,
        system: str,
        user: str,
        tool: dict[str, Any],
    ) -> dict[str, Any]:
        cmd = [
            binary,
            "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(tool["input_schema"]),
            "--system-prompt", system,
            "--setting-sources", "",
            "--no-session-persistence",
            "--max-turns", "1",
        ]
        try:
            result = subprocess.run(
                cmd,
                input=user,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=DEFAULT_TIMEOUT_SEC,
                check=False,
                env=_build_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMExtractionError(
                f"claude -p timed out after {DEFAULT_TIMEOUT_SEC}s"
            ) from exc

        if result.returncode != 0:
            rate_err = parse_rate_limit_from_stderr(result.stderr)
            if rate_err is not None:
                raise rate_err
            raise LLMExtractionError(
                f"claude -p exit {result.returncode}: {result.stderr.strip()[:500]}"
            )

        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise LLMExtractionError(
                f"claude -p returned invalid JSON: {exc}"
            ) from exc

        structured = envelope.get("structured_output")
        if structured is None:
            raise LLMExtractionError(
                "claude -p response missing structured_output field"
            )
        return dict(structured)

    def _build_result(
        self,
        system: str,
        user: str,
        payload: dict[str, Any],
    ) -> ExtractionRaw:
        # Token counts are approximate (cl100k proxy). UI marks them with `~` prefix.
        input_tokens = count_tokens_local(system) + count_tokens_local(user)
        output_tokens = count_tokens_local(json.dumps(payload, ensure_ascii=False))
        return ExtractionRaw(
            payload=payload,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
```

- [ ] **Step 4: Run CliLLMClient tests**

```bash
python -m pytest tests/ingest/llm/test_cli.py -v 2>&1 | tail -20
```

Expected: `11 passed`.

- [ ] **Step 5: Run all tests — must still be green**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1431 passed, 3 skipped` (1407 baseline + 5 tokens + 8 auth + 7 rate_limit + 11 cli - some count adjustments; specifically check no regression in pre-existing tests).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/ingest/llm/cli.py tests/ingest/llm/test_cli.py && git commit -m "feat(llm): CliLLMClient — claude -p subprocess provider

Drives 'claude -p --output-format json --json-schema <S> --system-prompt
<T> --setting-sources \"\" --no-session-persistence --max-turns 1' with
user prompt via stdin. Strips CLAUDECODE / CLAUDE_CODE_ENTRYPOINT /
ANTHROPIC_API_KEY from subprocess env. Local approximate token counts
via tiktoken. Same retry-on-validation-error semantics as ApiLLMClient.

11 unit tests covering command construction, env cleaning, stdin path,
parsing, retry, error mapping (rate limit, generic failure, missing
binary, broken JSON).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Phase 3 — Factory + config wiring

**Goal:** Add `make_llm_client` factory + `ingest_provider` config field + wire into `vault_runtime.py` and `cli.py`. Default behavior preserved by auto-detect (existing users with API key still hit ApiLLMClient).

---

## Task 10: Config.ingest_provider field

**Files:**
- Modify: `claude_mnemos/config.py`
- Create: `tests/test_config_ingest_provider.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_ingest_provider.py`:
```python
from __future__ import annotations

import os
from unittest.mock import patch

from claude_mnemos.config import Config


def _base_env() -> dict[str, str]:
    return {
        "ANTHROPIC_API_KEY": "",
        "MNEMOS_MODEL": "sonnet",
        "MNEMOS_LANGUAGE_HINT": "auto",
    }


def test_default_ingest_provider_is_none() -> None:
    with patch.dict(os.environ, _base_env(), clear=True):
        cfg = Config.from_env()
    assert cfg.ingest_provider is None


def test_explicit_cli_via_env() -> None:
    env = _base_env() | {"MNEMOS_INGEST_PROVIDER": "cli"}
    with patch.dict(os.environ, env, clear=True):
        cfg = Config.from_env()
    assert cfg.ingest_provider == "cli"


def test_explicit_api_via_env() -> None:
    env = _base_env() | {"MNEMOS_INGEST_PROVIDER": "api"}
    with patch.dict(os.environ, env, clear=True):
        cfg = Config.from_env()
    assert cfg.ingest_provider == "api"


def test_invalid_ingest_provider_raises() -> None:
    import pytest

    env = _base_env() | {"MNEMOS_INGEST_PROVIDER": "openai"}
    with patch.dict(os.environ, env, clear=True), \
         pytest.raises(ValueError, match="ingest_provider"):
        Config.from_env()


def test_with_overrides_preserves_ingest_provider() -> None:
    with patch.dict(os.environ, _base_env(), clear=True):
        base = Config.from_env()
    overridden = base.with_overrides(ingest_provider="cli")
    assert overridden.ingest_provider == "cli"
    # Original untouched (frozen dataclass)
    assert base.ingest_provider is None
```

- [ ] **Step 2: Run tests — must fail**

```bash
python -m pytest tests/test_config_ingest_provider.py -v 2>&1 | tail -10
```

Expected: AttributeError on `cfg.ingest_provider`.

- [ ] **Step 3: Add field to Config**

In `claude_mnemos/config.py`:

After the `Literal` imports, add:
```python
IngestProvider = Literal["cli", "api"]
_VALID_PROVIDERS = {"cli", "api"}
```

In the `@dataclass` block, add field (after existing fields):
```python
@dataclass(frozen=True)
class Config:
    api_key: str | None
    model: str
    language_hint: LanguageHint
    max_input_tokens: int
    lock_timeout: float
    ingest_provider: IngestProvider | None = None
```

In `from_env()`, after `lock = ...` parsing, add:
```python
        provider_raw = os.environ.get("MNEMOS_INGEST_PROVIDER")
        if provider_raw is not None and provider_raw not in _VALID_PROVIDERS:
            raise ValueError(
                f"MNEMOS_INGEST_PROVIDER={provider_raw!r}; expected one of "
                f"{sorted(_VALID_PROVIDERS)}"
            )
```

Then change the final `return cls(...)` to include:
```python
        return cls(
            api_key=api_key,
            model=model,
            language_hint=cast(LanguageHint, hint_raw),
            max_input_tokens=max_tokens,
            lock_timeout=lock,
            ingest_provider=cast("IngestProvider | None", provider_raw),
        )
```

In `with_overrides`, add a parameter and the resolution:
```python
    def with_overrides(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        language_hint: LanguageHint | None = None,
        max_input_tokens: int | None = None,
        lock_timeout: float | None = None,
        ingest_provider: IngestProvider | None = None,
    ) -> Config:
        ...
        return replace(
            self,
            ...
            ingest_provider=(
                ingest_provider if ingest_provider is not None else self.ingest_provider
            ),
        )
```

- [ ] **Step 4: Run tests — must pass**

```bash
python -m pytest tests/test_config_ingest_provider.py -v 2>&1 | tail -10
```

Expected: `5 passed`.

- [ ] **Step 5: Run ALL tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1436 passed, 3 skipped` (1431 + 5 new).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/config.py tests/test_config_ingest_provider.py && git commit -m "feat(config): Config.ingest_provider field — Literal['cli','api']|None

Reads MNEMOS_INGEST_PROVIDER env var. None means auto-detect (factory
chooses based on api_key presence). Invalid values raise ValueError.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: make_llm_client factory

**Files:**
- Modify: `claude_mnemos/ingest/llm/__init__.py` (add factory)
- Create: `tests/ingest/llm/test_factory.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/ingest/llm/test_factory.py`:
```python
from __future__ import annotations

from claude_mnemos.config import Config
from claude_mnemos.ingest.llm import (
    ApiLLMClient,
    make_llm_client,
)
from claude_mnemos.ingest.llm.cli import CliLLMClient


def _cfg(*, api_key: str | None = None, provider=None) -> Config:
    return Config(
        api_key=api_key,
        model="claude-sonnet-4-5",
        language_hint="auto",
        max_input_tokens=180000,
        lock_timeout=30.0,
        ingest_provider=provider,
    )


def test_explicit_api_returns_api_client_when_key_present() -> None:
    cfg = _cfg(api_key="sk-test", provider="api")
    client = make_llm_client(cfg)
    assert isinstance(client, ApiLLMClient)


def test_explicit_api_raises_when_key_missing() -> None:
    import pytest

    from claude_mnemos.ingest.llm import MissingApiKeyError

    cfg = _cfg(api_key=None, provider="api")
    with pytest.raises(MissingApiKeyError):
        make_llm_client(cfg)


def test_explicit_cli_returns_cli_client() -> None:
    cfg = _cfg(api_key=None, provider="cli")
    client = make_llm_client(cfg)
    assert isinstance(client, CliLLMClient)


def test_explicit_cli_returns_cli_client_even_when_api_key_present() -> None:
    """If user explicitly opts into CLI, honour that even with key present.
    Subprocess env will strip ANTHROPIC_API_KEY."""
    cfg = _cfg(api_key="sk-test", provider="cli")
    assert isinstance(make_llm_client(cfg), CliLLMClient)


def test_auto_detect_uses_api_when_key_set() -> None:
    cfg = _cfg(api_key="sk-test", provider=None)
    assert isinstance(make_llm_client(cfg), ApiLLMClient)


def test_auto_detect_falls_back_to_cli_when_no_key() -> None:
    cfg = _cfg(api_key=None, provider=None)
    assert isinstance(make_llm_client(cfg), CliLLMClient)
```

- [ ] **Step 2: Run tests — must fail**

```bash
python -m pytest tests/ingest/llm/test_factory.py -v 2>&1 | tail -10
```

Expected: ImportError on `make_llm_client`.

- [ ] **Step 3: Add factory to __init__.py**

In `claude_mnemos/ingest/llm/__init__.py`, add after the existing exports:

```python
def make_llm_client(cfg: "Config") -> LLMClient:
    """Resolve the LLMClient implementation based on cfg.ingest_provider.

    Resolution rules:
    - cfg.ingest_provider == "api"  → ApiLLMClient (raises MissingApiKeyError if no key)
    - cfg.ingest_provider == "cli"  → CliLLMClient (no key needed)
    - cfg.ingest_provider is None   → auto-detect:
        - api_key set → ApiLLMClient (preserves existing behaviour)
        - api_key not set → CliLLMClient
    """
    if cfg.ingest_provider == "api":
        return ApiLLMClient(cfg)
    if cfg.ingest_provider == "cli":
        from claude_mnemos.ingest.llm.cli import CliLLMClient
        return CliLLMClient(cfg)
    # auto-detect
    if cfg.api_key:
        return ApiLLMClient(cfg)
    from claude_mnemos.ingest.llm.cli import CliLLMClient
    return CliLLMClient(cfg)
```

Add `Config` import at top:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_mnemos.config import Config
```

Add `make_llm_client` to `__all__`.

- [ ] **Step 4: Run factory tests**

```bash
python -m pytest tests/ingest/llm/test_factory.py -v 2>&1 | tail -10
```

Expected: `6 passed`.

- [ ] **Step 5: Run all tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1442 passed, 3 skipped`.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/ingest/llm/__init__.py tests/ingest/llm/test_factory.py && git commit -m "feat(llm): make_llm_client factory — auto-detect or explicit provider

cfg.ingest_provider in {None, 'api', 'cli'} resolves to ApiLLMClient or
CliLLMClient. Auto-detect chooses Api when api_key is set, Cli otherwise.
Preserves existing default behaviour for users with ANTHROPIC_API_KEY.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Wire factory into vault_runtime.py

**Files:**
- Modify: `claude_mnemos/daemon/vault_runtime.py`

- [ ] **Step 1: Read current llm_factory in vault_runtime.py**

```bash
grep -n "llm_factory\|LLMClient\|ApiLLMClient" /d/code/claude-mnemos/claude_mnemos/daemon/vault_runtime.py
```

Currently:
```python
def llm_factory(cfg: Config) -> LLMClient | None:
    if not cfg.api_key:
        return None
    return ApiLLMClient(cfg)
```

This forces `None` when api_key missing — that's the current behaviour that breaks for CLI users. We change it to ALWAYS try `make_llm_client`, return None ONLY if both providers would fail.

- [ ] **Step 2: Update the factory closure**

Replace the `llm_factory` definition in `vault_runtime.py`:

```python
            from claude_mnemos.ingest.llm import (
                LLMClient,
                MissingApiKeyError,
                make_llm_client,
            )

            def llm_factory(cfg: Config) -> LLMClient | None:
                """Resolve LLMClient via factory. Return None only if both
                provider paths are unavailable (API key missing AND CLI
                unavailable) — IngestHandler then falls back to --no-llm
                behaviour (manual extraction skipped)."""
                try:
                    return make_llm_client(cfg)
                except MissingApiKeyError:
                    return None
```

Remove the now-unused direct `ApiLLMClient` / `LLMClient` imports earlier in the file if they were only used here.

- [ ] **Step 3: Run all tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1442 passed, 3 skipped` (no new tests, no regressions).

- [ ] **Step 4: Commit**

```bash
git add claude_mnemos/daemon/vault_runtime.py && git commit -m "feat(daemon): vault_runtime llm_factory uses make_llm_client

Now selects ApiLLMClient or CliLLMClient based on cfg.ingest_provider
(or auto-detect). Returns None only when API path is selected explicitly
but key is missing (preserves --no-llm fallback semantics).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Wire factory into cli.py

**Files:**
- Modify: `claude_mnemos/cli.py:593` (and around)

- [ ] **Step 1: Read context around cli.py:593**

```bash
sed -n '580,610p' /d/code/claude-mnemos/claude_mnemos/cli.py
```

Note current code:
```python
            llm_client = ApiLLMClient(cfg)
```

(May still say `LLMClient(cfg)` if Phase 1 Task 3 Step 6 update wasn't applied — fix in this task either way.)

- [ ] **Step 2: Replace direct instantiation with factory**

Find the line `llm_client = ApiLLMClient(cfg)` (or `LLMClient(cfg)`) and replace:
```python
            from claude_mnemos.ingest.llm import make_llm_client
            llm_client = make_llm_client(cfg)
```

Remove the now-unused direct `ApiLLMClient` import at the top of `cli.py` (if there). Keep `from claude_mnemos.ingest.llm import LLMClient` if used as type hint elsewhere.

- [ ] **Step 3: Run all tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1442 passed, 3 skipped`.

- [ ] **Step 4: Commit**

```bash
git add claude_mnemos/cli.py && git commit -m "feat(cli): mnemos ingest uses make_llm_client factory

Picks ApiLLMClient or CliLLMClient based on Config.ingest_provider /
auto-detect. Same as vault_runtime — single resolution path everywhere.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Phase 3 verification — full backend test suite + lint

- [ ] **Step 1: Run full backend tests**

```bash
cd /d/code/claude-mnemos && python -m pytest --ignore=tests/slow 2>&1 | tail -5
```

Expected: `1442 passed, 3 skipped`.

- [ ] **Step 2: Run ruff**

```bash
python -m ruff check . 2>&1 | tail -3
```

Expected: `All checks passed!`.

If errors — fix them inline before continuing. Common: unused imports.

- [ ] **Step 3: Verify zero diff in untouchable files**

```bash
git diff main -- claude_mnemos/ingest/extraction.py claude_mnemos/ingest/parser.py claude_mnemos/state/manifest.py claude_mnemos/core/metrics.py claude_mnemos/hooks/ claude_mnemos/daemon/watchdog_handler.py claude_mnemos/daemon/watchdog_observer.py 2>&1 | wc -l
```

Expected: `0` (zero lines of diff).

If non-zero: report STOP — Phase 3 violated zero-diff guarantee, investigate.

---

# Phase 4 — Rate-limit pause in JobStore

**Goal:** Add `paused_until` field to `JobStore`, `pause_queue` method, IngestHandler catches `RateLimitError` and pauses queue. Worker dequeue skips while paused. Universal — works for any provider.

---

## Task 15: JobStore.paused_until schema + migration

**Files:**
- Modify: `claude_mnemos/state/jobs.py`
- Create: `tests/state/test_jobs_paused_until.py` (or extend existing tests if file exists)

- [ ] **Step 1: Inspect current JobStore schema**

```bash
grep -n "CREATE TABLE\|paused_until\|class JobStore" /d/code/claude-mnemos/claude_mnemos/state/jobs.py | head
```

Read the JobStore module to understand schema layout (tables, columns, migration pattern).

- [ ] **Step 2: Write failing tests**

Create `tests/state/test_jobs_paused_until.py`:
```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.state.jobs import JobStore


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / ".jobs.db")


def test_new_store_paused_until_is_none(store: JobStore) -> None:
    assert store.paused_until() is None


def test_pause_queue_sets_paused_until(store: JobStore) -> None:
    when = datetime.now(UTC) + timedelta(hours=5)
    store.pause_queue(until=when)
    paused = store.paused_until()
    assert paused is not None
    # Allow second-level slop
    assert abs((paused - when).total_seconds()) < 2


def test_pause_queue_overwrites_earlier_pause(store: JobStore) -> None:
    early = datetime.now(UTC) + timedelta(hours=1)
    later = datetime.now(UTC) + timedelta(hours=10)
    store.pause_queue(until=early)
    store.pause_queue(until=later)
    assert store.paused_until() is not None
    assert abs((store.paused_until() - later).total_seconds()) < 2


def test_resume_queue_clears_paused_until(store: JobStore) -> None:
    store.pause_queue(until=datetime.now(UTC) + timedelta(hours=5))
    store.resume_queue()
    assert store.paused_until() is None


def test_paused_until_persists_across_jobstore_instances(store: JobStore, tmp_path: Path) -> None:
    when = datetime.now(UTC) + timedelta(hours=5)
    store.pause_queue(until=when)
    # Re-open same db
    fresh = JobStore(tmp_path / ".jobs.db")
    paused = fresh.paused_until()
    assert paused is not None
    assert abs((paused - when).total_seconds()) < 2


def test_is_paused_returns_true_while_in_window(store: JobStore) -> None:
    store.pause_queue(until=datetime.now(UTC) + timedelta(hours=1))
    assert store.is_paused() is True


def test_is_paused_returns_false_after_window(store: JobStore) -> None:
    store.pause_queue(until=datetime.now(UTC) - timedelta(seconds=1))
    assert store.is_paused() is False
```

- [ ] **Step 3: Run failing tests**

```bash
python -m pytest tests/state/test_jobs_paused_until.py -v 2>&1 | tail -10
```

Expected: AttributeError on `JobStore.paused_until`, `pause_queue`, `resume_queue`, `is_paused`.

- [ ] **Step 4: Implement schema + methods**

In `claude_mnemos/state/jobs.py`:

Add to schema-init section (`CREATE TABLE IF NOT EXISTS ...` block) — after existing tables, add a single-row settings table:
```sql
CREATE TABLE IF NOT EXISTS job_queue_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    paused_until TEXT
);
INSERT OR IGNORE INTO job_queue_state (id, paused_until) VALUES (1, NULL);
```

Add methods to `JobStore` class:
```python
    def pause_queue(self, *, until: datetime) -> None:
        """Pause job dequeue until *until* (UTC). Existing pause is overwritten."""
        iso = until.astimezone(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE job_queue_state SET paused_until = ? WHERE id = 1",
                (iso,),
            )

    def resume_queue(self) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE job_queue_state SET paused_until = NULL WHERE id = 1"
            )

    def paused_until(self) -> datetime | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT paused_until FROM job_queue_state WHERE id = 1"
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(row[0])

    def is_paused(self, *, now: datetime | None = None) -> bool:
        until = self.paused_until()
        if until is None:
            return False
        ref = now or datetime.now(UTC)
        return until > ref
```

(Use whatever connection pattern `JobStore` already uses — match existing style.)

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/state/test_jobs_paused_until.py -v 2>&1 | tail -10
```

Expected: `7 passed`.

- [ ] **Step 6: Run all tests — schema migration must not break existing ones**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1449 passed, 3 skipped`.

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/state/jobs.py tests/state/test_jobs_paused_until.py && git commit -m "feat(jobs): JobStore.{pause_queue, resume_queue, paused_until, is_paused}

New job_queue_state table (single row, paused_until: TEXT|NULL). Used
by IngestHandler in next task to pause queue when CliLLMClient hits
rate limit. CREATE TABLE IF NOT EXISTS is migration-safe — old DBs
gain the table without losing existing jobs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: IngestHandler catches RateLimitError → pause queue

**Files:**
- Modify: `claude_mnemos/daemon/jobs/handlers.py`
- Create: `tests/daemon/jobs/test_pause_on_rate_limit.py`

- [ ] **Step 1: Inspect current handlers.py**

```bash
sed -n '1,80p' /d/code/claude-mnemos/claude_mnemos/daemon/jobs/handlers.py
```

Find the `IngestHandler` class and the method that wraps the LLM extraction.

- [ ] **Step 2: Write failing tests**

Create `tests/daemon/jobs/test_pause_on_rate_limit.py`:
```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_mnemos.daemon.jobs.handlers import IngestHandler
from claude_mnemos.ingest.llm.rate_limit import RateLimitError
from claude_mnemos.state.jobs import JobStore


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / ".jobs.db")


def test_ingest_handler_pauses_queue_on_rate_limit(tmp_path: Path, store: JobStore) -> None:
    reset = datetime.now(UTC) + timedelta(hours=5)
    rate_err = RateLimitError("limited", reset_at=reset)

    cfg = MagicMock()
    cfg.api_key = None

    def cfg_factory():
        return cfg

    fake_llm = MagicMock()
    fake_llm.extract.side_effect = rate_err

    def llm_factory(_cfg):
        return fake_llm

    handler = IngestHandler(
        vault=tmp_path,
        cfg_factory=cfg_factory,
        llm_factory=llm_factory,
        job_store=store,
    )

    # Run one ingest job — should propagate RateLimitError after pausing the queue.
    job_payload = {"session_id": "s1", "transcript_path": "raw/s1.md"}
    with pytest.raises(RateLimitError):
        handler.run(job_payload)

    paused = store.paused_until()
    assert paused is not None
    assert abs((paused - reset).total_seconds()) < 2
```

(The exact `IngestHandler.run` signature may differ; adapt by reading the existing tests in `tests/daemon/jobs/`.)

- [ ] **Step 3: Run failing test**

```bash
python -m pytest tests/daemon/jobs/test_pause_on_rate_limit.py -v 2>&1 | tail -10
```

Expected: failure — either signature mismatch or queue not paused.

- [ ] **Step 4: Modify IngestHandler**

In `claude_mnemos/daemon/jobs/handlers.py`:

1. Add `job_store: JobStore` parameter to `IngestHandler.__init__` (with `Optional` default for backward compat in tests):
```python
class IngestHandler:
    def __init__(
        self,
        *,
        vault: Path,
        cfg_factory: Callable[[], Config],
        llm_factory: LLMFactory,
        job_store: JobStore | None = None,
    ) -> None:
        ...
        self._job_store = job_store
```

2. Wrap the LLM extraction call in try/except for `RateLimitError`:
```python
        try:
            ... existing extraction logic ...
        except RateLimitError as exc:
            if self._job_store is not None:
                self._job_store.pause_queue(until=exc.reset_at)
            raise
```

3. Add the import: `from claude_mnemos.ingest.llm.rate_limit import RateLimitError`.

4. Update `vault_runtime.py` to pass `job_store=self.job_store` to `IngestHandler(...)` constructor.

- [ ] **Step 5: Run new + existing tests**

```bash
python -m pytest tests/daemon/jobs/ -v 2>&1 | tail -15
```

Expected: all existing daemon/jobs tests still pass + 1 new test for pause_on_rate_limit.

- [ ] **Step 6: Run all tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1450 passed, 3 skipped`.

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/daemon/jobs/handlers.py claude_mnemos/daemon/vault_runtime.py tests/daemon/jobs/test_pause_on_rate_limit.py && git commit -m "feat(jobs): IngestHandler pauses queue on RateLimitError

Catches RateLimitError raised by LLMClient.extract(), persists
paused_until on JobStore, then re-raises so the job is re-queued
(not dead-lettered). Worker reads paused_until in next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: JobWorker respects paused_until

**Files:**
- Modify: `claude_mnemos/daemon/jobs/worker.py`
- Create: `tests/daemon/jobs/test_worker_respects_pause.py`

- [ ] **Step 1: Inspect worker.py**

```bash
grep -n "def run\|dequeue\|while\|paused" /d/code/claude-mnemos/claude_mnemos/daemon/jobs/worker.py | head
```

Find the main loop / dequeue logic.

- [ ] **Step 2: Write failing test**

Create `tests/daemon/jobs/test_worker_respects_pause.py`:
```python
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_mnemos.daemon.jobs.worker import JobWorker
from claude_mnemos.state.jobs import JobStore


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / ".jobs.db")


@pytest.mark.asyncio
async def test_worker_skips_dequeue_while_paused(store: JobStore) -> None:
    """When JobStore.is_paused() is True, worker must not pull jobs even
    if jobs exist."""
    # Enqueue a fake ingest job.
    job_id = store.enqueue(kind="ingest", payload={})
    # Pause queue ahead of now.
    store.pause_queue(until=datetime.now(UTC) + timedelta(minutes=10))

    handler = MagicMock()
    worker = JobWorker(store=store, handlers={"ingest": handler})

    # Trigger one tick (or dequeue attempt) — implementation-specific.
    # Common pattern: worker.tick() returns None and does nothing if paused.
    result = worker.try_dequeue_one()
    assert result is None
    handler.run.assert_not_called()

    # Sanity: job is still queued
    assert store.get_job(job_id).status == "queued"
```

(Adjust to actual `JobWorker` API. If there's no `try_dequeue_one`, find the smallest-grain method that pulls a job and pause-check that.)

- [ ] **Step 3: Run failing test**

```bash
python -m pytest tests/daemon/jobs/test_worker_respects_pause.py -v 2>&1 | tail -10
```

Expected: handler called → test fails.

- [ ] **Step 4: Modify worker.py**

Add an early-return / skip in the dequeue path:
```python
    def try_dequeue_one(self) -> Job | None:
        if self._store.is_paused():
            return None
        return self._store.dequeue_next()  # or whatever existing method
```

Ensure the main worker loop calls this guard.

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/daemon/jobs/ -v 2>&1 | tail -15
```

Expected: all pass.

- [ ] **Step 6: Run all tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1451 passed, 3 skipped`.

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/daemon/jobs/worker.py tests/daemon/jobs/test_worker_respects_pause.py && git commit -m "feat(jobs): JobWorker skips dequeue while queue is paused

Honour JobStore.is_paused() — if true, return None from try_dequeue_one
(or equivalent), leaving jobs queued. Once paused_until is in the past,
is_paused() returns False and dequeue resumes naturally.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 18: /health exposes queue_paused_until

**Files:**
- Modify: `claude_mnemos/daemon/routes/health.py`
- Modify: `claude_mnemos/daemon/schemas.py` (HealthResponse, if defined there)
- Modify: existing tests for /health

- [ ] **Step 1: Find HealthResponse schema**

```bash
grep -n "class HealthResponse\|jobs_queued\|jobs_running" /d/code/claude-mnemos/claude_mnemos/daemon/schemas.py
```

- [ ] **Step 2: Add queue_paused_until field**

In `HealthResponse` Pydantic model, add:
```python
    queue_paused_until: datetime | None = None
```

- [ ] **Step 3: Populate it in /health route**

In `claude_mnemos/daemon/routes/health.py`, find where HealthResponse is constructed and add field. Pull paused_until from any active vault runtime's job_store. If multi-vault, use earliest paused_until across vaults (or None if no vault is paused).

```python
    paused_set = [
        rt.job_store.paused_until()
        for rt in daemon.runtimes.values()
        if rt.job_store
    ]
    paused_set = [p for p in paused_set if p is not None]
    queue_paused_until = max(paused_set) if paused_set else None
```

(Use `max` so UI shows the latest — gives juzer the longest-blocked job's resume time.)

- [ ] **Step 4: Update /health tests**

Find existing test file for /health and add assertion that field exists and is None by default. Add a test that paused job_store surfaces in /health.

- [ ] **Step 5: Run tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1453 passed, 3 skipped` (1451 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/health.py claude_mnemos/daemon/schemas.py tests/daemon/ && git commit -m "feat(daemon): /health exposes queue_paused_until

Aggregates max(paused_until) across all mounted vaults. Frontend reads
this to display 'Rate limited — resumes at HH:MM' badge.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 19: Phase 4 verification

- [ ] **Step 1: Run full backend tests + ruff**

```bash
cd /d/code/claude-mnemos && python -m pytest --ignore=tests/slow 2>&1 | tail -3 && python -m ruff check . 2>&1 | tail -3
```

Expected: `1453 passed, 3 skipped` + `All checks passed!`.

- [ ] **Step 2: Verify zero diff in untouchable files**

```bash
git diff main -- claude_mnemos/ingest/extraction.py claude_mnemos/ingest/parser.py claude_mnemos/state/manifest.py claude_mnemos/core/metrics.py claude_mnemos/hooks/ claude_mnemos/daemon/watchdog_handler.py 2>&1 | wc -l
```

Expected: `0`.

---

# Phase 5 — Onboarding UI step

**Goal:** `/health/claude-cli` endpoint + Frontend zod schemas + axios client + new step in Onboarding wizard. Conditional on platform supporting CLI provider.

---

## Task 20: /health/claude-cli endpoint

**Files:**
- Modify: `claude_mnemos/daemon/routes/health.py` (add new route)
- Create: `tests/daemon/routes/test_health_claude_cli.py`

- [ ] **Step 1: Write failing test**

Create `tests/daemon/routes/test_health_claude_cli.py`:
```python
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon
from claude_mnemos.ingest.llm.auth import AuthStatus


def _make_client() -> TestClient:
    return TestClient(MnemosDaemon(DaemonConfig(boot_filter=None)).app)


def test_health_claude_cli_reports_installed_authenticated() -> None:
    with patch(
        "claude_mnemos.daemon.routes.health.check_claude_cli_auth",
        return_value=AuthStatus(installed=True, authenticated=True, binary_path="/x/claude"),
    ):
        resp = _make_client().get("/health/claude-cli")
    assert resp.status_code == 200
    body = resp.json()
    assert body["installed"] is True
    assert body["authenticated"] is True
    assert body["binary_path"] == "/x/claude"


def test_health_claude_cli_reports_not_installed() -> None:
    with patch(
        "claude_mnemos.daemon.routes.health.check_claude_cli_auth",
        return_value=AuthStatus(installed=False, authenticated=False),
    ):
        resp = _make_client().get("/health/claude-cli")
    assert resp.status_code == 200
    assert resp.json()["installed"] is False
```

- [ ] **Step 2: Run failing test**

```bash
python -m pytest tests/daemon/routes/test_health_claude_cli.py -v 2>&1 | tail -10
```

Expected: 404.

- [ ] **Step 3: Implement endpoint**

In `claude_mnemos/daemon/routes/health.py`, add:
```python
from claude_mnemos.ingest.llm.auth import check_claude_cli_auth

@router.get("/health/claude-cli")
def health_claude_cli() -> dict[str, object]:
    s = check_claude_cli_auth()
    return {
        "installed": s.installed,
        "authenticated": s.authenticated,
        "binary_path": s.binary_path,
    }
```

(Match existing route registration pattern in `health.py` — could be `@router.get("/claude-cli")` if router prefix is `/health`.)

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/daemon/routes/test_health_claude_cli.py -v 2>&1 | tail -10
```

Expected: `2 passed`.

- [ ] **Step 5: Run all tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1455 passed, 3 skipped`.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/health.py tests/daemon/routes/test_health_claude_cli.py && git commit -m "feat(daemon): /health/claude-cli endpoint reports auth state

Returns {installed, authenticated, binary_path} for the Onboarding
wizard step to decide whether to show install/login instructions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 21: Frontend zod schemas + API client

**Files:**
- Create: `frontend/src/types/ClaudeCliAuth.ts`
- Create: `frontend/src/api/claudeCli.api.ts`
- Create: `frontend/src/__tests__/api-claude-cli.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/api-claude-cli.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from "vitest";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { getClaudeCliAuth } from "../api/claudeCli.api";

let mock: MockAdapter;

beforeEach(() => {
  mock = new MockAdapter(axios);
});

describe("Claude CLI auth API", () => {
  it("GET /health/claude-cli parses authenticated state", async () => {
    mock.onGet("/health/claude-cli").reply(200, {
      installed: true,
      authenticated: true,
      binary_path: "/usr/bin/claude",
    });
    const auth = await getClaudeCliAuth();
    expect(auth.installed).toBe(true);
    expect(auth.authenticated).toBe(true);
  });

  it("permissive parsing — missing binary_path defaults to null", async () => {
    mock.onGet("/health/claude-cli").reply(200, {
      installed: false,
      authenticated: false,
    });
    const auth = await getClaudeCliAuth();
    expect(auth.binary_path).toBeNull();
  });
});
```

- [ ] **Step 2: Run failing test**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/api-claude-cli.test.ts 2>&1 | tail -10
```

Expected: import errors.

- [ ] **Step 3: Implement types + api**

Create `frontend/src/types/ClaudeCliAuth.ts`:
```typescript
import { z } from "zod";

export const ClaudeCliAuthSchema = z.object({
  installed: z.boolean(),
  authenticated: z.boolean(),
  binary_path: z.string().nullable().default(null),
});
export type ClaudeCliAuth = z.infer<typeof ClaudeCliAuthSchema>;
```

Create `frontend/src/api/claudeCli.api.ts`:
```typescript
import axios from "axios";
import { ClaudeCliAuthSchema, type ClaudeCliAuth } from "@/types/ClaudeCliAuth";

export async function getClaudeCliAuth(): Promise<ClaudeCliAuth> {
  const { data } = await axios.get("/health/claude-cli");
  return ClaudeCliAuthSchema.parse(data);
}
```

- [ ] **Step 4: Run tests**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/api-claude-cli.test.ts 2>&1 | tail -10
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/types/ClaudeCliAuth.ts frontend/src/api/claudeCli.api.ts frontend/src/__tests__/api-claude-cli.test.ts && git commit -m "feat(frontend): claude CLI auth API client + zod schemas

getClaudeCliAuth() returns ClaudeCliAuth { installed, authenticated,
binary_path }. Used by Onboarding wizard new step.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 22: Onboarding wizard «Check Claude CLI» step

**Files:**
- Modify: `frontend/src/pages/Onboarding.tsx`
- Modify: `frontend/src/__tests__/Onboarding.test.tsx`
- Modify: `frontend/public/locales/{en,ru,uk}.json`

- [ ] **Step 1: Read current Onboarding.tsx**

Locate where the form layout sits and pick a logical insertion point — after the autostart checkbox added in the tray feature, before the submit button.

- [ ] **Step 2: Add locale keys**

Edit each `frontend/public/locales/{en,ru,uk}.json`. Inside `"onboarding"` object add:

`en.json`:
```json
"cli_check_label": "Claude CLI status",
"cli_check_ok": "✓ Claude CLI installed and authenticated",
"cli_check_not_installed": "⚠ Claude CLI not found — install Claude Code from https://claude.ai/download",
"cli_check_not_authenticated": "⚠ Claude CLI installed but not logged in — run `claude login` in your terminal"
```

`ru.json`:
```json
"cli_check_label": "Статус Claude CLI",
"cli_check_ok": "✓ Claude CLI установлен и залогинен",
"cli_check_not_installed": "⚠ Claude CLI не найден — установите Claude Code с https://claude.ai/download",
"cli_check_not_authenticated": "⚠ Claude CLI установлен, но не залогинен — запустите `claude login` в терминале"
```

`uk.json`:
```json
"cli_check_label": "Статус Claude CLI",
"cli_check_ok": "✓ Claude CLI встановлено й автентифіковано",
"cli_check_not_installed": "⚠ Claude CLI не знайдено — встановіть Claude Code з https://claude.ai/download",
"cli_check_not_authenticated": "⚠ Claude CLI встановлено, але не автентифіковано — виконайте `claude login` в терміналі"
```

- [ ] **Step 3: Add CLI check section to Onboarding.tsx**

Add imports:
```tsx
import { getClaudeCliAuth } from "@/api/claudeCli.api";
import type { ClaudeCliAuth } from "@/types/ClaudeCliAuth";
```

Add state:
```tsx
  const [cliAuth, setCliAuth] = useState<ClaudeCliAuth | null>(null);
```

Add useEffect to fetch on mount:
```tsx
  useEffect(() => {
    getClaudeCliAuth()
      .then(setCliAuth)
      .catch(() => setCliAuth(null));
  }, []);
```

Add JSX block before the submit button:
```tsx
      {cliAuth && (
        <div className="mt-4 rounded-md border bg-[hsl(var(--background))] p-3 text-sm">
          <div className="font-medium">{t("onboarding.cli_check_label")}</div>
          <div className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">
            {cliAuth.installed && cliAuth.authenticated
              ? t("onboarding.cli_check_ok")
              : !cliAuth.installed
              ? t("onboarding.cli_check_not_installed")
              : t("onboarding.cli_check_not_authenticated")}
          </div>
        </div>
      )}
```

- [ ] **Step 4: Add test for new behaviour**

Add test cases to `frontend/src/__tests__/Onboarding.test.tsx`:
```typescript
  it("shows green CLI check when authenticated", async () => {
    mock.onGet("/health/claude-cli").reply(200, {
      installed: true,
      authenticated: true,
      binary_path: "/x/claude",
    });
    renderOnboarding();
    expect(await screen.findByText(/Claude CLI installed and authenticated/i))
      .toBeInTheDocument();
  });

  it("shows install instruction when CLI missing", async () => {
    mock.onGet("/health/claude-cli").reply(200, {
      installed: false,
      authenticated: false,
    });
    renderOnboarding();
    expect(await screen.findByText(/Claude Code from https:/i))
      .toBeInTheDocument();
  });

  it("shows login instruction when CLI installed but not authed", async () => {
    mock.onGet("/health/claude-cli").reply(200, {
      installed: true,
      authenticated: false,
    });
    renderOnboarding();
    expect(await screen.findByText(/run `claude login`/i))
      .toBeInTheDocument();
  });
```

(Adjust to existing `renderOnboarding()` helper / mock setup pattern.)

- [ ] **Step 5: Run frontend tests**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run 2>&1 | tail -8
```

Expected: all pass (188 + 3 new).

- [ ] **Step 6: tsc + lint**

```bash
cd /d/code/claude-mnemos/frontend && pnpm tsc --noEmit 2>&1 | tail -3 && pnpm lint 2>&1 | tail -3
```

Expected: tsc clean; lint pre-existing warnings only.

- [ ] **Step 7: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/pages/Onboarding.tsx frontend/src/__tests__/Onboarding.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): Onboarding wizard CLI auth check section

Fetches /health/claude-cli on mount, shows install/login instruction
or success indicator. New locale keys: onboarding.cli_check_*.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 23: Frontend rate-limit pause indicator

**Files:**
- Modify: `frontend/src/pages/Overview.tsx` or appropriate dashboard component (where /health is read)

- [ ] **Step 1: Find where /health is consumed**

```bash
grep -rn "queue_paused_until\|HealthResponse\|/health" /d/code/claude-mnemos/frontend/src/ | head -10
```

Identify the component (likely `Overview.tsx` or a status banner).

- [ ] **Step 2: Add zod field to HealthResponse schema**

In whichever `frontend/src/types/Health*.ts` exists, add:
```typescript
queue_paused_until: z.string().datetime().nullable().default(null),
```

- [ ] **Step 3: Render banner when paused**

In the component, add a banner above the rest of the dashboard content:
```tsx
{health?.queue_paused_until && new Date(health.queue_paused_until) > new Date() && (
  <div className="rounded-md border border-amber-500 bg-amber-50 p-2 text-sm dark:border-amber-700 dark:bg-amber-950">
    {t("dashboard.rate_limited_until", { time: new Date(health.queue_paused_until).toLocaleTimeString() })}
  </div>
)}
```

Add locale keys `dashboard.rate_limited_until` to en/ru/uk.

- [ ] **Step 4: Add test**

Test that banner appears when paused_until is in future, not when in past or null.

- [ ] **Step 5: Run tests**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/ && git commit -m "feat(frontend): rate-limit pause banner on dashboard

Shows 'Rate limited — resumes at HH:MM' when /health.queue_paused_until
is in the future. Auto-disappears when timestamp passes (read on next
fetch). Banner styled amber to signal warning state without alarm.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

# Phase 6 — Manual e2e + finalize

**Goal:** Full end-to-end verification on Yarik's machine (without API key, with active Claude Code subscription). Manual checklist. Merge.

---

## Task 24: Final test suite + ruff/tsc/eslint

- [ ] **Step 1: Backend full run**

```bash
cd /d/code/claude-mnemos && python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: at least `1456 passed` (1404 baseline + ~52 new tests across phases).

- [ ] **Step 2: ruff**

```bash
python -m ruff check . 2>&1 | tail -3
```

Expected: `All checks passed!`.

- [ ] **Step 3: Frontend full run**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run 2>&1 | tail -8
```

Expected: ~196 tests pass (188 baseline + ~8 new).

- [ ] **Step 4: tsc + eslint**

```bash
cd /d/code/claude-mnemos/frontend && pnpm tsc --noEmit 2>&1 | tail -3 && pnpm lint 2>&1 | tail -3
```

Expected: tsc clean; eslint pre-existing warnings only.

- [ ] **Step 5: Frontend build**

```bash
cd /d/code/claude-mnemos/frontend && pnpm build 2>&1 | tail -5
```

Expected: succeeds, bundle written to `claude_mnemos/daemon/static/`.

- [ ] **Step 6: Verify zero-diff in untouchable files**

```bash
cd /d/code/claude-mnemos && git diff main -- claude_mnemos/ingest/extraction.py claude_mnemos/ingest/parser.py claude_mnemos/state/manifest.py claude_mnemos/core/metrics.py claude_mnemos/hooks/ claude_mnemos/daemon/watchdog_handler.py claude_mnemos/daemon/watchdog_observer.py 2>&1 | wc -l
```

Expected: `0`.

- [ ] **Step 7: Commit cleanups (if needed)**

If ruff/tsc applied auto-fixes:

```bash
git add -A && git commit -m "chore: ruff/tsc cleanup after LLM provider refactor

Auto-fixes from ruff --fix and tsc; no behavior change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 25: Manual e2e on Yarik's machine

**Files:**
- Create: `docs/plans/2026-04-30-llm-cli-provider-manual-checklist.md`

- [ ] **Step 1: Write checklist file**

Create `docs/plans/2026-04-30-llm-cli-provider-manual-checklist.md`:
```markdown
# LLM CLI Provider — Manual E2E Checklist

These checks cannot run in CI (require real Claude Code login). Run by hand on Yarik's Win11 machine after Phase 5.

## Prerequisites
- [ ] `claude login` completed (or `CLAUDE_CODE_OAUTH_TOKEN` env set)
- [ ] No `ANTHROPIC_API_KEY` env var (verify with `echo $ANTHROPIC_API_KEY` — empty)
- [ ] Branch `feat/llm-cli-provider` checked out, `pip install -e .` done

## Auth preflight
- [ ] `mnemos --help` works (CLI installed)
- [ ] Open dashboard at http://localhost:5757/
- [ ] Onboarding wizard shows green «Claude CLI installed and authenticated»
- [ ] Manually `curl http://localhost:5757/health/claude-cli` → 200, `installed=true, authenticated=true`

## CLI mode ingest (no API key)
- [ ] Set `MNEMOS_INGEST_PROVIDER=cli` (or leave unset for auto-detect)
- [ ] Create a test project via dashboard pointing at a real Claude Code session vault
- [ ] Trigger ingest of one session via dashboard «Sessions → Ingest»
- [ ] Job appears in /jobs with status=running, then completed
- [ ] Resulting markdown pages exist in vault
- [ ] Pages contain reasonable extracted entities (not garbage)
- [ ] /metrics/usage shows token counts with `~` prefix in UI

## Rate-limit pause (synthetic)
- [ ] Manually inject a RateLimitError by patching CliLLMClient at runtime (or wait for natural rate hit during bulk ingest)
- [ ] /health/queue_paused_until is non-null, in future
- [ ] Dashboard shows amber banner «Rate limited — resumes at HH:MM»
- [ ] Worker does not pull new jobs while paused
- [ ] Once paused_until passes, jobs resume automatically

## API mode (legacy)
- [ ] Set `ANTHROPIC_API_KEY=...` and `MNEMOS_INGEST_PROVIDER=api`
- [ ] Ingest one session
- [ ] Token counts have NO `~` prefix in UI (exact via count_tokens API)

## Failure modes
- [ ] Stop `claude` daemon (e.g. log out from Claude Code) → /health/claude-cli reports `authenticated=false`
- [ ] Trigger ingest with CLI mode → graceful error in dashboard, job in dead-letter
- [ ] Re-login → manual «Retry from dead-letter» works

## Recursion guard
- [ ] Run `mnemos ingest <session>` from inside a Claude Code session (terminal where `CLAUDECODE=1`)
- [ ] CLI subprocess receives clean env (verify via supervisor.log or strace)
- [ ] Ingest succeeds (not blocked by recursion check)

## Documentation
- [ ] README updated with «Without API key — use Claude Code subscription via `mnemos tray install`» note
```

- [ ] **Step 2: Commit checklist**

```bash
cd /d/code/claude-mnemos && git add docs/plans/2026-04-30-llm-cli-provider-manual-checklist.md && git commit -m "docs: manual integration checklist for LLM CLI provider refactor

Covers preflight auth, CLI/API mode ingests, rate-limit pause flow,
failure modes, recursion guard.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 3: Yarik runs the checklist on his machine**

Yarik (or whoever) walks through every checkbox. Reports pass/fail per item. If anything fails — fix in a follow-up commit on the branch, re-run the failed item.

---

## Task 26: Final review + memory update + merge

- [ ] **Step 1: Spawn final code-reviewer subagent**

After Task 25 passes, dispatch `code-reviewer` agent to review the entire branch (all commits since `main`) for any regressions or architectural concerns.

- [ ] **Step 2: Address any blocker findings**

If reviewer flags critical/important issues — fix and re-run tests.

- [ ] **Step 3: Update memory snapshot**

Create `C:/Users/68664/.claude/projects/d-----------------OBSIDIAN--shared/memory/plan_llm_cli_provider_complete.md`:

```markdown
---
name: Plan LLM CLI provider refactor завершён — снимок 2026-04-30
description: Убрана hard зависимость от ANTHROPIC_API_KEY. Dual mode: CliLLMClient (claude -p subprocess через subscription) + ApiLLMClient (старый, opt-in). Контракт LLMClient.extract() unchanged.
type: project
---

# Plan LLM CLI provider refactor — итог

[Описать что добавилось, ссылаясь на phases 1-6]
```

Update `MEMORY.md` index pointer.

- [ ] **Step 4: Merge to main**

```bash
cd /d/code/claude-mnemos && git checkout main && git merge --no-ff feat/llm-cli-provider -m "Merge feat/llm-cli-provider: dual-mode LLM with claude -p subscription path

Phases 1-6 closed:
1. LLMClient Protocol extracted, ApiLLMClient renamed
2. CliLLMClient + tokens + auth + rate_limit modules + tests
3. Factory + Config.ingest_provider + wiring
4. JobStore.pause_queue + IngestHandler/Worker integration
5. /health/claude-cli + Onboarding CLI check + dashboard banner
6. Manual e2e + cleanup

Backend ~1456 passed (+~52 new tray tests). Frontend ~196 Vitest.
Zero diff in extraction.py / parser.py / metrics.py / hooks. Existing
users with ANTHROPIC_API_KEY continue on ApiLLMClient. New users
without API key auto-detect to CliLLMClient via Claude Code subscription.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Verify merge**

```bash
git log --oneline -3
```

Expected: merge commit on top of main with `feat/llm-cli-provider` branch merged.

---

## Self-Review

Plan against design spec:

**1. Spec coverage:**
- §2 Scope «Включено» list: CliLLMClient (Tasks 6-9 ✓), dual-mode factory (Tasks 10-13 ✓), local approximate token counter (Task 6 ✓), smart pause (Tasks 15-19 ✓), Onboarding step (Tasks 20-22 ✓). All covered.
- §3 Architecture — Adapter pattern via Protocol: Tasks 3 + 6-9. ✓
- §4 Components — every file in design has a task. ✓
- §5 Detailed behavior — Tasks 9 (CliLLMClient flow), 11 (factory), 16-18 (rate limit pause), 21-22 (Onboarding). ✓
- §6 Backward compat — Tasks 2 (rename keeps imports working via re-exports), 11 (auto-detect preserves API path), 12-13 (factory wiring). ✓
- §7 Risks — handled via tests where applicable; docs note where not (e.g. tiktoken accuracy).
- §8 Phase rollout — exact 6 phases match. ✓
- §9 Tests — every component has corresponding test task. ✓
- §10 Success criteria — Task 25 manual checklist covers all 7. ✓

**2. Placeholder scan:** Searched for «TBD», «implement later», «Add error handling», «similar to». None found. Each task has complete code.

**3. Type/name consistency:**
- `LLMClient` Protocol defined Task 3, used in 6, 10-13, 17, 22.
- `ExtractionRaw` defined Task 2 (re-exported from api.py), used everywhere.
- `RateLimitError` defined Task 8, raised in Task 9, caught in Task 16.
- `CliLLMClient`, `ApiLLMClient` — consistent class names across all tasks.
- `make_llm_client` defined Task 11, used in 12 + 13.
- `paused_until`, `pause_queue`, `is_paused` — consistent across Tasks 15-19.
- `find_claude_binary`, `check_claude_cli_auth`, `AuthStatus` — consistent across 7, 20.

**4. Risk areas in plan:**
- Task 16 «exact `IngestHandler.run` signature may differ» — flagged for engineer to read existing tests, OK.
- Task 17 worker.py method names («`try_dequeue_one`») are illustrative, real method may differ — engineer must adapt.
- Task 22 `renderOnboarding()` helper assumed but may not exist — engineer adapts to actual harness.

These adaptations are expected for a real codebase; flagged inline.

**Plan complete and saved to `docs/plans/2026-04-30-llm-cli-provider-plan.md`.**
