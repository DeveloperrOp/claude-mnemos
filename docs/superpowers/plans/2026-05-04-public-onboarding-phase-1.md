# Public Onboarding Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Halve the friction of the current pipx-based mnemos install/onboarding flow by adding `mnemos init`, browser auto-open, cwd auto-detection, a Welcome screen, a Setup-Checklist widget, first-session celebration, `mnemos doctor`, autostart-by-default, and PreCompact hook fix — all without rebuilding the installer.

**Architecture:** Additive layer on top of existing CLI / daemon / frontend. New backend endpoints under `/api/onboarding/*`, new frontend page `OnboardingWelcome.tsx` (the existing technical wizard is renamed to `OnboardingAdvanced.tsx` and reachable via "Show advanced"). New `mnemos init` and `mnemos doctor` CLI subcommands wire existing tray + hooks + health-check primitives. New singleton state file `~/.claude-mnemos/install-state.json` for autostart decision and "first session celebrated" flag. No existing API contracts change.

**Tech Stack:** Python 3.12+ (pipx-installed), FastAPI, React 19 + TypeScript + Tailwind v4, Vitest + pytest. Existing pipx-venv: `~/pipx/venvs/claude-mnemos/Scripts/python.exe`. Backend tests baseline: 1662 passed. Frontend: 343 passed.

---

## File Structure (decisions locked here, not in tasks)

### Backend new

| File | Responsibility | Approx LoC |
|---|---|---|
| `claude_mnemos/cli_init.py` | `mnemos init` command — orchestrates hooks-install + tray-install + tray-start + browser-open. Idempotent. | ~140 |
| `claude_mnemos/cli_doctor.py` | `mnemos doctor` command — runs install-level + health detector checks, prints colored ✓/⚠/✗ list. | ~110 |
| `claude_mnemos/core/cwd_detection.py` | Pure helper: scan `~/.claude/projects/`, aggregate by cwd, rank by recent session count. | ~90 |
| `claude_mnemos/core/install_checks.py` | 4 install-level detectors: claude_cli_installed, hooks_present, daemon_reachable, vault_writable. Same StoredAlert shape as existing detectors for symmetry. | ~140 |
| `claude_mnemos/state/install_state.py` | Tiny singleton wrapping `~/.claude-mnemos/install-state.json` with fields `{first_run_ts, autostart_decision, first_session_celebrated_for: list[str]}`. Lock-protected. | ~80 |
| `claude_mnemos/daemon/routes/onboarding.py` | New router. `GET /api/onboarding/detected-cwds`, `GET /api/onboarding/setup-status`. | ~120 |

### Backend modified

| File | Change |
|---|---|
| `claude_mnemos/cli_hooks.py` | Add PreCompact event installation alongside SessionStart/SessionEnd. Update status output. |
| `claude_mnemos/cli.py` | Register `init` and `doctor` subparsers. |
| `claude_mnemos/daemon/app.py` | Mount `onboarding_router` at `/api/`. |
| `claude_mnemos/daemon/process.py` | On daemon startup, if `install_state.autostart_decision is None`, schedule a one-shot autostart-install attempt after first health-success. |

### Frontend new

| File | Responsibility | Approx LoC |
|---|---|---|
| `frontend/src/pages/OnboardingWelcome.tsx` | New default landing for empty-state. Setup status block + detected workspaces list + "Track selected" button + "Show advanced" → `OnboardingAdvanced`. | ~280 |
| `frontend/src/api/onboarding.api.ts` | API client for `/api/onboarding/*` endpoints. | ~40 |
| `frontend/src/hooks/onboarding/useDetectedCwds.ts` | React Query hook for detected workspaces. | ~15 |
| `frontend/src/hooks/onboarding/useSetupStatus.ts` | React Query hook for setup-status (polled 30s). | ~15 |
| `frontend/src/components/widgets/dashboard/SetupChecklist.tsx` | Persistent setup-state widget on Overview. Auto-collapses when all ✓ for >24h, expands on any ⚠/✗. | ~180 |
| `frontend/src/hooks/useFirstSessionCelebration.ts` | Watches `useDashboardSnapshot` per-project counts, fires one-time toast on 0→1 transition. State stored in `localStorage` AND mirrored to backend `install_state.first_session_celebrated_for`. | ~70 |
| `frontend/src/pages/Diagnostics.tsx` | UI mirror of `mnemos doctor`. Cards per check + Fix buttons (Re-install hooks, Restart daemon via tray, etc). | ~200 |
| `frontend/src/api/diagnostics.api.ts` | API client for `/api/onboarding/setup-status` (used both by checklist widget and diagnostics page). | ~30 |
| `frontend/src/types/Onboarding.ts` | Zod schemas matching `routes/onboarding.py` response shapes. | ~50 |

### Frontend modified

| File | Change |
|---|---|
| `frontend/src/pages/Onboarding.tsx` → `frontend/src/pages/OnboardingAdvanced.tsx` | Rename file + component identifier. Behaviour unchanged. |
| `frontend/src/App.tsx` | Route `/onboarding` swapped to render `<OnboardingWelcome />`. Add `/onboarding/advanced` → `<OnboardingAdvanced />`. Add `/diagnostics` → `<Diagnostics />`. |
| `frontend/src/pages/Overview.tsx` | Mount `<SetupChecklist />` between `<HealthAlertsBar />` and KpiBar. Wire `useFirstSessionCelebration()`. |
| `frontend/src/pages/Help.tsx` (or sidebar) | Add "Diagnostics" link. |
| `frontend/public/locales/en.json`, `ru.json`, `uk.json` | Add ~50 new keys for Welcome screen + checklist + Diagnostics. |

---

## Tasks

### Task 1: PreCompact in `mnemos hooks install` (1.1)

`hooks/hooks.json` already declares PreCompact, but `cli_hooks.py::install` only writes SessionStart/SessionEnd. After the recent PreCompact landing (commit `664111b`), this is a real gap — users running `mnemos hooks install` get an incomplete installation.

**Files:**
- Modify: `claude_mnemos/cli_hooks.py:39-58` (`_detect_hook_scripts`), `:98-152` (`install`), `:206-236` (`_cmd_status`)
- Modify: `tests/cli/test_cli_hooks.py`

- [ ] **Step 1: Write failing test for PreCompact registration**

```python
# tests/cli/test_cli_hooks.py — add to existing test file
def test_install_writes_precompact_block(tmp_path, monkeypatch):
    """install() must register a PreCompact hook alongside SessionStart/SessionEnd."""
    settings = tmp_path / "settings.json"
    monkeypatch.setattr("claude_mnemos.cli_hooks.CLAUDE_SETTINGS", settings)

    from claude_mnemos import cli_hooks

    result = cli_hooks.install()

    import json
    data = json.loads(settings.read_text(encoding="utf-8"))
    events = set(data["hooks"].keys())
    assert "PreCompact" in events
    assert "SessionStart" in events
    assert "SessionEnd" in events

    pc_blocks = data["hooks"]["PreCompact"]
    pc_cmds = [h["command"] for block in pc_blocks for h in block["hooks"]]
    assert any("pre_compact.py" in c for c in pc_cmds)
    assert result["pre_compact_script"].endswith('pre_compact.py"')
```

- [ ] **Step 2: Run test to confirm it fails**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/cli/test_cli_hooks.py::test_install_writes_precompact_block -v
```
Expected: FAIL — `KeyError: 'PreCompact'` (the install function doesn't write it yet) OR `KeyError: 'pre_compact_script'`.

- [ ] **Step 3: Update `_detect_hook_scripts` to also locate `pre_compact.py`**

```python
# claude_mnemos/cli_hooks.py — replace existing _detect_hook_scripts
def _detect_hook_scripts() -> tuple[str, str, str]:
    """Locate session_start.py, session_end.py, pre_compact.py.

    Returns three quoted absolute paths.
    """
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "hooks",            # source tree: <repo>/hooks/
        here.parent / "hooks",                   # alt layout
    ]
    for d in candidates:
        ss = d / "session_start.py"
        se = d / "session_end.py"
        pc = d / "pre_compact.py"
        if ss.exists() and se.exists() and pc.exists():
            return f'"{ss}"', f'"{se}"', f'"{pc}"'
    raise FileNotFoundError(
        f"Could not locate mnemos hook scripts. Tried: {[str(c) for c in candidates]}"
    )
```

- [ ] **Step 4: Update `install()` to write PreCompact block + return its path**

```python
# claude_mnemos/cli_hooks.py — replace install() body
def install(*, dry_run: bool = False) -> dict:
    py = _detect_python()
    ss_script, se_script, pc_script = _detect_hook_scripts()

    if dry_run:
        return {
            "ok": True,
            "python": py,
            "session_start_script": ss_script,
            "session_end_script": se_script,
            "pre_compact_script": pc_script,
            "backup_path": None,
            "dry_run": True,
        }

    backup = _backup_settings()
    settings = _load_settings()
    settings.setdefault("hooks", {})
    hooks = settings["hooks"]

    ss_block = _build_hook_block(f"{py} {ss_script}")
    se_block = _build_hook_block(f"{py} {se_script}")
    pc_block = _build_hook_block(f"{py} {pc_script}")

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
        "python": py,
        "session_start_script": ss_script,
        "session_end_script": se_script,
        "pre_compact_script": pc_script,
        "backup_path": str(backup) if backup else None,
    }
```

- [ ] **Step 5: Update `_cmd_install` print + `_cmd_uninstall` + `_cmd_status` to mention PreCompact**

```python
# in _cmd_install, after the SessionEnd line, add:
print(f"  PreCompact:   {result['python']} {result['pre_compact_script']}")

# in _cmd_uninstall, change the loop:
for event in ("SessionStart", "SessionEnd", "PreCompact"):
    ...

# in _cmd_status, add:
pc_installed, pc_cmds = _summarize("PreCompact")
print()
print(f"PreCompact:   {'[OK] mnemos installed' if pc_installed else '[X]  no mnemos hook'}")
for c in pc_cmds:
    marker = "  [mnemos]" if _is_mnemos_command(c) else "  [other]"
    print(f"{marker} {c}")
# bottom return:
return 0 if (ss_installed and se_installed and pc_installed) else 1
```

- [ ] **Step 6: Run test, confirm pass + run full cli_hooks suite**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/cli/test_cli_hooks.py -v
```
Expected: ALL PASS, no regressions.

- [ ] **Step 7: Commit**

```
git add claude_mnemos/cli_hooks.py tests/cli/test_cli_hooks.py
git commit -m "fix(hooks): include PreCompact in mnemos hooks install/uninstall/status (1.1)

cli_hooks only registered SessionStart + SessionEnd. After PreCompact
landed in hooks/hooks.json (commit 664111b), the CLI was not updated
— users running 'mnemos hooks install' got an incomplete installation
and never received pre-compact safety net coverage. Add PreCompact
to all three subcommands."
```

