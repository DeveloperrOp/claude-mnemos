# Plugin + Hooks Implementation Plan (Plan #7)

> Use TDD. Steps use checkbox (`- [ ]`).

**Goal:** Pack existing CLI/daemon/MCP into a Claude Code plugin: SessionEnd auto-ingest + 5 skills + MCP registration via `.mcp.json`. No SessionStart/PreCompact, no commands (deprecated).

**Architecture:** see `docs/plans/2026-04-26-plugin-hooks-design.md`.

**Tech stack:** Python 3.12 (hook script), JSON (manifests), YAML (skill frontmatter), pytest.

---

## Files map

**Создаём:**

```
.claude-plugin/
  plugin.json
hooks/
  hooks.json
  session_end.py
.mcp.json
skills/
  mnemos/SKILL.md
  mnemos-status/SKILL.md
  mnemos-search/SKILL.md
  mnemos-undo/SKILL.md
  mnemos-activity/SKILL.md
tests/plugin/
  __init__.py
  test_manifest.py
  test_session_end_hook.py
  test_skills.py
```

**Изменяем:**

| Файл | Что |
|---|---|
| `README.md` | Добавить раздел «Install as Claude Code plugin» |

---

## Зависимости задач

```
Task 1: manifests (.claude-plugin/, .mcp.json, hooks/hooks.json) + tests
    ↓
Task 2: SessionEnd hook script + unit tests
    ↓
Task 3: skills (5 SKILL.md) + frontmatter tests
    ↓
Task 4: README install section + manual smoke + merge + memory
```

---

## Task 1: Manifests + manifest tests

**Files create:** `.claude-plugin/plugin.json`, `.mcp.json`, `hooks/hooks.json`, `tests/plugin/__init__.py`, `tests/plugin/test_manifest.py`

- [ ] `.claude-plugin/plugin.json` — name + version + description + author
- [ ] `.mcp.json` — `mcpServers.mnemos` с `python -m claude_mnemos.mcp --vault ${MNEMOS_VAULT_ROOT}`
- [ ] `hooks/hooks.json` — `SessionEnd` → `python ${CLAUDE_PLUGIN_ROOT}/hooks/session_end.py`, blocking: false, timeout: 15
- [ ] Tests: каждый JSON parseable, обязательные поля присутствуют (`name`, `description` в plugin.json; `mcpServers.mnemos.command` в .mcp.json; `hooks.SessionEnd[0].command` в hooks.json)
- [ ] `pytest tests/plugin/test_manifest.py -q`
- [ ] Commit `feat(plugin): plugin manifest, .mcp.json, hooks/hooks.json`

---

## Task 2: SessionEnd hook script

**Files create:** `hooks/session_end.py`, `tests/plugin/test_session_end_hook.py`

- [ ] Реализация `hooks/session_end.py` по design §3.4: recursion guard → vault env → payload parsing → transcript path check → spawn detached `python -m claude_mnemos ingest <transcript> <vault>` с `MNEMOS_INGEST_RUNNING=1`
- [ ] Tests via pytest + monkeypatch:
   - recursion guard active → no spawn, exit 0
   - VAULT_ROOT not set → no spawn, exit 0, stderr message
   - invalid JSON payload → no spawn, exit 0
   - transcript_path missing in payload → no spawn, exit 0
   - transcript_path doesn't exist → no spawn, exit 0
   - happy path → Popen called with правильными args + env
   - Windows path: creationflags includes CREATE_NEW_PROCESS_GROUP
   - POSIX path: start_new_session=True
- [ ] Lint+mypy (mypy on hook script тоже)
- [ ] Commit `feat(plugin): SessionEnd hook for auto-ingest`

---

## Task 3: Skills

**Files create:** 5 `SKILL.md` файлов + `tests/plugin/test_skills.py`

- [ ] `skills/mnemos/SKILL.md` — главный behavioral prompt (см. design §3.6)
- [ ] `skills/mnemos-status/SKILL.md` — invoke `get_status` MCP tool
- [ ] `skills/mnemos-search/SKILL.md` — `argument-hint: <query>`, invoke `search_pages` с $ARGUMENTS
- [ ] `skills/mnemos-undo/SKILL.md` — `argument-hint: <op_id|--last>`, invoke `undo_operation`
- [ ] `skills/mnemos-activity/SKILL.md` — invoke `get_recent_activity`
- [ ] Tests: каждый файл существует, имеет frontmatter `---\n...\n---`, frontmatter parseable as YAML, есть `name` и `description`
- [ ] Tests: `name` совпадает с именем директории
- [ ] Commit `feat(plugin): 5 skills (mnemos main + 4 sub)`

---

## Task 4: README + merge + memory

- [ ] README раздел `## Install as Claude Code plugin` с конкретными командами:
   - `git clone` + `claude --plugin-dir $(pwd)` (dev)
   - `export MNEMOS_VAULT_ROOT=/path` (bash) + PowerShell вариант
   - `mnemos daemon start` (для write tools)
   - Описание 4 skill'ов
- [ ] Final pytest + ruff + mypy
- [ ] Manual smoke (если возможно) — `claude --plugin-dir` + проверить что hook hook'ается
- [ ] Update `claude_mnemos_project.md` memory с Plan #7
- [ ] Commit README
- [ ] `git checkout main && git merge --no-ff feat/plugin-hooks -m "..."`
