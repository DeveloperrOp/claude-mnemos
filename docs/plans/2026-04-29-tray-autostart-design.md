# Tray Icon + Autostart — Design

**Date:** 2026-04-29
**Status:** Approved by Yarik (autonomous run)
**Goal:** При логине в Windows / macOS daemon claude-mnemos автоматически запускается, иконка появляется в системном трее, открытие дашборда — один клик. Никакого терминала.

---

## 1. Scope

### Included

- **Платформы:** Windows 11 + macOS, единый Python codebase с OS-specific shim'ами.
- **Архитектура:** Supervisor pattern — один tray-процесс владеет daemon как subprocess.
- **Recovery:** Silent auto-restart при крашах с защитой от restart-loop (>3 краша за 5 мин → останов).
- **Меню:** Расширенное — статус, кол-во проектов, restart, show logs, open dashboard, quit.
- **CLI:** `mnemos tray {install, uninstall, run, status}`.
- **UI:** Чекбокс «Auto-start at login» в Onboarding wizard'е (вызывает API → CLI install).

### Excluded (out of MVP)

- **Linux** — отложено на следующую итерацию (`systemd --user`).
- **Windows Service** — несовместимо с user-session tray.
- **Native preference windows** — всё конфигурируется через дашборд.
- **Tray-without-daemon** — отвергнуто на этапе brainstorming (вариант C).

---

## 2. Архитектура

```
┌────────────────────────────────────────────────────┐
│  OS autostart entry (per-user)                     │
│  Win: %APPDATA%\...\Startup\Mnemos.lnk             │
│  Mac: ~/Library/LaunchAgents/com.claude-mnemos.    │
│       tray.plist                                   │
└────────────────────┬───────────────────────────────┘
                     ↓ при логине
        ┌────────────────────────────────┐
        │  mnemos-tray (Python)          │ ← supervisor
        │                                │
        │  ├ pystray icon + меню         │
        │  ├ subprocess.Popen daemon     │
        │  ├ liveness watcher (5s poll)  │
        │  ├ restart limiter             │
        │  └ HTTP /health → projects N   │
        └──────────┬─────────────────────┘
                   │ управляет
                   ↓
        ┌────────────────────────────────┐
        │  claude-mnemos daemon          │
        │  (uvicorn :5757, без изменений)│
        └────────────────────────────────┘
```

### Принципы

- **Один tray-процесс на машину** — защита через `tray.pid` lockfile (аналогично уже существующему `daemon.pid`).
- **Supervisor владеет subprocess'ом daemon'а** — но если daemon уже запущен извне (через CLI), supervisor его «усыновляет» через `is_daemon_running()` и просто мониторит.
- **Daemon код не меняется** — supervisor работает с ним через те же контракты что CLI/UI: PID-file, `/health`, signals.
- **Платформо-зависимая часть изолирована** в `claude_mnemos/tray/platform/{windows,macos}.py` за общим `AutostartManager` Protocol.

---

## 3. Компоненты

```
claude_mnemos/tray/
├── __init__.py
├── __main__.py              ← entrypoint `mnemos-tray`
├── supervisor.py            ← state machine + subprocess + restart limiter
├── icon.py                  ← pystray setup, меню, обновление иконки
├── platform/
│   ├── __init__.py
│   ├── base.py              ← AutostartManager Protocol
│   ├── windows.py           ← .lnk через PowerShell + WScript.Shell
│   └── macos.py             ← .plist render + launchctl load/unload
└── assets/
    ├── icon-running.ico     (Windows)
    ├── icon-stopped.ico
    ├── icon-running.png     (macOS, 22x22)
    └── icon-stopped.png

claude_mnemos/cli_tray.py    ← подкоманды `mnemos tray ...`

claude_mnemos/daemon/routes/tray.py  ← POST /tray/install, POST /tray/uninstall, GET /tray/status

frontend/src/pages/Onboarding.tsx     ← + чекбокс «Auto-start at login»
frontend/src/api/tray.api.ts          ← клиент для /tray/*
frontend/src/__tests__/Onboarding.test.tsx  ← + тест нового шага
```

### Ответственности

