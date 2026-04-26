# MCP Server Implementation Plan (Plan #6)

> **For agentic workers:** Use TDD at every step. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** stdio MCP server (Python `mcp` SDK low-level) с 5 read + 4 write tools поверх существующего daemon (Plan #5) и vault.

**Architecture:** see `docs/plans/2026-04-26-mcp-server-design.md`.

**Tech Stack:** Python 3.12, `mcp>=1.12` SDK, httpx (для write tools), pytest-asyncio.

---

## Что НЕ делаем

См. §2.2 design doc'а — hooks/plugin manifest/slash commands → Plan #7. `add_entity`/`query_wiki`/`run_lint`/ontology → Plan #9/#11+. Frontend → Plan #8. Multi-vault. Auth.

---

## Files map

**Создаём:**

```
claude_mnemos/mcp/
  __init__.py        # re-export build_server, MCPConfig
  __main__.py        # python -m claude_mnemos.mcp --vault PATH
  config.py          # MCPConfig
  errors.py          # format_error, daemon_unreachable_message, PageRefError
  schemas.py         # JSON Schema dicts для inputSchema каждого tool
  server.py          # build_server(config) -> Server
  vault_access.py    # safe page resolution (anti-traversal)
  read_tools/__init__.py
  read_tools/pages.py     # list_pages, read_page, search_pages
  read_tools/status.py    # get_status
  read_tools/activity.py  # get_recent_activity
  write_tools/__init__.py
  write_tools/activity.py    # undo_operation
  write_tools/snapshots.py   # create_snapshot, restore_snapshot, delete_snapshot
tests/mcp/
  __init__.py
  test_config.py
  test_schemas.py
  test_vault_access.py
  test_read_pages.py
  test_read_status.py
  test_read_activity.py
  test_write_activity.py
  test_write_snapshots.py
  test_server_smoke.py    # in-process Client smoke, list_tools, call_tool
  test_e2e_with_daemon.py # slow: реальный daemon subprocess
```

**Изменяем:**

| Файл | Что |
|---|---|
| `pyproject.toml` | dep `mcp>=1.12`, console_script `mnemos-mcp = "claude_mnemos.mcp.__main__:main"`, mypy override `mcp.*` |

---

## Зависимости между задачами

```
Task 1: deps + branch
    ↓
Task 2: config + errors + schemas (data layer)
    ↓
Task 3: vault_access (page resolution + traversal protection)
    ↓
Task 4: read_tools/pages (list, read, search) — uses vault_access
    ↓
Task 5: read_tools/status + read_tools/activity
    ↓
Task 6: write_tools/activity (undo через httpx)
    ↓
Task 7: write_tools/snapshots (create/restore/delete через httpx)
    ↓
Task 8: server.build_server + tool dispatch
    ↓
Task 9: __main__ + console_script
    ↓
Task 10: E2E smoke (in-process Client) + slow E2E с реальным daemon
    ↓
Task 11: README MCP section + manual smoke + merge
```

---

## Task 1: Branch + deps

- [ ] `git checkout -b feat/mcp-server` (уже сделано)
- [ ] `pyproject.toml`: `mcp>=1.12` в `dependencies`; `[project.scripts]` добавить `mnemos-mcp = "claude_mnemos.mcp.__main__:main"`; `[[tool.mypy.overrides]]` для `mcp.*`
- [ ] `pip install -e .[dev]` + sanity import
- [ ] Baseline: `pytest -q` → 306 passed
- [ ] Commit `chore: add mcp SDK dependency + mnemos-mcp console_script`

---

## Task 2: config + errors + schemas

- [ ] `mcp/config.py`: `MCPConfig` Pydantic (vault_root, daemon_url, daemon_timeout_s, log_level) + `from_env`
- [ ] `mcp/errors.py`: `format_error(exc) -> str`, `daemon_unreachable_message(url, vault) -> str`, `PageRefError(ValueError)`
- [ ] `mcp/schemas.py`: dict'ы JSON Schema для каждого из 9 tools (см. design §4.1-4.2)
- [ ] Tests:
   - `test_config.py` — defaults, env, validation
   - `test_schemas.py` — каждый schema parseable как JSON Schema (через `jsonschema` если есть, иначе hand-validation: required keys, type values)
- [ ] Commit `feat(mcp): config, error formatters, tool input schemas`

---

## Task 3: vault_access (safe page resolution)

`mcp/vault_access.py`:
```python
def resolve_page_path(vault: Path, page_ref: str) -> Path:
    """Resolve page_ref to absolute path inside vault.

    Order:
    1. Reject if contains ".." or is absolute → PageRefError
    2. Try exact path: vault / page_ref (if .md suffix)
    3. Try in standard dirs: wiki/entities/<ref>.md, wiki/concepts/<ref>.md,
       wiki/sources/<ref>.md, raw/chats/<ref>.md
    4. Verify final path is_relative_to(vault.resolve())
    5. Return if exists, else PageRefError
    """
```

Tests:
- exact path with .md → resolves
- bare name `foo` → finds in wiki/entities/foo.md if exists
- bare name with multiple matches → PageRefError "ambiguous"
- `../etc/passwd` → PageRefError
- `/abs/path` → PageRefError
- non-existent → PageRefError

Commit `feat(mcp): safe page reference resolution`

---

## Task 4: read_tools/pages

`mcp/read_tools/pages.py`:
- `list_pages(vault, type=None, flavor=None, limit=50) -> list[dict]` — iterdir wiki/<type>, parse frontmatter (yaml.safe_load), filter, sort by mtime desc
- `read_page(vault, page_ref) -> dict` — uses `resolve_page_path`, splits frontmatter+body, returns `{"path": ..., "frontmatter": {...}, "body": "..."}`
- `search_pages(vault, query, limit=20) -> list[dict]` — case-insensitive substring in filename + body, returns matches with snippet

Tests:
- `list_pages` empty / 3 pages / type=entity filter / flavor filter / limit
- `read_page` known/unknown / with frontmatter / without frontmatter / traversal
- `search_pages` substring matches / case-insensitive / limit / no matches → []

Commit `feat(mcp): read_tools for pages (list, read, search)`

---

## Task 5: read_tools/status + read_tools/activity

`mcp/read_tools/status.py`:
- `get_status(vault) -> dict` — те же поля что `/vault/info`: vault, raw_chats, wiki_pages, manifest_processed, activity_entries, snapshots, total_size_bytes

`mcp/read_tools/activity.py`:
- `get_recent_activity(vault, limit=10) -> list[dict]` — `ActivityLog.load`, reversed, slice, model_dump

Tests:
- `get_status` empty/populated; corrupt manifest/activity → raises (handler формирует error TextContent)
- `get_recent_activity` empty/with entries/limit

Commit `feat(mcp): read_tools for status + recent activity`

---

## Task 6: write_tools/activity

`mcp/write_tools/activity.py`:
- `undo_operation(client: httpx.AsyncClient, daemon_url: str, op_id: str) -> dict` — `await client.post(f"{daemon_url}/activity/{op_id}/undo")`, на ConnectError/timeout/4xx/5xx — raise specific exception which handler формирует в error TextContent

Tests (mocked httpx):
- happy → returns parsed JSON
- `httpx.ConnectError` → raises `DaemonUnreachableError`
- 409 → raises `DaemonRefusedError(detail=...)`
- timeout → raises `DaemonTimeoutError`

Commit `feat(mcp): write_tools/activity (undo via daemon REST)`

---

## Task 7: write_tools/snapshots

`mcp/write_tools/snapshots.py`:
- `create_snapshot(client, daemon_url, label=None) -> dict` → POST /snapshots
- `restore_snapshot(client, daemon_url, name) -> dict` → POST /snapshots/{name}/restore
- `delete_snapshot(client, daemon_url, name) -> dict` → DELETE /snapshots/{name}

Tests (mocked httpx):
- happy paths для всех 3
- 400 invalid_name, 404 not_found, ConnectError

Commit `feat(mcp): write_tools/snapshots (create/restore/delete via daemon REST)`

---

## Task 8: server.build_server

`mcp/server.py`:
- `build_server(config: MCPConfig) -> Server`:
   - `server = Server("claude-mnemos")`
   - `@server.list_tools()` — возвращает `[Tool(name, description, inputSchema=schemas.X)]` для всех 9
   - `@server.call_tool()` — диспетчер: `match name: case "list_pages": ...`. Для read tools — sync вызов handler в threadpool через `asyncio.to_thread`. Для write tools — создаёт `httpx.AsyncClient(timeout=config.daemon_timeout_s)` и вызывает write handler. Любое исключение ловится и оборачивается в `[TextContent(text=format_error(exc))]` с пометкой через `raise` (SDK сам обернёт в isError) или через возврат — выбрать стратегию
   - Возврат всегда `[TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]`

Tests:
- `build_server(config).request_handlers` содержит list_tools + call_tool
- list_tools возвращает 9 tools с правильными именами
- call_tool unknown name → error
- call_tool list_pages → возвращает TextContent с JSON
- call_tool undo_operation с unreachable daemon → error TextContent с инструкцией

Commit `feat(mcp): server build with 9 tool handlers`

---

## Task 9: __main__ + console_script

`mcp/__main__.py`:
- argparse: `--vault` (required), `--daemon-url`, `--log-level`
- Build `MCPConfig`, `build_server`, run via `mcp.server.stdio.stdio_server()` + `await server.run(...)`
- Logging в stderr (stdout зарезервирован для JSON-RPC)

Tests:
- `build_parser` accepts/rejects flags correctly
- `main(argv)` без `--vault` → SystemExit

Commit `feat(mcp): python -m claude_mnemos.mcp + mnemos-mcp script`

---

## Task 10: E2E smoke (in-process) + slow E2E with daemon

`tests/mcp/test_server_smoke.py`:
- in-process: создаём `MCPConfig`, `server = build_server(config)`, инициализируем `Client(server, ...)` — но MCP SDK in-process Client API нужно проверить (research указал на `Client(app, raise_exceptions=True)` — но это FastMCP). Для low-level — может потребоваться MemoryStream pair. Если SDK не даёт удобный in-process — fallback на subprocess test (slow).
- Покрыть: list_tools count=9, call_tool list_pages → TextContent

`tests/mcp/test_e2e_with_daemon.py` (slow):
- Поднять daemon как subprocess (как в Plan #5 e2e), MCP server в test process через in-process call_tool
- `create_snapshot` → snapshot реально создан в vault
- `delete_snapshot` → удалён

Commit `test(mcp): in-process smoke + slow E2E with real daemon`

---

## Task 11: Manual smoke + README + merge

- [ ] Manual:
   - `mnemos daemon start --vault /tmp/test-vault`
   - В отдельном терминале: `python -m claude_mnemos.mcp --vault /tmp/test-vault < /dev/null`  
     (server заблокирует на stdin; чтоб реально smoke — лучше через `mcp` CLI client если есть, или через тест)
   - Проверить, что нет import errors, server поднялся, log в stderr читаемый
- [ ] Update README с разделом `## MCP server` и командой `claude mcp add`
- [ ] Update memory `claude_mnemos_project.md` про Plan #6
- [ ] Final pytest + ruff + mypy
- [ ] `git checkout main && git merge --no-ff feat/mcp-server -m "Merge ..."`

---

## Risks

1. **MCP SDK API на 1.12 может отличаться от research.** Если что-то не работает как описано (`Server`, `stdio_server`, `Client`) — адаптируем по факту чтения SDK кода. План не ломается.
2. **In-process Client может не быть в low-level API.** Тогда e2e smoke = subprocess (медленнее, slow marker).
3. **`asyncio.to_thread` в read tools** для file I/O — не критично для correctness, но важно для не-блокирования event loop'а MCP server'а.
4. **`yaml.safe_load` уже есть в зависимостях** (через pyyaml). Frontmatter parsing reuse существующего кода если можно (`core/frontmatter.py` если есть, иначе inline).