---

### Task 2: `state/install_state.py` singleton (foundation for 1.6 + 1.8)

A tiny JSON-backed state file that several other tasks consume. Implement first so they can wire to it.

**Files:**
- Create: `claude_mnemos/state/install_state.py`
- Test: `tests/state/test_install_state.py`

- [ ] **Step 1: Write failing test for create + load roundtrip**

```python
# tests/state/test_install_state.py
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_mnemos.state.install_state import InstallState, load_install_state


@pytest.fixture
def state_path(tmp_path: Path, monkeypatch) -> Path:
    p = tmp_path / "install-state.json"
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        p,
    )
    return p


def test_load_returns_default_when_file_missing(state_path: Path) -> None:
    s = load_install_state()
    assert s.first_run_ts is None
    assert s.autostart_decision is None
    assert s.first_session_celebrated_for == []


def test_save_then_load_roundtrip(state_path: Path) -> None:
    s = InstallState(
        first_run_ts=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        autostart_decision="accepted",
        first_session_celebrated_for=["proj-a", "proj-b"],
    )
    s.save()
    loaded = load_install_state()
    assert loaded.first_run_ts == s.first_run_ts
    assert loaded.autostart_decision == "accepted"
    assert loaded.first_session_celebrated_for == ["proj-a", "proj-b"]


def test_mark_celebrated_is_idempotent(state_path: Path) -> None:
    s = load_install_state()
    s.mark_celebrated("proj-x")
    s.mark_celebrated("proj-x")  # second call must not duplicate
    assert s.first_session_celebrated_for == ["proj-x"]
```

- [ ] **Step 2: Run test, confirm fail**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/state/test_install_state.py -v
```
Expected: FAIL with `ModuleNotFoundError: claude_mnemos.state.install_state`.

- [ ] **Step 3: Create the module**

```python
# claude_mnemos/state/install_state.py
"""Tiny singleton state file for install-level UX flags.

Stored at ~/.claude-mnemos/install-state.json. Used by the onboarding
flow + first-session celebration + autostart-default-on logic.

Schema is intentionally tiny — fields can be added later, missing
fields default. No version bump expected for the foreseeable future.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from claude_mnemos.core.atomic import atomic_write

_STATE_PATH: Path = Path.home() / ".claude-mnemos" / "install-state.json"
_LOCK = threading.RLock()


class InstallState(BaseModel):
    first_run_ts: datetime | None = None
    autostart_decision: Literal["accepted", "declined"] | None = None
    first_session_celebrated_for: list[str] = Field(default_factory=list)

    def mark_celebrated(self, project_name: str) -> None:
        if project_name not in self.first_session_celebrated_for:
            self.first_session_celebrated_for.append(project_name)

    def save(self) -> None:
        with _LOCK:
            _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(
                _STATE_PATH,
                self.model_dump_json(indent=2).encode("utf-8"),
            )


def load_install_state() -> InstallState:
    """Load the singleton; return defaults if file missing or unreadable."""
    with _LOCK:
        if not _STATE_PATH.exists():
            return InstallState()
        try:
            data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            return InstallState.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            # Treat corrupt file as missing — caller can re-save.
            return InstallState()
```

- [ ] **Step 4: Run test, confirm pass**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/state/test_install_state.py -v
```
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```
git add claude_mnemos/state/install_state.py tests/state/test_install_state.py
git commit -m "feat(state): InstallState singleton for onboarding UX flags

~/.claude-mnemos/install-state.json with first_run_ts,
autostart_decision (accepted/declined/None), and
first_session_celebrated_for list. Atomic-write protected.
Foundation for tasks 1.6 (first-session toast) and 1.8 (autostart
default-on)."
```

---

### Task 3: `core/cwd_detection.py` — scan `~/.claude/projects/` (1.3 backend)

Aggregate JSONL transcripts under `~/.claude/projects/` by their cwd, count sessions, return the top-N most-active in last 30 days. Skip cwds that already match a registered project's `cwd_patterns`.

**Files:**
- Create: `claude_mnemos/core/cwd_detection.py`
- Test: `tests/core/test_cwd_detection.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/test_cwd_detection.py
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.core.cwd_detection import (
    DetectedCwd,
    detect_cwds,
)


def _write_jsonl(p: Path, cwd: str, mtime: datetime) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"cwd": cwd, "type": "user", "message": {"role": "user", "content": "hi"}}) + "\n",
        encoding="utf-8",
    )
    ts = mtime.timestamp()
    import os
    os.utime(p, (ts, ts))


def test_detect_cwds_aggregates_by_directory(tmp_path: Path, monkeypatch) -> None:
    transcripts_root = tmp_path / "claude_projects"
    monkeypatch.setattr(
        "claude_mnemos.core.cwd_detection._transcripts_root",
        lambda: transcripts_root,
    )
    now = datetime.now(tz=UTC)

    _write_jsonl(transcripts_root / "p1" / "a.jsonl", "D:/code/app1", now - timedelta(days=1))
    _write_jsonl(transcripts_root / "p1" / "b.jsonl", "D:/code/app1", now - timedelta(days=2))
    _write_jsonl(transcripts_root / "p2" / "c.jsonl", "D:/code/app2", now - timedelta(days=3))

    result = detect_cwds(now=now)

    assert isinstance(result, list)
    assert len(result) == 2
    # Most active first
    assert result[0].cwd == "D:/code/app1"
    assert result[0].session_count == 2
    assert result[1].cwd == "D:/code/app2"
    assert result[1].session_count == 1


def test_detect_cwds_filters_old_sessions(tmp_path: Path, monkeypatch) -> None:
    transcripts_root = tmp_path / "claude_projects"
    monkeypatch.setattr(
        "claude_mnemos.core.cwd_detection._transcripts_root",
        lambda: transcripts_root,
    )
    now = datetime.now(tz=UTC)
    _write_jsonl(transcripts_root / "p1" / "old.jsonl", "D:/old", now - timedelta(days=60))
    _write_jsonl(transcripts_root / "p1" / "fresh.jsonl", "D:/fresh", now - timedelta(days=1))

    result = detect_cwds(now=now)

    assert len(result) == 1
    assert result[0].cwd == "D:/fresh"


def test_detect_cwds_excludes_already_registered(tmp_path: Path, monkeypatch) -> None:
    transcripts_root = tmp_path / "claude_projects"
    monkeypatch.setattr(
        "claude_mnemos.core.cwd_detection._transcripts_root",
        lambda: transcripts_root,
    )
    now = datetime.now(tz=UTC)
    _write_jsonl(transcripts_root / "p1" / "a.jsonl", "D:/code/registered", now)
    _write_jsonl(transcripts_root / "p1" / "b.jsonl", "D:/code/new", now)

    result = detect_cwds(now=now, exclude_cwds={"D:/code/registered"})

    cwds = [r.cwd for r in result]
    assert "D:/code/registered" not in cwds
    assert "D:/code/new" in cwds


def test_detect_cwds_caps_at_ten(tmp_path: Path, monkeypatch) -> None:
    transcripts_root = tmp_path / "claude_projects"
    monkeypatch.setattr(
        "claude_mnemos.core.cwd_detection._transcripts_root",
        lambda: transcripts_root,
    )
    now = datetime.now(tz=UTC)
    for i in range(15):
        _write_jsonl(
            transcripts_root / "p1" / f"s{i}.jsonl",
            f"D:/code/app{i}",
            now - timedelta(hours=i),
        )

    result = detect_cwds(now=now)
    assert len(result) == 10
```

- [ ] **Step 2: Run test, confirm fail**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_cwd_detection.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# claude_mnemos/core/cwd_detection.py
"""Scan ~/.claude/projects/ to detect cwds where Claude Code sessions live.

Used by the Welcome onboarding screen to suggest workspaces a user
might want to track. Reads the first JSON object from every JSONL
transcript and aggregates by `cwd` field.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

_DEFAULT_LOOKBACK_DAYS = 30
_MAX_RESULTS = 10


class DetectedCwd(BaseModel):
    cwd: str
    session_count: int
    last_seen: datetime


def _transcripts_root() -> Path:
    return Path.home() / ".claude" / "projects"


def _read_cwd(jsonl_path: Path) -> str | None:
    """Return the `cwd` field of the first JSON line, or None on parse error."""
    try:
        with jsonl_path.open("r", encoding="utf-8") as f:
            line = f.readline()
        if not line:
            return None
        obj = json.loads(line)
        cwd = obj.get("cwd")
        return cwd if isinstance(cwd, str) and cwd else None
    except (OSError, json.JSONDecodeError):
        return None


def detect_cwds(
    *,
    now: datetime | None = None,
    exclude_cwds: Iterable[str] = (),
    lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
) -> list[DetectedCwd]:
    """Return up to 10 cwds ranked by session count in the last lookback window.

    Each result reports `session_count` (jsonl files seen with that cwd within
    the lookback window) and `last_seen` (max mtime across those files).
    """
    now = now or datetime.now(tz=UTC)
    cutoff = now - timedelta(days=lookback_days)
    excluded = set(exclude_cwds)

    root = _transcripts_root()
    if not root.is_dir():
        return []

    counts: dict[str, int] = {}
    last_seen_by_cwd: dict[str, datetime] = {}

    for jsonl in root.rglob("*.jsonl"):
        try:
            mtime_ts = jsonl.stat().st_mtime
        except OSError:
            continue
        mtime = datetime.fromtimestamp(mtime_ts, tz=UTC)
        if mtime < cutoff:
            continue
        cwd = _read_cwd(jsonl)
        if not cwd or cwd in excluded:
            continue
        counts[cwd] = counts.get(cwd, 0) + 1
        prev = last_seen_by_cwd.get(cwd)
        if prev is None or mtime > prev:
            last_seen_by_cwd[cwd] = mtime

    items = [
        DetectedCwd(cwd=k, session_count=v, last_seen=last_seen_by_cwd[k])
        for k, v in counts.items()
    ]
    items.sort(key=lambda d: (-d.session_count, -d.last_seen.timestamp()))
    return items[:_MAX_RESULTS]
```

- [ ] **Step 4: Run test, confirm pass**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_cwd_detection.py -v
```
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```
git add claude_mnemos/core/cwd_detection.py tests/core/test_cwd_detection.py
git commit -m "feat(core): cwd_detection scans ~/.claude/projects/ and ranks by session count

Pure helper that powers the Welcome screen's auto-suggested
workspaces. 30-day lookback, top-10 results, supports excluding
already-registered cwds."
```

