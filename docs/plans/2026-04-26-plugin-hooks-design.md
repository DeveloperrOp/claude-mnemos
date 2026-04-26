# Design: Claude Code Plugin Manifest + SessionEnd Hook + Skills (Plan #7)

**Status:** drafted, awaiting Yarik approval before implementation-plan generation.
**Date:** 2026-04-26
**Author:** Claude (with Yarik approval).
**Predecessor:** `2026-04-26-mcp-server-design.md` (Plan #6, merged in `053ae87`).
**Successor planned:** Plan #8 (frontend dashboard) → Plan #9 (ontology) → Plan #10 (watchdog) → Plan #11 (tiered_query, lint, add_entity).

---

## 1. Goal

Упаковать существующий код (CLI + daemon + MCP) в **Claude Code plugin** так, чтобы:

1. Пользователь делает `claude --plugin-dir /path/to/claude-mnemos` (или `claude plugins install …`) и получает **всё работающее**: MCP tools зарегистрированы, hooks подключены, skills доступны.
2. **Auto-ingest каждой сессии** через `SessionEnd` hook — пользователь больше не вызывает `mnemos ingest` руками. После завершения каждой Claude Code сессии плагин в фоне пускает ingest на `transcript_path` из payload'а.
3. **Skills** обёртывают самые частые операции (`/mnemos-status`, `/mnemos-search <query>`, `/mnemos-undo <op_id>`) — короткий путь для частых команд через MCP tools, без необходимости LLM писать tool-call синтаксис вручную.

После Plan #7 пользователь:

```bash
# 1. Один раз
claude --plugin-dir /path/to/claude-mnemos
# (или claude plugins install <git-repo>)

# 2. Запустить daemon (для write tools и hook'а)
mnemos daemon start --vault /path/to/your/vault
export MNEMOS_VAULT_ROOT=/path/to/your/vault

# 3. Работать в Claude Code как обычно — каждая сессия после завершения
#    автоматически попадает в vault через SessionEnd hook
```

### Что НЕ даёт (явно отложено)

- **SessionStart adaptive context** (spec §9.2) → Plan #11+. Нужен `tiered_query` модуль (hot.md → index → grep) — нет такого. Пустой SessionStart hook добавлять не буду — без adaptive context он бесполезен.
- **PreCompact hook** → Plan #11+. Без `flush_worker` (lightweight ingest) тоже бесполезен. Полный ingest на PreCompact = слишком тяжело и дорого LLM tokens.
- **Marketplace.json submission** → Plan #12+. Сначала dogfooding, потом релиз.
- **`add_entity`, `query_wiki`, `run_lint`, `apply_ontology_suggestion` skills** → Plan #9/#11+ (вместе с соответствующими модулями).
- **Multi-vault routing** через project_map.json → Plan #11+ (как и в Plans #5/#6 — single vault).
- **Daemon ingest endpoint `POST /api/ingest/sessions/{sid}`** → Plan #11+. Hook идёт прямо к CLI subprocess `mnemos ingest`. Daemon-as-orchestrator подождёт.

---

## 2. Scope

### 2.1 In scope

| Компонент | Где | Зачем |
|---|---|---|
| Plugin manifest | `.claude-plugin/plugin.json` | Декларирует имя/версию/описание плагина |
| Hooks manifest | `hooks/hooks.json` | Регистрирует `SessionEnd` hook |
| SessionEnd auto-ingest | `hooks/session_end.py` | Spawn detached `mnemos ingest <transcript_path> $MNEMOS_VAULT_ROOT` (с recursion guard) |
| MCP server registration | `.mcp.json` (root плагина) | Регистрирует `mnemos` stdio MCP server из Plan #6 без `claude mcp add` |
| Главный skill (behavioral) | `skills/mnemos/SKILL.md` | LLM знает что у него есть наш MCP + как им пользоваться |
| Status skill | `skills/mnemos-status/SKILL.md` | `/mnemos-status` → invoke `get_status` MCP tool |
| Search skill | `skills/mnemos-search/SKILL.md` | `/mnemos-search <query>` → invoke `search_pages` |
| Undo skill | `skills/mnemos-undo/SKILL.md` | `/mnemos-undo <op_id>` → invoke `undo_operation` |
| Activity skill | `skills/mnemos-activity/SKILL.md` | `/mnemos-activity` → invoke `get_recent_activity` |
| Recursion guard в hook'е | `MNEMOS_INGEST_RUNNING=1` env передаётся в subprocess | Защита от того чтоб ingest worker не триггерил новый SessionEnd hook |
| Tests: hook script | `tests/plugin/test_session_end_hook.py` | unit-тесты hook'а: payload parsing, recursion guard, vault resolution, subprocess spawn |
| Tests: manifest validity | `tests/plugin/test_manifest.py` | JSON parseable, обязательные поля есть |
| Tests: skills frontmatter | `tests/plugin/test_skills.py` | YAML frontmatter валиден в каждом SKILL.md |
| README раздел | `README.md` | Как установить и пользоваться плагином |

### 2.2 Out of scope (явно отложено)

| Component | План |
|---|---|
| `SessionStart` hook adaptive context | Plan #11+ (нужен `tiered_query` + `hot.md`) |
| `PreCompact` hook flush worker | Plan #11+ |
| `add_entity`, `query_wiki`, `run_lint`, `apply_ontology` skills | Plan #9/#11+ (когда tools появятся в MCP) |
| `marketplace.json` для Anthropic Marketplace | Plan #12+ |
| Per-project routing (`project_map.json`) | Plan #11+ |
| Daemon ingest endpoint (`POST /api/ingest/...`) | Plan #11+ |
| MCP server auth | Plan #12+ |
| `references/*.md` глубокие skill references (ingest-prompts, lint-rules, etc.) | Plan #11+ когда соответствующие фичи появятся |
| Auto-start daemon из hook'а | Plan #11+ (сложно: race conditions с CLI start, тяжёлая логика; пока пользователь сам стартует) |
| Skill с `disable-model-invocation: true` (только user invoke) | YAGNI пока |

---

## 3. Architecture

### 3.1 Plugin layout

```
claude-mnemos/                    # repo root (наш существующий проект)
├── .claude-plugin/
│   └── plugin.json               # NEW
├── hooks/
│   ├── hooks.json                # NEW
│   └── session_end.py            # NEW
├── skills/                       # NEW
│   ├── mnemos/
│   │   └── SKILL.md
│   ├── mnemos-status/SKILL.md
│   ├── mnemos-search/SKILL.md
│   ├── mnemos-undo/SKILL.md
│   └── mnemos-activity/SKILL.md
├── .mcp.json                     # NEW — registers mnemos MCP server
├── claude_mnemos/                # existing Python package
├── tests/plugin/                 # NEW
└── ...
```

### 3.2 Plugin manifest (`.claude-plugin/plugin.json`)

```json
{
  "$schema": "https://claude.com/schemas/plugin/v1.json",
  "name": "claude-mnemos",
  "version": "0.0.1",
  "description": "Per-project memory and structured wiki for Claude Code. Auto-ingest sessions, search vault, undo operations.",
  "author": { "name": "Yarik" }
}
```

Минимум — `name` + `description` (по docs). Остальное опционально.

### 3.3 Hooks manifest (`hooks/hooks.json`)

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/session_end.py",
        "timeout_seconds": 15,
        "blocking": false
      }
    ]
  }
}
```

`blocking: false` — hook не задерживает закрытие сессии. Spawn detached subprocess + exit 0 быстро.

### 3.4 SessionEnd hook script

```python
# hooks/session_end.py
import json
import os
import subprocess
import sys
from pathlib import Path

