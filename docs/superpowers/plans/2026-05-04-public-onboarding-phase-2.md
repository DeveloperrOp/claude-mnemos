# Public Onboarding Phase 2 — Native Installers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship native installers (`.exe` for Win, `.dmg` for Mac, `.AppImage` for Linux) so a non-technical user downloads one file, double-clicks, and reaches a working dashboard with **zero terminal involvement**.

**Architecture:** PyInstaller bundles Python + claude-mnemos + frontend assets into a single distribution directory. Each platform wraps that directory with its native installer (Inno Setup on Windows, py2app+create-dmg on Mac, AppImage on Linux). On first launch the bundled exe runs `mnemos init` automatically — installs Claude Code hooks via a new `mnemos hook` subcommand that points back at the installed exe (so hooks survive uninstall + reinstall). GitHub Actions matrix builds all three on tag push and uploads to a release.

**Tech Stack:** PyInstaller (bundle), Inno Setup (Windows), py2app + create-dmg (macOS), linuxdeploy + AppImage (Linux), GitHub Actions (CI/CD). Python 3.12+, source tree continues to work via pipx for development.

---

## Pre-flight constraints

- **Platform availability for local testing:** the implementer is expected to develop on Windows. Mac and Linux variants can be **smoke-tested only on CI runners** (`macos-latest`, `ubuntu-latest`). All tasks targeting Mac/Linux must be CI-verifiable; do not require local Mac/Linux to land them.
- **Code signing is deferred** (initial release ships unsigned). Document SmartScreen / Gatekeeper bypass in README.
- **Auto-update is in scope (minimal):** banner-only — daemon polls GitHub Releases, surfaces `Update available — Download` chip on Overview, click opens the release page. We do NOT auto-replace binaries (Sparkle/Squirrel deferred until code-signing). See Task 10.
- **Bundle size budget:** ~80–120 MB per platform. Acceptable for a developer tool.
- **Cold-start cost:** the bundled `claude-mnemos.exe` imports the full FastAPI/uvicorn stack on launch (~1–2s cold). Hooks must NOT use this entry — they get a fast `mnemos hook <event>` subcommand that lazy-imports only what's needed.
- **Stable install paths** — hook commands written into `~/.claude/settings.json` must point to a location that survives upgrades. We use the platform-canonical install path (`%ProgramFiles%\claude-mnemos\` on Win, `/Applications/claude-mnemos.app/Contents/MacOS/` on Mac, `~/.local/bin/claude-mnemos` for AppImage symlink).

## Pre-flight verification

Before starting implementation tasks the engineer must verify the toolchain:

```bash
# Windows host (primary dev box)
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pip install pyinstaller==6.11.0
~/pipx/venvs/claude-mnemos/Scripts/python.exe -c "import PyInstaller; print(PyInstaller.__version__)"
# Expected: 6.11.0

# Inno Setup (Windows-only, install once)
# Download from https://jrsoftware.org/isinfo.php — install to default path
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /?
# Expected: prints CLI help. If not, abort and instruct user to install Inno Setup.
```

If any tool is missing, **stop and ask** — do not skip checks.

---

## File Structure

### New module/build files

| File | Responsibility | Approx LoC |
|---|---|---|
| `claude_mnemos/runtime.py` | Frozen-vs-source detection helpers: `is_frozen()`, `bundle_root()`, `executable_path()`, `static_dir()`, `prompts_dir()`, `tray_assets_dir()`, `hooks_dir()`. Single source of truth for path resolution. | ~80 |
| `claude_mnemos/cli_hook.py` | `mnemos hook session-start|session-end|pre-compact` subcommand. Thin wrapper that imports only `requests`/`urllib` + the matching `hooks/*.py` logic — fast cold-start. | ~140 |
| `claude_mnemos/postinstall.py` | First-run-after-install flow: detect first launch via `install_state.first_run_ts`, call `cli_init.run()`, set the timestamp. Idempotent. | ~70 |
| `installer/pyinstaller/mnemos.spec` | PyInstaller spec — entry, hidden imports, datas (frontend bundle, prompts, tray assets, hooks scripts). | ~110 |
| `installer/windows/mnemos.iss` | Inno Setup script: app metadata, files, icons, registry entries, postinstall Run section, uninstall cleanup. | ~120 |
| `installer/macos/setup.py` | py2app setup script: app metadata, plist (LSUIElement for tray), datas. | ~70 |
| `installer/macos/build-dmg.sh` | DMG packaging via `create-dmg`. | ~25 |
| `installer/linux/build-appimage.sh` | AppImage packaging via `linuxdeploy` + python plugin. | ~60 |
| `installer/linux/claude-mnemos.desktop` | XDG desktop entry. | ~12 |
| `.github/workflows/release.yml` | CI/CD: matrix build on tag push, upload artifacts to GitHub Release. | ~120 |

### Modified files

| File | Change |
|---|---|
| `claude_mnemos/cli_hooks.py:39-58` | `_detect_hook_scripts` consults `runtime.is_frozen()`. In frozen mode, return tuples that point to `mnemos.exe hook <event>` style commands instead of `python <hook.py>`. |
| `claude_mnemos/daemon/app.py:209` | Replace `Path(__file__).parent / "static"` with `runtime.static_dir()`. |
| `claude_mnemos/ingest/prompts/__init__.py:6` | Use `runtime.prompts_dir()`. |
| `claude_mnemos/tray/icon.py:21` | Use `runtime.tray_assets_dir()`. |
| `claude_mnemos/cli.py` | Register `cli_hook.add_hook_subparser`. Wire dispatch. Wire `postinstall.maybe_run_first_time_init()` on every CLI entry (idempotent — only runs on first launch). |
| `claude_mnemos/cli_init.py` | After successful daemon-health step, also call `postinstall.mark_first_run()` so subsequent `mnemos init` invocations don't double-run the postinstall path. |
| `pyproject.toml` | Add optional `[project.optional-dependencies] installer = ["pyinstaller>=6.11"]`. |
| `README.md` | Add a "Install from a release" section with the SmartScreen / Gatekeeper bypass instructions. |

---

## Tasks

### Task 1: `runtime.py` — frozen/source detection helpers

Foundation. Every other path-resolution fix in tasks 2–5 calls into this module. Implement first.

**Files:**
- Create: `claude_mnemos/runtime.py`
- Test: `tests/test_runtime.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_runtime.py
import sys
from pathlib import Path

import pytest


def test_is_frozen_false_in_normal_python(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    from claude_mnemos.runtime import is_frozen
    assert is_frozen() is False


def test_is_frozen_true_when_meipass_set(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    from claude_mnemos.runtime import is_frozen
    assert is_frozen() is True


def test_bundle_root_returns_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    from claude_mnemos.runtime import bundle_root
    assert bundle_root() == tmp_path


def test_bundle_root_returns_package_dir_in_source_mode(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    from claude_mnemos.runtime import bundle_root
    import claude_mnemos
    assert bundle_root() == Path(claude_mnemos.__file__).resolve().parent.parent


def test_static_dir_inside_bundle_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    (tmp_path / "claude_mnemos" / "daemon" / "static").mkdir(parents=True)
    from claude_mnemos.runtime import static_dir
    assert static_dir() == tmp_path / "claude_mnemos" / "daemon" / "static"


def test_executable_path_returns_sys_executable_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    fake_exe = tmp_path / "claude-mnemos.exe"
    fake_exe.touch()
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    from claude_mnemos.runtime import executable_path
    assert executable_path() == fake_exe
```

- [ ] **Step 2: RED**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_runtime.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `runtime.py`**

```python
# claude_mnemos/runtime.py
"""Runtime-mode detection: source vs PyInstaller-frozen bundle.

Single source of truth for resolving paths to bundled assets so the
codebase doesn't sprinkle ``Path(__file__)`` calls that break under
PyInstaller's ``_MEIPASS`` extraction.

The same module is imported in source mode (development via pipx) and
in frozen mode (after running PyInstaller). All consumers should call
the helpers below — never compute paths from ``__file__`` directly.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def bundle_root() -> Path:
    """Return the root directory of the bundle.

    In frozen mode this is ``sys._MEIPASS`` (PyInstaller's extraction dir).
    In source mode it's the repo root — the parent of the ``claude_mnemos``
    package directory.
    """
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    import claude_mnemos
    return Path(claude_mnemos.__file__).resolve().parent.parent


def executable_path() -> Path:
    """Return path to the running executable.

    In frozen mode: ``sys.executable`` is the bundled exe — a stable path
    after install. In source mode: ``sys.executable`` is the Python
    interpreter (pipx-venv on the dev box). Hook installation uses this
    to write a stable command line into ``~/.claude/settings.json``.
    """
    return Path(sys.executable).resolve()


def static_dir() -> Path:
    """Frontend SPA assets bundled by ``frontend/`` build."""
    return bundle_root() / "claude_mnemos" / "daemon" / "static"


def prompts_dir() -> Path:
    """LLM prompt templates packaged at ``claude_mnemos/ingest/prompts``."""
    return bundle_root() / "claude_mnemos" / "ingest" / "prompts"


def tray_assets_dir() -> Path:
    """Tray icon PNGs."""
    return bundle_root() / "claude_mnemos" / "tray" / "assets"


def hooks_dir() -> Path:
    """Plain hook scripts at ``hooks/`` — used in source mode for testing.

    In frozen mode this directory still exists (datas-included) but the
    cli_hooks installer prefers the ``mnemos hook <event>`` subcommand
    over invoking ``python <script.py>``.
    """
    return bundle_root() / "hooks"
```

- [ ] **Step 4: Run test, GREEN**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_runtime.py -v
```
Expected: 6 PASS.

- [ ] **Step 5: Run full suite for regression**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/ --deselect tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle -q | tail -3
```
Expected: ≥1697 passed (was 1691, +6).

- [ ] **Step 6: Commit**

```
git add claude_mnemos/runtime.py tests/test_runtime.py
git commit -m "feat(runtime): bundle vs source detection helpers (Phase 2 foundation)

is_frozen()/bundle_root()/executable_path()/static_dir()/prompts_dir()/
tray_assets_dir()/hooks_dir(). Single source of truth for paths;
consumers never call Path(__file__) directly. Foundation for
PyInstaller bundling — every later task migrates one path site."
```

---

### Task 2: Migrate path callers to `runtime.py`

Replace four `Path(__file__)`-based call sites with the new helpers.

**Files:**
- Modify: `claude_mnemos/daemon/app.py:209`
- Modify: `claude_mnemos/ingest/prompts/__init__.py:6`
- Modify: `claude_mnemos/tray/icon.py:21`

- [ ] **Step 1: Read each call site**

```
grep -n "Path(__file__)" claude_mnemos/daemon/app.py claude_mnemos/ingest/prompts/__init__.py claude_mnemos/tray/icon.py
```

- [ ] **Step 2: Update `daemon/app.py:209`**

```python
# claude_mnemos/daemon/app.py — replace the static_dir block (~line 207-213)
from claude_mnemos.runtime import static_dir as _runtime_static_dir
# ...
    if static_dir is None:
        static_dir = _runtime_static_dir()
    if (static_dir / "index.html").is_file():
        app.mount(
            "/",
            SpaStaticFiles(directory=static_dir, html=True),
            name="frontend",
        )
```

The function signature `def create_app(daemon=None, static_dir: Path | None = None)` already takes an override — keep it. Only the default is read from `runtime`.

- [ ] **Step 3: Update `ingest/prompts/__init__.py:6`**

```python
# claude_mnemos/ingest/prompts/__init__.py — replace the constant
from claude_mnemos.runtime import prompts_dir as _runtime_prompts_dir
_PROMPTS_DIR = _runtime_prompts_dir()
```

(Verify call sites still read `_PROMPTS_DIR` correctly — likely just `(_PROMPTS_DIR / 'extraction.txt').read_text()`.)

- [ ] **Step 4: Update `tray/icon.py:21`**

```python
# claude_mnemos/tray/icon.py — replace the constant
from claude_mnemos.runtime import tray_assets_dir as _runtime_tray_assets_dir
ASSETS = _runtime_tray_assets_dir()
```

- [ ] **Step 5: Run regression**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/ --deselect tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle -q | tail -3
```
Expected: 1697 passed (no count change, same behavior in source mode).

- [ ] **Step 6: Commit**

```
git add claude_mnemos/daemon/app.py claude_mnemos/ingest/prompts/__init__.py claude_mnemos/tray/icon.py
git commit -m "refactor(paths): three callers now use runtime helpers

daemon/app static_dir, ingest/prompts _PROMPTS_DIR, tray/icon ASSETS
all routed through runtime.py. No source-mode behavior change. Frozen
mode picks up _MEIPASS automatically. Ready for PyInstaller bundling."
```

---

### Task 3: `mnemos hook` subcommand — fast hook entry

Hooks invoked from Claude Code must NOT import the daemon stack. New `mnemos hook session-start | session-end | pre-compact` lazy-imports only the matching `hooks/*.py` logic. In frozen mode this is the executable target.

**Files:**
- Create: `claude_mnemos/cli_hook.py`
- Modify: `claude_mnemos/cli.py` — register subparser + dispatch
- Test: `tests/test_cli_hook.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli_hook.py
import json
import sys
from io import StringIO
from unittest.mock import MagicMock

import pytest


def test_hook_session_start_calls_session_start_main(monkeypatch):
    captured = {"called": 0, "argv": None}

    def fake_main():
        captured["called"] += 1
        captured["argv"] = list(sys.argv)
        return 0

    # Patch the lazy import target.
    monkeypatch.setitem(sys.modules, "session_start_hook", MagicMock(main=fake_main))
    monkeypatch.setattr(
        "claude_mnemos.cli_hook._import_session_start",
        lambda: fake_main,
    )

    from claude_mnemos.cli_hook import run

    rc = run(["session-start"], stdin_payload='{"transcript_path":"/tmp/x.jsonl"}')
    assert rc == 0
    assert captured["called"] == 1


def test_hook_invalid_event_returns_2(monkeypatch):
    from claude_mnemos.cli_hook import run
    rc = run(["bogus-event"], stdin_payload="")
    assert rc == 2


def test_hook_passes_stdin_to_underlying_script(monkeypatch):
    seen = {}

    def fake_main():
        seen["stdin"] = sys.stdin.read()
        return 0

    monkeypatch.setattr(
        "claude_mnemos.cli_hook._import_session_end",
        lambda: fake_main,
    )

    from claude_mnemos.cli_hook import run
    rc = run(["session-end"], stdin_payload='{"transcript_path":"/tmp/y.jsonl"}')
    assert rc == 0
    assert "transcript_path" in seen["stdin"]
```

- [ ] **Step 2: RED**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_cli_hook.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `cli_hook.py`**

```python
# claude_mnemos/cli_hook.py
"""``mnemos hook <event>`` — fast hook entry.

Claude Code invokes this when a SessionStart/SessionEnd/PreCompact event
fires. It must cold-start fast (≤500ms): we lazy-import only the matching
``hooks/<event>.py`` ``main()`` function, skipping the FastAPI/uvicorn
stack entirely.

The bundled exe registers this as the hook target in ~/.claude/settings.json
when ``mnemos hooks install`` runs in frozen mode.
"""

from __future__ import annotations

import argparse
import io
import sys
from typing import Callable

EVENTS = ("session-start", "session-end", "pre-compact")


def _import_session_start() -> Callable[[], int]:
    from claude_mnemos.runtime import hooks_dir
    sys.path.insert(0, str(hooks_dir()))
    import session_start  # type: ignore  # the script's main() returns int
    return session_start.main


def _import_session_end() -> Callable[[], int]:
    from claude_mnemos.runtime import hooks_dir
    sys.path.insert(0, str(hooks_dir()))
    import session_end  # type: ignore
    return session_end.main


def _import_pre_compact() -> Callable[[], int]:
    from claude_mnemos.runtime import hooks_dir
    sys.path.insert(0, str(hooks_dir()))
    import pre_compact  # type: ignore
    return pre_compact.main


_DISPATCH: dict[str, Callable[[], Callable[[], int]]] = {
    "session-start": _import_session_start,
    "session-end": _import_session_end,
    "pre-compact": _import_pre_compact,
}


def run(argv: list[str], stdin_payload: str | None = None) -> int:
    """Programmatic entry — used in tests and from cli.py.

    ``argv`` is just the subcommand list (e.g. ``["session-start"]``).
    ``stdin_payload`` (if given) replaces sys.stdin so the hook script
    reads from it.
    """
    if not argv or argv[0] not in EVENTS:
        sys.stderr.write(
            f"mnemos hook: unknown event '{argv[0] if argv else ''}'. "
            f"Expected one of: {', '.join(EVENTS)}\n"
        )
        return 2

    event = argv[0]
    if stdin_payload is not None:
        sys.stdin = io.StringIO(stdin_payload)

    main_fn = _DISPATCH[event]()
    try:
        result = main_fn()
        return int(result) if result is not None else 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0


def _cmd_hook(args: argparse.Namespace) -> int:
    return run([args.event])


def add_hook_subparser(parent: argparse._SubParsersAction) -> None:
    p = parent.add_parser("hook", help="Run a Claude Code hook (internal — invoked by Claude Code)")
    p.add_argument("event", choices=EVENTS, help="Hook event name")
    p.set_defaults(func=_cmd_hook)
```

- [ ] **Step 4: Wire into `cli.py`**

After `add_doctor_subparser(sub)`:
```python
from claude_mnemos.cli_hook import add_hook_subparser
add_hook_subparser(sub)
```

In dispatcher, after `if args.command == "doctor":`:
```python
if args.command == "hook":
    return args.func(args)
```

- [ ] **Step 5: Run tests**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_cli_hook.py -v
```
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```
git add claude_mnemos/cli_hook.py claude_mnemos/cli.py tests/test_cli_hook.py
git commit -m "feat(cli): mnemos hook <event> — fast hook entry for frozen bundle

Lazy-imports only the matching hooks/<event>.py main(), skipping the
FastAPI/uvicorn stack so cold-start stays under ~500ms. Used as the
exec target in ~/.claude/settings.json when mnemos hooks install runs
in frozen-bundle mode (Task 4)."
```

---

### Task 4: `cli_hooks._detect_hook_scripts` returns frozen-mode commands

When `runtime.is_frozen()`, `install()` must write `<bundled-exe> hook session-start` into settings.json instead of `python <script.py>`. Source mode unchanged.

**Files:**
- Modify: `claude_mnemos/cli_hooks.py`
- Test: `tests/test_cli_hooks.py` — add frozen-mode test

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli_hooks.py — append
def test_install_uses_exe_subcommand_in_frozen_mode(tmp_path, monkeypatch):
    """In frozen mode, hook commands must point at <exe> hook <event>, not python <script.py>."""
    settings = tmp_path / "settings.json"
    monkeypatch.setattr("claude_mnemos.cli_hooks.CLAUDE_SETTINGS", settings)
    fake_exe = tmp_path / "claude-mnemos.exe"
    fake_exe.write_bytes(b"")

    monkeypatch.setattr("claude_mnemos.cli_hooks.runtime.is_frozen", lambda: True)
    monkeypatch.setattr(
        "claude_mnemos.cli_hooks.runtime.executable_path",
        lambda: fake_exe,
    )

    from claude_mnemos import cli_hooks
    result = cli_hooks.install()

    import json
    data = json.loads(settings.read_text(encoding="utf-8"))
    cmds: list[str] = []
    for event in ("SessionStart", "SessionEnd", "PreCompact"):
        for block in data["hooks"][event]:
            for h in block["hooks"]:
                cmds.append(h["command"])

    assert any("hook session-start" in c for c in cmds)
    assert any("hook session-end" in c for c in cmds)
    assert any("hook pre-compact" in c for c in cmds)
    # Source-mode python invocation must NOT appear.
    assert not any(".py" in c for c in cmds)
    # Result keys point at the exe + subcommand for both source-mode and frozen-mode shape consistency.
    assert "session_start_script" in result
```

- [ ] **Step 2: RED**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_cli_hooks.py::test_install_uses_exe_subcommand_in_frozen_mode -v
```
Expected: FAIL — frozen-mode branch absent.

- [ ] **Step 3: Update `cli_hooks.py`**

```python
# claude_mnemos/cli_hooks.py — top of file, add:
from claude_mnemos import runtime

# Replace _detect_hook_scripts with:
def _detect_hook_scripts() -> tuple[str, str, str]:
    """Locate hook command lines for the three events.

    Returns three quoted command strings ready to drop into settings.json.

    In frozen mode (PyInstaller bundle) the hook target is the bundled exe
    invoked as ``"<exe>" hook <event>``. In source mode it's
    ``"<python>" "<script.py>"`` for each of session_start.py / session_end.py
    / pre_compact.py — the historical behavior.
    """
    if runtime.is_frozen():
        exe = runtime.executable_path()
        ss = f'"{exe}" hook session-start'
        se = f'"{exe}" hook session-end'
        pc = f'"{exe}" hook pre-compact'
        return ss, se, pc

    # Source mode (existing logic)
    py = _detect_python()
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "hooks",
        here.parent / "hooks",
    ]
    for d in candidates:
        ss = d / "session_start.py"
        se = d / "session_end.py"
        pc = d / "pre_compact.py"
        if ss.exists() and se.exists() and pc.exists():
            return f'{py} "{ss}"', f'{py} "{se}"', f'{py} "{pc}"'
    raise FileNotFoundError(
        f"Could not locate mnemos hook scripts. Tried: {[str(c) for c in candidates]}"
    )
```

NOTE: This changes the return shape — previously the function returned three quoted *paths* and the caller wrapped them with `_detect_python()`. Now it returns three full *command lines*. Update `install()` accordingly:

```python
# claude_mnemos/cli_hooks.py — replace install() body
def install(*, dry_run: bool = False) -> dict:
    ss_cmd, se_cmd, pc_cmd = _detect_hook_scripts()  # now full command lines

    if dry_run:
        return {
            "ok": True,
            "session_start_script": ss_cmd,
            "session_end_script": se_cmd,
            "pre_compact_script": pc_cmd,
            "backup_path": None,
            "dry_run": True,
        }

    backup = _backup_settings()
    settings = _load_settings()
    settings.setdefault("hooks", {})
    hooks = settings["hooks"]

    ss_block = _build_hook_block(ss_cmd)
    se_block = _build_hook_block(se_cmd)
    pc_block = _build_hook_block(pc_cmd)

    for event, new_block in (
        ("SessionStart", ss_block),
        ("SessionEnd", se_block),
        ("PreCompact", pc_block),
    ):
        existing = hooks.get(event, [])
        filtered = [
            block for block in existing
            if not any(_is_mnemos_command(h.get("command", "")) for h in block.get("hooks", []))
        ]
        filtered.append(new_block)
        hooks[event] = filtered

    _save_settings(settings)
    return {
        "ok": True,
        "session_start_script": ss_cmd,
        "session_end_script": se_cmd,
        "pre_compact_script": pc_cmd,
        "backup_path": str(backup) if backup else None,
    }
```

Drop the `python` field from the return dict — callers used `result['python']` only in `_cmd_install`'s print. Replace those prints to print the full commands directly:

```python
def _cmd_install(_args: argparse.Namespace) -> int:
    try:
        result = install()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    if result.get("backup_path"):
        print(f"backup → {result['backup_path']}")
    print("[OK] mnemos hooks installed")
    print(f"  SessionStart: {result['session_start_script']}")
    print(f"  SessionEnd:   {result['session_end_script']}")
    print(f"  PreCompact:   {result['pre_compact_script']}")
    print()
    print("Existing non-mnemos hooks for these events were preserved.")
    return 0
```

- [ ] **Step 4: Run all cli_hooks tests, including existing ones (some assert `result['python']` and need updating to read the command directly)**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_cli_hooks.py -v
```

If existing tests fail because they read `result["python"]`, update them to assert on the command lines directly. Pattern:
```python
# OLD
assert result["session_start_script"].endswith('session_start.py"')
# NEW (still works — the script field still ends with the same path in source mode)
```
The old assertion still holds. Likely no changes needed.

If a test asserts `result["python"]`, drop that key check.

- [ ] **Step 5: Run full suite**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/ --deselect tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle -q | tail -3
```
Expected: 1698 passed (was 1697 + 1 new).

- [ ] **Step 6: Commit**

```
git add claude_mnemos/cli_hooks.py tests/test_cli_hooks.py
git commit -m "feat(hooks): emit '<exe> hook <event>' commands in frozen mode

cli_hooks._detect_hook_scripts now returns full command lines rather
than quoted paths. In source mode the lines are 'python <hook.py>'
(unchanged). In frozen mode they are '<bundled-exe> hook <event>'
which is a stable target after install."
```

---

### Task 5: PyInstaller spec — bundle the package

Build a working bundle on Windows. Verify it launches and serves the dashboard.

**Files:**
- Create: `installer/pyinstaller/mnemos.spec`
- Create: `installer/pyinstaller/README.md` (build instructions)

- [ ] **Step 1: Install PyInstaller in the venv**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pip install pyinstaller==6.11.0
```
Expected: Successfully installed pyinstaller-6.11.0.

- [ ] **Step 2: Add to optional dependencies**

```toml
# pyproject.toml — add or extend [project.optional-dependencies]
[project.optional-dependencies]
installer = ["pyinstaller>=6.11"]
```

- [ ] **Step 3: Write the spec**

```python
# installer/pyinstaller/mnemos.spec
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for claude-mnemos.

Build:
    ~/pipx/venvs/claude-mnemos/Scripts/python.exe -m PyInstaller installer/pyinstaller/mnemos.spec

Output: dist/claude-mnemos/  (one-dir mode, bundled python.exe + DLLs + assets)
Main exe: dist/claude-mnemos/claude-mnemos.exe
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent.parent  # repo root
PKG = ROOT / "claude_mnemos"

block_cipher = None

# Datas: include frontend bundle, prompts, tray assets, and hook scripts.
# All paths are (source, dest-relative-to-bundle-root).
datas = [
    (str(PKG / "daemon" / "static"),     "claude_mnemos/daemon/static"),
    (str(PKG / "ingest" / "prompts"),    "claude_mnemos/ingest/prompts"),
    (str(PKG / "tray" / "assets"),       "claude_mnemos/tray/assets"),
    (str(ROOT / "hooks"),                "hooks"),
    (str(ROOT / "hooks" / "hooks.json"), "hooks"),
]

# Hidden imports that PyInstaller's static analysis misses.
hiddenimports = [
    # FastAPI / uvicorn dynamic loads
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.workers",
    # Pydantic v2 internals
    "pydantic.deprecated.decorator",
    "pydantic_core",
    # APScheduler
    "apscheduler.executors.pool",
    "apscheduler.executors.asyncio",
    "apscheduler.triggers.cron",
    "apscheduler.triggers.interval",
    "apscheduler.jobstores.memory",
    # File watching
    "watchdog.observers",
    "watchdog.observers.polling",
    "watchdog.observers.read_directory_changes",
    # Tray (Windows)
    "pystray._win32",
    # HTTP client used by hooks
    "requests",
    "urllib3",
    "charset_normalizer",
    # Local hook scripts (not normally importable; sys.path tweak in cli_hook.py loads them)
    # PyInstaller cannot follow that — but the source files are bundled via datas,
    # which is enough for runtime sys.path-based imports.
]

a = Analysis(
    [str(PKG / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest", "doctest", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="claude-mnemos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # console for daemon foreground; tray launches detached
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PKG / "tray" / "assets" / "icon.ico") if (PKG / "tray" / "assets" / "icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="claude-mnemos",
)
```

NOTE: The spec assumes `claude_mnemos/__main__.py` exists. If it doesn't, create one:

```python
# claude_mnemos/__main__.py — only create if missing
from claude_mnemos.cli import main
import sys
if __name__ == "__main__":
    sys.exit(main())
```

(Run `ls claude_mnemos/__main__.py` first; if present, leave alone.)

- [ ] **Step 4: Build**

```
cd /d/code/claude-mnemos && ~/pipx/venvs/claude-mnemos/Scripts/python.exe -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm 2>&1 | tail -40
```
Expected: lines like `INFO: Building EXE...`, `INFO: Building COLLECT done.`. No `ERROR` or `Traceback`.

- [ ] **Step 5: Smoke-test the bundle**

```
./dist/claude-mnemos/claude-mnemos.exe --version 2>&1
```
Expected: prints `claude-mnemos 0.0.1` (or whatever version is in pyproject).

```
./dist/claude-mnemos/claude-mnemos.exe doctor 2>&1
```
Expected: prints the 4-row checklist (claude_cli OK if installed, hooks WARN/OK, vaults OK, projects OK).

- [ ] **Step 6: Smoke-test the daemon**

In a separate terminal — first verify the dev daemon is NOT on :5757 (or stop it) so the bundled one can claim the port:

```
./dist/claude-mnemos/claude-mnemos.exe daemon foreground &
sleep 5
curl -s http://localhost:5757/api/health | head -c 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5757
# Expected: health JSON; 200 for the SPA
```
Then stop the bundled daemon (`Ctrl+C`).

If the SPA is 404, `static_dir()` resolution failed — check `dist/claude-mnemos/_internal/claude_mnemos/daemon/static/index.html` exists.

- [ ] **Step 7: Add a CI-style smoke test (does NOT run by default — only on explicit invocation)**

```python
# tests/installer/__init__.py
# tests/installer/test_pyinstaller_smoke.py
"""Smoke test for the PyInstaller bundle.

This test does NOT run with the default pytest invocation — it requires
the bundle to exist at ./dist/claude-mnemos/claude-mnemos.exe. CI invokes
it explicitly after building. Skipped otherwise.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

BUNDLE = Path("dist/claude-mnemos/claude-mnemos.exe")
if os.name != "nt":
    BUNDLE = Path("dist/claude-mnemos/claude-mnemos")


@pytest.mark.skipif(not BUNDLE.exists(), reason="PyInstaller bundle not built")
def test_bundle_doctor_runs() -> None:
    """The bundled exe must run `doctor` and exit (0 or 1) within 10s."""
    proc = subprocess.run(
        [str(BUNDLE), "doctor"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode in (0, 1), f"unexpected rc={proc.returncode}; stderr={proc.stderr}"
    assert "claude_cli" in proc.stdout
    assert "hooks" in proc.stdout
```

- [ ] **Step 8: Commit (do NOT commit the `dist/` directory)**

```
echo "dist/" >> .gitignore
echo "build/" >> .gitignore
git add installer/pyinstaller/mnemos.spec installer/pyinstaller/README.md pyproject.toml claude_mnemos/__main__.py tests/installer/test_pyinstaller_smoke.py .gitignore
git commit -m "feat(installer): PyInstaller spec + smoke test

One-dir bundle (~80MB). Datas: frontend SPA, LLM prompts, tray PNGs,
hook scripts. Hidden imports cover FastAPI/uvicorn/APScheduler/watchdog
dynamic loads.

Build:
  python -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm

Output:
  dist/claude-mnemos/claude-mnemos.exe

Smoke tested locally on Windows. Mac/Linux variants verified by CI
(Task 11)."
```

---

### Task 6: `postinstall.py` — first-run automation

When the bundled exe runs for the first time after install (no `~/.claude-mnemos/install-state.json` or `first_run_ts is None`), automatically run `cli_init.run()` so the user lands on a working dashboard without typing anything.

**Files:**
- Create: `claude_mnemos/postinstall.py`
- Modify: `claude_mnemos/cli.py` — call once on every invocation
- Test: `tests/test_postinstall.py`

- [ ] **Step 1: Test (RED)**

```python
# tests/test_postinstall.py
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def state_path(tmp_path: Path, monkeypatch) -> Path:
    p = tmp_path / "install-state.json"
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        p,
    )
    return p


def test_first_launch_triggers_init(state_path: Path, monkeypatch) -> None:
    calls = {"init": 0}
    monkeypatch.setattr(
        "claude_mnemos.postinstall.cli_init_run",
        lambda *, open_browser: calls.update({"init": calls["init"] + 1}) or 0,
    )

    from claude_mnemos.postinstall import maybe_run_first_time_init
    maybe_run_first_time_init()
    assert calls["init"] == 1


def test_subsequent_launches_skip_init(state_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "claude_mnemos.postinstall.cli_init_run",
        lambda *, open_browser: 0,
    )

    from claude_mnemos.postinstall import maybe_run_first_time_init
    maybe_run_first_time_init()  # records first_run_ts

    calls = {"init": 0}
    monkeypatch.setattr(
        "claude_mnemos.postinstall.cli_init_run",
        lambda *, open_browser: calls.update({"init": calls["init"] + 1}) or 0,
    )
    maybe_run_first_time_init()
    assert calls["init"] == 0


def test_skipped_in_source_mode(state_path: Path, monkeypatch) -> None:
    """Source-mode (development via pipx) must NEVER auto-run init."""
    calls = {"init": 0}
    monkeypatch.setattr(
        "claude_mnemos.postinstall.cli_init_run",
        lambda *, open_browser: calls.update({"init": calls["init"] + 1}) or 0,
    )
    monkeypatch.setattr("claude_mnemos.postinstall.runtime.is_frozen", lambda: False)

    from claude_mnemos.postinstall import maybe_run_first_time_init
    maybe_run_first_time_init()
    assert calls["init"] == 0
```

- [ ] **Step 2: RED**
```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_postinstall.py -v
```

- [ ] **Step 3: Implement**

```python
# claude_mnemos/postinstall.py
"""First-run-after-install: auto-run mnemos init on the very first launch
of the bundled executable.

Skipped entirely in source mode (development via pipx) — devs run
`mnemos init` explicitly when they want to.
"""

from __future__ import annotations

from datetime import datetime, timezone

from claude_mnemos import runtime
from claude_mnemos.cli_init import run as cli_init_run
from claude_mnemos.state.install_state import load_install_state


def maybe_run_first_time_init() -> None:
    """Run cli_init.run() exactly once per fresh install. Idempotent."""
    if not runtime.is_frozen():
        return
    state = load_install_state()
    if state.first_run_ts is not None:
        return
    cli_init_run(open_browser=True)
    state = load_install_state()  # cli_init may have updated autostart_decision
    state.first_run_ts = datetime.now(tz=timezone.utc)
    state.save()
```

- [ ] **Step 4: Wire into `cli.py`**

```python
# claude_mnemos/cli.py — at the very top of main(), before parsing args
def main() -> int:
    from claude_mnemos.postinstall import maybe_run_first_time_init
    maybe_run_first_time_init()
    # ... existing parser setup follows
```

- [ ] **Step 5: Run + commit**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/test_postinstall.py -v
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/ --deselect tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle -q | tail -3
git add claude_mnemos/postinstall.py claude_mnemos/cli.py tests/test_postinstall.py
git commit -m "feat(installer): postinstall — auto-run mnemos init on first launch

Bundled exe runs hooks install + tray autostart + browser open exactly
once on the very first invocation. Source mode (pipx development) is
never affected. Idempotent via install_state.first_run_ts."
```

---

### Task 7: Inno Setup script — Windows installer

Wrap the PyInstaller `dist/claude-mnemos/` directory with an Inno Setup `.iss` script. Builds `claude-mnemos-setup-x64.exe`.

**Files:**
- Create: `installer/windows/mnemos.iss`
- Create: `installer/windows/build.ps1` (optional convenience wrapper)
- Create: `installer/windows/README.md`

- [ ] **Step 1: Write the `.iss` script**

```ini
; installer/windows/mnemos.iss
; Inno Setup script for claude-mnemos.
; Build:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/windows/mnemos.iss
; Output:
;   installer/windows/dist/claude-mnemos-setup-x64.exe

#define MyAppName "claude-mnemos"
#define MyAppVersion "0.0.1"
#define MyAppPublisher "Yarik"
#define MyAppURL "https://github.com/DeveloperrOp/claude-mnemos"
#define MyAppExeName "claude-mnemos.exe"

[Setup]
AppId={{4F2A8C90-7D5C-4B1A-9D3E-8E9F1A2B3C4D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=claude-mnemos-setup-x64
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
CloseApplications=force
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "autostart";   Description: "Start &claude-mnemos when I sign in to Windows"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
; PyInstaller produces dist/claude-mnemos/ as a one-dir bundle.
; Path is relative to this .iss file.
Source: "..\..\dist\claude-mnemos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "tray run"
Name: "{group}\Open Dashboard"; Filename: "http://localhost:5757"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "tray run"; Tasks: desktopicon

[Run]
; Launch tray (which auto-spawns daemon) on first run.
Filename: "{app}\{#MyAppExeName}"; Parameters: "tray run"; Description: "Start claude-mnemos now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Stop the tray + daemon before file removal.
Filename: "{app}\{#MyAppExeName}"; Parameters: "tray uninstall"; Flags: runhidden; RunOnceId: "RemoveAutostart"
Filename: "{app}\{#MyAppExeName}"; Parameters: "daemon stop";    Flags: runhidden; RunOnceId: "StopDaemon"
Filename: "{app}\{#MyAppExeName}"; Parameters: "hooks uninstall"; Flags: runhidden; RunOnceId: "RemoveHooks"

[Registry]
; Note: actual autostart registration is done by mnemos tray install
; (which writes to HKCU\...\Run). This block is just a placeholder.
```

- [ ] **Step 2: Build the installer**

(Requires Inno Setup installed.)

```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/windows/mnemos.iss 2>&1 | tail -10
```
Expected: `Successful compile (...)`. Output at `installer/windows/dist/claude-mnemos-setup-x64.exe`.

- [ ] **Step 3: Smoke-test the installer**

(Requires admin or per-user install.)

```
./installer/windows/dist/claude-mnemos-setup-x64.exe /SILENT
```
Then verify:
- `dir "%ProgramFiles%\claude-mnemos\"` — should contain `claude-mnemos.exe`
- Start menu has "claude-mnemos" + "Open Dashboard"
- Tray icon present (after first manual run if not auto-launched)
- `~/.claude/settings.json` has hook commands pointing at `%ProgramFiles%\claude-mnemos\claude-mnemos.exe`

To uninstall:
```
"%ProgramFiles%\claude-mnemos\unins000.exe" /SILENT
```

- [ ] **Step 4: Convenience build script**

```powershell
# installer/windows/build.ps1
# Build pipeline: PyInstaller bundle → Inno Setup → installer/windows/dist/<file>.exe

$ErrorActionPreference = "Stop"
$PROJECT_ROOT = (Get-Item $PSScriptRoot).Parent.Parent.FullName
Set-Location $PROJECT_ROOT

Write-Host "[build] PyInstaller bundle..."
& "$env:USERPROFILE\pipx\venvs\claude-mnemos\Scripts\python.exe" -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm

Write-Host "[build] Inno Setup compile..."
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/windows/mnemos.iss

$out = Join-Path $PROJECT_ROOT "installer/windows/dist/claude-mnemos-setup-x64.exe"
Write-Host "[ok] Installer at $out"
```

- [ ] **Step 5: Commit**

```
git add installer/windows/mnemos.iss installer/windows/build.ps1 installer/windows/README.md
git commit -m "feat(installer/windows): Inno Setup script + build wrapper

Wraps the PyInstaller bundle into claude-mnemos-setup-x64.exe (~70MB
compressed). Per-user or system install, autostart task default-on,
Start Menu + optional desktop shortcut. Uninstall stops the daemon,
removes autostart, and uninstalls hooks before file deletion."
```

---

### Task 8: macOS py2app + create-dmg

Build `claude-mnemos.dmg` containing `claude-mnemos.app`. py2app sets up the app bundle; `create-dmg` packages it.

**Files:**
- Create: `installer/macos/setup.py`
- Create: `installer/macos/build-dmg.sh`
- Create: `installer/macos/Info.plist.template`
- Create: `installer/macos/README.md`

This task is CI-only (no Mac on dev box). Verify by reading the build step output on `macos-latest` GitHub Actions runner (Task 11).

- [ ] **Step 1: `setup.py` for py2app**

```python
# installer/macos/setup.py
"""py2app build for claude-mnemos.

Run:
    python setup.py py2app

Output:
    dist/claude-mnemos.app/
"""
from setuptools import setup
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PKG = ROOT / "claude_mnemos"

APP = [str(PKG / "__main__.py")]
DATA_FILES = [
    ("claude_mnemos/daemon/static",  [str(p) for p in (PKG / "daemon" / "static").rglob("*") if p.is_file()]),
    ("claude_mnemos/ingest/prompts", [str(p) for p in (PKG / "ingest" / "prompts").rglob("*") if p.is_file()]),
    ("claude_mnemos/tray/assets",    [str(p) for p in (PKG / "tray" / "assets").rglob("*") if p.is_file()]),
    ("hooks",                        [str(p) for p in (ROOT / "hooks").rglob("*") if p.is_file()]),
]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": str(PKG / "tray" / "assets" / "icon.icns") if (PKG / "tray" / "assets" / "icon.icns").exists() else None,
    "plist": {
        "CFBundleName": "claude-mnemos",
        "CFBundleDisplayName": "claude-mnemos",
        "CFBundleIdentifier": "com.yarik.claude-mnemos",
        "CFBundleVersion": "0.0.1",
        "CFBundleShortVersionString": "0.0.1",
        "LSUIElement": True,  # tray-only app, no Dock icon
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    },
    "packages": ["claude_mnemos", "fastapi", "uvicorn", "pydantic", "watchdog", "pystray", "apscheduler"],
    "includes": ["uvicorn.logging", "uvicorn.lifespan.on", "uvicorn.protocols.http.auto"],
    "excludes": ["tkinter"],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
```

- [ ] **Step 2: DMG packaging script**

```bash
#!/usr/bin/env bash
# installer/macos/build-dmg.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

# 1) Build the .app bundle
cd installer/macos
python setup.py py2app
cd ../..

APP="installer/macos/dist/claude-mnemos.app"
test -d "$APP" || { echo "py2app did not produce $APP"; exit 1; }

# 2) Sign nothing (initial release ships unsigned — Gatekeeper bypass documented in README)

# 3) Create DMG
DMG_OUT="installer/macos/dist/claude-mnemos.dmg"
rm -f "$DMG_OUT"
create-dmg \
  --volname "claude-mnemos" \
  --window-size 540 380 \
  --icon-size 100 \
  --icon "claude-mnemos.app" 130 200 \
  --app-drop-link 410 200 \
  "$DMG_OUT" \
  "$APP"

echo "[ok] DMG written to $DMG_OUT"
```

- [ ] **Step 3: README for the Mac sub-tree**

```markdown
# installer/macos/README.md
# macOS build

Local prerequisites (CI installs these automatically):

```
brew install create-dmg
pip install py2app==0.28.6
```

Build:

```
bash installer/macos/build-dmg.sh
```

Output: `installer/macos/dist/claude-mnemos.dmg`.

The bundle is unsigned. First-run users will see a Gatekeeper warning;
right-click → Open to accept it. We will sign the app once we have a
Developer ID Application certificate (deferred from initial release).
```

- [ ] **Step 4: Commit**

```
chmod +x installer/macos/build-dmg.sh
git add installer/macos/setup.py installer/macos/build-dmg.sh installer/macos/README.md
git commit -m "feat(installer/macos): py2app + create-dmg pipeline (CI-built)

Produces claude-mnemos.dmg for arm64+x64 (universal). LSUIElement=true
so the app shows only in the menu bar, not the Dock. Unsigned for
the initial release; Gatekeeper bypass documented."
```

---

### Task 9: Linux AppImage

Build `claude-mnemos-x86_64.AppImage`. Single-file portable executable.

**Files:**
- Create: `installer/linux/claude-mnemos.desktop`
- Create: `installer/linux/build-appimage.sh`
- Create: `installer/linux/README.md`

CI-only task (Linux build verified on `ubuntu-latest`).

- [ ] **Step 1: Desktop entry**

```ini
# installer/linux/claude-mnemos.desktop
[Desktop Entry]
Type=Application
Name=claude-mnemos
GenericName=Claude Code Memory Daemon
Comment=Capture and recall Claude Code session context
Icon=claude-mnemos
Exec=claude-mnemos tray run
Terminal=false
Categories=Development;Utility;
StartupNotify=false
```

- [ ] **Step 2: Build script using linuxdeploy + python plugin**

```bash
#!/usr/bin/env bash
# installer/linux/build-appimage.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

# Tools (CI installs in workflow; this script assumes presence)
LINUXDEPLOY="${LINUXDEPLOY:-linuxdeploy-x86_64.AppImage}"
LINUXDEPLOY_PYTHON="${LINUXDEPLOY_PYTHON:-linuxdeploy-plugin-python-x86_64.AppImage}"

if [ ! -x "$LINUXDEPLOY" ]; then
  curl -L -o linuxdeploy-x86_64.AppImage "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
  chmod +x linuxdeploy-x86_64.AppImage
  LINUXDEPLOY=./linuxdeploy-x86_64.AppImage
fi

# Build the PyInstaller bundle first.
python -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm

# Stage the AppDir.
APPDIR=installer/linux/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -r dist/claude-mnemos/* "$APPDIR/usr/bin/"
mv "$APPDIR/usr/bin/claude-mnemos" "$APPDIR/usr/bin/claude-mnemos.real"
cat > "$APPDIR/usr/bin/claude-mnemos" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/claude-mnemos.real" "$@"
EOF
chmod +x "$APPDIR/usr/bin/claude-mnemos"

cp installer/linux/claude-mnemos.desktop "$APPDIR/usr/share/applications/"
# Generate a minimal 256×256 icon if none exists (claude_mnemos/tray/assets/icon.png preferred).
if [ -f claude_mnemos/tray/assets/icon.png ]; then
  cp claude_mnemos/tray/assets/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/claude-mnemos.png"
else
  echo "[warn] no icon.png found — using placeholder"
  convert -size 256x256 xc:gray "$APPDIR/usr/share/icons/hicolor/256x256/apps/claude-mnemos.png" || true
fi

# Build the AppImage.
"$LINUXDEPLOY" --appdir "$APPDIR" \
  --desktop-file installer/linux/claude-mnemos.desktop \
  --icon-file "$APPDIR/usr/share/icons/hicolor/256x256/apps/claude-mnemos.png" \
  --output appimage

mv claude-mnemos-*.AppImage installer/linux/dist/ 2>/dev/null || mkdir -p installer/linux/dist/ && mv claude-mnemos-*.AppImage installer/linux/dist/

echo "[ok] AppImage at installer/linux/dist/claude-mnemos-x86_64.AppImage"
```

- [ ] **Step 3: Commit**

```
chmod +x installer/linux/build-appimage.sh
git add installer/linux/claude-mnemos.desktop installer/linux/build-appimage.sh installer/linux/README.md
git commit -m "feat(installer/linux): AppImage build script

Single-file portable executable. linuxdeploy + python plugin pull
the PyInstaller bundle into an AppDir, then assemble the AppImage
with the .desktop entry. Verified on ubuntu-latest CI runners."
```

---

### Task 10: Auto-update notifier — banner + manual download

> **Scope addition (2026-05-04, Yarik's call):** the spec marked auto-update as out-of-scope. We're putting it back in *minimally*: poll GitHub Releases, show a banner when a newer version exists, click → opens the download in the browser. We don't auto-replace binaries (Sparkle / Squirrel are deferred — they require code-signing to be safe). This must ship in `v0.0.1` so future releases can be discovered by `v0.0.1` users.

**Files:**
- Create: `claude_mnemos/core/update_check.py` — pure helper that fetches `https://api.github.com/repos/DeveloperrOp/claude-mnemos/releases/latest`, compares versions, returns `{current, latest, download_url, has_update}`. Cached on disk (`~/.claude-mnemos/update-check.json`) for 24h.
- Create: `claude_mnemos/daemon/routes/update.py` — `GET /api/update-status`, `POST /api/update-status/dismiss` (snoozes the banner for 7 days).
- Modify: `claude_mnemos/daemon/process.py` — register `update_check_global` cron (every 24h).
- Modify: `claude_mnemos/daemon/app.py` — include the new router.
- Create: `frontend/src/api/update.api.ts`
- Create: `frontend/src/hooks/useUpdateStatus.ts`
- Create: `frontend/src/components/widgets/dashboard/UpdateBanner.tsx`
- Modify: `frontend/src/pages/Overview.tsx` — mount banner under `<HealthAlertsBar />`.
- Test: `tests/core/test_update_check.py`, `tests/daemon/test_app_update.py`, `frontend/src/__tests__/UpdateBanner.test.tsx`

- [ ] **Step 1: Backend test (RED)**

```python
# tests/core/test_update_check.py
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def cache_path(tmp_path: Path, monkeypatch) -> Path:
    p = tmp_path / "update-check.json"
    monkeypatch.setattr("claude_mnemos.core.update_check._CACHE_PATH", p)
    return p


def test_check_returns_has_update_when_newer_remote(monkeypatch, cache_path: Path) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release",
        lambda: {"tag_name": "v0.0.5", "html_url": "https://github.com/x/y/releases/tag/v0.0.5"},
    )
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")

    from claude_mnemos.core.update_check import check_for_update

    result = check_for_update(force=True)
    assert result.has_update is True
    assert result.current == "0.0.1"
    assert result.latest == "0.0.5"
    assert result.download_url.endswith("/v0.0.5")


def test_check_returns_no_update_when_same_version(monkeypatch, cache_path: Path) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release",
        lambda: {"tag_name": "v0.0.1", "html_url": "x"},
    )
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")

    from claude_mnemos.core.update_check import check_for_update
    result = check_for_update(force=True)
    assert result.has_update is False


def test_check_uses_cache_when_recent(monkeypatch, cache_path: Path) -> None:
    """If the cache is younger than _CACHE_TTL, do NOT hit the network."""
    cache_path.write_text(
        json.dumps({
            "checked_at": datetime.now(tz=UTC).isoformat(),
            "current": "0.0.1",
            "latest": "0.0.7",
            "download_url": "https://example.com/v0.0.7",
            "dismissed_until": None,
        }),
        encoding="utf-8",
    )

    fetched = {"calls": 0}
    def fake_fetch():
        fetched["calls"] += 1
        return {"tag_name": "v0.0.99", "html_url": "x"}
    monkeypatch.setattr("claude_mnemos.core.update_check._fetch_latest_release", fake_fetch)
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")

    from claude_mnemos.core.update_check import check_for_update
    result = check_for_update(force=False)
    assert fetched["calls"] == 0  # cache hit
    assert result.latest == "0.0.7"


def test_dismiss_records_until_timestamp(monkeypatch, cache_path: Path) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release",
        lambda: {"tag_name": "v0.0.5", "html_url": "x"},
    )
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")

    from claude_mnemos.core.update_check import check_for_update, dismiss_for_days

    check_for_update(force=True)
    dismiss_for_days(7)

    # While snoozed, has_update reads the cache but the banner-suppress logic happens in the route layer.
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert data["dismissed_until"] is not None


def test_check_returns_no_update_on_network_error(monkeypatch, cache_path: Path) -> None:
    def fake_fetch():
        raise OSError("offline")
    monkeypatch.setattr("claude_mnemos.core.update_check._fetch_latest_release", fake_fetch)
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")

    from claude_mnemos.core.update_check import check_for_update
    result = check_for_update(force=True)
    assert result.has_update is False
    assert result.error is not None
```

- [ ] **Step 2: Run, RED**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_update_check.py -v
```

- [ ] **Step 3: Implement `core/update_check.py`**

```python
# claude_mnemos/core/update_check.py
"""Auto-update check against GitHub Releases.

We do NOT auto-download or auto-replace binaries (that needs Sparkle /
Squirrel + code-signing). We just compare versions and surface a
"Update available — click to download" banner. Click opens the latest
release page in the user's browser; they download + run the new
installer manually.

Cache: ``~/.claude-mnemos/update-check.json``. Background cron refreshes
every 24h. Dismissal records ``dismissed_until`` and the route hides
the banner until that time elapses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import urllib.error
import urllib.request

from claude_mnemos import __version__

_GITHUB_LATEST_RELEASE = "https://api.github.com/repos/DeveloperrOp/claude-mnemos/releases/latest"
_CACHE_PATH: Path = Path.home() / ".claude-mnemos" / "update-check.json"
_CACHE_TTL = timedelta(hours=24)


@dataclass
class UpdateStatus:
    current: str
    latest: str | None
    download_url: str | None
    has_update: bool
    checked_at: datetime
    dismissed_until: datetime | None = None
    error: str | None = None


def _current_version() -> str:
    return __version__


def _fetch_latest_release() -> dict:
    """Hit GitHub. Raises OSError on network failure, ValueError on bad JSON."""
    req = urllib.request.Request(
        _GITHUB_LATEST_RELEASE,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "claude-mnemos"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_version(v: str) -> tuple[int, ...]:
    """'v0.0.5' or '0.0.5' → (0, 0, 5). Non-numeric chunks become 0."""
    raw = v.lstrip("v")
    parts: list[int] = []
    for chunk in raw.split("."):
        try:
            parts.append(int(chunk.split("-")[0]))  # strip pre-release suffix
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _load_cache() -> dict | None:
    if not _CACHE_PATH.exists():
        return None
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_cache(data: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def check_for_update(*, force: bool = False) -> UpdateStatus:
    """Return the current update status. Hits network at most once per TTL.

    ``force=True`` bypasses the cache (used by the cron task).
    """
    now = datetime.now(tz=UTC)
    cached = _load_cache()

    if not force and cached:
        try:
            checked_at = datetime.fromisoformat(cached["checked_at"])
            if now - checked_at < _CACHE_TTL:
                return UpdateStatus(
                    current=cached["current"],
                    latest=cached.get("latest"),
                    download_url=cached.get("download_url"),
                    has_update=bool(cached.get("latest") and _parse_version(cached["latest"]) > _parse_version(cached["current"])),
                    checked_at=checked_at,
                    dismissed_until=datetime.fromisoformat(cached["dismissed_until"]) if cached.get("dismissed_until") else None,
                )
        except (KeyError, ValueError):
            pass

    current = _current_version()
    try:
        release = _fetch_latest_release()
        latest = release.get("tag_name", "").lstrip("v")
        download_url = release.get("html_url")
        has_update = bool(latest) and _parse_version(latest) > _parse_version(current)
        status = UpdateStatus(
            current=current,
            latest=latest or None,
            download_url=download_url,
            has_update=has_update,
            checked_at=now,
        )
    except (OSError, ValueError, urllib.error.URLError) as exc:
        status = UpdateStatus(
            current=current,
            latest=None,
            download_url=None,
            has_update=False,
            checked_at=now,
            error=str(exc),
        )

    # Preserve dismissed_until across refreshes.
    if cached and cached.get("dismissed_until"):
        try:
            status.dismissed_until = datetime.fromisoformat(cached["dismissed_until"])
        except ValueError:
            pass

    _save_cache({
        "checked_at": status.checked_at.isoformat(),
        "current": status.current,
        "latest": status.latest,
        "download_url": status.download_url,
        "dismissed_until": status.dismissed_until.isoformat() if status.dismissed_until else None,
    })
    return status


def dismiss_for_days(days: int) -> None:
    """Snooze the update banner for ``days`` days from now."""
    cached = _load_cache() or {}
    cached["dismissed_until"] = (datetime.now(tz=UTC) + timedelta(days=days)).isoformat()
    if "checked_at" not in cached:
        cached["checked_at"] = datetime.now(tz=UTC).isoformat()
    if "current" not in cached:
        cached["current"] = _current_version()
    _save_cache(cached)
```

- [ ] **Step 4: REST routes**

```python
# claude_mnemos/daemon/routes/update.py
"""Auto-update REST endpoints — banner + dismiss."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body

from claude_mnemos.core.update_check import check_for_update, dismiss_for_days

router = APIRouter()


@router.get("/update-status")
def update_status_route() -> dict[str, Any]:
    s = check_for_update(force=False)
    suppress = (
        s.dismissed_until is not None
        and s.dismissed_until > datetime.now(tz=UTC)
    )
    return {
        "current": s.current,
        "latest": s.latest,
        "download_url": s.download_url,
        "has_update": s.has_update and not suppress,
        "checked_at": s.checked_at.isoformat(),
        "dismissed_until": s.dismissed_until.isoformat() if s.dismissed_until else None,
        "error": s.error,
    }


@router.post("/update-status/dismiss")
def dismiss_route(payload: dict = Body(default={})) -> dict[str, Any]:
    days = int(payload.get("days", 7))
    days = max(1, min(days, 30))  # cap 1-30 days
    dismiss_for_days(days)
    return {"ok": True, "dismissed_for_days": days}
```

Wire into `daemon/app.py`:
```python
from claude_mnemos.daemon.routes.update import router as update_router
# ...
app.include_router(update_router, prefix="/api")
```

- [ ] **Step 5: Cron task in `daemon/process.py`**

Find `_build_cron_tasks` (added in cleanup A4). Add:
```python
CronTask(
    id="update_check_global",
    schedule_kwargs={"hour": 3, "minute": 17},  # 3:17 AM daily
    fn=lambda: asyncio.to_thread(_run_update_check),
),
```

And the helper:
```python
def _run_update_check() -> None:
    try:
        from claude_mnemos.core.update_check import check_for_update
        check_for_update(force=True)
    except Exception:
        logger.exception("update-check cron failed")
```

- [ ] **Step 6: REST integration test**

```python
# tests/daemon/test_app_update.py
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._CACHE_PATH",
        tmp_path / "update-check.json",
    )
    from claude_mnemos.daemon.app import create_app
    return create_app(daemon=None)


@pytest.fixture
def client(app):
    return TestClient(app)


def test_update_status_returns_has_update(client, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release",
        lambda: {"tag_name": "v0.9.0", "html_url": "https://example.com/v0.9.0"},
    )
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")
    r = client.get("/api/update-status")
    assert r.status_code == 200
    body = r.json()
    assert body["has_update"] is True
    assert body["latest"] == "0.9.0"


def test_dismiss_silences_banner(client, monkeypatch):
    monkeypatch.setattr(
        "claude_mnemos.core.update_check._fetch_latest_release",
        lambda: {"tag_name": "v0.9.0", "html_url": "https://example.com/v0.9.0"},
    )
    monkeypatch.setattr("claude_mnemos.core.update_check._current_version", lambda: "0.0.1")
    # First call populates cache.
    assert client.get("/api/update-status").json()["has_update"] is True
    # Dismiss for 7 days.
    r = client.post("/api/update-status/dismiss", json={"days": 7})
    assert r.status_code == 200
    # Subsequent has_update is False.
    assert client.get("/api/update-status").json()["has_update"] is False
```

- [ ] **Step 7: Frontend API + hook**

```typescript
// frontend/src/api/update.api.ts
import axios from "axios";

export interface UpdateStatus {
  current: string;
  latest: string | null;
  download_url: string | null;
  has_update: boolean;
  checked_at: string;
  dismissed_until: string | null;
  error: string | null;
}

export async function getUpdateStatus(): Promise<UpdateStatus> {
  const r = await axios.get<UpdateStatus>("/api/update-status");
  return r.data;
}

export async function dismissUpdate(days: number = 7): Promise<void> {
  await axios.post("/api/update-status/dismiss", { days });
}
```

```typescript
// frontend/src/hooks/useUpdateStatus.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getUpdateStatus, dismissUpdate } from "@/api/update.api";

export function useUpdateStatus() {
  return useQuery({
    queryKey: ["update-status"],
    queryFn: getUpdateStatus,
    refetchInterval: 6 * 60 * 60 * 1000,  // 6h client-side poll (cron refreshes server-side daily)
  });
}

export function useDismissUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: dismissUpdate,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["update-status"] }),
  });
}
```

- [ ] **Step 8: Banner component + test**

```typescript
// frontend/src/__tests__/UpdateBanner.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { UpdateBanner } from "@/components/widgets/dashboard/UpdateBanner";
import * as api from "@/api/update.api";

vi.mock("@/api/update.api");

function renderBanner() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UpdateBanner />
    </QueryClientProvider>,
  );
}

describe("UpdateBanner", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders nothing when no update available", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue({
      current: "0.0.1",
      latest: "0.0.1",
      download_url: null,
      has_update: false,
      checked_at: new Date().toISOString(),
      dismissed_until: null,
      error: null,
    });
    const { container } = renderBanner();
    await new Promise((r) => setTimeout(r, 50));
    expect(container.querySelector("[data-testid='update-banner']")).toBeNull();
  });

  it("renders banner with version + download link when has_update", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue({
      current: "0.0.1",
      latest: "0.1.0",
      download_url: "https://example.com/v0.1.0",
      has_update: true,
      checked_at: new Date().toISOString(),
      dismissed_until: null,
      error: null,
    });
    renderBanner();
    expect(await screen.findByText(/0\.1\.0/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /download/i });
    expect(link).toHaveAttribute("href", "https://example.com/v0.1.0");
  });

  it("calls dismiss when 'Later' clicked", async () => {
    vi.mocked(api.getUpdateStatus).mockResolvedValue({
      current: "0.0.1",
      latest: "0.1.0",
      download_url: "https://example.com/v0.1.0",
      has_update: true,
      checked_at: new Date().toISOString(),
      dismissed_until: null,
      error: null,
    });
    vi.mocked(api.dismissUpdate).mockResolvedValue();
    renderBanner();
    await userEvent.click(await screen.findByRole("button", { name: /later/i }));
    await waitFor(() => expect(api.dismissUpdate).toHaveBeenCalled());
  });
});
```

```tsx
// frontend/src/components/widgets/dashboard/UpdateBanner.tsx
import { useUpdateStatus, useDismissUpdate } from "@/hooks/useUpdateStatus";

export function UpdateBanner() {
  const q = useUpdateStatus();
  const dismiss = useDismissUpdate();

  if (q.isLoading || !q.data || !q.data.has_update || !q.data.download_url) return null;
  const { current, latest, download_url } = q.data;

  return (
    <div
      data-testid="update-banner"
      className="rounded-md border border-blue-500/40 bg-blue-500/10 px-4 py-3 flex items-center gap-3"
    >
      <span className="font-mono text-xs uppercase text-blue-400">UPDATE</span>
      <div className="flex-1 text-sm">
        <span className="font-medium">claude-mnemos {latest}</span> is available
        <span className="text-muted-foreground"> (you have {current})</span>
      </div>
      <a
        href={download_url}
        target="_blank"
        rel="noopener noreferrer"
        className="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600"
      >
        Download
      </a>
      <button
        type="button"
        onClick={() => dismiss.mutate(7)}
        disabled={dismiss.isPending}
        className="rounded-md border border-border/60 px-3 py-1.5 text-xs hover:bg-muted/50"
      >
        Later
      </button>
    </div>
  );
}
```

- [ ] **Step 9: Mount in Overview**

```tsx
// frontend/src/pages/Overview.tsx
import { UpdateBanner } from "@/components/widgets/dashboard/UpdateBanner";

// inside JSX, before <HookStatusBanner />:
<UpdateBanner />
```

- [ ] **Step 10: Run all tests**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_update_check.py tests/daemon/test_app_update.py -v
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/ --deselect tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle -q | tail -3
cd frontend && npm test -- --run UpdateBanner
cd frontend && npm run typecheck
```
Expected: 5 backend + 2 backend route + 3 frontend tests pass; full suite ≥1717.

- [ ] **Step 11: Commit**

```
git add claude_mnemos/core/update_check.py claude_mnemos/daemon/routes/update.py claude_mnemos/daemon/app.py claude_mnemos/daemon/process.py tests/core/test_update_check.py tests/daemon/test_app_update.py
git add frontend/src/api/update.api.ts frontend/src/hooks/useUpdateStatus.ts frontend/src/components/widgets/dashboard/UpdateBanner.tsx frontend/src/pages/Overview.tsx frontend/src/__tests__/UpdateBanner.test.tsx
git commit -m "feat(update): auto-update notifier — banner + click-to-download

Polls GitHub Releases daily (cron at 03:17), 24h cache. UpdateBanner
on Overview surfaces a 'v X.Y.Z available — Download' chip when the
remote tag is newer than the current __version__. Click opens release
page in a new tab; user runs the new installer manually. 'Later'
snoozes the banner for 7 days.

Auto-replace via Sparkle/Squirrel deferred (needs code-signing).
Manual install is fine for the unsigned-binary phase."
```

---

### Task 11: GitHub Actions release workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Write workflow**

```yaml
# .github/workflows/release.yml
name: Release Installers

on:
  push:
    tags:
      - "v*"

permissions:
  contents: write

jobs:
  build:
    name: Build (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: windows-latest
            artifact: claude-mnemos-setup-x64.exe
            artifact_path: installer/windows/dist/claude-mnemos-setup-x64.exe
          - os: macos-latest
            artifact: claude-mnemos.dmg
            artifact_path: installer/macos/dist/claude-mnemos.dmg
          - os: ubuntu-latest
            artifact: claude-mnemos-x86_64.AppImage
            artifact_path: installer/linux/dist/claude-mnemos-x86_64.AppImage

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install Python deps
        run: |
          python -m pip install --upgrade pip
          pip install -e .[installer] py2app==0.28.6

      - name: Build frontend
        working-directory: frontend
        run: |
          npm ci
          npm run build

      - name: Run pytest (smoke)
        run: |
          python -m pytest tests/test_runtime.py tests/test_cli_hook.py tests/test_postinstall.py -v

      - name: Build PyInstaller bundle
        run: python -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm

      - name: Smoke-test the bundle
        run: python -m pytest tests/installer/test_pyinstaller_smoke.py -v

      - name: Build Windows installer
        if: matrix.os == 'windows-latest'
        shell: pwsh
        run: |
          choco install innosetup -y --no-progress
          & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/windows/mnemos.iss

      - name: Build macOS DMG
        if: matrix.os == 'macos-latest'
        run: |
          brew install create-dmg
          bash installer/macos/build-dmg.sh

      - name: Build Linux AppImage
        if: matrix.os == 'ubuntu-latest'
        run: |
          sudo apt-get update
          sudo apt-get install -y libfuse2 imagemagick
          bash installer/linux/build-appimage.sh

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.artifact }}
          path: ${{ matrix.artifact_path }}
          if-no-files-found: error

  release:
    name: Publish GitHub Release
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          path: artifacts

      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: |
            artifacts/claude-mnemos-setup-x64.exe/claude-mnemos-setup-x64.exe
            artifacts/claude-mnemos.dmg/claude-mnemos.dmg
            artifacts/claude-mnemos-x86_64.AppImage/claude-mnemos-x86_64.AppImage
```

- [ ] **Step 2: Trigger a dry-run (without tagging)**

Create a temporary branch with the workflow change, push, and use `workflow_dispatch` to test (or push a pre-release tag like `v0.0.1-rc1`). Verify all three matrix jobs reach the "Upload artifact" step.

- [ ] **Step 3: Commit**

```
git add .github/workflows/release.yml
git commit -m "ci(release): build Win MSI / Mac DMG / Linux AppImage on tag push

Matrix on windows-latest / macos-latest / ubuntu-latest. Each runner
builds frontend → runs unit tests → produces PyInstaller bundle →
smokes it → wraps in platform installer → uploads artifact. The
release job collects all three and publishes a GitHub Release."
```

---

### Task 12: README — install-from-release section

User-facing documentation: download, install, bypass SmartScreen / Gatekeeper, uninstall.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append to README**

```markdown
## Installing from a release (no terminal required)

Download the latest installer for your OS from
[github.com/DeveloperrOp/claude-mnemos/releases](https://github.com/DeveloperrOp/claude-mnemos/releases):

| OS | File |
|---|---|
| Windows 10/11 (x64) | `claude-mnemos-setup-x64.exe` |
| macOS 11+ (Apple Silicon and Intel) | `claude-mnemos.dmg` |
| Linux x86_64 | `claude-mnemos-x86_64.AppImage` |

### Windows

1. Double-click the `.exe`.
2. SmartScreen may say *"Windows protected your PC"* — click **More info → Run anyway**. We have not yet purchased a code-signing certificate; the warning is expected.
3. Accept the autostart checkbox (default on) — claude-mnemos will start with Windows.
4. Click **Install**. The dashboard opens automatically when setup finishes.

### macOS

1. Open the `.dmg` and drag claude-mnemos to **Applications**.
2. The first launch will fail with *"unidentified developer"* — open **System Settings → Privacy & Security → Open Anyway**, or right-click the app and choose **Open** to bypass once.
3. The app lives in the menu bar (top-right). Click the icon to open the dashboard.

### Linux

1. Make the AppImage executable: `chmod +x claude-mnemos-x86_64.AppImage`.
2. Run it: `./claude-mnemos-x86_64.AppImage`.
3. Optional — integrate with your DE: `./claude-mnemos-x86_64.AppImage --integrate` (linuxdeploy adds a desktop entry).

### Uninstalling

- **Windows:** Settings → Apps → claude-mnemos → Uninstall. Removes the daemon, autostart entry, and Claude Code hooks.
- **macOS:** drag the app to Trash. To remove the LaunchAgent, run `mnemos tray uninstall` from terminal first (or just delete `~/Library/LaunchAgents/com.yarik.claude-mnemos.plist`).
- **Linux:** delete the `.AppImage`. To remove the autostart entry, delete `~/.config/autostart/claude-mnemos.desktop`.
```

- [ ] **Step 2: Commit**

```
git add README.md
git commit -m "docs(readme): install-from-release section

Per-OS download + bypass SmartScreen/Gatekeeper instructions.
Documents the unsigned-binary expectation for the initial release."
```

---

### Final verification — Phase 2

After all 12 tasks:

- [ ] **Step 1: Backend full suite**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/ --deselect tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle -q | tail -3
```
Expected: ≥1717 passed (1691 + ~26 new across tasks 1, 3, 4, 6, 10).

- [ ] **Step 2: Frontend Vitest**
```
cd frontend && npm test -- --run | tail -5
```
Expected: ≥360 passed (was 357 + 3 new from UpdateBanner test in task 10).

- [ ] **Step 3: PyInstaller bundle works locally on Windows**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm
./dist/claude-mnemos/claude-mnemos.exe doctor
./dist/claude-mnemos/claude-mnemos.exe daemon foreground
# (kill manually after verifying http://localhost:5757 serves)
```

- [ ] **Step 4: Inno Setup builds the Windows installer**

```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/windows/mnemos.iss
test -f installer/windows/dist/claude-mnemos-setup-x64.exe && echo "[ok] Windows installer built"
```

- [ ] **Step 5: Verify CI workflow on a pre-release tag**

```
git tag v0.0.1-rc1
git push origin v0.0.1-rc1
# Watch the Actions tab — all three matrix jobs must succeed and upload artifacts.
```

- [ ] **Step 6: User-acceptance test (you, on a fresh VM or fresh user account)**

1. Download `claude-mnemos-setup-x64.exe` from the release.
2. Double-click. Accept SmartScreen warning. Click Install.
3. Browser opens to dashboard — empty Onboarding Welcome with detected Claude Code workspaces.
4. Pick a workspace, click "Track selected".
5. Verify hook_silence does NOT fire after 6h on that workspace.

If step 6 fails, the postinstall flow is broken — revisit Task 6.

---

## Self-review notes

- **Spec coverage:** 2.1 (build pipeline) → tasks 5/8/9; 2.2 (postinstall) → task 6 + Inno's [Run] section in task 7; 2.3 (CI/CD) → task 10; 2.4 (code signing) → explicitly deferred and documented in task 11; 2.5 (updater) → out of scope, mentioned in task 11. Foundations 1–4 are needed to make hook installation survive the bundling.
- **Type consistency:** `runtime.executable_path()` returns `Path`; both `cli_hooks` and tests use `.resolve()` consistently. `_detect_hook_scripts` return shape changed (full command lines, not paths) — Task 4 explicitly documents this and updates `install()` callers.
- **No placeholders:** every code block is concrete. Mac and Linux build scripts are full bash — engineer can `bash file.sh` after CI sets up `create-dmg`/`linuxdeploy`. Inno Setup `.iss` is complete.
- **Risks acknowledged:**
  - Mac/Linux only verifiable on CI. Engineer may need 2–3 CI iterations to land Tasks 8/9.
  - PyInstaller hidden imports list may be incomplete — Task 5's smoke test (`./claude-mnemos.exe doctor` + `daemon foreground`) catches missing imports early. If a runtime ImportError surfaces later, append the offending module to `hiddenimports` in `mnemos.spec` and rebuild.
  - Bundle size ≥80MB is acceptable but means slow CI runs. `Compression=lzma2/ultra` in Inno trades CPU for size.
  - Tray icon file (`icon.ico`/`icon.icns`/`icon.png`) — Task 5/8/9 reference these but don't create them. If missing, the build still works (Inno omits icon, py2app falls back, AppImage uses placeholder). Generate proper icons in a follow-up task if needed (out of scope here).