---

### Task 4: `core/install_checks.py` — install-level detectors (foundation for 1.7 doctor)

Four checks that complement the existing 7 health detectors: claude_cli_installed, hooks_present, daemon_reachable, vault_writable. Same `StoredAlert` shape so the UI/CLI can render them uniformly.

**Files:**
- Create: `claude_mnemos/core/install_checks.py`
- Test: `tests/core/test_install_checks.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_install_checks.py
from pathlib import Path

import pytest

from claude_mnemos.core.install_checks import (
    check_claude_cli_installed,
    check_hooks_present,
    check_vault_writable,
)


def test_claude_cli_installed_when_present(monkeypatch) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.install_checks._which",
        lambda name: "/usr/bin/claude",
    )
    alert = check_claude_cli_installed()
    assert alert is None


def test_claude_cli_installed_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.install_checks._which",
        lambda name: None,
    )
    alert = check_claude_cli_installed()
    assert alert is not None
    assert alert.id == "claude_cli_not_installed"
    assert alert.severity == "critical"


def test_hooks_present_when_settings_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "claude_mnemos.core.install_checks.CLAUDE_SETTINGS",
        tmp_path / "missing.json",
    )
    alert = check_hooks_present()
    assert alert is not None
    assert alert.id == "hooks_not_installed"


def test_hooks_present_when_all_three_present(tmp_path: Path, monkeypatch) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(
        '{"hooks": {"SessionStart": [{"hooks":[{"command":"py claude_mnemos/hooks/session_start.py"}]}],'
        '          "SessionEnd":   [{"hooks":[{"command":"py claude_mnemos/hooks/session_end.py"}]}],'
        '          "PreCompact":   [{"hooks":[{"command":"py claude_mnemos/hooks/pre_compact.py"}]}]}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "claude_mnemos.core.install_checks.CLAUDE_SETTINGS",
        settings,
    )
    alert = check_hooks_present()
    assert alert is None


def test_hooks_present_when_partial(tmp_path: Path, monkeypatch) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(
        '{"hooks": {"SessionStart": [{"hooks":[{"command":"py claude_mnemos/hooks/session_start.py"}]}]}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "claude_mnemos.core.install_checks.CLAUDE_SETTINGS",
        settings,
    )
    alert = check_hooks_present()
    assert alert is not None
    assert alert.id == "hooks_partial"
    assert "SessionEnd" in alert.message
    assert "PreCompact" in alert.message


def test_vault_writable_when_writable(tmp_path: Path) -> None:
    alert = check_vault_writable([tmp_path])
    assert alert is None


def test_vault_writable_when_not_writable(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does-not-exist"
    alert = check_vault_writable([nonexistent])
    assert alert is not None
    assert alert.id == "vault_not_writable"
```

- [ ] **Step 2: Run test, confirm fail**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_install_checks.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the module**

```python
# claude_mnemos/core/install_checks.py
"""Install-level health detectors complementing core/health_checks.py.

These run on demand from `mnemos doctor` and from the Diagnostics
UI page. Same StoredAlert shape as the cron-based detectors so the
UI can render them uniformly.

Async daemon-reachable check stays here too but the daemon-reachable
caller is in cli_doctor.py since the daemon URL configuration lives
there.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

from claude_mnemos.core.clock import utcnow
from claude_mnemos.state.alerts_store import StoredAlert

CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
_REQUIRED_HOOK_EVENTS = ("SessionStart", "SessionEnd", "PreCompact")
_MNEMOS_TOKEN = "claude_mnemos"
_MNEMOS_DASHED = "claude-mnemos"


def _which(name: str) -> str | None:
    return shutil.which(name)


def check_claude_cli_installed() -> StoredAlert | None:
    """Critical alert if `claude` is not on PATH."""
    if _which("claude") is not None:
        return None
    now = utcnow()
    return StoredAlert(
        id="claude_cli_not_installed",
        detector="check_claude_cli_installed",
        severity="critical",
        message=(
            "Claude Code CLI is not installed. Install it from "
            "https://docs.anthropic.com/en/docs/claude-code/quickstart "
            "before using mnemos."
        ),
        context={},
        first_seen=now,
        last_seen=now,
        silenced_until=None,
        dismissed=False,
    )


def _hook_events_installed() -> set[str]:
    if not CLAUDE_SETTINGS.exists():
        return set()
    try:
        data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    hooks = data.get("hooks", {})
    out: set[str] = set()
    for event in _REQUIRED_HOOK_EVENTS:
        blocks = hooks.get(event, [])
        for block in blocks:
            for h in block.get("hooks", []):
                cmd = h.get("command", "")
                if _MNEMOS_TOKEN in cmd or _MNEMOS_DASHED in cmd:
                    out.add(event)
                    break
    return out


def check_hooks_present() -> StoredAlert | None:
    """Critical if no mnemos hooks; warning if partial; None if all 3 present."""
    installed = _hook_events_installed()
    now = utcnow()
    if not installed:
        return StoredAlert(
            id="hooks_not_installed",
            detector="check_hooks_present",
            severity="critical",
            message=(
                "Claude Code hooks are not installed. Run `mnemos hooks "
                "install` so mnemos can capture sessions."
            ),
            context={"installed": []},
            first_seen=now,
            last_seen=now,
            silenced_until=None,
            dismissed=False,
        )
    missing = [e for e in _REQUIRED_HOOK_EVENTS if e not in installed]
    if missing:
        return StoredAlert(
            id="hooks_partial",
            detector="check_hooks_present",
            severity="warning",
            message=(
                f"Some Claude Code hooks are missing: {', '.join(missing)}. "
                f"Re-run `mnemos hooks install`."
            ),
            context={"installed": sorted(installed), "missing": missing},
            first_seen=now,
            last_seen=now,
            silenced_until=None,
            dismissed=False,
        )
    return None


def check_vault_writable(vault_roots: Iterable[Path]) -> StoredAlert | None:
    """Critical if any registered vault_root is not writable."""
    bad: list[str] = []
    for vr in vault_roots:
        try:
            vr.mkdir(parents=True, exist_ok=True)
            probe = vr / ".write_probe.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError:
            bad.append(str(vr))
    if not bad:
        return None
    now = utcnow()
    return StoredAlert(
        id="vault_not_writable",
        detector="check_vault_writable",
        severity="critical",
        message=(
            "These vault roots are not writable: "
            + ", ".join(bad)
            + ". Check permissions."
        ),
        context={"unwritable": bad},
        first_seen=now,
        last_seen=now,
        silenced_until=None,
        dismissed=False,
    )
```

- [ ] **Step 4: Run test, confirm pass**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/core/test_install_checks.py -v
```
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```
git add claude_mnemos/core/install_checks.py tests/core/test_install_checks.py
git commit -m "feat(core): install_checks — claude_cli + hooks_present + vault_writable

Three install-level detectors using the existing StoredAlert shape.
Foundation for 'mnemos doctor' (task 1.7) and the Setup-Checklist
widget (task 1.5)."
```

---

### Task 5: `daemon/routes/onboarding.py` — REST endpoints (1.3 + 1.5)

Two endpoints:
- `GET /api/onboarding/detected-cwds` — wraps `detect_cwds()`, excludes cwds already covered by registered projects.
- `GET /api/onboarding/setup-status` — runs `check_claude_cli_installed`, `check_hooks_present`, `check_vault_writable`, daemon's own self-check, and returns the four results plus a derived `all_ok: bool`.

**Files:**
- Create: `claude_mnemos/daemon/routes/onboarding.py`
- Modify: `claude_mnemos/daemon/app.py:30` (after `inject_preview_router` import + include_router call)
- Test: `tests/daemon/test_app_onboarding.py`

- [ ] **Step 1: Write failing test for the endpoints**

```python
# tests/daemon/test_app_onboarding.py
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.core.cwd_detection import DetectedCwd
from claude_mnemos.daemon.app import create_app


@pytest.fixture
def app(tmp_path: Path):
    return create_app(daemon=None)


@pytest.fixture
def client(app):
    return TestClient(app)


def test_detected_cwds_returns_list(client, monkeypatch) -> None:
    fake_now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.detect_cwds",
        lambda *, now=None, exclude_cwds=(): [
            DetectedCwd(cwd="D:/code/app1", session_count=12, last_seen=fake_now),
            DetectedCwd(cwd="D:/code/app2", session_count=3, last_seen=fake_now),
        ],
    )
    r = client.get("/api/onboarding/detected-cwds")
    assert r.status_code == 200
    body = r.json()
    assert "cwds" in body
    assert len(body["cwds"]) == 2
    assert body["cwds"][0]["cwd"] == "D:/code/app1"
    assert body["cwds"][0]["session_count"] == 12


def test_detected_cwds_excludes_registered(client, monkeypatch) -> None:
    captured_excludes: list[set[str]] = []

    def fake_detect(*, now=None, exclude_cwds=()):
        captured_excludes.append(set(exclude_cwds))
        return []

    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.detect_cwds",
        fake_detect,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding._registered_cwds",
        lambda req: {"D:/already/registered"},
    )
    r = client.get("/api/onboarding/detected-cwds")
    assert r.status_code == 200
    assert captured_excludes == [{"D:/already/registered"}]


def test_setup_status_all_ok(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_claude_cli_installed",
        lambda: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_hooks_present",
        lambda: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_vault_writable",
        lambda roots: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding._project_count",
        lambda req: 2,
    )
    r = client.get("/api/onboarding/setup-status")
    assert r.status_code == 200
    body = r.json()
    assert body["all_ok"] is True
    assert body["claude_cli"]["status"] == "ok"
    assert body["hooks"]["status"] == "ok"
    assert body["vaults"]["status"] == "ok"
    assert body["projects"]["status"] == "ok"
    assert body["projects"]["count"] == 2


def test_setup_status_reports_critical(client, monkeypatch) -> None:
    from datetime import UTC, datetime

    from claude_mnemos.state.alerts_store import StoredAlert

    now = datetime(2026, 5, 4, tzinfo=UTC)
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_claude_cli_installed",
        lambda: StoredAlert(
            id="claude_cli_not_installed",
            detector="x",
            severity="critical",
            message="missing",
            context={},
            first_seen=now,
            last_seen=now,
            silenced_until=None,
            dismissed=False,
        ),
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_hooks_present",
        lambda: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding.check_vault_writable",
        lambda roots: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.daemon.routes.onboarding._project_count",
        lambda req: 1,
    )
    r = client.get("/api/onboarding/setup-status")
    assert r.status_code == 200
    body = r.json()
    assert body["all_ok"] is False
    assert body["claude_cli"]["status"] == "critical"
    assert body["claude_cli"]["message"] == "missing"
```