VAULT_ENV = "MNEMOS_VAULT_ROOT"
RECURSION_ENV = "MNEMOS_INGEST_RUNNING"


def main() -> int:
    # Recursion guard: ingest worker shouldn't re-trigger SessionEnd
    if os.environ.get(RECURSION_ENV) == "1":
        return 0

    vault = os.environ.get(VAULT_ENV)
    if not vault:
        # No vault configured — soft-skip, don't block
        print("mnemos: MNEMOS_VAULT_ROOT not set; skipping auto-ingest", file=sys.stderr)
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        print("mnemos: invalid hook payload; skipping", file=sys.stderr)
        return 0

    transcript = payload.get("transcript_path")
    if not transcript:
        print("mnemos: no transcript_path in payload; skipping", file=sys.stderr)
        return 0

    transcript_path = Path(transcript)
    if not transcript_path.is_file():
        print(f"mnemos: transcript {transcript} not found; skipping", file=sys.stderr)
        return 0

    # Spawn detached `mnemos ingest <transcript> <vault>`
    cmd = [sys.executable, "-m", "claude_mnemos", "ingest", str(transcript_path), vault]
    env = {**os.environ, RECURSION_ENV: "1"}
    popen_kwargs = {"stdin": subprocess.DEVNULL, "env": env}
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
        popen_kwargs["stdout"] = subprocess.DEVNULL
        popen_kwargs["stderr"] = subprocess.DEVNULL
    else:
        popen_kwargs["start_new_session"] = True

    subprocess.Popen(cmd, **popen_kwargs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Поведение в edge cases:**
- `MNEMOS_VAULT_ROOT` не задан → soft-skip + stderr message. Пользователь сам поймёт после первой сессии что забыл.
- Невалидный payload → soft-skip.
- `transcript_path` не существует → soft-skip.
- Hook **никогда не блокирует** Claude Code (timeout=15s, blocking=false, мгновенный spawn-и-выход).

### 3.5 MCP server registration (`.mcp.json`)

```json
{
  "mcpServers": {
    "mnemos": {
      "command": "python",
      "args": ["-m", "claude_mnemos.mcp", "--vault", "${MNEMOS_VAULT_ROOT}"],
      "env": {}
    }
  }
}
```

Pattern `mcpServers` (как в Claude Code main `.mcp.json`). При установке плагина пользователь только должен один раз `export MNEMOS_VAULT_ROOT=/path/to/vault` — это решает и hook, и MCP, и daemon (последний идёт через CLI с `--vault`).

**Decision: env var `MNEMOS_VAULT_ROOT` — single source of truth для plugin.** Vault path не пишется в `.mcp.json` напрямую (был бы hardcoded), не приходит из cwd (рискованно если пользователь работает в подпапках). Env var — единственный способ.

### 3.6 Skills

Главный skill (`skills/mnemos/SKILL.md`) — поведенческий промпт для LLM:

```markdown
---
name: mnemos
description: |
  Long-term per-project memory via mnemos vault.
  Use when user asks to: search past decisions, undo operations,
  look up entities/concepts, see project status, manage snapshots.
---

# claude-mnemos

You have access to MCP tools provided by the `mnemos` server. They expose:

**Read** (no daemon needed):
- `list_pages(type?, flavor?, limit)` — browse wiki
- `read_page(page_ref)` — read a specific page
- `search_pages(query, limit)` — substring search
- `get_status` — vault summary
- `get_recent_activity(limit)` — recent operations

**Write** (require running daemon `mnemos daemon start`):
- `undo_operation(op_id)` — undo by activity id
- `create_snapshot(label?)` / `restore_snapshot(name)` / `delete_snapshot(name)` — snapshot management

**When to invoke:**
- User asks about past work / decisions → `search_pages` or `read_page`
- User says "undo" / "revert" / "rollback" → `get_recent_activity` to find op_id, then `undo_operation`
- User wants to know vault state → `get_status`
- Before risky operation → suggest `create_snapshot` so user can rollback

**Always** prefer mnemos tools over guessing from chat history.
```

Sub-skills (короткие, делают одну вещь):

```markdown
<!-- skills/mnemos-status/SKILL.md -->
---
name: mnemos-status
description: Show mnemos vault summary — counts of pages, snapshots, recent activity.
---

Invoke `get_status` MCP tool from the `mnemos` server. Render the JSON to user
as a short table.
```

```markdown
<!-- skills/mnemos-search/SKILL.md -->
---
name: mnemos-search
description: Search mnemos vault by substring. Use when user wants to find past mentions of a topic.
argument-hint: "<query>"
---

User query: $ARGUMENTS

Invoke `search_pages` MCP tool with `query=$ARGUMENTS, limit=20`. If results,
list paths + snippets. If empty, say so and suggest broader query.
```

```markdown
<!-- skills/mnemos-undo/SKILL.md -->
---
name: mnemos-undo
description: Undo a previously logged mnemos operation by activity id (or last undoable).
argument-hint: "<op_id|--last>"
---

If $ARGUMENTS is `--last` or empty, first invoke `get_recent_activity` and pick
the newest with `can_undo: true`. Otherwise treat $ARGUMENTS as op_id.

Then invoke `undo_operation(op_id)`. Tell user what was reverted.

Requires running daemon: if response contains "daemon not reachable", tell user
to run `mnemos daemon start --vault $MNEMOS_VAULT_ROOT` first.
```

```markdown
<!-- skills/mnemos-activity/SKILL.md -->
---
name: mnemos-activity
description: Show recent mnemos activity entries.
argument-hint: "[limit]"
---

Invoke `get_recent_activity` MCP tool with limit=${ARGUMENTS:-10}.
Render entries newest-first with operation_type, timestamp, undo hint.
```

### 3.7 Module map

**Создаётся (всё новое — outside `claude_mnemos/` package):**

| Файл | Ответственность |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `hooks/hooks.json` | Hooks registration |
| `hooks/session_end.py` | Auto-ingest спавнер |
| `.mcp.json` | MCP server registration |
| `skills/mnemos/SKILL.md` | Главный behavioral prompt |
| `skills/mnemos-status/SKILL.md` | |
| `skills/mnemos-search/SKILL.md` | |
| `skills/mnemos-undo/SKILL.md` | |
| `skills/mnemos-activity/SKILL.md` | |
| `tests/plugin/__init__.py` | |
| `tests/plugin/test_manifest.py` | JSON validity, обязательные поля |
| `tests/plugin/test_session_end_hook.py` | Hook script behaviour |
| `tests/plugin/test_skills.py` | YAML frontmatter валиден в каждом SKILL.md |

**Изменяется:**

| Файл | Что |
|---|---|
| `pyproject.toml` | `[tool.hatch.build.targets.wheel.force-include]` добавить `.claude-plugin/`, `hooks/`, `skills/`, `.mcp.json` если хотим распространять через pip (пока не делаем — distribution via git clone + plugin-dir) |
| `README.md` | Раздел «Install as Claude Code plugin» с конкретной командой |

---

## 4. Распространение

В Plan #7 — **только локальная разработка**: пользователь делает `git clone` + `claude --plugin-dir <path>`. Подключение по абсолютному пути.

`pip install claude-mnemos` всё ещё работает для CLI/daemon/MCP стандалонно (как сейчас). Но плагин (hooks + skills + plugin.json) — отдельно через `--plugin-dir`.

Версия в `plugin.json` синхронизирована с `pyproject.toml` вручную (0.0.1 → 0.1.0 → ... — пока не автоматизируем).

Marketplace publication — Plan #12+, после dogfooding.

---

## 5. Single source of truth для vault path

| Component | Source |
|---|---|
| `mnemos ingest` CLI | argv `<vault>` |
| `mnemos daemon start` | `--vault` или `MNEMOS_VAULT_ROOT` env |
| `mnemos-mcp` | `--vault` argv (обязательно) |
| `.mcp.json` (plugin) | `${MNEMOS_VAULT_ROOT}` интерполируется Claude Code'ом при spawn |
| `hooks/session_end.py` | `MNEMOS_VAULT_ROOT` env |

**Decision:** пользователь экспортит `MNEMOS_VAULT_ROOT` в shell rc (`.bashrc`/`.zshrc`/`$PROFILE`) — один раз. Все компоненты плагина это видят. CLI команды (ingest/daemon) могут override через флаг.

В README дам conкретную команду:

```bash
# bash/zsh
echo 'export MNEMOS_VAULT_ROOT=/absolute/path/to/your/vault' >> ~/.bashrc

# PowerShell
[Environment]::SetEnvironmentVariable('MNEMOS_VAULT_ROOT', 'C:\path\to\vault', 'User')
```

---

## 6. Concurrency / safety

1. **Recursion guard.** SessionEnd hook spawn'ит ingest worker; ingest worker НЕ должен триггерить SessionEnd хук рекурсивно (если бы LLM в worker'е использовал Claude Code, что не наш случай — но защита всё равно есть). Передаём `MNEMOS_INGEST_RUNNING=1` в env subprocess'а.
2. **Detached subprocess.** Hook не ждёт ingest worker — spawn-и-выход. Hook'у нельзя блокировать сессию.
3. **`pipeline_lock` в самом ingest** уже стоит (Plan #1+). Если две сессии завершаются одновременно — второй ingest подождёт первый.
4. **Daemon offline во время ingest** — не страшно, ingest синхронный CLI. Daemon только для MCP write tools.

---

## 7. Error handling matrix

| Сценарий | Поведение hook'а |
|---|---|
| `MNEMOS_VAULT_ROOT` не задан | Soft-skip + stderr message. Hook возвращает 0. |
| Payload invalid JSON | Soft-skip + stderr message. Hook возвращает 0. |
| `transcript_path` отсутствует в payload | Soft-skip + stderr message. Hook возвращает 0. |
| `transcript_path` не существует | Soft-skip + stderr message. Hook возвращает 0. |
| Recursion guard active | Silent exit 0. |
| Subprocess Popen бросает OSError | Stderr message, exit 0. Не бросаем — иначе Claude Code покажет error пользователю. |
| Vault corrupt → ingest worker сам упадёт с exit 73/74/75 | Hook не видит — он уже вышел. Worker логирует в stderr (которое идёт в /dev/null для detached). **Acceptable trade-off для Plan #7.** В Plan #11+ worker будет писать ошибки в `<vault>/.dead-letter/` (spec §8.9). |

**Принцип:** hook **никогда** не блокирует пользователя. Все ошибки ingest — async, разбираемся через `mnemos activity`.

---

## 8. Testing strategy

### 8.1 Уровни

1. **Plugin manifest validity:**
   - `plugin.json` parseable, имеет `name` + `description`
   - `.mcp.json` parseable, имеет `mcpServers.mnemos.command`
   - `hooks/hooks.json` parseable, имеет `hooks.SessionEnd[0].command`

2. **Skills validity:**
   - Каждый `SKILL.md` имеет валидный YAML frontmatter (через `yaml.safe_load`)
   - Каждый имеет `name` и `description`
   - `argument-hint` если есть — строка

3. **SessionEnd hook unit:**
   - `MNEMOS_VAULT_ROOT` не задан → exit 0, no spawn
   - Recursion guard active → exit 0, no spawn
   - Invalid JSON payload → exit 0, no spawn
   - `transcript_path` missing → exit 0, no spawn
   - `transcript_path` non-existent → exit 0, no spawn
   - Happy path → spawn called с правильными args
   - На Windows — popen_kwargs содержит `creationflags`
   - На non-Windows — popen_kwargs содержит `start_new_session`

4. **Slow E2E** (опциональный, marker `slow`):
   - Поднять `claude --plugin-dir` в subprocess (если возможно), отправить тест-сессию, проверить что ingest сработал. Скорее всего нет — `claude` cli могут не запустить hook'и в test mode. Skip.

### 8.2 Coverage targets

- 393 текущих + ~15-20 новых.
- ruff + mypy strict чистые.
- Manual smoke в Task последний:
  - `claude --plugin-dir /path/to/claude-mnemos` (или `--debug` mode)
  - Запустить тест-сессию, проверить что после её закрытия в vault'е появилась новая страница (через `mnemos activity`).

---

## 9. Known limitations (для Plan #8+)

1. **SessionStart hook отсутствует.** LLM в новой сессии не знает что в vault'е — должен сам инвокнуть `get_status`. Plan #11+ добавит adaptive context.
2. **Vault единственный** через env. Multi-project нет — пользователь с 5 проектами либо один большой vault, либо ручной `MNEMOS_VAULT_ROOT` switch.
3. **Hook ошибки тихие.** Если ingest worker упал — единственный сигнал в `mnemos activity` (где new entry не появится) или в `~/AppData/.../mnemos-worker.log` (которого нет). Plan #11+ добавит dead-letter queue (spec §8.9).
4. **Daemon должен быть запущен пользователем.** Hook не пытается auto-start daemon — слишком рискованно (race conditions, port conflicts). Если daemon мёртв, MCP write tools вернут понятное сообщение, а ingest всё равно работает (CLI sync, не нуждается в daemon).
5. **Plugin не публикуется.** Только `--plugin-dir` или `git clone`. Marketplace — Plan #12+.
6. **Skills для write-операций (undo/restore/snapshot) требуют запущенный daemon.** Описано в SKILL.md — LLM знает.
7. **`hooks.json` не валидируется через JSON Schema** в test'ах — только parseable + ручная проверка ключевых полей.
8. **`MNEMOS_INGEST_RUNNING` env передаётся всем потомкам** — теоретически блокирует все будущие ingests из children. Acceptable для нашего scope (ingest worker не запускает другой ingest).

---

## 10. What this enables (#8+ onwards)

- **Plan #8 (frontend dashboard):** dashboard будет ходить в daemon REST. Пользователь открывает через `mnemos daemon start` + browser → uses те же endpoints.
- **Plan #9 (ontology):** добавим `apply_ontology_suggestion` MCP tool + skill `mnemos-ontology` без изменений plugin manifest'а — skills load'ятся динамически.
- **Plan #10 (watchdog):** daemon начнёт следить за external file changes; SessionEnd hook не меняется.
- **Plan #11 (adaptive context):** добавится `SessionStart` hook + `tiered_query` модуль + `query_wiki` MCP tool. Plugin manifest добавит ещё одну запись в `hooks.json`.

---

## 11. Решения, которые я принял сам (для протокола)

| Решение | Альтернатива | Почему выбрал |
|---|---|---|
| Plan #7 = только plugin/hooks/skills, без commands | Делать ещё legacy `commands/*.md` | Docs прямо говорят: commands deprecated, заменены skills. YAGNI |
| Только `SessionEnd` hook, не `SessionStart`/`PreCompact` | Все три из spec §9.2 | Без `tiered_query`/`hot.md` остальные два бесполезны. Узко по фокусу как Plans #1-#6 |
| Hook → CLI subprocess `mnemos ingest`, не REST endpoint | Hook → POST /api/ingest/sessions/{sid} к daemon | Spec §10.3 endpoint не реализован. Создавать его сейчас = большой кусок (queue, jobs.json, dead-letter) — это Plan #11+. CLI работает с Plan #1, надёжно. |
| `MNEMOS_VAULT_ROOT` env — single source of truth | Hardcode в `.mcp.json` / читать из cwd | Hardcode = непортабельно. Cwd рискованно (Claude Code может стартовать из под-директорий). Env — стандартный pattern, прост. |
| Hook никогда не блокирует (`blocking: false`, soft-skip всех ошибок) | Блокирующий hook с error reporting | Плохой UX: пользователь жмёт «выйти» — ждёт hook. Лучше тихо async + проверка через `mnemos activity` |
| Recursion guard через env `MNEMOS_INGEST_RUNNING` | Lock-файл / flag в config | Простое, кроссплатформенное, работает в наших subprocess'ах. Тот же pattern в spec §9.2 |
| 4 sub-skills (status/search/undo/activity) — без `read_page`, `list_pages`, snapshots | Один skill на каждый MCP tool (9 штук) | YAGNI. Самые частые операции = эти 4. Read_page LLM вызовет напрямую через MCP без skill. Snapshot management — редкая операция, тоже напрямую |
| Главный skill (`mnemos`) — behavioral описание, не routing | Skill-router который зовёт sub-skills | Claude Code сам routing делает по skill descriptions. Главный skill — общий контекст «что у тебя есть». |
| `version: "0.0.1"` в plugin.json sync с pyproject вручную | Auto-derived | YAGNI — релизим один раз сейчас. CI sync — в Plan #12 |
| Не пакуем plugin-files в pip wheel | Включать в wheel | Distribution через `claude --plugin-dir <git-path>` или `claude plugins install <git-url>`, pip wheel — отдельный канал для CLI/daemon. Дублирование ненужное. |
| Hook не auto-стартует daemon | Если MCP write tool падает — auto-start | Race conditions (port conflict, multiple sessions concurrently start), сложная логика. Пользователь сам делает `mnemos daemon start` после установки плагина. |

---

## 12. Open questions для имплементации (не блокеры)

- **Subprocess `python -m claude_mnemos` vs entry-point `mnemos`.** Hook использует `sys.executable` для Python — а `mnemos` script может не быть на PATH в среде где Claude Code запускает hook. `python -m claude_mnemos` гарантированно работает, потому что `sys.executable` это сам Python из venv где модуль установлен. Решение: `python -m claude_mnemos`.
- **`hooks.json` — это spec'овский формат или Claude Code актуально использует другой?** Доки research-агента говорят `hooks/hooks.json` — но если Claude Code на 2026-04 ушёл в `settings.json`/inline в `plugin.json`, то нужно адаптировать. Проверю при коде через `claude --debug`.
- **Skills frontmatter `argument-hint` или `arguments`?** Доки говорят оба, неясно когда какой. Использую `argument-hint` (string) — по примерам docs.
- **Hook timeout 15 секунд:** хватит ли на Popen + exit? Должно с запасом — мы не ждём ingest, только spawn.
- **`.mcp.json` с `${MNEMOS_VAULT_ROOT}` — Claude Code расширяет env vars в args?** Это нужно проверить. Если не расширяет — fallback: hook script runner для MCP, или wrapper script.
- **Tests on hooks:** hooks `python ${CLAUDE_PLUGIN_ROOT}/hooks/session_end.py` — `${CLAUDE_PLUGIN_ROOT}` интерполируется Claude Code'ом. В тестах мы зовём `python session_end.py` напрямую, без env interpolation. Тесты проверяют сам script, не интеграцию с Claude Code.

---

## 13. Why this scope

Через эту дверь:

1. **Авто-ingest без ручной команды.** Самая частая операция (`mnemos ingest`) переходит в фон. Пользователь работает в Claude Code как обычно — vault сам наполняется.
2. **Skills делают MCP tools удобными.** `/mnemos-search foo` короче чем «эй LLM, вызови `search_pages` с query=foo».
3. **Один env var = вся конфигурация плагина.** `MNEMOS_VAULT_ROOT` — единая точка настройки. CLI/daemon/MCP/hook всё видят.
4. **Plugin = упаковка существующего**, не новая логика. CLI/daemon/MCP уже работают; Plan #7 их **связывает** через manifest.
5. **Не блокирует существующие flows.** Если plugin не подключён — daemon, CLI, MCP работают как до Plan #7.
6. **Узкий cycle time** (~3-5 дней) как Plans #2-#6.
