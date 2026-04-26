# Design: MCP Server (Plan #6)

**Status:** drafted, awaiting Yarik approval before implementation-plan generation.
**Date:** 2026-04-26
**Author:** Claude (with Yarik approval).
**Predecessor:** `2026-04-26-daemon-foundation-design.md` (Plan #5, merged in `f32714f`).
**Successor planned:** Plan #7 (Claude Code hooks + plugin manifest) → Plan #8 (frontend dashboard).

---

## 1. Goal

Поднять **MCP server** (Model Context Protocol) — отдельный stdio-процесс, который Claude Code запускает в каждой сессии и который даёт LLM **прямой доступ к vault'у** через 9 tool'ов:

- 5 **read tools** — прямой файловый доступ к `<vault>/wiki/`, `<vault>/.activity.json`, `<vault>/.manifest.json`. Без сетевого hop'а.
- 4 **write tools** — через REST к daemon (`POST /activity/{id}/undo`, `POST /snapshots`, etc.). Если daemon offline — error с подсказкой `mnemos daemon start`.

После Plan #6 пользователь может в Claude Code через MCP:

- спросить «что у меня есть в vault'е» → `get_status`, `list_pages`, `search_pages`
- прочитать конкретную страницу → `read_page`
- увидеть историю операций → `get_recent_activity`
- откатить операцию → `undo_operation`
- сделать/восстановить/удалить snapshot → `create_snapshot`, `restore_snapshot`, `delete_snapshot`

**MCP — это первая руки-в-руки интеграция mnemos с Claude Code**. До Plan #6 mnemos живёт изолированно (CLI + REST). После Plan #6 LLM в чате видит vault.

Что **НЕ** даёт (явно отложено):

- Hooks (SessionStart/SessionEnd/PreCompact) → Plan #7. До Plan #7 ingest всё ещё ручной (`mnemos ingest`).
- Plugin manifest (`.claude-plugin/plugin.json`, marketplace.json) → Plan #7.
- Slash commands (`/mnemos:*`) → Plan #7.
- `add_entity`, `query_wiki`, `run_lint`, `apply_ontology_suggestion` из spec'а §9.5 — НЕ в Plan #6, потому что зависят от модулей которых ещё нет (`tiered_query`, `POST /pages`, lint, ontology).
- Frontend dashboard → Plan #8.
- Multi-vault routing — single-vault как и daemon в Plan #5.

---

## 2. Scope

### 2.1 In scope

| Tool | Kind | Реализация |
|---|---|---|
| `list_pages(type?, flavor?, limit=50)` | read | iterdir `<vault>/wiki/{entities,concepts,sources}/`, парсит frontmatter (через существующий `core/frontmatter` или yaml.safe_load) |
| `read_page(page_ref)` | read | `<vault>/wiki/**/<ref>.md` или `<vault>/raw/chats/<ref>.md`; возвращает full content + frontmatter dict |
| `search_pages(query, limit=20)` | read | grep по filename + body (case-insensitive substring; regex out of scope) |
| `get_status` | read | те же поля что `/vault/info` REST endpoint, но без сетевого hop'а |
| `get_recent_activity(limit=10)` | read | newest-first slice через `ActivityLog.load` |
| `undo_operation(op_id)` | write | `POST {daemon}/activity/{id}/undo` |
| `create_snapshot(label?)` | write | `POST {daemon}/snapshots` |
| `restore_snapshot(name)` | write | `POST {daemon}/snapshots/{name}/restore` |
| `delete_snapshot(name)` | write | `DELETE {daemon}/snapshots/{name}` |

| Component | Где |
|---|---|
| MCP server skeleton (low-level `Server` API) | `mcp/server.py` |
| `__main__.py` для `python -m claude_mnemos.mcp` | `mcp/__main__.py` |
| Config (`vault_root`, `daemon_url`, env overrides) | `mcp/config.py` |
| Read tool handlers | `mcp/read_tools/{pages,status,activity}.py` |
| Write tool handlers (httpx → daemon REST) | `mcp/write_tools/{activity,snapshots}.py` |
| Tool schema definitions (`inputSchema` JSON Schema) | `mcp/schemas.py` |
| Pretty error formatting (TextContent с понятным сообщением, не stack trace) | `mcp/errors.py` |
| Tests: read tools на fixture vault | `tests/mcp/test_read_tools.py` |
| Tests: write tools с mocked httpx | `tests/mcp/test_write_tools.py` |
| Tests: in-process MCP `Client(app)` E2E | `tests/mcp/test_server_e2e.py` |
| `pyproject.toml`: `mcp>=1.12` dep + console_script `mnemos-mcp` | `pyproject.toml` |

### 2.2 Out of scope (явно отложено)

| Component | Plan |
|---|---|
| `query_wiki` (tiered query: hot.md → index → grep → full) | Plan #11+ когда появится `tiered_query` модуль |
| `add_entity`, `add_concept` (manual page creation через MCP) | Plan #11+ когда добавим `POST /pages` endpoint |
| `run_lint`, `apply_ontology_suggestion` | Plan #9 (ontology) / Plan #11+ (lint) |
| Hooks (SessionStart/End, PreCompact) | Plan #7 |
| Plugin manifest + marketplace.json | Plan #7 |
| Slash commands `/mnemos:*` | Plan #7 |
| Skills + references (`skills/mnemos/SKILL.md`) | Plan #7 |
| Multi-vault (`project` parameter в каждом tool'е) | когда multi-vault routing появится |
| Auth между MCP и daemon (токен в headers) | когда daemon получит auth (v1.x) |
| Streaming/progress notifications в tool'ах | YAGNI |
| Resources/Prompts API (помимо tools) | YAGNI |

---

## 3. Architecture

### 3.1 Как процессы взаимодействуют

```
┌──────────────────┐         stdio        ┌──────────────────┐
│  Claude Code     │ ◄──────────────────► │  MCP server      │
│  (the chat)      │       JSON-RPC       │  (per-session)   │
└──────────────────┘                      └──────────────────┘
                                              │         │
                              read (direct)   │         │   write (HTTP)
                                              ▼         ▼
                                  ┌─────────────┐  ┌──────────────────┐
                                  │   vault/    │  │  mnemos daemon   │
                                  │ files+JSON  │  │  127.0.0.1:5757  │
                                  └─────────────┘  └──────────────────┘
                                                          │
                                                          ▼
                                                  ┌─────────────┐
                                                  │   vault/    │
                                                  │ (write path)│
                                                  └─────────────┘
```

- **Read tools** идут напрямую в файлы — быстро, не блокируются `pipeline_lock`'ом, eventual consistency приемлема (если в момент чтения daemon promote'ит staging → tools могут увидеть pre/post-promote, но не битое состояние благодаря `atomic_write`).
- **Write tools** идут через daemon REST — это гарантирует прохождение через 5 слоёв защиты (validation, staging, atomic, snapshot, activity log) + единый `pipeline_lock`. Прямой write из MCP **запрещён по спеке §9.5** — потому что MCP не контролирует один глобальный lock и не может атомарно записать pages+manifest+activity.
- **Если daemon offline** — write tool возвращает `TextContent` с error: `"backend daemon not running. Start it with: mnemos daemon start --vault <path>"`. Никаких silent retries / queues.

### 3.2 Single-vault, single-daemon

Как и в Plan #5, MCP server знает один vault (через `--vault` CLI argument или env `MNEMOS_VAULT_ROOT`). Daemon URL по умолчанию `http://127.0.0.1:5757`, override через env `MNEMOS_DAEMON_URL`.

Multi-project routing (spec §9.5 параметр `project`) **отложен**. Когда Plan #7 + multi-vault — параметр `project` добавится во все tool'ы как optional.

### 3.3 Module map

**Новое:**

| Файл | Ответственность |
|---|---|
| `claude_mnemos/mcp/__init__.py` | re-export `build_server`, `MCPConfig` |
| `claude_mnemos/mcp/__main__.py` | `python -m claude_mnemos.mcp --vault PATH [--daemon-url URL] [--log-level L]` |
| `claude_mnemos/mcp/config.py` | `MCPConfig` Pydantic + `from_env(vault_root)` |
| `claude_mnemos/mcp/server.py` | `build_server(config) -> Server` — регистрирует все tools, возвращает готовый `mcp.server.lowlevel.Server` |
| `claude_mnemos/mcp/schemas.py` | JSON Schema dict'ы для `inputSchema` каждого tool'а |
| `claude_mnemos/mcp/errors.py` | `format_error(exc) -> str`, `daemon_unreachable_message()` |
| `claude_mnemos/mcp/read_tools/__init__.py` | re-export handlers |
| `claude_mnemos/mcp/read_tools/pages.py` | `list_pages_handler`, `read_page_handler`, `search_pages_handler` |
| `claude_mnemos/mcp/read_tools/status.py` | `get_status_handler` |
| `claude_mnemos/mcp/read_tools/activity.py` | `get_recent_activity_handler` |
| `claude_mnemos/mcp/write_tools/__init__.py` | re-export handlers |
| `claude_mnemos/mcp/write_tools/activity.py` | `undo_operation_handler` |
| `claude_mnemos/mcp/write_tools/snapshots.py` | `create_snapshot_handler`, `restore_snapshot_handler`, `delete_snapshot_handler` |
| `tests/mcp/__init__.py` | |
| `tests/mcp/test_config.py` | |
| `tests/mcp/test_schemas.py` | |
| `tests/mcp/test_read_pages.py` | list/read/search pages |
| `tests/mcp/test_read_status.py` | get_status, get_recent_activity |
| `tests/mcp/test_write_activity.py` | undo через mocked httpx |
| `tests/mcp/test_write_snapshots.py` | create/restore/delete через mocked httpx |
| `tests/mcp/test_server_e2e.py` | in-process MCP `Client(app)` smoke |

**Изменяемое:**

| Файл | Что |
|---|---|
| `pyproject.toml` | `mcp>=1.12` в dependencies; `pytest-anyio>=0.0` в dev (если SDK его требует — иначе используем pytest-asyncio); `[project.scripts]` добавить `mnemos-mcp = "claude_mnemos.mcp.__main__:main"` |
| `[[tool.mypy.overrides]]` | `mcp.*` → `ignore_missing_imports = true` (на случай отсутствия type stubs) |

---

## 4. Tool contracts (input/output schemas)

### 4.1 Read tools

**`list_pages`**
```json
{
  "type": "object",
  "properties": {
    "type": {"type": "string", "enum": ["entity", "concept", "source"], "description": "Filter by page type"},
    "flavor": {"type": "string", "enum": ["pattern", "mistake", "decision", "lesson", "reference"], "description": "Filter by flavor tag"},
    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50}
  }
}
```
Returns:
```
[
  {"path": "wiki/entities/foo.md", "title": "Foo", "type": "entity", "flavor": ["pattern"]},
  ...
]
```

**`read_page`**
```json
{
  "type": "object",
  "required": ["page_ref"],
  "properties": {
    "page_ref": {"type": "string", "description": "Either page name (e.g. 'foo') or path relative to vault root (e.g. 'wiki/entities/foo.md')"}
  }
}
```
Returns:
```
{
  "path": "wiki/entities/foo.md",
  "frontmatter": {...},
  "body": "..."
}
```

**`search_pages`**
```json
{
  "type": "object",
  "required": ["query"],
  "properties": {
    "query": {"type": "string", "minLength": 1, "description": "Case-insensitive substring (filename + body)"},
    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}
  }
}
```

**`get_status`** — без аргументов. Returns тот же shape что `/vault/info` REST endpoint.

**`get_recent_activity`**
```json
{
  "type": "object",
  "properties": {
    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 10}
  }
}
```

### 4.2 Write tools

**`undo_operation`**
```json
{
  "type": "object",
  "required": ["op_id"],
  "properties": {
    "op_id": {"type": "string", "description": "Activity entry id (full UUID hex)"}
  }
}
```
Returns daemon response: `{"success": true, "op_id": ..., "restored_pages": [...], "new_entry_id": ...}`. На daemon error (4xx/5xx) — TextContent с распарсенным `error/detail` плюс `isError: true`.

**`create_snapshot`**
```json
{"type": "object", "properties": {"label": {"type": "string", "maxLength": 128}}}
```

**`restore_snapshot`**
```json
{"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}
```

**`delete_snapshot`** — то же что restore.

### 4.3 Output format

Tools всегда возвращают `list[TextContent]` где text — JSON-stringified dict (для машинного парсинга LLM'ом). Для нагляденности в `text` пишем `json.dumps(data, indent=2, ensure_ascii=False)`. Это совместимо с любым MCP клиентом и LLM прекрасно парсит JSON в TextContent.

При появлении в SDK более стабильной поддержки `structured_content` — добавим без breaking change. Сейчас (1.12) пишем оба поля если SDK даёт.

---

## 5. Error handling matrix

| Сценарий | Возврат |
|---|---|
| `read_page` page not found | `TextContent("page not found: <ref>")`, `isError: true` |
| `search_pages` пустой query (зашло мимо JSON Schema) | то же |
| `get_status` corrupt manifest/activity | `TextContent("vault state corrupt: <detail>. fix .manifest.json/.activity.json manually")` `isError: true` |
| Write tool: daemon connection refused | `TextContent("backend daemon not running on <url>. start it with: mnemos daemon start --vault <path>")` `isError: true` |
| Write tool: daemon HTTP 4xx (e.g. 409 undo_failed) | `TextContent("daemon refused: <error>. detail: <detail>")` `isError: true` |
| Write tool: daemon HTTP 5xx | то же, с подсказкой проверить логи daemon'а |
| Write tool: timeout (>30s) | `TextContent("daemon timeout after 30s for <endpoint>. is daemon overloaded?")` `isError: true` |
| Path traversal попытка в `read_page` (e.g. `../../../etc/passwd`) | `TextContent("invalid page reference: <ref>")` `isError: true` |
| Любое необработанное исключение в handler | `TextContent("internal error: <type>: <message>")` `isError: true` (полный stack — в stderr через logging) |

**Path traversal защита** для `read_page` обязательна. Реализация: `(vault / page_ref).resolve()` должно начинаться с `vault.resolve()`. Если `page_ref` без `.md` суффикса — сначала ищем в `wiki/entities/`, `wiki/concepts/`, `wiki/sources/`, `raw/chats/`. Если содержит `..` или абсолютный путь → reject.

---

## 6. Configuration

```python
class MCPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault_root: Path
    daemon_url: str = "http://127.0.0.1:5757"
    daemon_timeout_s: float = Field(default=30.0, gt=0)
    log_level: Literal["debug", "info", "warning", "error"] = "info"

    @classmethod
    def from_env(cls, vault_root: Path) -> "MCPConfig":
        return cls(
            vault_root=vault_root,
            daemon_url=os.environ.get("MNEMOS_DAEMON_URL", "http://127.0.0.1:5757"),
            daemon_timeout_s=float(os.environ.get("MNEMOS_MCP_TIMEOUT", "30")),
            log_level=os.environ.get("MNEMOS_MCP_LOG", "info"),  # type: ignore[arg-type]
        )
```

CLI:
```bash
python -m claude_mnemos.mcp --vault PATH [--daemon-url URL] [--log-level L]
mnemos-mcp --vault PATH ...   # console_script alias
```

`MNEMOS_VAULT_ROOT` env var — НЕ автоматический fallback (явное `--vault`), потому что MCP server запускается Claude Code'ом и vault там должен быть прописан явно в `claude mcp add`.

Регистрация в Claude Code (документация):
```bash
claude mcp add --transport stdio mnemos -- \
  python -m claude_mnemos.mcp --vault /path/to/your/vault
```

---

## 7. Concurrency

MCP server работает асинхронно (asyncio). Read tools — pure async I/O (читают файлы через `pathlib`/`json`, без аwait, но handlers async для соответствия SDK). Write tools — `httpx.AsyncClient`.

`pipeline_lock` MCP server **не берёт сам** — read tools не нуждаются (eventual consistency приемлема), write tools идут через daemon (он берёт lock сам).

Несколько одновременных tool вызовов от Claude Code — обрабатываются параллельно (asyncio). Read tools безопасны. Write tools все идут к одному daemon'у — он сериализует через `pipeline_lock`.

---

## 8. Testing strategy

### 8.1 Уровни

1. **Unit (`config.py`):**
   - Defaults + env overrides
   - Invalid daemon_timeout_s → ValidationError
   - Invalid log_level → ValidationError

2. **Unit (read tools на fixture vault):**
   - `list_pages` пустой / с 3 страницами / фильтр type=entity
   - `read_page` known/unknown ref / path traversal
   - `search_pages` substring matching, case-insensitive, limit
   - `get_status` пустой/наполненный vault, corrupt manifest/activity → error TextContent
   - `get_recent_activity` empty/with entries/limit

3. **Unit (write tools с mocked httpx):**
   - `undo_operation` happy path → возвращает daemon JSON
   - `undo_operation` daemon 409 → error TextContent
   - `undo_operation` connection refused → error TextContent с инструкцией
   - `create_snapshot` happy path
   - `restore_snapshot` happy path / 404
   - `delete_snapshot` happy path / traversal name → daemon вернёт 400

4. **E2E (in-process MCP client):**
   - `Client(server).list_tools()` возвращает 9 tools с правильными именами и schemas
   - `Client(server).call_tool("get_status")` возвращает TextContent с JSON

5. **Integration с реальным daemon (slow marker):**
   - Поднять daemon как subprocess (как в Plan #5 e2e), MCP server в том же процессе
   - `create_snapshot` через MCP → snapshot реально создаётся
   - `delete_snapshot` через MCP → snapshot реально удаляется

### 8.2 Coverage targets

- 307 текущих + ~50 новых.
- ruff + mypy strict чистые.
- Manual smoke в Task последний:
  - Поднять daemon, поднять MCP server в foreground, вручную POST'ить JSON-RPC requests (или использовать `mcp` CLI клиент если в SDK есть).

### 8.3 Async testing

`pytest-asyncio` уже стоит из Plan #5 (`asyncio_mode = "auto"`). MCP SDK `Client(app)` — async context manager. Тесты — async def.

---

## 9. Distribution

**Plan #6 не делает plugin-package.** MCP server ставится через:

```bash
pip install -e .   # уже работает, добавили console_script
claude mcp add --transport stdio mnemos -- python -m claude_mnemos.mcp --vault /path
```

Plugin manifest (`.claude-plugin/plugin.json`) с `mcp_servers` секцией — Plan #7 (когда добавим hooks). Тогда `pip install claude-mnemos` + `claude plugins install claude-mnemos` будут регистрировать MCP автоматически.

Документация для пользователя — README раздел «MCP server» добавлю в Task последний.

---

## 10. Known limitations (для Plan #7+)

1. **Нет multi-vault.** Один MCP server = один vault. Если у пользователя 5 проектов — нужно 5 MCP server registrations с разными `--vault`.
2. **Нет `add_entity` / `query_wiki`.** LLM не может через MCP создать страницу или сделать tiered-query. Только читать существующие + manage snapshots/undo.
3. **Нет search'а по wikilinks/backlinks.** `search_pages` — простой substring grep. Нет «what links to [[foo]]».
4. **Нет hooks-интеграции.** Без Plan #7 ingest всё ещё manual через CLI. MCP только наблюдает.
5. **Нет auth.** MCP→daemon httpx без токена. Localhost trust как у daemon.
6. **Path в `read_page`** — резолвится относительно vault. Защита от `..` есть, но если vault — symlink, реализация `is_relative_to` проверки может вести себя непредсказуемо. Acceptable для localhost dev.
7. **`get_status` дублирует `/vault/info`.** Не DRY: считаем counts pages в двух местах. Tradeoff: read tool без сетевого hop'а быстрее. Можно отрефакторить в общий helper `core/vault_stats.py` — отложу для Plan #7.
8. **Нет structured_content в Plan #6.** Все tools возвращают только `TextContent` с JSON-string. SDK 1.12 поддерживает `structured_content`, но client support пока спорадический. Добавим в v1.x.

---

## 11. What this enables (#7+ onwards)

- **Plan #7 (hooks + plugin manifest):** plugin manifest регистрирует MCP server автоматически. Slash commands `/mnemos:*` могут зовать MCP tools. SessionEnd hook + ingest endpoint в daemon → автоingest, MCP server в новой сессии видит обновлённый vault.
- **Plan #8 (dashboard):** dashboard и MCP — два разных UI на одни и те же daemon endpoints. Frontend читает через REST, MCP читает через файлы.
- **Plan #9 (ontology):** `apply_ontology_suggestion` MCP tool станет возможен — добавим в `mcp/write_tools/ontology.py` после ontology endpoint в daemon.
- **Plan #11+:** lint, tiered_query → новые MCP tools.

---

## 12. Решения, которые я принял сам (для протокола)

| Решение | Альтернатива | Почему выбрал |
|---|---|---|
| Plan #6 = только MCP, без hooks/plugin manifest | Один план «MCP + hooks + manifest» | Прецедент Plans #1-#5: фокусные узкие планы. Hooks требуют plugin manifest, marketplace-готового тестирования — большой кусок. Разделим. |
| 5 read + 4 write tools, не spec'овский набор | spec §9.5 (4 read + 3 write) | Spec'овский набор полагается на модули которых нет (`tiered_query`, `POST /pages`, lint, ontology). Беру что **реально работает сейчас** + добавляю `get_recent_activity`, `restore_snapshot`, `delete_snapshot` (последние есть в daemon, грех не отдать). |
| Read через прямой файловый доступ, write через REST | Всё через REST к daemon | Spec §9.5 принципиально различает: read fast/без lock'а, write через 5 слоёв защиты. Разделение оправдано. |
| stdio transport, не SSE/HTTP | SSE/HTTP | Stdio — стандарт для plugin distribution. SSE/HTTP добавим если понадобится remote (вряд ли). |
| Single-vault | Multi-vault `project` параметр в каждом tool'е | Daemon тоже single-vault в Plan #5 — консистентно. Multi-vault отложен. |
| Output как `TextContent(json.dumps(...))` | `structured_content` API | SDK 1.12 поддержка `structured_content` спорадическая в клиентах. JSON-string — universal. Добавим structured при апгрейде. |
| Нет MCP `Resources` или `Prompts` API | Зарегистрировать каждую страницу как Resource | YAGNI. Tools достаточно. Resources/Prompts — отдельный план если понадобится. |
| Daemon URL через env, default `127.0.0.1:5757` | CLI flag обязателен | Симметрично с daemon Plan #5 (тоже env-first). |
| Path в `read_page`: относительный к vault, проверка traversal | Абсолютный путь, без проверки | Безопасность. LLM может попытаться через `read_page("../../../etc/passwd")` — должны блокировать. |
| `mcp` Python SDK low-level `Server` API | FastMCP high-level | Low-level даёт полный контроль над `inputSchema`/`isError`. FastMCP лучше для quick prototypes; у нас 9 tools — стоит control. |
| Console_script `mnemos-mcp` + `python -m claude_mnemos.mcp` | Только `python -m` | UX: пользователь регистрирует через `claude mcp add` — короткий путь приятнее. |
| `pyproject.toml` deps: `mcp>=1.12` | Pinned `mcp==1.12.4` | Project ещё нестабильный, `>=` ловит patch fixes. CI ловит regressions. |
| Tests: in-process `Client(app)` через MCP SDK | Subprocess + JSON-RPC pipe | SDK даёт in-process клиент — быстрее, без race conditions, тестит handler контракт. Subprocess только для slow E2E. |
| Mock httpx в write-tool тестах | Поднимать реальный daemon в каждом тесте | Daemon уже unit-тестирован в Plan #5. MCP отвечает за **mapping** — этого достаточно покрыть mock'ом. Один slow E2E с реальным daemon. |

---

## 13. Open questions для имплементации (не блокеры)

- **MCP SDK API change risk.** Versions 1.10→1.12 меняли некоторые типы (`CallToolResult.isError` vs `is_error`). Найдём при коде, адаптируем.
- **`read_page` без `.md` суффикса** — искать в каком порядке? Решение: сначала точное совпадение пути → потом `wiki/entities/<ref>.md` → `wiki/concepts/<ref>.md` → `wiki/sources/<ref>.md` → `raw/chats/<ref>.md`. Если несколько матчей — error «ambiguous, specify path».
- **`search_pages` body matching на больших vault'ах** — наивный grep по всем `*.md`. Acceptable для <1000 страниц. Если станет проблемой — добавим indexing в Plan #11+.
- **`get_status`** дублирует `/vault/info`. Refactor в общий `core/vault_stats.py` — Plan #7 (когда понадобится).
- **`undo_operation` принимает только full UUID** (не prefix как CLI). Для MCP — full UUID нормально (LLM передаёт точные значения, не печатает). Если LLM путается — добавим server-side prefix matching как в CLI.
- **Регистрация в Claude Code в README** — формат `claude mcp add --transport stdio mnemos -- python -m claude_mnemos.mcp --vault /path/to/vault`. Документирую в Task 9.
- **stderr logging.** MCP server stdout зарезервирован для JSON-RPC. Все логи в stderr. Если запущен через Claude Code — stderr попадёт в его лог.

---

## 14. Why this scope

Через эту дверь:

1. **LLM в Claude Code наконец видит vault.** До Plan #6 mnemos жил отдельно. Now LLM может в чате попросить `read_page("fastapi")`, увидеть свои прежние выводы, не выдумывать заново.
2. **Snapshot management через MCP.** Удобный escape hatch — «откати последнюю операцию» прямо в чате.
3. **Подкладывает фундамент под Plan #7.** Когда добавим hooks + plugin manifest — MCP уже работает. Plugin будет просто паковать hooks + commands + skills + MCP в один манифест.
4. **Не блокирует existing flows.** Если MCP не подключён — daemon и CLI работают как до Plan #6.
5. **По cycle time** — узкий план как Plans #2-#5. ~1 неделя.