- [ ] **Step 2: Run test, confirm fail**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/daemon/test_app_onboarding.py -v
```
Expected: FAIL with `404 Not Found` on `/api/onboarding/detected-cwds`.

- [ ] **Step 3: Implement the route file**

```python
# claude_mnemos/daemon/routes/onboarding.py
"""REST endpoints powering the Welcome screen + Setup-Checklist widget.

GET /api/onboarding/detected-cwds  → suggested workspaces from ~/.claude/projects/
GET /api/onboarding/setup-status   → 4-row install/operational health summary
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from claude_mnemos.core.cwd_detection import detect_cwds
from claude_mnemos.core.install_checks import (
    check_claude_cli_installed,
    check_hooks_present,
    check_vault_writable,
)

router = APIRouter()


def _registered_cwds(request: Request) -> set[str]:
    daemon = request.app.state.daemon
    if daemon is None:
        return set()
    out: set[str] = set()
    try:
        for rt in daemon.runtimes():
            for pat in (rt.entry.cwd_patterns or []):
                # cwd_patterns are globs; the literal stem before any
                # wildcard is what we want to exclude. We treat the
                # pattern as-is for "exact" matching — detect_cwds will
                # only produce literal strings, so we match string-wise.
                out.add(pat.replace("\\**", "").replace("\\*", "").rstrip("\\/").rstrip("/"))
    except Exception:  # noqa: BLE001
        pass
    return out


def _project_count(request: Request) -> int:
    daemon = request.app.state.daemon
    if daemon is None:
        return 0
    try:
        return len(list(daemon.runtimes()))
    except Exception:  # noqa: BLE001
        return 0


def _vault_roots(request: Request) -> list:
    daemon = request.app.state.daemon
    if daemon is None:
        return []
    out = []
    try:
        for rt in daemon.runtimes():
            out.append(rt.vault_root)
    except Exception:  # noqa: BLE001
        pass
    return out


@router.get("/onboarding/detected-cwds")
def detected_cwds_route(request: Request) -> dict[str, Any]:
    excluded = _registered_cwds(request)
    items = detect_cwds(exclude_cwds=excluded)
    return {"cwds": [d.model_dump(mode="json") for d in items]}


def _row(alert: Any | None, ok_message: str) -> dict[str, Any]:
    if alert is None:
        return {"status": "ok", "message": ok_message}
    return {
        "status": alert.severity,
        "message": alert.message,
        "id": alert.id,
    }


@router.get("/onboarding/setup-status")
def setup_status_route(request: Request) -> dict[str, Any]:
    cli_alert = check_claude_cli_installed()
    hooks_alert = check_hooks_present()
    vaults_alert = check_vault_writable(_vault_roots(request))
    project_count = _project_count(request)

    rows = {
        "claude_cli": _row(cli_alert, "Claude Code CLI is installed."),
        "hooks": _row(hooks_alert, "All Claude Code hooks are installed."),
        "vaults": _row(vaults_alert, "All vault roots are writable."),
        "projects": (
            {"status": "ok", "message": f"{project_count} project(s) tracked.", "count": project_count}
            if project_count > 0
            else {"status": "warning", "message": "No projects tracked yet.", "count": 0}
        ),
    }
    all_ok = all(r["status"] == "ok" for r in rows.values())
    return {"all_ok": all_ok, **rows}
```

- [ ] **Step 4: Mount the router in `app.py`**

```python
# claude_mnemos/daemon/app.py — add import after line 27 (inject_preview)
from claude_mnemos.daemon.routes.onboarding import router as onboarding_router

# add include_router after line 78 (inject_preview_router include)
app.include_router(onboarding_router, prefix="/api")
```

- [ ] **Step 5: Run test, confirm pass + full suite no regressions**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/daemon/test_app_onboarding.py -v
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/ --deselect tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle -q
```
Expected: new file 4 PASS; full suite ≥ 1666 passed (1662 + 4).

- [ ] **Step 6: Commit**

```
git add claude_mnemos/daemon/routes/onboarding.py claude_mnemos/daemon/app.py tests/daemon/test_app_onboarding.py
git commit -m "feat(daemon): /api/onboarding/{detected-cwds,setup-status} routes

detected-cwds powers the Welcome screen's auto-suggested workspaces
list. setup-status drives the Setup-Checklist widget on Overview
and the upcoming Diagnostics page."
```

---

### Task 6: `mnemos init` CLI command (1.2 + 1.9)

A single command that does what 3 currently do: install hooks, register tray autostart, start tray, wait for daemon health, open browser. Idempotent.

**Files:**
- Create: `claude_mnemos/cli_init.py`
- Modify: `claude_mnemos/cli.py:534` (after the hooks subparser registration), and dispatcher around `:572`
- Test: `tests/cli/test_cli_init.py`

- [ ] **Step 1: Write failing test**

```python
# tests/cli/test_cli_init.py
from unittest.mock import MagicMock

import pytest


def _patch_init(monkeypatch, *, hooks_ok=True, tray_ok=True, daemon_ok=True, browser=True):
    """Patch all external side-effects of cli_init.run()."""
    calls = {"hooks": 0, "tray_install": 0, "tray_run_started": 0, "browser": 0, "wait_health": 0}

    def fake_install():
        calls["hooks"] += 1
        if hooks_ok:
            return {"ok": True}
        raise RuntimeError("hooks broke")

    def fake_tray_install():
        calls["tray_install"] += 1
        return tray_ok

    def fake_wait_health():
        calls["wait_health"] += 1
        return daemon_ok

    def fake_open_browser(url):
        calls["browser"] += 1

    monkeypatch.setattr("claude_mnemos.cli_init._install_hooks_safe", fake_install)
    monkeypatch.setattr("claude_mnemos.cli_init._install_tray_autostart_safe", fake_tray_install)
    monkeypatch.setattr("claude_mnemos.cli_init._wait_daemon_health", fake_wait_health)
    monkeypatch.setattr("claude_mnemos.cli_init._open_browser", fake_open_browser)
    return calls


def test_init_happy_path(monkeypatch) -> None:
    from claude_mnemos.cli_init import run

    calls = _patch_init(monkeypatch)
    rc = run(open_browser=True)
    assert rc == 0
    assert calls == {"hooks": 1, "tray_install": 1, "tray_run_started": 0, "wait_health": 1, "browser": 1}


def test_init_skips_browser_when_flag_off(monkeypatch) -> None:
    from claude_mnemos.cli_init import run

    calls = _patch_init(monkeypatch)
    rc = run(open_browser=False)
    assert rc == 0
    assert calls["browser"] == 0


def test_init_returns_nonzero_on_hook_failure(monkeypatch) -> None:
    from claude_mnemos.cli_init import run

    _patch_init(monkeypatch, hooks_ok=False)
    rc = run(open_browser=False)
    assert rc != 0


def test_init_continues_when_tray_install_fails(monkeypatch) -> None:
    """Tray install failure (e.g. unsupported platform) must not block daemon-start path."""
    from claude_mnemos.cli_init import run

    calls = _patch_init(monkeypatch, tray_ok=False)
    rc = run(open_browser=True)
    # Even with tray_ok=False, init must still try to wait for health + open browser.
    assert calls["wait_health"] == 1
    assert calls["browser"] == 1
    assert rc == 0  # tray failure is non-fatal
```

- [ ] **Step 2: Run test, confirm fail**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/cli/test_cli_init.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `cli_init.py`**

```python
# claude_mnemos/cli_init.py
"""`mnemos init` — single-command bootstrap.

Replaces the three-step flow (`hooks install` + `tray start` + open
browser) for new users. Idempotent: re-running on an already-set-up
machine is safe and prints ✓ for already-done steps.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
import webbrowser
from typing import Callable

from claude_mnemos.cli_hooks import install as _hooks_install_impl
from claude_mnemos.tray.__main__ import _cmd_install as _tray_install_impl

DEFAULT_DAEMON_URL = "http://127.0.0.1:5757/api/health"
HEALTH_TIMEOUT_S = 30.0
HEALTH_POLL_INTERVAL_S = 0.5
DASHBOARD_URL = "http://localhost:5757"


def _print(symbol: str, text: str) -> None:
    sys.stdout.write(f"  {symbol} {text}\n")
    sys.stdout.flush()


def _install_hooks_safe() -> dict | None:
    """Wrapper isolating hook-install for monkeypatching in tests."""
    return _hooks_install_impl()


def _install_tray_autostart_safe() -> bool:
    """Returns True on success, False on any failure (Linux unsupported, etc)."""
    try:
        rc = _tray_install_impl()
        return rc == 0
    except Exception:  # noqa: BLE001
        return False


