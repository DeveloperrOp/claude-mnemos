# claude-mnemos

> Long-term memory for Claude Code. Sessions become structured per-project knowledge bases in Obsidian-compatible vaults.

Claude Code holds context only within one session. **claude-mnemos** stores every conversation as atomic markdown wiki pages in your vault, then injects the most relevant ones into the next session's system prompt — so Claude effectively remembers what you did before.

## Status

`0.0.1` — early development. Single-user, runs locally, no server-side anything. Not on PyPI yet — install from source.

## Install

Recommended path uses **pipx** (industry-standard isolated installer for Python CLI tools). System-Python `pip install -e .` is documented as a fallback but **not recommended** — it produces dependency conflicts and orphan files over time.

### Get the source

```bash
git clone https://github.com/<your-fork>/claude-mnemos.git
cd claude-mnemos
```

### Install via pipx (recommended)

If you don't have pipx yet:

```bash
# Windows
py -3.12 -m pip install --user pipx
py -3.12 -m pipx ensurepath

# macOS / Linux
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

Open a new terminal so pipx is on `PATH`, then install mnemos editable:

```bash
pipx install --editable . --python 3.12
```

This puts mnemos in an isolated venv (`~/pipx/venvs/claude-mnemos/` on Windows, `~/.local/share/pipx/venvs/claude-mnemos/` on Unix) and publishes three commands on your `PATH`: `mnemos`, `mnemos-mcp`, `mnemos-tray`.

To upgrade later: `cd <path> && git pull && pipx reinstall claude-mnemos`. To uninstall cleanly: `pipx uninstall claude-mnemos`.

### Fallback: pip in your own venv

If you prefer manual venv management:

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\Activate.ps1         # Windows PowerShell
pip install -e .
```

You'll need to activate that venv every time before running mnemos commands. pipx avoids that step.

**Avoid:** `pip install -e .` directly into system Python. It works at first, but every future `pip install <other-package>` may conflict with mnemos's pinned deps; partial uninstalls leave orphan files behind.

### Verify

```bash
mnemos --version
mnemos --help
```

You should see subcommands (`project`, `daemon`, `tray`, `settings`, `ingest`, `lint`, `ontology`, …).

Python requirement: 3.12+.

## Quickstart

```bash
# 1. Authenticate Claude Code (uses your Pro/Max subscription — no separate API key needed)
claude login
claude -p "hi"            # smoke test

# 2. Create a project (registers a vault and CWD patterns)
mnemos project add my-project \
  --vault ~/code/my-project/.mnemos \
  --cwd-pattern "~/code/my-project/**"

# 3. Start the daemon (FastAPI on 127.0.0.1:5757)
mnemos daemon start

# 4. (Optional) Tray icon + autostart on every login
mnemos tray install
```

Then open `http://localhost:5757/` — the dashboard is live.

Now run Claude Code in a folder covered by your CWD patterns. After you exit, the session JSONL gets ingested automatically into the vault. Re-launch Claude in the same folder, and the SessionStart hook injects the most relevant pages into the system prompt.

## How it works

```
┌──────────────────┐                      ┌─────────────────────────┐
│  Claude Code     │  finishes session    │  ~/.claude/projects/    │
│  session         ├────────────────────►│  <hash>/<uuid>.jsonl     │
└──────────────────┘                      └────────────┬────────────┘
                                                       │ watchdog detects new file
                                                       ▼
                                          ┌─────────────────────────┐
                                          │  daemon (5757)          │
                                          │  ingest job → LLM       │
                                          │  extracts atomic facts  │
                                          └────────────┬────────────┘
                                                       │ writes via StagingTransaction
                                                       ▼
                                          ┌─────────────────────────┐
                                          │  vault/                 │
                                          │   wiki/                 │
                                          │     entities/*.md       │
                                          │     concepts/*.md       │
                                          │     sources/*.md        │
                                          │   .activity.json        │
                                          │   snapshots/            │
                                          └────────────┬────────────┘
                                                       │
┌──────────────────┐  start session       ┌────────────▼────────────┐
│  Claude Code     │◄─────────────────────┤  SessionStart hook      │
│  (next time,     │  inject top-N pages  │  scores pages by graph  │
│  same folder)    │   into system prompt │  proximity + freshness  │
└──────────────────┘                      └─────────────────────────┘
```

Two operations, both transparent to the user:

- **Ingest** — closed Claude session → LLM extracts atomic facts → markdown pages.
- **Inject** — new Claude session in the same folder → relevant pages auto-loaded into the system prompt.

## Dashboard

`http://localhost:5757/` (served by the daemon). React 19 + Tailwind v4 + shadcn/ui SPA, three locales (uk/ru/en), light/dark/system theme toggle.

Pages:

| Page | What |
|---|---|
| Overview | Project list with health, session counts, queue stats |
| Pages | Browse vault wiki pages by type (entity/concept/source) with frontmatter view + edit |
| Sessions | Ingested-session list per project (status, tokens, errors) |
| Lost | JSONL transcripts whose CWD didn't match any project — import or ignore |
| Queue | Live job queue with retry/cancel controls |
| Activity | Operation log (ingests, edits, merges, deletes) with one-click undo |
| Suggestions | HITL ontology proposals (merge / rename / delete) — approve, reject, defer |
| Trash | Soft-deleted pages (30-day retention by default) — restore or hard-delete |
| Snapshots | Daily and pre-op vault snapshots — create / restore / delete |
| Health | Watchdog + scheduler status, alerts, daemon uptime |
| Dead-letter | Failed jobs with traceback, retry / dismiss |
| Metrics | Token usage charts (input/output/compression) per period |
| Settings | Per-project + global settings (12-section accordion), CWD builder, vault path |
| Help | Concepts, workflows, troubleshooting, glossary — multi-language |