- **`supervisor.py`** — state machine, subprocess lifecycle, crash detection, restart limiter. Чистая логика, легко unit-test'ится с моком subprocess.
- **`icon.py`** — pystray-обёртка, биндинги меню к супервизору. Отдельный файл, потому что pystray требует display и не тестируется в CI.
- **`platform/base.py`** — `AutostartManager` Protocol: `install() -> None`, `uninstall() -> None`, `is_installed() -> bool`. Единый контракт для Win/Mac.
- **`platform/windows.py`** — реализация через PowerShell `New-Object -ComObject WScript.Shell` для создания `.lnk`. Удаление через `os.unlink`.
- **`platform/macos.py`** — рендеринг шаблона `.plist`, `launchctl load`/`unload` через subprocess.
- **`cli_tray.py`** — argparse-роутинг подкоманд + вызов соответствующих модулей.
- **`routes/tray.py`** — три HTTP-endpoint'а, тонкая обёртка вокруг CLI (запускает `mnemos tray install` через subprocess).

---

## 4. State machine супервизора

```
   start ──→ Starting ──ok──→ Running ──crash────→ Restarting (count++)
                │                                       │
                │                                       │ count>3 за 5мин
                │                                       ↓
                └──→ Stopping ──→ Stopped         Crashed (manual only)
                     (Quit/Restart action)
```

### Состояния иконки и tooltip

| State | Иконка | Tooltip |
|---|---|---|
| Starting | зелёная (спин-loading через alt frames? — нет, статичная) | «Mnemos · starting…» |
| Running | зелёная | «Mnemos · 3 projects mounted · uptime 2h 14m» |
| Restarting | зелёная (мерцает 1с) | «Mnemos · restarting…» |
| Stopped | красная | «Mnemos · stopped» |
| Crashed | красная | «Mnemos · crashed (3 failures in 5min)» |

Динамика мерцания — простой `set_icon()` свитч раз в секунду в течение перехода. Анимировать pystray-иконку не пытаемся (не у всех бэкендов работает).

### Restart limiter

- Скользящее окно 5 минут.
- При каждом крахе → `crash_times.append(now)`, drop entries старше 5 мин.
- Если `len(crash_times) > 3` → переход в Crashed, не перезапускать.
- Backoff между restart'ами: `1s, 2s, 4s` (exponential, capped).
- Сброс счётчика при ручном Restart из меню или при успешном `/health` ответе после 30s аптайма.

---

## 5. Поведение по сценариям

### Запуск `mnemos-tray run` (или autostart entry)

1. Захватить `tray.pid` lock — exit с warning если уже запущен другой tray.
2. Загрузить pystray icon.
3. Проверить `is_daemon_running(daemon_pid_file)`:
   - **Живой** → adopt. State = Running. Не stratуем subprocess.
   - **Нет** → spawn `python -m claude_mnemos.daemon foreground --all` через `subprocess.Popen`.
     - stdout/stderr → `~/.claude-mnemos/daemon.log` (append).
4. Запустить background-thread polling (5s):
   - `psutil.pid_exists(subprocess.pid)` — liveness.
   - `httpx.get('http://localhost:5757/health', timeout=2)` — projects count, errors.
5. Обновить иконку и tooltip согласно state.

### Daemon крашнулся

`subprocess.poll() != 0` и `not user_initiated_stop`:

1. Лог: `[supervisor] daemon crashed (exit=N), crash_count=K/5min`.
2. `crash_times.append(now)` + prune старых.
3. Если `> 3 / 5min`:
   - Переход в Crashed. Иконка красная.
   - Меню: Open dashboard и Quit неактивны (показывают grayed); Restart и Show logs — активны.
4. Иначе:
   - Backoff sleep по таблице.
   - `subprocess.Popen` снова → state = Restarting → Running по `/health` 200.

### Меню → Restart daemon

1. State → Stopping. `subprocess.terminate()` (SIGTERM/CTRL_BREAK_EVENT на Win).
2. `proc.wait(timeout=5)`. Если жив → `proc.kill()`.
3. Spawn новый. State → Starting → Running.
4. **Сброс crash counter** — это явный пользовательский reset.

### Меню → Show logs