def _wait_daemon_health(url: str = DEFAULT_DAEMON_URL, timeout_s: float = HEALTH_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 300:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(HEALTH_POLL_INTERVAL_S)
    return False


def _open_browser(url: str = DASHBOARD_URL) -> None:
    webbrowser.open(url)


def run(*, open_browser: bool = True) -> int:
    """Returns 0 on success, non-zero only on hook-install failure (the one fatal step)."""
    sys.stdout.write("mnemos init — setting up Claude Code memory\n\n")

    # 1. Hooks
    try:
        _install_hooks_safe()
        _print("OK", "hooks installed (SessionStart, SessionEnd, PreCompact)")
    except Exception as exc:  # noqa: BLE001
        _print("FAIL", f"hooks install failed: {exc}")
        sys.stdout.write("\nFix the error above and re-run `mnemos init`.\n")
        return 2

    # 2. Tray autostart (non-fatal)
    if _install_tray_autostart_safe():
        _print("OK", "tray autostart registered")
    else:
        _print("WARN", "tray autostart skipped (unsupported platform or already running)")

    # 3. Wait for daemon health
    if _wait_daemon_health():
        _print("OK", "daemon is responding on :5757")
    else:
        _print(
            "WARN",
            f"daemon did not respond within {int(HEALTH_TIMEOUT_S)}s — open dashboard "
            f"manually at {DASHBOARD_URL} once it starts",
        )

    # 4. Browser
    if open_browser:
        _open_browser()
        _print("OK", f"opened {DASHBOARD_URL} in your browser")

    sys.stdout.write("\nDone. Welcome to mnemos.\n")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    return run(open_browser=not args.no_browser)


def add_init_subparser(parent: argparse._SubParsersAction) -> None:
    p = parent.add_parser("init", help="One-command setup: hooks + autostart + dashboard")
    p.add_argument("--no-browser", action="store_true", help="Do not auto-open the dashboard")
    p.set_defaults(func=_cmd_init)
```

- [ ] **Step 4: Wire into `cli.py`**

```python
# claude_mnemos/cli.py — after the existing hooks subparser registration (~line 535), add:
from claude_mnemos.cli_init import add_init_subparser
add_init_subparser(sub)

# In the dispatcher after the hooks-handle block (~line 577), add:
if args.command == "init":
    return args.func(args)
```

- [ ] **Step 5: Run test, confirm pass**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/cli/test_cli_init.py -v
```
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```
git add claude_mnemos/cli_init.py claude_mnemos/cli.py tests/cli/test_cli_init.py
git commit -m "feat(cli): mnemos init — single-command bootstrap

Installs hooks, registers tray autostart, waits for daemon health,
opens the dashboard in browser. Idempotent. --no-browser flag for
headless / CI use."
```

---

### Task 7: `mnemos doctor` CLI + `Diagnostics` UI page (1.7)

CLI prints colored ✓/⚠/✗ list of all install + health checks. UI page renders the same checks as cards with Fix buttons.

**Files:**
- Create: `claude_mnemos/cli_doctor.py`
- Modify: `claude_mnemos/cli.py:535` (subparser) + dispatcher
- Test: `tests/cli/test_cli_doctor.py`
- Create: `frontend/src/pages/Diagnostics.tsx`
- Create: `frontend/src/api/diagnostics.api.ts`
- Modify: `frontend/src/App.tsx` (add `/diagnostics` route)
- Test: `frontend/src/__tests__/pages/Diagnostics.test.tsx`

- [ ] **Step 1: Write failing test for CLI doctor**

```python
# tests/cli/test_cli_doctor.py
from io import StringIO

import pytest


def test_doctor_prints_ok_lines_when_all_pass(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "claude_mnemos.cli_doctor.check_claude_cli_installed",
        lambda: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.cli_doctor.check_hooks_present",
        lambda: None,
    )
    monkeypatch.setattr(
        "claude_mnemos.cli_doctor._fetch_setup_status",
        lambda: {
            "all_ok": True,
            "claude_cli": {"status": "ok", "message": "ok"},
            "hooks": {"status": "ok", "message": "ok"},
            "vaults": {"status": "ok", "message": "ok"},
            "projects": {"status": "ok", "message": "ok", "count": 1},
        },
    )

    from claude_mnemos.cli_doctor import run

    rc = run()
    out = capsys.readouterr().out
    assert rc == 0
    assert "[OK]" in out
    assert "claude_cli" in out
    assert "hooks" in out


def test_doctor_returns_nonzero_when_any_fail(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "claude_mnemos.cli_doctor._fetch_setup_status",
        lambda: {
            "all_ok": False,
            "claude_cli": {"status": "critical", "message": "not installed"},
            "hooks": {"status": "ok", "message": "ok"},
            "vaults": {"status": "ok", "message": "ok"},
            "projects": {"status": "ok", "message": "ok", "count": 1},
        },
    )

    from claude_mnemos.cli_doctor import run

    rc = run()
    out = capsys.readouterr().out
    assert rc != 0
    assert "[FAIL]" in out or "[WARN]" in out
    assert "not installed" in out
```

- [ ] **Step 2: Run test, confirm fail**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/cli/test_cli_doctor.py -v
```
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `cli_doctor.py`**

```python
# claude_mnemos/cli_doctor.py
"""`mnemos doctor` — human-readable health check.

Hits the daemon's /api/onboarding/setup-status when reachable, falls
back to running install_checks directly if daemon is down. Prints
colored [OK]/[WARN]/[FAIL] rows. Exit 0 on all-OK, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

from claude_mnemos.core.install_checks import (
    check_claude_cli_installed,
    check_hooks_present,
)

DAEMON_STATUS_URL = "http://127.0.0.1:5757/api/onboarding/setup-status"
ROW_NAMES = ("claude_cli", "hooks", "vaults", "projects")


def _fetch_setup_status() -> dict[str, Any] | None:
    """Try the daemon first; return None on any error."""
    try:
        with urllib.request.urlopen(DAEMON_STATUS_URL, timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def _local_setup_status() -> dict[str, Any]:
    """Daemon-down fallback: run only the local install checks."""
    cli = check_claude_cli_installed()
    hooks = check_hooks_present()
    rows = {
        "claude_cli": (
            {"status": "ok", "message": "Claude CLI installed"}
            if cli is None
            else {"status": cli.severity, "message": cli.message}
        ),
        "hooks": (
            {"status": "ok", "message": "Hooks installed"}
            if hooks is None
            else {"status": hooks.severity, "message": hooks.message}
        ),
        "vaults": {"status": "warning", "message": "Daemon offline; cannot check vault writability."},
        "projects": {"status": "warning", "message": "Daemon offline; cannot count projects."},
    }
    return {
        "all_ok": all(r["status"] == "ok" for r in rows.values()),
        **rows,
    }


def _label(status: str) -> str:
    return {
        "ok": "[OK]  ",
        "info": "[INFO]",
        "warning": "[WARN]",
        "critical": "[FAIL]",
    }.get(status, "[????]")


def run() -> int:
    status = _fetch_setup_status() or _local_setup_status()
    sys.stdout.write("mnemos doctor — install + operational health check\n\n")
    for name in ROW_NAMES:
        row = status.get(name, {"status": "warning", "message": "missing"})
        sys.stdout.write(f"  {_label(row['status'])} {name:<14} {row['message']}\n")
    sys.stdout.write("\n")
    if status["all_ok"]:
        sys.stdout.write("All systems nominal.\n")
        return 0
    sys.stdout.write("One or more issues detected. Run `mnemos hooks install` or visit\n")
    sys.stdout.write("the dashboard's Diagnostics tab at http://localhost:5757/diagnostics\n")
    return 1


def _cmd_doctor(_args: argparse.Namespace) -> int:
    return run()


def add_doctor_subparser(parent: argparse._SubParsersAction) -> None:
    p = parent.add_parser("doctor", help="Print install + operational health check")
    p.set_defaults(func=_cmd_doctor)
```

- [ ] **Step 4: Wire `add_doctor_subparser` in `cli.py` next to init**

```python
# claude_mnemos/cli.py — after add_init_subparser(sub) add:
from claude_mnemos.cli_doctor import add_doctor_subparser
add_doctor_subparser(sub)

# In dispatcher, after init handler:
if args.command == "doctor":
    return args.func(args)
```

- [ ] **Step 5: Run CLI test, confirm pass**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/cli/test_cli_doctor.py -v
```
Expected: 2 PASS.

- [ ] **Step 6: Frontend — write failing test for Diagnostics page**

```typescript
// frontend/src/__tests__/pages/Diagnostics.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { Diagnostics } from "@/pages/Diagnostics";
import * as api from "@/api/diagnostics.api";

vi.mock("@/api/diagnostics.api");

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Diagnostics />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Diagnostics page", () => {
  it("renders four checklist rows", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: true,
      claude_cli: { status: "ok", message: "Claude Code installed" },
      hooks: { status: "ok", message: "Hooks installed" },
      vaults: { status: "ok", message: "Vaults writable" },
      projects: { status: "ok", message: "1 project tracked", count: 1 },
    });
    renderPage();
    expect(await screen.findByText(/claude_cli/i)).toBeInTheDocument();
    expect(await screen.findByText(/hooks/i)).toBeInTheDocument();
    expect(await screen.findByText(/vaults/i)).toBeInTheDocument();
    expect(await screen.findByText(/projects/i)).toBeInTheDocument();
  });

  it("shows critical message when claude_cli missing", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: false,
      claude_cli: { status: "critical", message: "Claude Code is not installed" },
      hooks: { status: "ok", message: "ok" },
      vaults: { status: "ok", message: "ok" },
      projects: { status: "ok", message: "ok", count: 1 },
    });
    renderPage();
    expect(await screen.findByText(/Claude Code is not installed/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 7: Run frontend test, confirm fail**

```
cd frontend && npm test -- --run Diagnostics
```
Expected: FAIL — `Diagnostics` not exported.

- [ ] **Step 8: Implement `frontend/src/api/diagnostics.api.ts`**

```typescript
// frontend/src/api/diagnostics.api.ts
import axios from "axios";

export interface SetupStatusRow {
  status: "ok" | "info" | "warning" | "critical";
  message: string;
  id?: string;
  count?: number;
}

export interface SetupStatus {
  all_ok: boolean;
  claude_cli: SetupStatusRow;
  hooks: SetupStatusRow;
  vaults: SetupStatusRow;
  projects: SetupStatusRow;
}

export async function getSetupStatus(): Promise<SetupStatus> {
  const r = await axios.get<SetupStatus>("/api/onboarding/setup-status");
  return r.data;
}
```

- [ ] **Step 9: Implement `frontend/src/pages/Diagnostics.tsx`**

```tsx
// frontend/src/pages/Diagnostics.tsx
import { useQuery } from "@tanstack/react-query";
import { getSetupStatus, type SetupStatusRow } from "@/api/diagnostics.api";
import { Skeleton } from "@/components/ui/skeleton";

const STATUS_STYLES: Record<SetupStatusRow["status"], string> = {
  ok: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
  info: "border-blue-500/40 bg-blue-500/10 text-blue-400",
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-400",
  critical: "border-rose-500/40 bg-rose-500/10 text-rose-400",
};

const ROW_LABELS: Record<string, string> = {
  claude_cli: "Claude Code CLI",
  hooks: "Claude Code hooks",
  vaults: "Vault writability",
  projects: "Tracked projects",
};

export function Diagnostics() {
  const q = useQuery({ queryKey: ["setup-status"], queryFn: getSetupStatus });

  if (q.isLoading) return <Skeleton className="h-48 w-full" />;
  if (q.isError || !q.data) {
    return <div className="rounded border border-rose-500/40 bg-rose-500/10 p-4 text-rose-400">Failed to load status.</div>;
  }
  const status = q.data;
  const rows: { key: keyof typeof ROW_LABELS; row: SetupStatusRow }[] = [
    { key: "claude_cli", row: status.claude_cli },
    { key: "hooks", row: status.hooks },
    { key: "vaults", row: status.vaults },
    { key: "projects", row: status.projects },
  ];

  return (
    <div className="space-y-4 py-6 max-w-3xl">
      <header>
        <span className="eyebrow">claude-mnemos · diagnostics</span>
        <h1 className="font-mono text-2xl mt-1">System health</h1>
      </header>
      <div className="space-y-2">
        {rows.map(({ key, row }) => (
          <div
            key={key}
            data-testid={`diag-row-${key}`}
            className={`flex items-center gap-3 rounded-md border p-3 ${STATUS_STYLES[row.status]}`}
          >
            <span className="font-mono uppercase text-[11px]">{row.status}</span>
            <span className="font-medium">{ROW_LABELS[key] ?? key}</span>
            <span className="ml-auto text-xs">{row.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 10: Add `/diagnostics` route in `frontend/src/App.tsx`**

```tsx
// near other lazy/eager imports
import { Diagnostics } from "./pages/Diagnostics";

// inside the children array, alongside /metrics and /help:
{ path: "diagnostics", element: <Diagnostics /> },
```

- [ ] **Step 11: Run frontend test, confirm pass**

```
cd frontend && npm test -- --run Diagnostics
cd frontend && npm run typecheck
```
Expected: 2 PASS, 0 TS errors.

- [ ] **Step 12: Commit**

```
git add claude_mnemos/cli_doctor.py claude_mnemos/cli.py tests/cli/test_cli_doctor.py
git add frontend/src/pages/Diagnostics.tsx frontend/src/api/diagnostics.api.ts frontend/src/App.tsx frontend/src/__tests__/pages/Diagnostics.test.tsx
git commit -m "feat(cli+ui): mnemos doctor + Diagnostics page

CLI prints colored OK/WARN/FAIL list of install + operational checks,
hits daemon when up, falls back to local checks when down. UI mirror
at /diagnostics shows the same data as colored rows."
```

---

### Task 8: Welcome screen replaces empty-state Onboarding (1.4 + part of 1.8)

Default landing for empty state. Existing `Onboarding.tsx` is renamed `OnboardingAdvanced.tsx`. New `OnboardingWelcome.tsx` shows setup status + detected workspaces + autostart opt-out (default ON) + button to track all selected workspaces in one shot. Falls back to advanced wizard via "Show advanced".

**Files:**
- Rename: `frontend/src/pages/Onboarding.tsx` → `frontend/src/pages/OnboardingAdvanced.tsx`
- Create: `frontend/src/pages/OnboardingWelcome.tsx`
- Create: `frontend/src/api/onboarding.api.ts`
- Create: `frontend/src/hooks/onboarding/useDetectedCwds.ts`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/__tests__/pages/OnboardingWelcome.test.tsx`

- [ ] **Step 1: Rename existing wizard (no behaviour change)**

```bash
git mv frontend/src/pages/Onboarding.tsx frontend/src/pages/OnboardingAdvanced.tsx
```

Edit the renamed file: change `export function Onboarding()` → `export function OnboardingAdvanced()`. Update any internal references.

- [ ] **Step 2: Write failing test for the new Welcome screen**

```typescript
// frontend/src/__tests__/pages/OnboardingWelcome.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { OnboardingWelcome } from "@/pages/OnboardingWelcome";
import * as onboardingApi from "@/api/onboarding.api";
import * as projectCreate from "@/hooks/useProjectCreate";

vi.mock("@/api/onboarding.api");
vi.mock("@/hooks/useProjectCreate");

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <OnboardingWelcome />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OnboardingWelcome", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders detected workspaces with session counts", async () => {
    vi.mocked(onboardingApi.getDetectedCwds).mockResolvedValue({
      cwds: [
        { cwd: "D:/code/app1", session_count: 12, last_seen: "2026-05-04T10:00Z" },
        { cwd: "D:/code/app2", session_count: 3, last_seen: "2026-05-03T10:00Z" },
      ],
    });
    renderPage();
    expect(await screen.findByText(/D:\/code\/app1/i)).toBeInTheDocument();
    expect(screen.getByText(/12 sessions/i)).toBeInTheDocument();
    expect(await screen.findByText(/D:\/code\/app2/i)).toBeInTheDocument();
  });

  it("shows empty hint when no cwds detected", async () => {
    vi.mocked(onboardingApi.getDetectedCwds).mockResolvedValue({ cwds: [] });
    renderPage();
    expect(
      await screen.findByText(/no claude code sessions found/i),
    ).toBeInTheDocument();
  });

  it("creates a project when user picks a workspace and clicks Track", async () => {
    vi.mocked(onboardingApi.getDetectedCwds).mockResolvedValue({
      cwds: [{ cwd: "D:/code/app1", session_count: 12, last_seen: "2026-05-04T10:00Z" }],
    });
    const mutate = vi.fn();
    vi.mocked(projectCreate.useProjectCreate).mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof projectCreate.useProjectCreate>);

    renderPage();
    const checkbox = await screen.findByRole("checkbox", { name: /D:\/code\/app1/i });
    await userEvent.click(checkbox);
    await userEvent.click(screen.getByRole("button", { name: /track selected/i }));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          name: expect.stringMatching(/app1/),
          vault_root: expect.stringContaining("D:/code/app1"),
          cwd_patterns: expect.arrayContaining(["D:/code/app1"]),
        }),
        expect.anything(),
      );
    });
  });

  it("offers Show advanced link", async () => {
    vi.mocked(onboardingApi.getDetectedCwds).mockResolvedValue({ cwds: [] });
    renderPage();
    expect(await screen.findByRole("link", { name: /show advanced/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run test, confirm fail**

```
cd frontend && npm test -- --run OnboardingWelcome
```
Expected: FAIL — file does not exist.

- [ ] **Step 4: Create the API client**

```typescript
// frontend/src/api/onboarding.api.ts
import axios from "axios";

export interface DetectedCwd {
  cwd: string;
  session_count: number;
  last_seen: string;
}
export interface DetectedCwdsResponse {
  cwds: DetectedCwd[];
}

export async function getDetectedCwds(): Promise<DetectedCwdsResponse> {
  const r = await axios.get<DetectedCwdsResponse>("/api/onboarding/detected-cwds");
  return r.data;
}
```

- [ ] **Step 5: Create the hook**

```typescript
// frontend/src/hooks/onboarding/useDetectedCwds.ts
import { useQuery } from "@tanstack/react-query";
import { getDetectedCwds } from "@/api/onboarding.api";

export function useDetectedCwds() {
  return useQuery({
    queryKey: ["onboarding", "detected-cwds"],
    queryFn: getDetectedCwds,
  });
}
```

- [ ] **Step 6: Implement `OnboardingWelcome.tsx`**

```tsx
// frontend/src/pages/OnboardingWelcome.tsx
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDetectedCwds } from "@/hooks/onboarding/useDetectedCwds";
import { useProjectCreate } from "@/hooks/useProjectCreate";
import { deriveSlug } from "@/lib/slugify";

function lastSegment(p: string): string {
  return p.replace(/[\\/]+$/, "").split(/[\\/]/).slice(-1)[0] ?? p;
}

function humanize(name: string): string {
  return name
    .replace(/[-_]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

export function OnboardingWelcome() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const detectedQ = useDetectedCwds();
  const createMut = useProjectCreate();
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggle = (cwd: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cwd)) next.delete(cwd);
      else next.add(cwd);
      return next;
    });
  };

  const trackSelected = async () => {
    const list = Array.from(selected);
    let lastSlug = "";
    for (const cwd of list) {
      const display = humanize(lastSegment(cwd));
      const slug = deriveSlug(display);
      lastSlug = slug;
      const vault = cwd.replace(/[\\/]+$/, "") + "/.mnemos";
      const patterns = [cwd, `${cwd}/*`, `${cwd}/**`];
      await new Promise<void>((res, rej) => {
        createMut.mutate(
          {
            name: slug,
            display_name: display,
            vault_root: vault,
            cwd_patterns: patterns,
          },
          { onSuccess: () => res(), onError: (e) => rej(e) },
        );
      });
    }
    navigate(lastSlug ? `/project/${encodeURIComponent(lastSlug)}` : "/");
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-8">
      <header className="rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <span className="eyebrow">claude-mnemos · welcome</span>
        <h1 className="mt-2 font-mono text-2xl">{t("onboarding.welcome.title", "Welcome to claude-mnemos")}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {t(
            "onboarding.welcome.subtitle",
            "Pick a folder where you use Claude Code — mnemos will start remembering what happens there.",
          )}
        </p>
      </header>

      <section className="rounded-md border border-border/60 bg-card/40 p-4 space-y-3">
        <h2 className="text-sm font-medium">
          {t("onboarding.welcome.detected_heading", "We found these Claude Code workspaces:")}
        </h2>
        {detectedQ.isLoading && <Skeleton className="h-24 w-full" />}
        {detectedQ.isSuccess && detectedQ.data.cwds.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {t(
              "onboarding.welcome.empty",
              "No Claude Code sessions found yet. Open Claude Code in a project folder, run a session, then refresh this page.",
            )}
          </p>
        )}
        {detectedQ.isSuccess && detectedQ.data.cwds.length > 0 && (
          <ul className="space-y-2">
            {detectedQ.data.cwds.map((d) => (
              <li
                key={d.cwd}
                className="flex items-center gap-3 rounded-md border border-border/60 bg-card/60 p-3"
              >
                <input
                  type="checkbox"
                  aria-label={d.cwd}
                  checked={selected.has(d.cwd)}
                  onChange={() => toggle(d.cwd)}
                />
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-sm truncate">{d.cwd}</div>
                  <div className="text-xs text-muted-foreground">
                    {d.session_count} sessions
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="flex items-center gap-3">
        <Button onClick={trackSelected} disabled={selected.size === 0 || createMut.isPending}>
          {createMut.isPending
            ? t("confirm.working", "Working…")
            : t("onboarding.welcome.track_selected", "Track selected")}
        </Button>
        <Button asChild variant="outline">
          <Link to="/onboarding/advanced">{t("onboarding.welcome.show_advanced", "Show advanced")}</Link>
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Update routing in `App.tsx`**

```tsx
// frontend/src/App.tsx — replace the Onboarding line
import { OnboardingWelcome } from "./pages/OnboardingWelcome";
import { OnboardingAdvanced } from "./pages/OnboardingAdvanced";

// inside children:
{ path: "onboarding", element: <OnboardingWelcome /> },
{ path: "onboarding/advanced", element: <OnboardingAdvanced /> },
```

Remove the old `import { Onboarding } from "./pages/Onboarding";` line.

- [ ] **Step 8: Run test, confirm pass + typecheck**

```
cd frontend && npm test -- --run OnboardingWelcome
cd frontend && npm run typecheck
```
Expected: 4 PASS, 0 TS errors.

- [ ] **Step 9: Commit**

```
git add frontend/src/pages/OnboardingWelcome.tsx frontend/src/pages/OnboardingAdvanced.tsx frontend/src/api/onboarding.api.ts frontend/src/hooks/onboarding/useDetectedCwds.ts frontend/src/App.tsx frontend/src/__tests__/pages/OnboardingWelcome.test.tsx
git commit -m "feat(ui): OnboardingWelcome — auto-detect workspaces, one-click track

New empty-state landing replaces the technical wizard. Renamed
old Onboarding to OnboardingAdvanced — reachable via Show advanced
link for users who need full control."
```

---

### Task 9: Setup-Checklist widget on Overview (1.5)

Persistent collapsing widget on Overview that always reflects current setup state. Calls `/api/onboarding/setup-status` (already created in Task 5). Auto-collapses to a single ✓ chip when all_ok. Expands on any non-ok row.

**Files:**
- Create: `frontend/src/components/widgets/dashboard/SetupChecklist.tsx`
- Create: `frontend/src/hooks/onboarding/useSetupStatus.ts`
- Modify: `frontend/src/pages/Overview.tsx` — mount widget between `<HealthAlertsBar />` and the rate-limit banner block.
- Test: `frontend/src/__tests__/widgets/SetupChecklist.test.tsx`

- [ ] **Step 1: Write failing test**

```typescript
// frontend/src/__tests__/widgets/SetupChecklist.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SetupChecklist } from "@/components/widgets/dashboard/SetupChecklist";
import * as api from "@/api/diagnostics.api";

vi.mock("@/api/diagnostics.api");

function renderWidget() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SetupChecklist />
    </QueryClientProvider>,
  );
}

describe("SetupChecklist widget", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders collapsed when all_ok", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: true,
      claude_cli: { status: "ok", message: "ok" },
      hooks: { status: "ok", message: "ok" },
      vaults: { status: "ok", message: "ok" },
      projects: { status: "ok", message: "ok", count: 1 },
    });
    renderWidget();
    expect(await screen.findByText(/setup ok/i)).toBeInTheDocument();
    // Detail rows hidden by default in collapsed state
    expect(screen.queryByText(/Claude Code installed/i)).toBeNull();
  });

  it("expands by default and shows non-ok row when any fail", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: false,
      claude_cli: { status: "critical", message: "Claude Code is not installed" },
      hooks: { status: "ok", message: "ok" },
      vaults: { status: "ok", message: "ok" },
      projects: { status: "ok", message: "ok", count: 1 },
    });
    renderWidget();
    expect(await screen.findByText(/Claude Code is not installed/i)).toBeInTheDocument();
  });

  it("expands collapsed widget on click", async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({
      all_ok: true,
      claude_cli: { status: "ok", message: "Claude CLI installed" },
      hooks: { status: "ok", message: "ok" },
      vaults: { status: "ok", message: "ok" },
      projects: { status: "ok", message: "ok", count: 1 },
    });
    renderWidget();
    const summary = await screen.findByText(/setup ok/i);
    fireEvent.click(summary);
    expect(await screen.findByText(/Claude CLI installed/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test, confirm fail**

```
cd frontend && npm test -- --run SetupChecklist
```
Expected: FAIL — file does not exist.

- [ ] **Step 3: Create the hook**

```typescript
// frontend/src/hooks/onboarding/useSetupStatus.ts
import { useQuery } from "@tanstack/react-query";
import { getSetupStatus } from "@/api/diagnostics.api";

export function useSetupStatus() {
  return useQuery({
    queryKey: ["setup-status"],
    queryFn: getSetupStatus,
    refetchInterval: 30_000,
  });
}
```

- [ ] **Step 4: Implement the widget**

```tsx
// frontend/src/components/widgets/dashboard/SetupChecklist.tsx
import { useState } from "react";
import { Link } from "react-router";
import { useSetupStatus } from "@/hooks/onboarding/useSetupStatus";
import type { SetupStatusRow } from "@/api/diagnostics.api";

const ICON: Record<SetupStatusRow["status"], string> = {
  ok: "✓",
  info: "•",
  warning: "⚠",
  critical: "✗",
};

const ROW_LABELS: Record<string, string> = {
  claude_cli: "Claude Code CLI",
  hooks: "Claude Code hooks",
  vaults: "Vault writability",
  projects: "Tracked projects",
};

export function SetupChecklist() {
  const q = useSetupStatus();
  const [forcedOpen, setForcedOpen] = useState(false);

  if (q.isLoading || !q.data) return null;
  const status = q.data;
  const collapsed = status.all_ok && !forcedOpen;

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setForcedOpen(true)}
        className="inline-flex items-center gap-2 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-mono text-emerald-400"
      >
        ✓ Setup OK
      </button>
    );
  }

  const rows: { key: keyof typeof ROW_LABELS; row: SetupStatusRow }[] = [
    { key: "claude_cli", row: status.claude_cli },
    { key: "hooks", row: status.hooks },
    { key: "vaults", row: status.vaults },
    { key: "projects", row: status.projects },
  ];

  return (
    <section className="rounded-md border border-border/60 bg-card/40 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="eyebrow">SETUP STATUS</span>
        <Link to="/diagnostics" className="text-xs underline text-primary">
          Diagnostics →
        </Link>
      </div>
      <ul className="space-y-1">
        {rows.map(({ key, row }) => (
          <li
            key={key}
            data-testid={`setup-row-${key}`}
            className={`flex items-center gap-2 rounded px-2 py-1 text-sm ${
              row.status === "ok" ? "text-emerald-400" :
              row.status === "warning" ? "text-amber-400" :
              row.status === "critical" ? "text-rose-400" :
              "text-muted-foreground"
            }`}
          >
            <span className="font-mono w-4">{ICON[row.status]}</span>
            <span className="font-medium w-44">{ROW_LABELS[key] ?? key}</span>
            <span className="text-xs">{row.message}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 5: Mount widget in Overview**

```tsx
// frontend/src/pages/Overview.tsx — add import
import { SetupChecklist } from "@/components/widgets/dashboard/SetupChecklist";

// inside the JSX, after <HealthAlertsBar /> and before {showRateLimitBanner && ...}:
<SetupChecklist />
```

- [ ] **Step 6: Run tests + typecheck**

```
cd frontend && npm test -- --run SetupChecklist
cd frontend && npm run typecheck
```
Expected: 3 PASS, 0 TS errors.

- [ ] **Step 7: Commit**

```
git add frontend/src/components/widgets/dashboard/SetupChecklist.tsx frontend/src/hooks/onboarding/useSetupStatus.ts frontend/src/pages/Overview.tsx frontend/src/__tests__/widgets/SetupChecklist.test.tsx
git commit -m "feat(ui): SetupChecklist widget on Overview

Persistent collapsing widget reflecting /api/onboarding/setup-status.
Polls every 30s. Collapses to a Setup OK chip when all_ok, expands
into a 4-row checklist on any non-ok or on click. Links to the
Diagnostics page."
```

---

### Task 10: First-session celebration (1.6)

When a project's manifest count goes 0 → 1+ between two `useDashboardSnapshot` polls, fire a one-time toast. Use `localStorage` for instant deduplication; backend `install_state.first_session_celebrated_for` is the durable record.

**Files:**
- Create: `frontend/src/hooks/useFirstSessionCelebration.ts`
- Modify: `frontend/src/pages/Overview.tsx` — call the hook
- Test: `frontend/src/__tests__/hooks/useFirstSessionCelebration.test.tsx`

- [ ] **Step 1: Write failing test**

```typescript
// frontend/src/__tests__/hooks/useFirstSessionCelebration.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { toast } from "sonner";
import { useFirstSessionCelebration } from "@/hooks/useFirstSessionCelebration";

vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));

interface FakeSnapshotShape {
  active_sessions: { project_name: string }[];
  kpi: Record<string, unknown>;
  running_jobs: unknown[];
  errors: string[];
  per_project_session_counts?: Record<string, number>;
}

beforeEach(() => {
  localStorage.clear();
  vi.mocked(toast.success).mockClear();
});

describe("useFirstSessionCelebration", () => {
  it("fires toast on 0→1 transition for a project", () => {
    const { rerender } = renderHook(
      ({ snapshot }: { snapshot: FakeSnapshotShape | undefined }) =>
        useFirstSessionCelebration(snapshot),
      { initialProps: { snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 0 } } } },
    );
    rerender({ snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 1 } } });
    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(vi.mocked(toast.success).mock.calls[0][0]).toMatch(/first session/i);
  });

  it("does not fire when count was already > 0", () => {
    const { rerender } = renderHook(
      ({ snapshot }: { snapshot: FakeSnapshotShape | undefined }) =>
        useFirstSessionCelebration(snapshot),
      { initialProps: { snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 5 } } } },
    );
    rerender({ snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 6 } } });
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("does not fire twice for the same project (localStorage guard)", () => {
    localStorage.setItem("mnemos.first_session_celebrated.my-app", "1");
    const { rerender } = renderHook(
      ({ snapshot }: { snapshot: FakeSnapshotShape | undefined }) =>
        useFirstSessionCelebration(snapshot),
      { initialProps: { snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 0 } } } },
    );
    rerender({ snapshot: { active_sessions: [], kpi: {}, running_jobs: [], errors: [], per_project_session_counts: { "my-app": 1 } } });
    expect(toast.success).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test, confirm fail**

```
cd frontend && npm test -- --run useFirstSessionCelebration
```
Expected: FAIL — file does not exist.

- [ ] **Step 3: Add `per_project_session_counts` to dashboard snapshot backend**

Modify `claude_mnemos/daemon/routes/dashboard.py`:

(a) Add the import at the top (alongside other imports, around line 17):
```python
from claude_mnemos.state.manifest import Manifest
```

(b) Inside `dashboard_snapshot` (function definition at line 96), insert a new aggregator block after the `running_jobs` try/except (which ends at line 139) and before the `return` at line 141:

```python
    per_project_counts: dict[str, int] = {}
    try:
        for rt in runtimes:
            try:
                m = Manifest.load(rt.vault_root)
                per_project_counts[rt.name] = len(m.ingested)
            except Exception as exc:
                log.debug("per_project_session_counts manifest read failed for %s: %s", rt.name, exc)
                per_project_counts[rt.name] = 0
    except Exception as exc:
        log.warning("per_project_session_counts aggregator failed: %s", exc)
        errors.append(f"per_project_session_counts: {exc}")
```

(c) Update the `return` block to include the new key:
```python
    return {
        "kpi": kpi,
        "active_sessions": active_sessions,
        "running_jobs": running_jobs,
        "per_project_session_counts": per_project_counts,
        "errors": errors,
    }
```

- [ ] **Step 4: Add a backend test for the new field**

```python
# tests/daemon/test_app_dashboard.py — append at the end of the file
def test_snapshot_includes_per_project_session_counts(monkeypatch):
    """The Overview's first-session-celebration hook depends on this field."""
    from fastapi.testclient import TestClient
    from claude_mnemos.daemon.app import create_app

    app = create_app(daemon=None)  # zero runtimes — counts dict will be empty but key present
    client = TestClient(app)
    r = client.get("/api/dashboard/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert "per_project_session_counts" in body
    assert isinstance(body["per_project_session_counts"], dict)
```

- [ ] **Step 5: Implement the hook**

```typescript
// frontend/src/hooks/useFirstSessionCelebration.ts
import { useEffect, useRef } from "react";
import { toast } from "sonner";

interface SnapshotLike {
  per_project_session_counts?: Record<string, number>;
}

const KEY_PREFIX = "mnemos.first_session_celebrated.";

function alreadyCelebrated(name: string): boolean {
  try {
    return localStorage.getItem(KEY_PREFIX + name) === "1";
  } catch {
    return false;
  }
}

function markCelebrated(name: string): void {
  try {
    localStorage.setItem(KEY_PREFIX + name, "1");
  } catch {
    /* ignore quota / disabled storage */
  }
}

export function useFirstSessionCelebration(snapshot: SnapshotLike | undefined): void {
  const prevRef = useRef<Record<string, number> | null>(null);

  useEffect(() => {
    if (!snapshot?.per_project_session_counts) return;
    const curr = snapshot.per_project_session_counts;
    const prev = prevRef.current;

    if (prev) {
      for (const [name, count] of Object.entries(curr)) {
        const prevCount = prev[name] ?? 0;
        if (prevCount === 0 && count > 0 && !alreadyCelebrated(name)) {
          toast.success(`🎉 First session ingested for ${name}!`);
          markCelebrated(name);
        }
      }
    }
    prevRef.current = curr;
  }, [snapshot]);
}
```

- [ ] **Step 6: Wire into Overview**

```tsx
// frontend/src/pages/Overview.tsx — add import
import { useFirstSessionCelebration } from "@/hooks/useFirstSessionCelebration";

// inside the component, after `const snapshot = snapshotQuery.data;`:
useFirstSessionCelebration(snapshot);
```

- [ ] **Step 7: Run tests**

```
cd frontend && npm test -- --run useFirstSessionCelebration
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/daemon/test_app_dashboard.py -v
```
Expected: 3 frontend PASS, backend snapshot test PASS.

- [ ] **Step 8: Commit**

```
git add frontend/src/hooks/useFirstSessionCelebration.ts frontend/src/pages/Overview.tsx frontend/src/__tests__/hooks/useFirstSessionCelebration.test.tsx claude_mnemos/daemon/routes/dashboard.py tests/daemon/test_app_dashboard.py
git commit -m "feat(ui+daemon): first-session celebration toast on 0→1 transition

Backend: dashboard snapshot now exposes per_project_session_counts.
Frontend: useFirstSessionCelebration hook watches the field on each
poll and fires a one-time toast when any project's manifest goes
from 0 to >0. Dedup'd via localStorage."
```

---

### Task 11: Tray autostart default-on (1.8)

When the daemon starts and `install_state.autostart_decision is None`, schedule a one-shot autostart-install attempt after the first successful health-check. Records `autostart_decision = "accepted"` so it doesn't re-fire. Users can still uninstall via `mnemos tray uninstall` (sets it to `"declined"`).

**Files:**
- Modify: `claude_mnemos/daemon/process.py` — add the post-startup hook
- Modify: `claude_mnemos/tray/__main__.py::_cmd_uninstall` — record decision = "declined"
- Modify: `claude_mnemos/cli_init.py` from Task 6 — same record on success (decision = "accepted")
- Test: `tests/daemon/test_install_autostart_default.py`

- [ ] **Step 1: Write failing test**

```python
# tests/daemon/test_install_autostart_default.py
from unittest.mock import MagicMock

import pytest


def test_autostart_attempted_on_first_run_when_decision_none(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )

    attempts = {"count": 0}
    monkeypatch.setattr(
        "claude_mnemos.daemon.process._attempt_autostart_install",
        lambda: attempts.update({"count": attempts["count"] + 1}) or True,
    )

    from claude_mnemos.daemon.process import maybe_install_autostart_default

    maybe_install_autostart_default()
    assert attempts["count"] == 1

    # Re-run — decision now stored as "accepted", should NOT re-attempt.
    maybe_install_autostart_default()
    assert attempts["count"] == 1


def test_autostart_skipped_if_already_declined(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "claude_mnemos.state.install_state._STATE_PATH",
        tmp_path / "install-state.json",
    )
    from claude_mnemos.state.install_state import InstallState
    InstallState(autostart_decision="declined").save()

    attempts = {"count": 0}
    monkeypatch.setattr(
        "claude_mnemos.daemon.process._attempt_autostart_install",
        lambda: attempts.update({"count": attempts["count"] + 1}) or True,
    )

    from claude_mnemos.daemon.process import maybe_install_autostart_default
    maybe_install_autostart_default()
    assert attempts["count"] == 0
```

- [ ] **Step 2: Run test, confirm fail**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/daemon/test_install_autostart_default.py -v
```
Expected: FAIL — `maybe_install_autostart_default` not defined.

- [ ] **Step 3: Add the helper to `daemon/process.py`**

```python
# claude_mnemos/daemon/process.py — add near the other startup helpers
import logging
from claude_mnemos.state.install_state import load_install_state, InstallState

log = logging.getLogger(__name__)


def _attempt_autostart_install() -> bool:
    """Best-effort tray autostart registration. Returns True on success."""
    try:
        from claude_mnemos.tray.__main__ import _cmd_install as tray_install
        rc = tray_install()
        return rc == 0
    except Exception:  # noqa: BLE001
        log.exception("autostart-default-on attempt failed")
        return False


def maybe_install_autostart_default() -> None:
    """If the user has not made a decision yet, register tray autostart and remember.

    Idempotent. Designed to be called on daemon startup from process.py.
    """
    state = load_install_state()
    if state.autostart_decision is not None:
        return
    if _attempt_autostart_install():
        state.autostart_decision = "accepted"
        state.save()
```

Wire the call inside `MnemosDaemon.run()` (defined at `claude_mnemos/daemon/process.py:96`). Insert one line after `asyncio.create_task(self._health_checks_task_fn())` (currently line 112), before `await self._serve_uvicorn()`:

```python
            # Best-effort: register tray autostart on first run if user hasn't
            # explicitly opted out. Idempotent — runs at most once across
            # daemon lifetimes (decision is persisted in install-state.json).
            asyncio.create_task(asyncio.to_thread(maybe_install_autostart_default))
```

The `asyncio.to_thread` wrapper isolates the Win-registry / launchd writes from the event loop. Because it's an `asyncio.create_task`, it does not delay daemon startup if the call hangs.

- [ ] **Step 4: Update tray `_cmd_uninstall` to record declined**

```python
# claude_mnemos/tray/__main__.py — inside _cmd_uninstall, after mgr.uninstall():
from claude_mnemos.state.install_state import load_install_state
state = load_install_state()
state.autostart_decision = "declined"
state.save()
```

- [ ] **Step 5: Update `cli_init.run()` to record accepted on tray-install success**

```python
# claude_mnemos/cli_init.py — inside run(), after successful _install_tray_autostart_safe():
from claude_mnemos.state.install_state import load_install_state
s = load_install_state()
if s.autostart_decision is None:
    s.autostart_decision = "accepted"
    s.save()
```

- [ ] **Step 6: Run tests**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/daemon/test_install_autostart_default.py -v
```
Expected: 2 PASS.

- [ ] **Step 7: Commit**

```
git add claude_mnemos/daemon/process.py claude_mnemos/tray/__main__.py claude_mnemos/cli_init.py tests/daemon/test_install_autostart_default.py
git commit -m "feat(daemon): autostart default-on (one-shot, idempotent)

When daemon starts and no autostart decision recorded, register tray
autostart and store decision='accepted' so we never re-attempt.
mnemos tray uninstall records decision='declined' to lock the state."
```

---

### Final verification — full suite + live walk

After all 11 tasks committed:

- [ ] **Step 1: Backend full suite**

```
~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest tests/ --deselect tests/daemon/test_e2e_subprocess.py::test_daemon_subprocess_lifecycle -q
```
Expected: ≥ 1685 passed (1662 + ~23 new tests across tasks 1, 2, 3, 4, 5, 6, 7, 11).

- [ ] **Step 2: Frontend Vitest**

```
cd frontend && npm test -- --run
```
Expected: ≥ 358 passed (343 + ~15 new tests across tasks 7, 8, 9, 10).

- [ ] **Step 3: TypeScript**

```
cd frontend && npm run typecheck
```
Expected: 0 errors.

- [ ] **Step 4: Frontend production build**

```
cd frontend && npm run build
```
Expected: build succeeds, bundle written to `claude_mnemos/daemon/static/`.

- [ ] **Step 5: Live walk** — restart daemon and walk through:
  - Visit `/` with no projects: confirm OnboardingWelcome page renders, detected workspaces show.
  - Click Show advanced: confirm OnboardingAdvanced renders.
  - Create project; confirm SetupChecklist appears on Overview.
  - Run `mnemos doctor` — confirm colored ✓/⚠/✗ output.
  - Run `mnemos init` on a fresh `~/.claude-mnemos/` — confirm browser opens.
  - Visit `/diagnostics` — confirm 4-row health card.

- [ ] **Step 6: Phase-1 wrap commit (optional)** — only if any docs/notes need updating; otherwise skip.

```
git add docs/superpowers/plans/2026-05-04-public-onboarding-phase-1.md
git commit -m "docs(plan): mark public-onboarding Phase 1 complete"
```

---

## Self-review notes

- **Spec coverage:** All 9 sub-tasks (1.1 through 1.9) are mapped. Task 1 = 1.1; Task 6 = 1.2 + 1.9; Task 5 = 1.3 backend; Task 8 = 1.4 + part of 1.8; Task 9 = 1.5; Task 10 = 1.6; Task 7 = 1.7; Task 11 = 1.8. Foundations Task 2 (`install_state.py`) and Task 4 (`install_checks.py`) feed the others.
- **Type consistency:** `StoredAlert`, `DetectedCwd`, `SetupStatus`, `SetupStatusRow`, `SnapshotLike` are defined once and re-used.
- **Test ordering:** Each task is independently committable with passing tests. `pytest tests/ --deselect …` always passes after each commit.
- **No placeholders:** Every code block is concrete; every command shows expected output.
- **Risks acknowledged:** Task 5's `_registered_cwds` uses a permissive heuristic on glob-stems; if `cwd_patterns` shape is more complex than the current `<cwd>`/`<cwd>/*`/`<cwd>/**` triplet pattern, executor may need to refine. Task 8's project-creation loop is sequential (one mutate per selected workspace); if the backend ever supports batch project-create, that's a future optimisation.
