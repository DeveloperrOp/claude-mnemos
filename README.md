# claude-mnemos

Long-term structured per-project knowledge base for Claude Code sessions.

Преемник [LLM Wiki Control Panel](../OBSIDIAN/.shared/). Самостоятельный проект, не Obsidian-companion.

## Статус

`0.0.1` — Plans #1-#10 в `main`. Готовы:

- **Ingest pipeline** (Plans #1-#2): JSONL чат → markdown vault (raw/chats + extracted wiki/entities/concepts/sources) через Claude API.
- **Транзакционный vault** (Plan #3): staging-first writes + atomic promote + pre-op snapshots + rollback.
- **Activity log + undo** (Plan #4): `.activity.json` + `mnemos undo <op_id>` / `mnemos undo --last`.
- **Daemon foundation** (Plan #5): FastAPI на `127.0.0.1:5757` + APScheduler (daily snapshot 04:00 UTC, backups cleanup 05:00 UTC, 180-day retention) + REST endpoints.
- **MCP server** (Plan #6): stdio MCP с 5 read tools (прямой доступ к vault) + 4 write tools (через REST к daemon).
- **Claude Code plugin** (Plan #7): SessionEnd auto-ingest hook + 5 skills + plugin manifest. После установки каждая сессия автоматически попадает в vault.
- **Ontology HITL** (Plan #8): `.ontology-suggestions/` Pydantic-валидируемые suggestion файлы + 3 операции (`merge_entities`, `rename_entity`, `delete_page`) + REST endpoints + 3 MCP tools + CLI subgroup. Применение через `StagingTransaction` с pre-op snapshot — undo через `mnemos undo` восстанавливает всё (sources возвращаются из trash, wikilinks переписываются обратно).
- **Watchdog real-time** (Plan #9): daemon наблюдает `wiki/*.md` через Python `watchdog`, отличает self-writes от human edits через in-memory `OurWritesTracker` (TTL set + paused() context). При external modify помечает страницу `agent_written: false` + `last_human_edit: <ts>` + пишет activity entry `human_edit_detected`. Alerts buffer (in-memory, cap 200) + endpoints `GET /alerts` / `DELETE /alerts/{id}`. `HealthResponse` расширен `watchdog_running` + `alerts_count`.
- **Lint** (Plan #10): 8 structural rules + 1 synthetic (`page_parse_failed`) — `wikilinks_broken` (with Levenshtein-typo autofix), `orphan_pages`, `stale_pages`, `duplicate_titles`, `provenance_inferred_high`, `provenance_ambiguous_high`, `trailing_whitespace`, `missing_required_frontmatter`. Cached report in `<vault>/.lint-results.json`. Safe autofix whitelist runs through `StagingTransaction` with snapshot — undo via `mnemos undo <activity_id>`. CLI `mnemos lint {run, results, autofix}`, REST `POST /lint/run|autofix` + `GET /lint/results`, MCP `run_lint` + `get_lint_results` (12→14 tools).

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

# Ontology (HITL suggestions)
mnemos ontology propose merge \
  --source wiki/entities/foo.md --source wiki/entities/bar.md \
  --target wiki/entities/foobar.md --reason "..." --vault <path>
mnemos ontology propose rename --source old.md --target new.md --vault <path>
mnemos ontology propose delete --source orphan.md --vault <path>
mnemos ontology list --vault <path> [--all]
mnemos ontology approve <id> --vault <path>
mnemos ontology reject <id> --vault <path>
mnemos ontology defer <id> --vault <path>
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
| `list_suggestions(status?)` | read | Список ontology suggestions |
| `apply_ontology_suggestion(id)` | write | Применить suggestion (merge/rename/delete) |
| `propose_ontology_change(...)` | write | Создать новый suggestion |

**Read tools** работают без daemon'а — читают файлы напрямую. **Write tools** требуют запущенный daemon (`mnemos daemon start`); если daemon offline — возвращают понятное сообщение со ссылкой на нужную команду.

## Install as Claude Code plugin

Plugin упаковывает CLI/daemon/MCP вместе с SessionEnd hook'ом и 5 skills. После установки каждая Claude Code сессия автоматически уходит в vault через hook, и LLM в чате видит мнемос-tools без необходимости вручную регистрировать MCP.

**Установка (dev mode):**

```bash
git clone <repo-url>
cd claude-mnemos
pip install -e .

# Настроить vault path как env var (single source of truth)
export MNEMOS_VAULT_ROOT=/absolute/path/to/your/vault     # bash/zsh
# либо:
[Environment]::SetEnvironmentVariable('MNEMOS_VAULT_ROOT', 'C:\path\to\vault', 'User')   # PowerShell

# Запустить daemon (нужен для write tools и snapshots)
mnemos daemon start

# Подключить плагин в Claude Code
claude --plugin-dir $(pwd)
```

После этого каждая сессия после закрытия → auto-ingest в vault через `hooks/session_end.py`.

**5 skills:**

| Skill | Что делает |
|---|---|
| `mnemos` | Главный behavioral prompt — даёт LLM понимание что есть mnemos и когда его дёргать |
| `/mnemos-status` | Показать summary vault'а |
| `/mnemos-search <query>` | Substring search по vault'у |
| `/mnemos-undo [op_id\|--last]` | Откатить операцию |
| `/mnemos-activity [limit]` | Последние записи activity log |

**Структура плагина:**

```
.claude-plugin/plugin.json     # манифест плагина
.mcp.json                       # регистрация MCP server'а
hooks/
  hooks.json                    # SessionEnd registration
  session_end.py                # spawn detached `mnemos ingest`
skills/
  mnemos/SKILL.md               # главный behavioral
  mnemos-{status,search,undo,activity}/SKILL.md
```

## Структура

```
claude_mnemos/
  core/      # примитивы: locks, atomic_write, snapshots, undo, wikilinks, ontology_apply
  state/     # state-файлы (manifest, activity, ontology suggestions)
  ingest/    # pipeline ингеста чатов в vault через Claude API
  daemon/    # FastAPI + APScheduler + REST endpoints
  mcp/       # MCP server (stdio) с read+write tools
  cli.py     # `mnemos` entrypoint
tests/
docs/plans/  # design + impl plans для каждого Plan #N
```

## Watchdog real-time

После `mnemos daemon start` daemon наблюдает за `wiki/*.md` через Python `watchdog`. Любое внешнее изменение (через Obsidian, IDE, любой текстовый редактор) детектируется в течение ~1 секунды:

- **External modify** → page marked `agent_written: false` + `last_human_edit: <ts>` (Obsidian-extras в frontmatter сохраняются при round-trip), активность пишется в `.activity.json` как `human_edit_detected` (non-undoable).
- **External create/rename** → alert (mutation не делается; user сам решает).
- **Frontmatter parsing failed** → alert; файл не трогается.
- **Pipeline lock timeout** → alert (на ваш ingest pipeline нет race).

Что наблюдается / нет:

| Path | Поведение |
|---|---|
| `wiki/**/*.md` | Watched |
| `raw/**`, `.staging/`, `.backups/`, `.trash/`, `.ontology-suggestions/`, `.obsidian/`, `.git/` | Skipped |
| Non-`.md` файлы под `wiki/` | Skipped |

Inspecting alerts:

```bash
curl http://127.0.0.1:5757/alerts
curl -X DELETE http://127.0.0.1:5757/alerts/<id>
curl http://127.0.0.1:5757/health  # содержит watchdog_running + alerts_count
```

**Известные ограничения:**

- Если CLI `mnemos ingest` запускается параллельно с daemon'ом, их writes могут пометиться daemon'ом как `human_edit_detected` (false positive). В стандартном flow (auto-ingest через SessionEnd hook → не concurrent с user editing) это не возникает. Закроется в Plan #11+, когда daemon станет orchestrator'ом ingest'а.
- Alerts хранятся только в памяти (cap 200) — теряются при restart daemon'а. Persistence — Plan #11+.
- Один daemon наблюдает один vault. Multi-vault — Plan #13.
- Debouncing batch external changes (replace-all из IDE) не реализован — handler обрабатывает каждый event отдельно.

## Lint

Health-check the wiki: 8 structural rules + 1 synthetic for parse failures.

```bash
mnemos lint run --vault <path>
mnemos lint results --vault <path> [--severity error|warning|info]
mnemos lint autofix --vault <path> [--dry-run]
```

### Rules

| ID | Severity | Autofix |
|---|---|---|
| `wikilinks_broken` | warning | typo fix (Levenshtein ≤ 2 unique) |
| `orphan_pages` | warning | — |
| `stale_pages` | info | — |
| `duplicate_titles` | warning | — |
| `provenance_inferred_high` (>=50%) | info | — |
| `provenance_ambiguous_high` (>30%) | info | — |
| `trailing_whitespace` | info | strip |
| `missing_required_frontmatter` | warning | (placeholder, no-op) |
| `page_parse_failed` (synthetic) | error | — |

REST: `POST /lint/run`, `GET /lint/results`, `POST /lint/autofix`. MCP: `run_lint` (write, daemon required), `get_lint_results` (read, direct file). Autofix runs through `StagingTransaction` with snapshot — undo via `mnemos undo <activity_id>`. Concurrent ingest is serialized by `pipeline_lock`.

### Known limitations

- LLM-powered rules (`contradictions_between_pages`) — Plan #11+.
- Auto-stale state transition (`draft → stale` after 90 days) — Plan #11+ via `core/lifecycle.py`.
- Scheduled weekly lint via APScheduler — Plan #11+.
- Lint-driven ontology suggestions for low-confidence wikilinks fixes — Plan #11+.

## Запуск всех тестов

```bash
pytest -q              # быстрые (~690 тестов)
pytest -q -m slow      # медленные E2E (subprocess daemon + watchdog)
```
