# claude-mnemos

Long-term structured per-project knowledge base for Claude Code sessions.

Преемник [LLM Wiki Control Panel](../OBSIDIAN/.shared/). Самостоятельный проект, не Obsidian-companion.

## Статус

`0.0.1` — Plans #1-#6 в `main`. Готовы:

- **Ingest pipeline** (Plans #1-#2): JSONL чат → markdown vault (raw/chats + extracted wiki/entities/concepts/sources) через Claude API.
- **Транзакционный vault** (Plan #3): staging-first writes + atomic promote + pre-op snapshots + rollback.
- **Activity log + undo** (Plan #4): `.activity.json` + `mnemos undo <op_id>` / `mnemos undo --last`.
- **Daemon foundation** (Plan #5): FastAPI на `127.0.0.1:5757` + APScheduler (daily snapshot 04:00 UTC, backups cleanup 05:00 UTC, 180-day retention) + REST endpoints.
- **MCP server** (Plan #6): stdio MCP с 5 read tools (прямой доступ к vault) + 4 write tools (через REST к daemon).

## Установка

```bash
pip install -e ".[dev]"
pytest -q
```

## CLI

```bash
# Ingest сессии в vault
mnemos ingest <session.jsonl> <vault-path>

# Activity / undo
mnemos activity --vault <path> [--limit N]
mnemos undo <op_id> --vault <path>
mnemos undo --last --vault <path>

# Daemon
mnemos daemon start --vault <path> [--port N] [--host H]
mnemos daemon status
mnemos daemon stop
mnemos daemon foreground --vault <path>   # для отладки
```

## MCP server

MCP server запускается Claude Code'ом автоматически — никакой отдельный сервис поднимать не надо. Регистрация:

```bash
claude mcp add --transport stdio mnemos -- \
  python -m claude_mnemos.mcp --vault /absolute/path/to/your/vault
```

Опционально через env:

```bash
MNEMOS_DAEMON_URL=http://127.0.0.1:5757 \
MNEMOS_MCP_LOG=info \
claude mcp add --transport stdio mnemos -- \
  python -m claude_mnemos.mcp --vault /path/to/vault
```

После регистрации в любой Claude Code сессии будут доступны 9 tools:

| Tool | Kind | Что делает |
|---|---|---|
| `list_pages(type?, flavor?, limit)` | read | Список wiki страниц с фильтрами |
| `read_page(page_ref)` | read | Прочитать конкретную страницу |
| `search_pages(query, limit)` | read | Substring grep по filename + body |
| `get_status` | read | Vault summary (counts, snapshots, size) |
| `get_recent_activity(limit)` | read | Последние activity entries |
| `undo_operation(op_id)` | write | Откатить операцию через daemon |
| `create_snapshot(label?)` | write | Создать manual snapshot |
| `restore_snapshot(name)` | write | Восстановить vault из snapshot'а |
| `delete_snapshot(name)` | write | Удалить snapshot |

**Read tools** работают без daemon'а — читают файлы напрямую. **Write tools** требуют запущенный daemon (`mnemos daemon start`); если daemon offline — возвращают понятное сообщение со ссылкой на нужную команду.

## Структура

```
claude_mnemos/
  core/      # примитивы: locks, atomic_write, snapshots, undo
  state/     # state-файлы (manifest, activity) и их инварианты
  ingest/    # pipeline ингеста чатов в vault через Claude API
  daemon/    # FastAPI + APScheduler + REST endpoints
  mcp/       # MCP server (stdio) с read+write tools
  cli.py     # `mnemos` entrypoint
tests/
docs/plans/  # design + impl plans для каждого Plan #N
```

## Запуск всех тестов

```bash
pytest -q              # быстрые (~395 тестов)
pytest -q -m slow      # медленные E2E (subprocess daemon)
```