- Открыть `~/.claude-mnemos/daemon.log` через:
  - Win: `os.startfile(log_path)` — откроется в дефолтном `.log` ассоциированном приложении (обычно Notepad).
  - Mac: `subprocess.run(['open', str(log_path)])` — откроется в Console.app или TextEdit.

### Меню → Open dashboard

- `webbrowser.open('http://localhost:5757/')`.
- Если daemon не Running → меню-итем grayed.

### Меню → Quit

1. State → Stopping.
2. **Если daemon spawned супервизором** (наш subprocess) → `subprocess.terminate()`, grace 10s, fallback `subprocess.kill()`.
3. **Если daemon adopted** (запущен извне, мы только мониторим) → НЕ трогаем. Юзер запустил daemon вручную, мы не имеем права его убивать.
4. Удалить `tray.pid`.
5. `pystray.Icon.stop()`.
6. Process exit 0.

То же самое для Restart daemon: рестартим только spawned subprocess. Если adopted — меню-итем grayed с tooltip «Daemon was started externally; restart it from CLI».

---

## 6. CLI

```
mnemos tray install      # создать autostart entry, запустить tray detached
mnemos tray uninstall    # удалить autostart entry; запущенный tray не убивает
mnemos tray run          # foreground запуск (используется в .lnk / .plist Target)
mnemos tray status       # human-readable: autostart enabled? tray PID? daemon PID?
```

### `install` поведение

1. Создать autostart entry (idempotent — переписать если уже есть).
2. Если tray ещё не работает → запустить detached subprocess: `mnemos tray run` (через `subprocess.Popen` без `wait`, с `creationflags=DETACHED_PROCESS` на Win / `start_new_session=True` на posix).
3. Печатать «Auto-start enabled at <path>. Tray started (PID <pid>).» в stdout.

### `uninstall` поведение

1. Удалить autostart entry (idempotent — no-op если нет).
2. **НЕ убивать** запущенный tray. Юзер сам решает Quit или нет.
3. Печатать «Auto-start disabled. Tray PID <pid> still running; Quit it from the tray menu.».

### `mnemos-tray` алиас

Добавляется в `[project.scripts]` pyproject.toml как алиас на `claude_mnemos.tray.__main__:main`. Используется в Target поле `.lnk` / `.plist`. Юзер с этим алиасом не работает напрямую — это деталь упаковки.

---

## 7. HTTP API

### `POST /tray/install`

```http
POST /tray/install
→ 200 {"installed": true}
→ 500 {"detail": "powershell exit 1: ..."}
→ 501 {"detail": "Autostart not supported on this platform"}
```

Под капотом — `subprocess.run(['mnemos', 'tray', 'install'])` (или `python -m claude_mnemos tray install` если `mnemos` не в PATH). Подробности (autostart_path, tray_pid) клиент получает отдельным `GET /tray/status` запросом.

### `POST /tray/uninstall`

```http
POST /tray/uninstall
→ 200 {"installed": false}
→ 500 {"detail": "..."}
→ 501 {"detail": "Autostart not supported on this platform"}
```

### `GET /tray/status`

```http
GET /tray/status
→ 200 {
    "platform": "windows" | "macos" | "unsupported",
    "autostart_enabled": true,
    "autostart_path": "C:\\...\\Mnemos.lnk",
    "tray_running": true,
    "tray_pid": 12345
}
```

При `platform=unsupported` (Linux в MVP) — поля `autostart_*` = `false` / `null`, install/uninstall возвращают 501.

---

## 8. UI (Onboarding)

В существующий Onboarding wizard ([Onboarding.tsx](D:/code/claude-mnemos/frontend/src/pages/Onboarding.tsx)) добавить **новый шаг после успешного создания проекта**, перед redirect на `/project/<name>`:

```
┌──────────────────────────────────────────┐
│  ✅ Project «sites-builder» created      │
│                                          │
│  ☑ Запускать mnemos автоматически        │
│    при логине                            │
│                                          │
│  [Done]                                  │
└──────────────────────────────────────────┘
```

При жатии `Done` с включенным чекбоксом → `POST /tray/install` → toast «Auto-start enabled». При ошибке — toast «Failed: <detail>», но всё равно redirect на проект.