Theme toggle (`Sun`/`Moon`/`Monitor` icon) cycles `system → light → dark`, persists to `localStorage`. The visual language is IDE/terminal-inspired: Geist Sans / Mono fonts, lime acid accent (`oklch(70% 0.22 130)` light, `oklch(85% 0.27 130)` dark), monospace section labels in `SECTION ▸ VALUE` pattern.

## CLI

```bash
# Project management
mnemos project {add,list,show,update,remove,resolve}
mnemos settings {get,set,reset} [--project NAME | --global]

# Daemon
mnemos daemon {start,stop,status,foreground}

# Tray (Win/Mac autostart)
mnemos tray {install,uninstall,start,run,status}

# Ingest pipeline
mnemos ingest <jsonl> [--project NAME | --vault PATH]
mnemos sessions {list,show,ingest}
mnemos lost-sessions {list,scan,import,ignore}

# Vault operations
mnemos page {edit,verify,archive,delete}
mnemos trash {list,restore,dismiss,empty}
mnemos activity [--limit N]
mnemos undo <op_id> | --last

# Queue + retry
mnemos jobs {list,show,cancel,retry-dead,dismiss}

# Quality
mnemos lint {run,results,autofix}
mnemos ontology {propose,list,approve,reject,defer}

# Metrics
mnemos metrics {usage,top-sessions,timeline}
```

All vault-touching commands take `--project NAME` (auto-resolved from CWD if omitted) or `--vault PATH` (direct).

## Plugin install (Claude Code)

The plugin bundles the CLI/daemon/MCP server with a SessionEnd hook and 5 skills. After install, every Claude Code session auto-ingests into the vault, and the LLM in chat sees mnemos tools without manual MCP registration.

```bash
mnemos daemon start                     # write tools and snapshots need this
claude --plugin-dir $(pwd)              # from the cloned repo root
```

Skills exposed: `mnemos` (main behavioral prompt), `/mnemos-status`, `/mnemos-search`, `/mnemos-undo`, `/mnemos-activity`.

## MCP server (manual, alternative to plugin)

```bash
claude mcp add --transport stdio mnemos -- mnemos-mcp --auto-resolve
```

12 tools exposed (5 read direct + 7 write through daemon REST). See `claude_mnemos/mcp/__main__.py` for the full list.

## Architecture

```
claude_mnemos/
  core/         # primitives: locks, atomic write, snapshots, undo, wikilinks, ontology apply
  state/        # state files: manifest, activity, ontology suggestions, jobs (SQLite)
  ingest/       # JSONL → markdown pipeline through Claude API or CLI subscription
  daemon/       # FastAPI + APScheduler + REST endpoints + watchdog + jobs worker
  mcp/          # stdio MCP server with read/write tools
  tray/         # Pystray icon + supervisor (auto-restart daemon, autostart on login)
  hooks/        # SessionEnd / SessionStart hooks
  cli.py        # `mnemos` entrypoint
frontend/
  src/          # React 19 + Tailwind v4 + shadcn/ui dashboard
  public/       # static assets, locales (uk/ru/en), Geist Sans + Mono fonts
tests/          # 1488 fast pytest + 11 slow E2E (subprocess daemon, watchdog, jobs, pages)
docs/plans/     # design + implementation plans for each Plan #N (the project's history)
```

The daemon serves the built React SPA from `claude_mnemos/daemon/static/` (output of `pnpm build`), so a single `mnemos daemon start` gives both the API and the dashboard.

## Development

### Run backend tests

```bash
# pipx-installed mnemos has the test deps via pipx inject:
pipx inject claude-mnemos pytest pytest-cov pytest-asyncio

# Then run:
"$(pipx environment --value PIPX_HOME)/venvs/claude-mnemos/Scripts/python.exe" -m pytest tests/ -m "not slow"
# or under the venv directly: ~/pipx/venvs/claude-mnemos/bin/pytest tests/ -m "not slow"

# Or with a manual venv:
pip install -e ".[dev]"
pytest tests/ -m "not slow"        # 1488 fast tests
pytest tests/ -m slow              # 11 slow E2E tests
```

### Frontend

```bash
cd frontend
pnpm install
pnpm vitest run        # 307 tests
pnpm lint              # 0 errors expected
pnpm build             # writes to ../claude_mnemos/daemon/static/
pnpm dev               # vite dev server (separate from daemon — unusual; daemon serves the built dist)
```

### Project history

`docs/plans/` contains design + implementation specs for every major change (Plan #1 through Plan #14 series, Plan A/B settings UI, dashboard redesign, etc.). Each major feature lives as `YYYY-MM-DD-<name>-design.md` + `YYYY-MM-DD-<name>-plan.md`.

## License

MIT. See `pyproject.toml`.

## Contributing

The repo is currently private and single-author. PRs welcome once it's open-sourced — for now, the design specs in `docs/plans/` are the entry point for understanding any subsystem.
