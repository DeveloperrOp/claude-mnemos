# claude-mnemos

Long-term structured per-project knowledge base for Claude Code sessions.

Преемник [LLM Wiki Control Panel](../OBSIDIAN/.shared/). Самостоятельный проект, не Obsidian-companion.

## Статус

`0.0.1` — Plans #1-#13a в `main`. Готовы:

- **Ingest pipeline** (Plans #1-#2): JSONL чат → markdown vault (raw/chats + extracted wiki/entities/concepts/sources) через Claude API.
- **Транзакционный vault** (Plan #3): staging-first writes + atomic promote + pre-op snapshots + rollback.
- **Activity log + undo** (Plan #4): `.activity.json` + `mnemos undo <op_id>` / `mnemos undo --last`.
- **Daemon foundation** (Plan #5): FastAPI на `127.0.0.1:5757` + APScheduler (daily snapshot 04:00 UTC, backups cleanup 05:00 UTC, 180-day retention) + REST endpoints.
- **MCP server** (Plan #6): stdio MCP с 5 read tools (прямой доступ к vault) + 4 write tools (через REST к daemon).
- **Claude Code plugin** (Plan #7): SessionEnd auto-ingest hook + 5 skills + plugin manifest. После установки каждая сессия автоматически попадает в vault.
- **Ontology HITL** (Plan #8): `.ontology-suggestions/` Pydantic-валидируемые suggestion файлы + 3 операции (`merge_entities`, `rename_entity`, `delete_page`) + REST endpoints + 3 MCP tools + CLI subgroup. Применение через `StagingTransaction` с pre-op snapshot — undo через `mnemos undo` восстанавливает всё (sources возвращаются из trash, wikilinks переписываются обратно).
- **Watchdog real-time** (Plan #9): daemon наблюдает `wiki/*.md` через Python `watchdog`, отличает self-writes от human edits через in-memory `OurWritesTracker` (TTL set + paused() context). При external modify помечает страницу `agent_written: false` + `last_human_edit: <ts>` + пишет activity entry `human_edit_detected`. Alerts buffer (in-memory, cap 200) + endpoints `GET /alerts` / `DELETE /alerts/{id}`. `HealthResponse` расширен `watchdog_running` + `alerts_count`.
- **Lint** (Plan #10): 8 structural rules + 1 synthetic (`page_parse_failed`) — `wikilinks_broken` (with Levenshtein-typo autofix), `orphan_pages`, `stale_pages`, `duplicate_titles`, `provenance_inferred_high`, `provenance_ambiguous_high`, `trailing_whitespace`, `missing_required_frontmatter`. Cached report in `<vault>/.lint-results.json`. Safe autofix whitelist runs through `StagingTransaction` with snapshot — undo via `mnemos undo <activity_id>`. CLI `mnemos lint {run, results, autofix}`, REST `POST /lint/run|autofix` + `GET /lint/results`, MCP `run_lint` + `get_lint_results` (12→14 tools).
- **Jobs queue + Dead-letter** (Plan #11): persistent SQLite-backed queue at `<vault>/.jobs.db` (excluded from snapshots). `IngestHandler` runs the existing sync ingest in `asyncio.to_thread`, with retry policy 4 attempts × backoff 30s/2min/20min. SessionEnd hook now prefers `POST /jobs` over the detached subprocess (closes Plan #9 watchdog false-positive). REST `POST/GET/DELETE /jobs`, `GET /dead-letter`, `POST /dead-letter/{id}/retry`, `DELETE /dead-letter/{id}`. CLI `mnemos jobs {list, show, cancel, retry-dead, dismiss}`. Health response gains `jobs_queued/running/dead_letter/jobs_alert` (alert at >10 dead-letter).
- **Page edit + Trash** (Plan #12): direct page mutations (edit/verify/archive/delete) and trash management (list/restore/dismiss/empty). All mutations route through `StagingTransaction` with pre-op snapshot — undo via `mnemos undo` reverts everything. `.trash/<id>/.metadata.json` carries `original_path` so restore puts content back to its original location. REST `PATCH/POST/DELETE /pages/{ref:path}` + `GET/POST/DELETE /trash`. CLI `mnemos page {edit, verify, archive, delete}` and `mnemos trash {list, restore, dismiss, empty}`. New activity types: `manual_edit`, `manual_delete` (undoable), `manual_restore_trash` (undoable), `trash_dismissed`, `trash_emptied` (audit-only).
- **Sessions + Lost-sessions + Token metrics** (Plan #13a): backend views of session lifecycle (merged manifest IngestRecord + jobs queue), lost-session scanner over `~/.claude/projects/` with cache + ignore-list, token usage aggregations (per-period summary, per-project, top-sessions, daily timeline). Manifest extended with `transcript_path` + `raw_transcript_bytes` (cross-ref + compression metric). New state file `<vault>/.lost-sessions-ignore.json`. REST `/sessions/*` + `/lost-sessions/*` + `/metrics/usage*`. CLI `mnemos {sessions, lost-sessions, metrics} ...`. Multi-vault `by-project` returns single entry — multi-vault routing → Plan #13b.

### Plan #13b-α — Settings + project-map foundation (2026-04-27)

- `~/.claude-mnemos/project-map.json` now routes cwd → vault.
- Per-project settings: `~/.claude-mnemos/settings/<project>.json` (9 spec §12.8 groups).
- Global settings: `~/.claude-mnemos/global-settings.json`.
- New CLI: `mnemos project {add,list,show,update,remove,resolve}`,
  `mnemos settings {get,set,reset} --project NAME | --global`.
- All other CLI commands now take `--project NAME` (auto-resolves via cwd if omitted).
- Daemon at startup applies `snapshots.retention_days` + `snapshots.daily_enabled`
  for its registered vault; `PATCH /settings/{project}` reloads live (rescheduling
  daily snapshot job + backups cleanup).
- MCP server defaults to `--auto-resolve` (cwd → project-map). Falls back to
  degraded mode if no match (server stays alive, every tool returns a fix-hint
  TextContent — avoids Claude Code spawn-loop on crash).
- SessionEnd hook resolves cwd → project; unmatched cwd → silent skip
  (transcript stays in lost-sessions, picked up by `mnemos lost-sessions scan`).
- One-shot migration: PID file moved from `~/.mnemos/` to `~/.claude-mnemos/`
  (legacy files relocated automatically on daemon start, never overwritten).

#### Migration from previous versions

If you previously set `MNEMOS_VAULT_ROOT`, register your vault explicitly:

```bash
mnemos project add \
  --name claude-mnemos \
  --vault $MNEMOS_VAULT_ROOT \
  --cwd-pattern "$(dirname $MNEMOS_VAULT_ROOT)/*"
unset MNEMOS_VAULT_ROOT
```

Then restart any running daemon so it can read your project's settings.

The `MNEMOS_VAULT_ROOT` env var is no longer read by anything (CLI, hook,
MCP server, daemon).

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

## Jobs queue

Persistent job queue inside the daemon (SQLite at `<vault>/.jobs.db`). Single
asyncio worker pulls ready jobs and dispatches to `IngestHandler` (only
`kind="ingest"` in Plan #11 — Plans #12+ add lint, ontology, etc.).

```bash
mnemos jobs list --vault <path> [--status STATUS] [--limit N]
mnemos jobs show <job_id> --vault <path>
mnemos jobs cancel <job_id> --vault <path>          # queued only
mnemos jobs retry-dead <job_id> --vault <path>      # restore from dead-letter
mnemos jobs dismiss <job_id> --vault <path>         # permanent delete from dead-letter
```

REST: `POST /jobs`, `GET /jobs?status=...`, `GET /jobs/{id}`, `DELETE /jobs/{id}`,
`GET /dead-letter`, `POST /dead-letter/{id}/retry`, `DELETE /dead-letter/{id}`.

### Retry policy

- 4 attempts total: initial + 3 retries.
- Backoff between attempts: 30s, 2min, 20min.
- After the 4th failure → `dead_letter`. Auto-cleanup never (per spec §8.9).
- Health alert flips on when dead-letter > 10.

### Crash recovery

On daemon startup, every `running` job is requeued (`attempt += 1`) or moved to
`dead_letter` if that would exceed `MAX_ATTEMPTS`. ingest pipeline is idempotent
via SHA-dedup manifest, so re-running a partially-applied ingest is safe.

### SessionEnd hook integration

The hook now POSTs to `/jobs` first; if the daemon is offline it falls back to
the existing detached `mnemos ingest` subprocess. Concurrent CLI ingest with the
daemon running no longer triggers the watchdog false-positive
`human_edit_detected` (Plan #9 known limitation closed).

## Pages + Trash

Direct page edit/verify/archive/delete + trash management with snapshot+undo.

```bash
mnemos page edit wiki/entities/foo --vault <path> --frontmatter '{"status":"verified","tags":["important"]}'
mnemos page verify wiki/entities/foo --vault <path>
mnemos page archive wiki/entities/foo --vault <path>
mnemos page delete wiki/entities/foo --vault <path>      # → trash, undoable

mnemos trash list --vault <path>
mnemos trash restore <trash-id> --vault <path>           # back to original location
mnemos trash dismiss <trash-id> --vault <path>           # hard delete (no undo)
mnemos trash empty --vault <path> [--yes]                # empty all trash entries
```

REST: PATCH/POST/DELETE on `/pages/{page_ref:path}{,/verify,/archive}` + GET/POST/DELETE on `/trash`. Activity entries: `manual_edit`, `manual_delete` (undoable via `mnemos undo`), `manual_restore_trash`, `trash_dismissed`, `trash_emptied` (audit-only).

Trash entries with `.metadata.json` (`original_path`, `operation_id`, etc.) are restorable. Old trash dirs from before Plan #12 (no metadata) are listed but not restorable.

## Sessions + Metrics

Backend views on session lifecycle, lost transcripts, and token usage.

```bash
mnemos sessions list --vault <path> [--status STATUS] [--limit N]
mnemos sessions show <session_id> --vault <path>
mnemos sessions ingest <transcript_path> --vault <path>      # → POST /jobs queue

mnemos lost-sessions list --vault <path>
mnemos lost-sessions scan --vault <path>                      # rescan ~/.claude/projects/
mnemos lost-sessions import <session_id> --vault <path>       # enqueue ingest
mnemos lost-sessions ignore <session_id> --vault <path>

mnemos metrics usage --vault <path> [--period 30d]
mnemos metrics top-sessions --vault <path> [--limit 10]
mnemos metrics timeline --vault <path> [--period 30d]
```

REST: `/sessions/*` (merged manifest + jobs view), `/lost-sessions/*` (scanner with cache + ignore list), `/metrics/usage*` (summary, by-project, top-sessions, timeline). Manifest extended with `transcript_path` + `raw_transcript_bytes` for cross-ref + compression metric. New state file: `<vault>/.lost-sessions-ignore.json`.

## Запуск всех тестов

```bash
pytest -q              # быстрые (924 теста + 2 skipped)
pytest -q -m slow      # медленные E2E (11 тестов + 2 skipped: subprocess daemon + watchdog + jobs + pages E2E)
```