Чекбокс показывается **только если platform поддерживается** (`GET /tray/status` → platform != unsupported). На Linux MVP шаг скрыт.

---

## 9. Зависимости

Добавить в `pyproject.toml`:

```toml
dependencies = [
    ...
    "pystray>=0.19",
    "Pillow>=10",
    ...
]
```

**Pystray бэкенды:**
- Windows: `win32` backend (встроен в pystray, без extra deps).
- macOS: `darwin` backend (встроен).

**Уже есть:** `psutil` (liveness), `httpx` (HTTP /health).

**Не нужны:** pywin32, pyobjc, tkinter, plyer.

---

## 10. Файлы / OS-impact

| | Windows | macOS |
|---|---|---|
| Autostart entry | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Mnemos.lnk` | `~/Library/LaunchAgents/com.claude-mnemos.tray.plist` |
| Logs dir | `%USERPROFILE%\.claude-mnemos\` | `~/.claude-mnemos/` |
| Tray PID | `~/.claude-mnemos/tray.pid` (новый) | то же |
| Daemon PID | `~/.claude-mnemos/daemon.pid` (уже существует) | то же |
| Supervisor log | `~/.claude-mnemos/supervisor.log` (новый) | то же |
| Daemon log (redirect) | `~/.claude-mnemos/daemon.log` | то же |

`com.claude-mnemos.tray` — Reverse-DNS bundle id (стандарт для launchd plist'ов).

---

## 11. Логи

### `~/.claude-mnemos/supervisor.log`

ISO timestamps + state transitions + crash details:

```
2026-04-29T18:32:01Z [supervisor] state Starting → Running (daemon pid=8821)
2026-04-29T20:14:55Z [supervisor] daemon crashed (exit=1), crash_count=1/5min
2026-04-29T20:14:56Z [supervisor] backoff 1s
2026-04-29T20:14:57Z [supervisor] state Restarting → Running (daemon pid=8945)
2026-04-29T22:05:11Z [supervisor] /health failed: ConnectError, retrying
```

Rotation: append-only, без ротации в MVP. Если файл вырастет — отдельный issue.

### `~/.claude-mnemos/daemon.log`

stdout + stderr из subprocess uvicorn'а. Append.

---

## 12. Тесты

### Unit (CI)

| Файл | Что покрывается |
|---|---|
| `tests/tray/test_supervisor.py` | State machine transitions; restart limiter (3-крахов-5мин логика); backoff schedule; user-initiated stop не triggers crash; adopt существующего daemon. Mock subprocess.Popen + psutil. |
| `tests/tray/test_platform_windows.py` | Генерация PowerShell-команды для создания .lnk. Mock `subprocess.run`. Verify Target/Arguments/WorkingDirectory paths. Idempotent install. |
| `tests/tray/test_platform_macos.py` | Render .plist content (string match against expected). Mock `launchctl load/unload`. Verify Label/ProgramArguments/RunAtLoad. |
| `tests/tray/test_cli_tray.py` | argparse routing; idempotent `install`; `uninstall` не убивает tray; `status` output format. |
| `tests/daemon/routes/test_tray.py` | Endpoint integration — mock subprocess.run from route, verify exit-code mapping → HTTP status. |

### Manual / integration (вне CI, документировано в README)

1. `pip install -e .` → `mnemos tray install` → reboot → tray появился, daemon работает, `curl :5757/health` → 200.
2. `kill -9 <daemon_pid>` → видеть restart в `supervisor.log`, иконка не теряется.
3. `for i in 1..5: kill -9 <daemon_pid>` (с интервалом <1мин) → state=Crashed, в меню Restart активен.
4. `mnemos tray uninstall` → reboot → не запускается, .lnk/.plist удалены.
5. `mnemos tray install` дважды подряд → idempotent, без ошибок.
6. macOS: `launchctl list | grep claude-mnemos` после install → видим запись.

### Что не тестируется в CI

- `icon.py` — pystray требует display server. Помечается `@pytest.mark.manual` и skipped при `CI=true`.
- Реальный reboot. Документируется в plan'е как ручной checkpoint.

---

## 13. Error handling

| Сценарий | Поведение |
|---|---|
| `mnemos tray install` повторно | Idempotent — переписывает .lnk/.plist. |
| Port 5757 занят при старте daemon | Supervisor видит crash subprocess'a, state=Crashed, tooltip «Port 5757 in use». |
| `~/.claude-mnemos/` нет прав на запись | Fail-fast в supervisor: stderr error + exit 1. |
| macOS `launchctl load` exit≠0 | CLI install возвращает exit 1, stderr из launchctl forward'ится в stdout. HTTP /tray/install → 500. |
| Второй `mnemos tray run` пока работает первый | Lock-file conflict → exit 1 с warning «another tray running, PID <X>». |
| Tray crash | Если запущен через autostart — Windows OS не рестартит startup-folder entries. Unix launchd с `KeepAlive=true` рестартит. На Win пропускаем (юзер увидит при следующем логине что иконки нет). |
| Удаление .lnk вручную юзером | При следующем `mnemos tray status` → autostart_enabled=false. Не пытаемся «лечить». |

---

## 14. Backwards-compatibility

- `mnemos daemon {start, stop, status, foreground}` работают без изменений.
- Если юзер раньше запускал daemon через cron/systemd/Task Scheduler — это не сломается. Tray просто adopt'ит работающий процесс через PID-файл.
- При `mnemos tray install` — warning если найдены **старые autostart entries для daemon**:
  - Win: проверяем Startup folder, Run-key, Task Scheduler на наличие `claude_mnemos.daemon`.
  - Mac: проверяем `~/Library/LaunchAgents/` на старые plist с маркером `claude_mnemos.daemon` (если когда-либо существовали).
  - Если нашли → printed warning «Existing daemon autostart found at <path>, consider removing it». Не удаляем сами.

---

## 15. Risks / Open questions

| Риск | Mitigation |
|---|---|
| Windows Defender / антивирус блокирует .lnk запуск | Стандартный путь Startup folder — тот же где Discord/Slack. Не должны. Если упадёт — fallback на Run-key (B из вопроса 5). |
| pystray `win32` бэкенд требует pywin32 на некоторых версиях | Проверить — в 0.19+ self-contained. Если требует — добавить в deps. |
| macOS Sequoia может требовать Notarization для .plist Auto-Start | Если упадёт — документируем «system settings → login items → разрешить». Альтернатива — System Events AppleScript prompt при первом запуске (откладываем). |
| Restart-loop limiter false-positive при flaky сети | Defining: «crash» = `subprocess.poll() != 0 в течение first 30s`, не любой `/health` failure. После 30s аптайма — flaky сеть не считается крашем, только subprocess exit. |
| pystray icon недоступен в RDP / headless server | Tray не работает, но daemon работает (subprocess живёт). Документируем «for headless use stick to `mnemos daemon start`». |

---

## 16. Размер / оценка

~10 новых файлов Python (~600-800 LOC) + ~100 LOC frontend (Onboarding шаг + API клиент) + ассеты иконок. **Оценка: 3-5 дней работы** (детализация в `plan.md`).

---

## 17. Success criteria

После merge:
1. `mnemos tray install` создаёт корректный autostart entry на Win/Mac.
2. После reboot tray появляется в трее, daemon работает на :5757.
3. Двойной клик / Open dashboard открывает браузер на http://localhost:5757/.
4. Show logs открывает `daemon.log` в дефолтном приложении ОС.
5. `kill -9` daemon → автоперезапуск в течение 5 секунд (видно в supervisor.log).
6. `kill -9` daemon 4 раза за минуту → state=Crashed, иконка красная, в меню остался Restart.
7. `mnemos tray uninstall` → после reboot не запускается.
8. Все unit-тесты зелёные в CI; manual checklist пройден на Win11 (у Ярика).

---

## 18. Future work (out of scope)

- Linux support (`systemd --user`).
- Custom иконка (сейчас плейсхолдер «м»).
- Автообновления tray-приложения.
- Возможность запуска daemon не на :5757 (multi-instance support).
- Notification на toast при крашах (отвергнуто на этапе brainstorming, вариант B из Q3).
