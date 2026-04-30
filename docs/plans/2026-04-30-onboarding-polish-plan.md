# Onboarding Polish Implementation Plan (Plan A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрыть 3 UX pain points project management при создании нового проекта: display_name (UTF-8 имена с auto-derived slug), DirectoryPicker (modal с browse/breadcrumbs/recent/new folder), CWD mini-builder (список вместо textarea с glob). Plan B (Settings UI) — отдельный план.

**Architecture:** Backend добавляет `display_name: str | None` в `ProjectMapEntry` (без миграции — fallback в UI) + 3 endpoint'а `/fs/{home,browse,mkdir}`. Frontend получает reusable `<DirectoryPicker>` modal, `slugify()` lib (`@sindresorhus/slugify`), `<CwdBuilder>` который переиспользует picker. Onboarding.tsx переписан на новые компоненты + везде в UI fallback `display_name ?? name`.

**Tech Stack:** Python 3.12+ Pydantic v2 FastAPI; React 19 + Vite + TypeScript + zod; `@sindresorhus/slugify` (новая dep frontend).

**Design doc:** `docs/plans/2026-04-30-onboarding-polish-design.md`.

**Branch:** `feat/onboarding-polish` (из `main` после merge `8bc42b5`, design committed `9772e18`).

**Critical safety rule:** В конце каждой фазы — `python -m pytest --ignore=tests/slow` показывает baseline или больше (1465 currently). Никаких regressions. Frontend Vitest baseline 196.

---

## File Structure

### New backend files

```
claude_mnemos/daemon/routes/fs.py        # GET /fs/home, GET /fs/browse, POST /fs/mkdir
claude_mnemos/daemon/schemas_fs.py       # FsBrowseResponse, FsMkdirRequest, FsHomeResponse Pydantic models

tests/daemon/routes/test_fs.py
tests/state/test_projects_display_name.py
```

### New frontend files

```
frontend/src/types/Fs.ts                 # zod schemas
frontend/src/api/fs.api.ts                # browseDirectory, mkdir, getHome

frontend/src/lib/slugify.ts               # deriveSlug(displayName) using @sindresorhus/slugify
frontend/src/lib/projectDisplayName.ts    # getProjectDisplayName(project) helper

frontend/src/hooks/useRecentPaths.ts      # localStorage CRUD for picker recent

frontend/src/components/picker/
├── DirectoryPicker.tsx                   # main modal (composes other pieces)
├── DirectoryPickerInner.tsx              # state machine + layout (testable)

frontend/src/components/onboarding/
└── CwdBuilder.tsx                        # list + add via picker

frontend/src/__tests__/lib-slugify.test.ts
frontend/src/__tests__/api-fs.test.ts
frontend/src/__tests__/useRecentPaths.test.ts
frontend/src/__tests__/DirectoryPicker.test.tsx
frontend/src/__tests__/CwdBuilder.test.tsx
```

### Modified files

```
claude_mnemos/state/projects.py          # +display_name: str | None field
claude_mnemos/daemon/app.py               # mount fs router
claude_mnemos/daemon/routes/projects.py   # accept + return display_name in POST/GET
claude_mnemos/cli_project.py              # +--display-name flag for `mnemos project add/update`

frontend/package.json                     # +@sindresorhus/slugify dep
frontend/src/pages/Onboarding.tsx         # rewrite to two-field + Browse + CwdBuilder
frontend/src/__tests__/Onboarding.test.tsx # extend tests
frontend/src/types/Project.ts             # add display_name field to zod schema
frontend/public/locales/{en,ru,uk}.json   # +new keys

# Sidebar / breadcrumbs / project switcher — везде применить getProjectDisplayName helper
frontend/src/components/Sidebar.tsx       # if exists; or wherever project name is shown
frontend/src/components/ProjectSwitcher.tsx
# (exact files identified in Task 12 inspection step)
```

### Untouched (zero-diff)

```
claude_mnemos/ingest/                     # extraction pipeline
claude_mnemos/state/manifest.py           # IngestRecord schema
claude_mnemos/core/metrics.py
claude_mnemos/hooks/
claude_mnemos/state/jobs.py
claude_mnemos/daemon/jobs/
claude_mnemos/state/settings.py           # 8 settings groups (Plan B will touch)
```

---

# Phase 1 — Backend: display_name + fs endpoints

**Goal:** Добавить `display_name` в схему ProjectMapEntry, реализовать 3 fs endpoint'а. Backend behavior unchanged for users without display_name (defaults None, treated as before). Тесты — backend pytest baseline 1465 → ~1473 после Phase 1.

---

## Task 1: ProjectMapEntry.display_name field

**Files:**
- Modify: `claude_mnemos/state/projects.py`
- Create: `tests/state/test_projects_display_name.py`

- [ ] **Step 1: Write failing tests**

Create `tests/state/test_projects_display_name.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

from claude_mnemos.state.projects import ProjectMap, ProjectMapEntry


def test_default_display_name_is_none() -> None:
    entry = ProjectMapEntry(name="x", vault_root=Path("/tmp/x"))
    assert entry.display_name is None


def test_display_name_accepts_unicode() -> None:
    entry = ProjectMapEntry(
        name="x",
        display_name="Конструктор сайтов",
        vault_root=Path("/tmp/x"),
    )
    assert entry.display_name == "Конструктор сайтов"


def test_load_legacy_json_without_display_name() -> None:
    """Existing project-map.json files (no display_name key) must load."""
    raw = {
        "version": 1,
        "projects": [
            {"name": "test-cli", "vault_root": "/tmp/test-cli", "cwd_patterns": []}
        ],
    }
    parsed = ProjectMap.model_validate(raw)
    assert len(parsed.projects) == 1
    assert parsed.projects[0].display_name is None
    assert parsed.projects[0].name == "test-cli"


def test_load_json_with_display_name() -> None:
    raw = {
        "version": 1,
        "projects": [
            {
                "name": "test-cli",
                "display_name": "Test Project",
                "vault_root": "/tmp/test-cli",
                "cwd_patterns": [],
            }
        ],
    }
    parsed = ProjectMap.model_validate(raw)
    assert parsed.projects[0].display_name == "Test Project"


def test_serialize_includes_display_name_when_set() -> None:
    entry = ProjectMapEntry(
        name="x",
        display_name="X Project",
        vault_root=Path("/tmp/x"),
    )
    data = entry.model_dump(mode="json")
    assert data["display_name"] == "X Project"


def test_serialize_includes_none_display_name() -> None:
    """Pydantic by default serialises None fields. Verify behaviour explicit."""
    entry = ProjectMapEntry(name="x", vault_root=Path("/tmp/x"))
    data = entry.model_dump(mode="json")
    assert "display_name" in data
    assert data["display_name"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /d/code/claude-mnemos && python -m pytest tests/state/test_projects_display_name.py -v 2>&1 | tail -10
```

Expected: AttributeError on `display_name`.

- [ ] **Step 3: Add field to ProjectMapEntry**

In `claude_mnemos/state/projects.py`, find `class ProjectMapEntry(BaseModel):` block. Add field:

```python
class ProjectMapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=PROJECT_NAME_PATTERN)
    display_name: str | None = None
    vault_root: Path
    cwd_patterns: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests — must pass**

```bash
python -m pytest tests/state/test_projects_display_name.py -v 2>&1 | tail -10
```

Expected: `6 passed`.

- [ ] **Step 5: Run all backend tests — no regressions**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1471 passed, 3 skipped` (1465 baseline + 6 new).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/state/projects.py tests/state/test_projects_display_name.py && git commit -m "feat(projects): ProjectMapEntry.display_name field (nullable, no migration)

Optional UTF-8 friendly display name. Fallback in UI: display_name ?? name.
Existing project-map.json files load without changes (Pydantic applies
default None for missing field).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Update CLI + REST to handle display_name

**Files:**
- Modify: `claude_mnemos/cli_project.py` (add --display-name flag, show in `project show`)
- Modify: `claude_mnemos/daemon/routes/projects.py` (accept display_name in POST body, return in GET)
- Test: extend `tests/test_cli_project.py` and `tests/daemon/test_routes_projects.py`

- [ ] **Step 1: Inspect existing CLI + routes**

```bash
grep -n "display_name\|cwd_patterns\|vault_root" /d/code/claude-mnemos/claude_mnemos/cli_project.py | head -20
grep -n "display_name\|cwd_patterns\|vault_root\|class.*Request\|class.*Response" /d/code/claude-mnemos/claude_mnemos/daemon/routes/projects.py | head -20
```

Note current parameter names + response shapes.

- [ ] **Step 2: Write failing test (CLI)**

Append to `tests/test_cli_project.py`:
```python
def test_project_add_with_display_name(tmp_path, monkeypatch) -> None:
    """`mnemos project add foo --display-name "Foo Project" --vault ..." stores both."""
    import json
    monkeypatch.setenv("MNEMOS_PROJECT_MAP", str(tmp_path / "project-map.json"))
    import sys
    from claude_mnemos.cli import main

    monkeypatch.setattr(sys, "argv", [
        "mnemos", "project", "add", "foo",
        "--vault", str(tmp_path / "vault"),
        "--display-name", "Foo Project",
    ])
    rc = main()
    assert rc == 0

    raw = json.loads((tmp_path / "project-map.json").read_text(encoding="utf-8"))
    entries = {p["name"]: p for p in raw["projects"]}
    assert entries["foo"]["display_name"] == "Foo Project"


def test_project_add_without_display_name_stores_none(tmp_path, monkeypatch) -> None:
    import json
    monkeypatch.setenv("MNEMOS_PROJECT_MAP", str(tmp_path / "project-map.json"))
    import sys
    from claude_mnemos.cli import main

    monkeypatch.setattr(sys, "argv", [
        "mnemos", "project", "add", "foo",
        "--vault", str(tmp_path / "vault"),
    ])
    rc = main()
    assert rc == 0

    raw = json.loads((tmp_path / "project-map.json").read_text(encoding="utf-8"))
    entries = {p["name"]: p for p in raw["projects"]}
    assert entries["foo"]["display_name"] is None
```

- [ ] **Step 3: Write failing test (REST)**

Append to existing test file for projects routes (find via `grep -l "POST.*/projects\|test.*project.*add" /d/code/claude-mnemos/tests/daemon/`). Inside, add:

```python
def test_post_projects_accepts_display_name() -> None:
    """POST /projects with display_name persists it."""
    # Adapt to existing test harness — likely uses TestClient + tmp project-map env.
    # Body shape: {"name": "foo", "vault_root": "...", "cwd_patterns": [], "display_name": "Foo Project"}
    # Assert: GET /projects/foo returns display_name="Foo Project"
    ...  # actual implementation in this step uses existing test helpers


def test_post_projects_without_display_name_returns_null() -> None:
    """POST /projects without display_name → response has display_name=null."""
    ...
```

(The plan author can't predict exact test harness — match patterns from existing `test_routes_projects*.py`.)

- [ ] **Step 4: Run failing tests**

```bash
python -m pytest tests/test_cli_project.py -v 2>&1 | tail -15
```

Expected: argparse error on `--display-name` + CLI returns non-zero.

- [ ] **Step 5: Update CLI argparse**

In `claude_mnemos/cli_project.py`, find the `add` subparser. Add:

```python
    p_add.add_argument("--display-name", default=None, help="Optional UTF-8 display name shown in dashboard")
```

Update the handler that constructs `ProjectMapEntry` to pass `display_name=args.display_name`.

For `update` subcommand — add same `--display-name` flag (sets the field if provided, leaves alone otherwise).

For `show` subcommand — extend the printed output to include `display_name` line.

- [ ] **Step 6: Update REST routes**

In `claude_mnemos/daemon/routes/projects.py`:

Find the request model for POST (likely `ProjectAddRequest` or similar). Add field:
```python
class ProjectAddRequest(BaseModel):
    name: str
    display_name: str | None = None
    vault_root: str
    cwd_patterns: list[str] = []
```

In the route handler, pass `display_name=req.display_name` to `ProjectStore.add(...)` (or whatever it's called).

Find response model (likely `ProjectEntryResponse`). Add:
```python
class ProjectEntryResponse(BaseModel):
    name: str
    display_name: str | None
    vault_root: str
    cwd_patterns: list[str]
```

For `update` (PATCH) endpoint — same field added to body.

- [ ] **Step 7: Run tests**

```bash
python -m pytest tests/test_cli_project.py tests/daemon/test_routes_projects.py -v 2>&1 | tail -15
```

Expected: all pass.

- [ ] **Step 8: Run all backend tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1473 passed, 3 skipped` (1471 + 2 new CLI tests).

- [ ] **Step 9: Commit**

```bash
git add claude_mnemos/cli_project.py claude_mnemos/daemon/routes/projects.py tests/test_cli_project.py tests/daemon/test_routes_projects.py && git commit -m "feat(projects): CLI/REST plumbing for display_name field

mnemos project add|update|show — new --display-name flag.
POST/PATCH /projects — accept display_name in body.
GET /projects[/{name}] — return display_name (null if not set).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: /fs router skeleton + GET /fs/home

**Files:**
- Create: `claude_mnemos/daemon/routes/fs.py`
- Modify: `claude_mnemos/daemon/app.py` (mount router)
- Create: `tests/daemon/routes/test_fs.py`

- [ ] **Step 1: Write failing test**

Create `tests/daemon/routes/test_fs.py`:
```python
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from claude_mnemos.daemon.app import create_app
from claude_mnemos.daemon.config import DaemonConfig
from claude_mnemos.daemon.process import MnemosDaemon


def _client() -> TestClient:
    return TestClient(MnemosDaemon(DaemonConfig(boot_filter=None)).app)


def test_get_fs_home_returns_absolute_path() -> None:
    resp = _client().get("/fs/home")
    assert resp.status_code == 200
    body = resp.json()
    assert "home" in body
    assert os.path.isabs(body["home"])


def test_get_fs_home_returns_user_home() -> None:
    """Should mirror os.path.expanduser('~')."""
    resp = _client().get("/fs/home")
    assert resp.status_code == 200
    expected = os.path.expanduser("~")
    assert Path(resp.json()["home"]) == Path(expected)
```

- [ ] **Step 2: Run failing test**

```bash
python -m pytest tests/daemon/routes/test_fs.py -v 2>&1 | tail -10
```

Expected: 404 (no router registered).

- [ ] **Step 3: Create fs router**

Create `claude_mnemos/daemon/routes/fs.py`:
```python
"""Filesystem browsing endpoints — used by frontend DirectoryPicker.

Daemon binds 127.0.0.1 by default, so these endpoints are local-only;
no path-traversal hardening beyond input validation. List/create directories
on behalf of the user — they already control the machine.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/fs", tags=["fs"])

LIST_LIMIT = 100


@router.get("/home")
def get_home() -> dict[str, str]:
    return {"home": os.path.expanduser("~")}
```

- [ ] **Step 4: Mount router in app.py**

In `claude_mnemos/daemon/app.py`, find existing `app.include_router(...)` calls and add:
```python
from claude_mnemos.daemon.routes import fs as fs_routes
app.include_router(fs_routes.router)
```

(Match existing pattern.)

- [ ] **Step 5: Run tests — must pass**

```bash
python -m pytest tests/daemon/routes/test_fs.py -v 2>&1 | tail -10
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/fs.py claude_mnemos/daemon/app.py tests/daemon/routes/test_fs.py && git commit -m "feat(fs): /fs router skeleton + GET /fs/home

First endpoint of three. Returns os.path.expanduser('~') as default
starting point for DirectoryPicker.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: GET /fs/browse implementation

**Files:**
- Modify: `claude_mnemos/daemon/routes/fs.py`
- Modify: `tests/daemon/routes/test_fs.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/daemon/routes/test_fs.py`:
```python
def test_get_fs_browse_lists_directories(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "file.txt").write_text("hello")  # files filtered out

    resp = _client().get(f"/fs/browse?path={tmp_path}")
    assert resp.status_code == 200
    body = resp.json()
    assert Path(body["cwd"]) == tmp_path.resolve()
    names = [e["name"] for e in body["entries"]]
    assert names == ["alpha", "beta"]
    assert body["truncated"] is False


def test_get_fs_browse_parent_returns_parent_path(tmp_path: Path) -> None:
    sub = tmp_path / "child"
    sub.mkdir()
    resp = _client().get(f"/fs/browse?path={sub}")
    assert resp.status_code == 200
    assert Path(resp.json()["parent"]) == tmp_path.resolve()


def test_get_fs_browse_returns_400_for_relative_path() -> None:
    resp = _client().get("/fs/browse?path=relative/path")
    assert resp.status_code == 400
    assert "absolute" in resp.json()["detail"].lower()


def test_get_fs_browse_returns_400_for_missing_path(tmp_path: Path) -> None:
    resp = _client().get(f"/fs/browse?path={tmp_path / 'nonexistent'}")
    assert resp.status_code == 400


def test_get_fs_browse_returns_400_for_file_path(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi")
    resp = _client().get(f"/fs/browse?path={f}")
    assert resp.status_code == 400
    assert "directory" in resp.json()["detail"].lower()


def test_get_fs_browse_truncates_at_limit(tmp_path: Path) -> None:
    """Folders >100 — truncated=true, entries capped at 100."""
    for i in range(105):
        (tmp_path / f"d{i:03d}").mkdir()
    resp = _client().get(f"/fs/browse?path={tmp_path}")
    body = resp.json()
    assert len(body["entries"]) == 100
    assert body["truncated"] is True


def test_get_fs_browse_sorts_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "Beta").mkdir()
    (tmp_path / "alpha").mkdir()
    resp = _client().get(f"/fs/browse?path={tmp_path}")
    names = [e["name"] for e in resp.json()["entries"]]
    assert names == ["alpha", "Beta"]
```

- [ ] **Step 2: Run failing tests**

```bash
python -m pytest tests/daemon/routes/test_fs.py -v 2>&1 | tail -15
```

Expected: 404 for /fs/browse.

- [ ] **Step 3: Implement /fs/browse**

In `claude_mnemos/daemon/routes/fs.py`, add:
```python
@router.get("/browse")
def browse(path: str) -> dict[str, object]:
    p = Path(path)
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="path must be absolute")
    try:
        resolved = p.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"path does not exist: {exc}") from exc
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")

    try:
        children = [c for c in resolved.iterdir() if c.is_dir()]
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail=f"permission denied: {exc}"
        ) from exc

    children.sort(key=lambda c: c.name.casefold())
    truncated = len(children) > LIST_LIMIT
    children = children[:LIST_LIMIT]

    parent_path = resolved.parent
    parent_str = str(parent_path) if parent_path != resolved else None

    return {
        "cwd": str(resolved),
        "parent": parent_str,
        "entries": [{"name": c.name, "path": str(c)} for c in children],
        "truncated": truncated,
    }
```

- [ ] **Step 4: Run tests — must pass**

```bash
python -m pytest tests/daemon/routes/test_fs.py -v 2>&1 | tail -15
```

Expected: `9 passed` (2 home + 7 browse).

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/fs.py tests/daemon/routes/test_fs.py && git commit -m "feat(fs): GET /fs/browse — list subdirectories with truncation

path validation: must be absolute + exist + be a directory. Returns
sorted (case-insensitive) list of subdirs, capped at 100, truncated
flag if more. parent=null at drive root. PermissionError → 403.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: POST /fs/mkdir implementation

**Files:**
- Modify: `claude_mnemos/daemon/routes/fs.py`
- Modify: `tests/daemon/routes/test_fs.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/daemon/routes/test_fs.py`:
```python
def test_post_fs_mkdir_creates_directory(tmp_path: Path) -> None:
    target = tmp_path / "new_folder"
    resp = _client().post("/fs/mkdir", json={"path": str(target)})
    assert resp.status_code == 200
    assert Path(resp.json()["path"]) == target.resolve()
    assert target.is_dir()


def test_post_fs_mkdir_returns_400_when_target_exists(tmp_path: Path) -> None:
    target = tmp_path / "exists"
    target.mkdir()
    resp = _client().post("/fs/mkdir", json={"path": str(target)})
    assert resp.status_code == 400
    assert "exists" in resp.json()["detail"].lower()


def test_post_fs_mkdir_returns_400_when_parent_missing(tmp_path: Path) -> None:
    target = tmp_path / "parent" / "child"  # parent doesn't exist
    resp = _client().post("/fs/mkdir", json={"path": str(target)})
    assert resp.status_code == 400
    assert "parent" in resp.json()["detail"].lower()


def test_post_fs_mkdir_returns_400_for_relative_path() -> None:
    resp = _client().post("/fs/mkdir", json={"path": "relative/here"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run failing tests**

```bash
python -m pytest tests/daemon/routes/test_fs.py -v 2>&1 | tail -10
```

Expected: 404.

- [ ] **Step 3: Implement POST /fs/mkdir**

In `claude_mnemos/daemon/routes/fs.py`, add:
```python
from pydantic import BaseModel


class MkdirRequest(BaseModel):
    path: str


@router.post("/mkdir")
def mkdir(req: MkdirRequest) -> dict[str, str]:
    p = Path(req.path)
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="path must be absolute")
    if p.exists():
        raise HTTPException(status_code=400, detail=f"path already exists: {p}")
    if not p.parent.exists():
        raise HTTPException(
            status_code=400, detail=f"parent directory does not exist: {p.parent}"
        )
    try:
        p.mkdir(parents=False, exist_ok=False)
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail=f"permission denied: {exc}"
        ) from exc
    return {"path": str(p.resolve())}
```

- [ ] **Step 4: Run tests — must pass**

```bash
python -m pytest tests/daemon/routes/test_fs.py -v 2>&1 | tail -15
```

Expected: `13 passed` (2 home + 7 browse + 4 mkdir).

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/daemon/routes/fs.py tests/daemon/routes/test_fs.py && git commit -m "feat(fs): POST /fs/mkdir — create new folder

Validates absolute path, parent exists, target doesn't. Returns
resolved absolute path on success. PermissionError → 403.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Phase 1 verification + cleanup

- [ ] **Step 1: Full backend tests**

```bash
cd /d/code/claude-mnemos && python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: `1477 passed, 3 skipped` (1465 baseline + 6 display_name + 2 CLI + 2 + 7 + 4 fs = 21 new ≈ 1486; allow ±5 variance — exact count depends on pre-existing tests around projects routes that may have grown).

- [ ] **Step 2: ruff**

```bash
python -m ruff check . 2>&1 | tail -3
```

Expected: `All checks passed!`. If errors, fix and amend the relevant commit (or new chore commit).

- [ ] **Step 3: Zero-diff check (untouchable files)**

```bash
git diff main -- claude_mnemos/ingest/ claude_mnemos/state/manifest.py claude_mnemos/core/metrics.py claude_mnemos/hooks/ claude_mnemos/state/jobs.py claude_mnemos/daemon/jobs/ claude_mnemos/state/settings.py 2>&1 | wc -l
```

Expected: `0`.

If non-zero, STOP — investigate; Phase 1 should not touch these files.

---

# Phase 2 — Frontend slugify + Onboarding two-field

**Goal:** Add `@sindresorhus/slugify` dep + `slugify()` lib + rewrite Onboarding form with two linked fields (display_name with auto-derived slug). Behaviour change: form layout. No CLI/backend changes.

---

## Task 7: Add @sindresorhus/slugify + slugify lib

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/lib/slugify.ts`
- Create: `frontend/src/__tests__/lib-slugify.test.ts`

- [ ] **Step 1: Add dep**

```bash
cd /d/code/claude-mnemos/frontend && pnpm add @sindresorhus/slugify
```

Verify in `package.json`: `@sindresorhus/slugify` listed in `dependencies`.

- [ ] **Step 2: Write failing tests**

Create `frontend/src/__tests__/lib-slugify.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { deriveSlug } from "../lib/slugify";

describe("deriveSlug", () => {
  it("returns empty string for empty input", () => {
    expect(deriveSlug("")).toBe("");
  });

  it("lowercases ASCII letters", () => {
    expect(deriveSlug("My Project")).toBe("my-project");
  });

  it("transliterates Cyrillic", () => {
    const slug = deriveSlug("Конструктор сайтов");
    // exact form depends on @sindresorhus/slugify rules; assert shape:
    expect(slug).toMatch(/^[a-z0-9][a-z0-9-]+$/);
    expect(slug.length).toBeGreaterThan(5);
    expect(slug.length).toBeLessThan(30);
  });

  it("strips special characters", () => {
    expect(deriveSlug("Hello! World?")).toBe("hello-world");
  });

  it("preserves numbers", () => {
    expect(deriveSlug("Project 2025")).toBe("project-2025");
  });

  it("truncates to 64 characters", () => {
    const long = "a".repeat(200);
    const result = deriveSlug(long);
    expect(result.length).toBeLessThanOrEqual(64);
  });

  it("output matches PROJECT_NAME_PATTERN", () => {
    const pattern = /^[a-z0-9][a-z0-9_-]{0,63}$/;
    const inputs = [
      "Hello World",
      "Конструктор сайтов",
      "Test-Project_2025",
      "12345",
    ];
    for (const inp of inputs) {
      const slug = deriveSlug(inp);
      if (slug) {
        expect(slug).toMatch(pattern);
      }
    }
  });

  it("handles leading-digit slugs", () => {
    const slug = deriveSlug("123-test");
    expect(slug).toMatch(/^[a-z0-9]/);
  });

  it("strips leading non-[a-z0-9] safely", () => {
    // unidecode might give a slug starting with `-`; normaliser must fix it
    const slug = deriveSlug("---hello");
    if (slug) {
      expect(slug).toMatch(/^[a-z0-9]/);
    }
  });
});
```

- [ ] **Step 3: Run failing tests**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/lib-slugify.test.ts 2>&1 | tail -10
```

Expected: import error.

- [ ] **Step 4: Implement lib**

Create `frontend/src/lib/slugify.ts`:
```typescript
import slugifyLib from "@sindresorhus/slugify";

const MAX_LEN = 64;

/**
 * Derive a project slug from a display name.
 *
 * Output matches the backend PROJECT_NAME_PATTERN: ^[a-z0-9][a-z0-9_-]{0,63}$
 *
 * - empty input → empty output
 * - transliterates Unicode (Cyrillic etc.) via @sindresorhus/slugify
 * - normalises to lowercase, "-" separator
 * - truncates to 64 chars
 * - if result doesn't start with [a-z0-9], strips leading separator chars
 */
export function deriveSlug(input: string): string {
  if (!input.trim()) return "";
  let slug = slugifyLib(input, { lowercase: true, separator: "-" });
  // Strip leading non-alphanumeric (rare edge case).
  slug = slug.replace(/^[^a-z0-9]+/, "");
  // Truncate, then strip trailing "-" again (might be left after cut).
  slug = slug.slice(0, MAX_LEN).replace(/[-_]+$/, "");
  return slug;
}
```

- [ ] **Step 5: Run tests — must pass**

```bash
pnpm test --run src/__tests__/lib-slugify.test.ts 2>&1 | tail -10
```

Expected: `9 passed`.

- [ ] **Step 6: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/lib/slugify.ts frontend/src/__tests__/lib-slugify.test.ts && git commit -m "feat(frontend): deriveSlug() — UTF-8 display name → ASCII slug

Wraps @sindresorhus/slugify with normalisation to match backend
PROJECT_NAME_PATTERN. Handles empty input, Cyrillic, special chars,
leading-digit, and 64-char truncation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Rewrite Onboarding form with display_name + slug

**Files:**
- Modify: `frontend/src/pages/Onboarding.tsx`
- Modify: `frontend/src/__tests__/Onboarding.test.tsx`
- Modify: `frontend/public/locales/{en,ru,uk}.json`
- Modify: `frontend/src/types/Project.ts` (if exists; else where ProjectMapEntry zod lives)

- [ ] **Step 1: Locate Project zod schema**

```bash
grep -rn "ProjectMapEntry\|name:.*z\.string\|cwd_patterns:.*z\." /d/code/claude-mnemos/frontend/src/types/ | head -10
```

Find the file (e.g. `frontend/src/types/Project.ts` or `frontend/src/types/Projects.ts`).

- [ ] **Step 2: Add display_name to project schema**

In the schema file, add field:
```typescript
export const ProjectMapEntrySchema = z.object({
  name: z.string(),
  display_name: z.string().nullable().default(null),
  vault_root: z.string(),
  cwd_patterns: z.array(z.string()).default([]),
});
```

(Adapt to existing import pattern.)

- [ ] **Step 3: Update useProjectCreate hook to send display_name**

```bash
grep -n "useProjectCreate\|name:\|vault_root:" /d/code/claude-mnemos/frontend/src/hooks/useProjectCreate.ts
```

Find the body type / mutation function. Add `display_name: string | null` to the request body type. Pass it through.

- [ ] **Step 4: Add locale keys**

Edit `frontend/public/locales/en.json` `onboarding` block:
```json
"display_name_label": "Display name",
"display_name_hint": "Name shown in the dashboard. Any characters allowed.",
"slug_label": "Slug (technical)",
"slug_hint": "Used in URLs and folder names. Auto-derived from display name.",
"slug_edit": "Edit slug",
"slug_lock": "Auto",
"slug_invalid": "Invalid slug. Use a-z, 0-9, _, - only; must start with a letter or digit.",
```

`ru.json`:
```json
"display_name_label": "Название проекта",
"display_name_hint": "Имя, которое будет видно в дашборде. Можно любые символы.",
"slug_label": "Slug (технический)",
"slug_hint": "Используется в URL и путях файлов. Подставляется автоматически.",
"slug_edit": "Изменить slug",
"slug_lock": "Авто",
"slug_invalid": "Некорректный slug. Только a-z, 0-9, _, -; начинается с буквы или цифры.",
```

`uk.json`:
```json
"display_name_label": "Назва проекту",
"display_name_hint": "Ім'я, що буде показано в дашборді. Будь-які символи.",
"slug_label": "Slug (технічний)",
"slug_hint": "Використовується в URL і шляхах файлів. Підставляється автоматично.",
"slug_edit": "Редагувати slug",
"slug_lock": "Авто",
"slug_invalid": "Некоректний slug. Лише a-z, 0-9, _, -; починається з літери або цифри.",
```

- [ ] **Step 5: Write failing tests**

Add to `frontend/src/__tests__/Onboarding.test.tsx` (use existing harness — wrap helper, MockAdapter etc.):

```typescript
  it("auto-derives slug from display_name input", async () => {
    renderOnboarding();
    const displayInput = screen.getByLabelText(/Display name|Название/i);
    await userEvent.type(displayInput, "Конструктор сайтов");
    const slugInput = screen.getByLabelText(/Slug/i);
    expect((slugInput as HTMLInputElement).value).toMatch(/^[a-z0-9][a-z0-9-]+$/);
  });

  it("locks slug auto-derive when user clicks Edit slug", async () => {
    renderOnboarding();
    const displayInput = screen.getByLabelText(/Display name|Название/i);
    await userEvent.type(displayInput, "Test");
    const slugInput = screen.getByLabelText(/Slug/i) as HTMLInputElement;
    expect(slugInput.value).toBe("test");

    const editBtn = screen.getByRole("button", { name: /Edit slug|Изменить/i });
    await userEvent.click(editBtn);
    await userEvent.clear(slugInput);
    await userEvent.type(slugInput, "custom-slug");
    expect(slugInput.value).toBe("custom-slug");

    // Subsequent typing in display does NOT change slug
    await userEvent.type(displayInput, " More");
    expect(slugInput.value).toBe("custom-slug");
  });

  it("submits display_name + slug + vault_root to /projects", async () => {
    // mock POST /projects
    apiMock.onPost("/projects").reply((config) => {
      const body = JSON.parse(config.data as string);
      expect(body.display_name).toBe("My Project");
      expect(body.name).toBe("my-project");
      expect(body.vault_root).toBe("/tmp/x");
      return [200, { name: "my-project", display_name: "My Project", vault_root: "/tmp/x", cwd_patterns: [] }];
    });

    renderOnboarding();
    await userEvent.type(screen.getByLabelText(/Display name|Название/i), "My Project");
    await userEvent.type(screen.getByLabelText(/vault|Path to vault/i), "/tmp/x");
    await userEvent.click(screen.getByRole("button", { name: /Create|Создать/i }));

    await waitFor(() => {
      expect(apiMock.history.post.find((c) => c.url === "/projects")).toBeTruthy();
    });
  });
```

- [ ] **Step 6: Run failing tests**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/Onboarding.test.tsx 2>&1 | tail -10
```

Expected: assertions about slug auto-derive fail (current form has single `name` field).

- [ ] **Step 7: Rewrite Onboarding form**

Replace `frontend/src/pages/Onboarding.tsx` with two-field design (preserve existing tray/CLI sections; only the name section changes):

```tsx
import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router";
import { useTranslation } from "react-i18next";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { useProjectCreate } from "@/hooks/useProjectCreate";
import { getTrayStatus, installTray } from "@/api/tray.api";
import type { TrayStatus } from "@/types/Tray";
import { getClaudeCliAuth } from "@/api/claudeCli.api";
import type { ClaudeCliAuth } from "@/types/ClaudeCliAuth";
import { deriveSlug } from "@/lib/slugify";

const SLUG_REGEX = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export function Onboarding() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useProjectCreate();

  const [displayName, setDisplayName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugLocked, setSlugLocked] = useState(false);
  const [vault, setVault] = useState("");
  const [cwd, setCwd] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [nameTakenError, setNameTakenError] = useState(false);
  const [mountFailedDetail, setMountFailedDetail] = useState<string | null>(null);
  const [trayStatus, setTrayStatus] = useState<TrayStatus | null>(null);
  const [autostartChecked, setAutostartChecked] = useState<boolean>(true);
  const [cliAuth, setCliAuth] = useState<ClaudeCliAuth | null>(null);

  useEffect(() => {
    getTrayStatus().then(setTrayStatus).catch(() => setTrayStatus(null));
  }, []);
  useEffect(() => {
    getClaudeCliAuth().then(setCliAuth).catch(() => setCliAuth(null));
  }, []);

  // Auto-derive slug from display name unless user has unlocked it.
  useEffect(() => {
    if (!slugLocked) {
      setSlug(deriveSlug(displayName));
    }
  }, [displayName, slugLocked]);

  const slugValid = SLUG_REGEX.test(slug);
  const vaultValid = vault.trim().length > 0;
  const canSubmit = slugValid && vaultValid && displayName.trim().length > 0 && !create.isPending;
  const showSlugInvalid = slug.length > 0 && !slugValid;

  const submit = () => {
    setNameTakenError(false);
    setMountFailedDetail(null);
    const cwd_patterns = cwd
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    create.mutate(
      {
        name: slug,
        display_name: displayName.trim() || null,
        vault_root: vault.trim(),
        cwd_patterns,
      },
      {
        onSuccess: (entry) => {
          if (
            autostartChecked &&
            trayStatus &&
            (trayStatus.platform === "windows" || trayStatus.platform === "macos")
          ) {
            installTray().catch(() => {});
          }
          navigate(`/project/${encodeURIComponent(entry.name)}`);
        },
        onError: (err) => {
          if (axios.isAxiosError(err)) {
            const status = err.response?.status;
            if (status === 409) setNameTakenError(true);
            else if (status === 500) {
              const detail = err.response?.data?.detail;
              setMountFailedDetail(typeof detail === "string" ? detail : err.message);
            }
          }
        },
      },
    );
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold">{t("onboarding.title")}</h1>
        <p className="mt-1 text-sm text-[hsl(var(--muted-foreground))]">{t("onboarding.subtitle")}</p>
      </div>

      <div className="space-y-2">
        <label htmlFor="onb-display" className="text-sm font-medium">{t("onboarding.display_name_label")}</label>
        <input
          id="onb-display"
          type="text"
          value={displayName}
          onChange={(e) => { setDisplayName(e.target.value); setNameTakenError(false); }}
          disabled={create.isPending}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
        />
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.display_name_hint")}</p>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label htmlFor="onb-slug" className="text-sm font-medium">{t("onboarding.slug_label")}</label>
          {!slugLocked ? (
            <button
              type="button"
              className="text-xs text-[hsl(var(--primary))] underline"
              onClick={() => setSlugLocked(true)}
            >
              {t("onboarding.slug_edit")}
            </button>
          ) : (
            <span className="text-xs text-[hsl(var(--muted-foreground))]">
              <button
                type="button"
                className="underline"
                onClick={() => { setSlugLocked(false); setSlug(deriveSlug(displayName)); }}
              >
                {t("onboarding.slug_lock")}
              </button>
            </span>
          )}
        </div>
        <input
          id="onb-slug"
          type="text"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          disabled={!slugLocked || create.isPending}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono disabled:opacity-60"
        />
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.slug_hint")}</p>
        {showSlugInvalid && (
          <p className="text-xs text-red-700 dark:text-red-400">{t("onboarding.slug_invalid")}</p>
        )}
        {nameTakenError && (
          <p className="text-xs text-red-700 dark:text-red-400">{t("onboarding.name_taken")}</p>
        )}
      </div>

      <div className="space-y-2">
        <label htmlFor="onb-vault" className="text-sm font-medium">{t("onboarding.vault_label")}</label>
        <input
          id="onb-vault"
          type="text"
          value={vault}
          onChange={(e) => setVault(e.target.value)}
          disabled={create.isPending}
          className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
        />
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.vault_hint")}</p>
      </div>

      <div className="space-y-2">
        <button
          type="button"
          className="text-sm text-[hsl(var(--primary))] underline"
          onClick={() => setAdvancedOpen(!advancedOpen)}
        >
          {t("onboarding.advanced_toggle")}
        </button>
        {advancedOpen && (
          <div className="space-y-1 rounded-md border bg-[hsl(var(--muted))] p-3">
            <label htmlFor="onb-cwd" className="text-sm font-medium">{t("onboarding.cwd_label")}</label>
            <textarea
              id="onb-cwd"
              value={cwd}
              onChange={(e) => setCwd(e.target.value)}
              disabled={create.isPending}
              rows={3}
              className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
            />
            <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.cwd_hint")}</p>
          </div>
        )}
      </div>

      {mountFailedDetail && (
        <div className="rounded-md border-2 border-red-600 bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          <div className="font-semibold">{t("onboarding.mount_failed_title")}</div>
          <div className="mt-1 break-all font-mono text-xs">{mountFailedDetail}</div>
        </div>
      )}

      {trayStatus && (trayStatus.platform === "windows" || trayStatus.platform === "macos") && (
        <div className="mt-4">
          <label className="inline-flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={autostartChecked}
              onChange={(e) => setAutostartChecked(e.target.checked)}
            />
            {t("onboarding.autostart_label")}
          </label>
          <p className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">
            {t("onboarding.autostart_hint")}
          </p>
        </div>
      )}

      {cliAuth && (
        <div className="mt-4 rounded-md border bg-[hsl(var(--background))] p-3 text-sm">
          <div className="font-medium">{t("onboarding.cli_check_label")}</div>
          <div className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">
            {cliAuth.installed && cliAuth.authenticated
              ? t("onboarding.cli_check_ok")
              : !cliAuth.installed
              ? t("onboarding.cli_check_not_installed")
              : t("onboarding.cli_check_not_authenticated")}
          </div>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button onClick={submit} disabled={!canSubmit}>
          {create.isPending ? t("confirm.working") : t("onboarding.submit")}
        </Button>
        <Button asChild variant="outline">
          <Link to="/">{t("onboarding.cancel")}</Link>
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Update i18n test resources**

If the existing Onboarding test file uses `i18n.addResourceBundle(...)` to seed locale keys for tests, add the new keys (`display_name_label`, `slug_label`, etc.) to that resource bundle.

- [ ] **Step 9: Run tests — must pass**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/Onboarding.test.tsx 2>&1 | tail -10
```

Expected: all pass. tsc/eslint clean.

- [ ] **Step 10: Run full Vitest**

```bash
pnpm test --run 2>&1 | tail -5
```

Expected: ~205 passed (196 baseline + 9 slugify + 3 onboarding).

- [ ] **Step 11: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/ && git commit -m "feat(frontend): Onboarding form with display_name + auto-derived slug

Two linked fields: display name (any chars) drives slug auto-derivation
via deriveSlug(). User can click 'Edit slug' to unlock manual mode.
Submit body now includes display_name field. New locale keys for
en/ru/uk.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Phase 2 verification

- [ ] **Step 1: Backend + frontend tests + lint**

```bash
cd /d/code/claude-mnemos && python -m pytest --ignore=tests/slow 2>&1 | tail -3
python -m ruff check . 2>&1 | tail -3
cd frontend && pnpm test --run 2>&1 | tail -5
pnpm tsc --noEmit 2>&1 | tail -3
pnpm lint 2>&1 | tail -5
```

Expected: all green; backend ~1486, frontend ~205. Pre-existing button.tsx eslint warning OK; otherwise clean.

- [ ] **Step 2: Zero-diff (same files as before, plus settings.py)**

```bash
cd /d/code/claude-mnemos && git diff main -- claude_mnemos/ingest/ claude_mnemos/state/manifest.py claude_mnemos/core/metrics.py claude_mnemos/hooks/ claude_mnemos/state/jobs.py claude_mnemos/daemon/jobs/ claude_mnemos/state/settings.py | wc -l
```

Expected: `0`.

---

# Phase 3 — DirectoryPicker modal

**Goal:** Reusable `<DirectoryPicker>` component used by Onboarding (Phase 4) and Settings (Plan B). Composes browse, breadcrumbs, path input, filter, recent, new folder.

---

## Task 10: Frontend types + api/fs.api.ts

**Files:**
- Create: `frontend/src/types/Fs.ts`
- Create: `frontend/src/api/fs.api.ts`
- Create: `frontend/src/__tests__/api-fs.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/api-fs.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from "vitest";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { browseDirectory, mkdir, getHome } from "../api/fs.api";

let mock: MockAdapter;

beforeEach(() => {
  mock = new MockAdapter(axios);
});

describe("fs API", () => {
  it("getHome returns absolute path", async () => {
    mock.onGet("/fs/home").reply(200, { home: "C:\\Users\\test" });
    const result = await getHome();
    expect(result.home).toBe("C:\\Users\\test");
  });

  it("browseDirectory returns entries + parent", async () => {
    mock.onGet(/\/fs\/browse/).reply(200, {
      cwd: "C:\\code",
      parent: "C:\\",
      entries: [
        { name: "claude-mnemos", path: "C:\\code\\claude-mnemos" },
        { name: "test", path: "C:\\code\\test" },
      ],
      truncated: false,
    });
    const result = await browseDirectory("C:\\code");
    expect(result.entries).toHaveLength(2);
    expect(result.parent).toBe("C:\\");
    expect(result.truncated).toBe(false);
  });

  it("browseDirectory passes path as query param", async () => {
    mock.onGet(/\/fs\/browse/).reply((config) => {
      expect(config.params).toEqual({ path: "/tmp/x" });
      return [200, { cwd: "/tmp/x", parent: "/tmp", entries: [], truncated: false }];
    });
    await browseDirectory("/tmp/x");
  });

  it("mkdir POSTs path and returns resolved path", async () => {
    mock.onPost("/fs/mkdir").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({ path: "/tmp/new" });
      return [200, { path: "/tmp/new" }];
    });
    const result = await mkdir("/tmp/new");
    expect(result.path).toBe("/tmp/new");
  });

  it("browseDirectory schema permissive — truncated defaults to false", async () => {
    mock.onGet(/\/fs\/browse/).reply(200, {
      cwd: "/tmp",
      parent: null,
      entries: [],
    });
    const result = await browseDirectory("/tmp");
    expect(result.truncated).toBe(false);
    expect(result.parent).toBeNull();
  });
});
```

- [ ] **Step 2: Run failing tests**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/api-fs.test.ts 2>&1 | tail -10
```

Expected: import errors.

- [ ] **Step 3: Implement types**

Create `frontend/src/types/Fs.ts`:
```typescript
import { z } from "zod";

export const FsHomeSchema = z.object({
  home: z.string(),
});
export type FsHome = z.infer<typeof FsHomeSchema>;

export const FsEntrySchema = z.object({
  name: z.string(),
  path: z.string(),
});
export type FsEntry = z.infer<typeof FsEntrySchema>;

export const FsBrowseSchema = z.object({
  cwd: z.string(),
  parent: z.string().nullable(),
  entries: z.array(FsEntrySchema),
  truncated: z.boolean().default(false),
});
export type FsBrowse = z.infer<typeof FsBrowseSchema>;

export const FsMkdirResponseSchema = z.object({
  path: z.string(),
});
export type FsMkdirResponse = z.infer<typeof FsMkdirResponseSchema>;
```

- [ ] **Step 4: Implement api**

Create `frontend/src/api/fs.api.ts`:
```typescript
import axios from "axios";
import {
  FsBrowseSchema,
  FsHomeSchema,
  FsMkdirResponseSchema,
  type FsBrowse,
  type FsHome,
  type FsMkdirResponse,
} from "@/types/Fs";

export async function getHome(): Promise<FsHome> {
  const { data } = await axios.get("/fs/home");
  return FsHomeSchema.parse(data);
}

export async function browseDirectory(path: string): Promise<FsBrowse> {
  const { data } = await axios.get("/fs/browse", { params: { path } });
  return FsBrowseSchema.parse(data);
}

export async function mkdir(path: string): Promise<FsMkdirResponse> {
  const { data } = await axios.post("/fs/mkdir", { path });
  return FsMkdirResponseSchema.parse(data);
}
```

- [ ] **Step 5: Run tests**

```bash
pnpm test --run src/__tests__/api-fs.test.ts 2>&1 | tail -10
```

Expected: `5 passed`.

- [ ] **Step 6: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/types/Fs.ts frontend/src/api/fs.api.ts frontend/src/__tests__/api-fs.test.ts && git commit -m "feat(frontend): fs API client + zod schemas

getHome / browseDirectory / mkdir wrappers for /fs endpoints. Permissive
parsing (truncated defaults to false).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: useRecentPaths hook

**Files:**
- Create: `frontend/src/hooks/useRecentPaths.ts`
- Create: `frontend/src/__tests__/useRecentPaths.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/useRecentPaths.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useRecentPaths } from "../hooks/useRecentPaths";

beforeEach(() => {
  localStorage.clear();
});

describe("useRecentPaths", () => {
  it("starts empty", () => {
    const { result } = renderHook(() => useRecentPaths());
    expect(result.current.recent).toEqual([]);
  });

  it("adds path to head", () => {
    const { result } = renderHook(() => useRecentPaths());
    act(() => result.current.addRecent("/tmp/a"));
    expect(result.current.recent).toEqual(["/tmp/a"]);
  });

  it("dedupes and moves to head on re-add", () => {
    const { result } = renderHook(() => useRecentPaths());
    act(() => result.current.addRecent("/tmp/a"));
    act(() => result.current.addRecent("/tmp/b"));
    act(() => result.current.addRecent("/tmp/a"));
    expect(result.current.recent).toEqual(["/tmp/a", "/tmp/b"]);
  });

  it("caps at 5 entries", () => {
    const { result } = renderHook(() => useRecentPaths());
    for (let i = 0; i < 7; i++) {
      act(() => result.current.addRecent(`/tmp/${i}`));
    }
    expect(result.current.recent).toHaveLength(5);
    expect(result.current.recent[0]).toBe("/tmp/6");
  });

  it("persists across hook instances via localStorage", () => {
    const { result: r1 } = renderHook(() => useRecentPaths());
    act(() => r1.current.addRecent("/tmp/x"));
    const { result: r2 } = renderHook(() => useRecentPaths());
    expect(r2.current.recent).toEqual(["/tmp/x"]);
  });
});
```

- [ ] **Step 2: Run failing tests**

```bash
pnpm test --run src/__tests__/useRecentPaths.test.ts 2>&1 | tail -10
```

Expected: import error.

- [ ] **Step 3: Implement hook**

Create `frontend/src/hooks/useRecentPaths.ts`:
```typescript
import { useCallback, useEffect, useState } from "react";

const KEY = "mnemos_recent_paths";
const MAX = 5;

function readStorage(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function writeStorage(paths: string[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(paths));
  } catch {
    // localStorage may be unavailable in private mode; silently ignore.
  }
}

export function useRecentPaths(): {
  recent: string[];
  addRecent: (path: string) => void;
} {
  const [recent, setRecent] = useState<string[]>(() => readStorage());

  const addRecent = useCallback((path: string) => {
    setRecent((prev) => {
      const dedup = prev.filter((p) => p !== path);
      const next = [path, ...dedup].slice(0, MAX);
      writeStorage(next);
      return next;
    });
  }, []);

  // Sync with other hook instances on the same page.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY) setRecent(readStorage());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return { recent, addRecent };
}
```

- [ ] **Step 4: Run tests — must pass**

```bash
pnpm test --run src/__tests__/useRecentPaths.test.ts 2>&1 | tail -10
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/hooks/useRecentPaths.ts frontend/src/__tests__/useRecentPaths.test.ts && git commit -m "feat(frontend): useRecentPaths hook (localStorage CRUD)

Stores up to 5 most-recent paths for DirectoryPicker. Dedup + LRU
ordering. Survives reload via localStorage.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: DirectoryPicker modal — full implementation

**Files:**
- Create: `frontend/src/components/picker/DirectoryPicker.tsx`
- Create: `frontend/src/__tests__/DirectoryPicker.test.tsx`

This is a single-file component containing everything (subcomponents inlined as functions). For design simplicity in Phase 3 — split into multiple files only if exceeds ~300 LOC.

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/DirectoryPicker.test.tsx`:
```typescript
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { DirectoryPicker } from "../components/picker/DirectoryPicker";

let mock: MockAdapter;

beforeEach(() => {
  mock = new MockAdapter(axios);
  localStorage.clear();
});

const TEST_HOME = "C:\\Users\\test";

function setupMock() {
  mock.onGet("/fs/home").reply(200, { home: TEST_HOME });
  mock.onGet(/\/fs\/browse/).reply((config) => {
    const path = (config.params as { path: string }).path;
    if (path === TEST_HOME) {
      return [
        200,
        {
          cwd: TEST_HOME,
          parent: "C:\\Users",
          entries: [
            { name: "code", path: `${TEST_HOME}\\code` },
            { name: "Documents", path: `${TEST_HOME}\\Documents` },
          ],
          truncated: false,
        },
      ];
    }
    if (path === `${TEST_HOME}\\code`) {
      return [
        200,
        {
          cwd: `${TEST_HOME}\\code`,
          parent: TEST_HOME,
          entries: [
            { name: "claude-mnemos", path: `${TEST_HOME}\\code\\claude-mnemos` },
          ],
          truncated: false,
        },
      ];
    }
    return [400, { detail: "path does not exist" }];
  });
}

describe("DirectoryPicker", () => {
  it("opens at home and lists entries", async () => {
    setupMock();
    const onSelect = vi.fn();
    render(<DirectoryPicker open onSelect={onSelect} onClose={() => {}} />);
    expect(await screen.findByText("code")).toBeInTheDocument();
    expect(screen.getByText("Documents")).toBeInTheDocument();
  });

  it("navigates into folder on click", async () => {
    setupMock();
    render(<DirectoryPicker open onSelect={() => {}} onClose={() => {}} />);
    const codeFolder = await screen.findByText("code");
    await userEvent.click(codeFolder);
    expect(await screen.findByText("claude-mnemos")).toBeInTheDocument();
  });

  it("calls onSelect with current cwd when Select clicked", async () => {
    setupMock();
    const onSelect = vi.fn();
    render(<DirectoryPicker open onSelect={onSelect} onClose={() => {}} />);
    await screen.findByText("code");
    await userEvent.click(screen.getByRole("button", { name: /Select|Выбрать/i }));
    expect(onSelect).toHaveBeenCalledWith(TEST_HOME);
  });

  it("filters entries via FilterInput", async () => {
    setupMock();
    render(<DirectoryPicker open onSelect={() => {}} onClose={() => {}} />);
    await screen.findByText("code");
    const filter = screen.getByPlaceholderText(/Filter|Поиск|Пошук/i);
    await userEvent.type(filter, "doc");
    expect(screen.queryByText("code")).not.toBeInTheDocument();
    expect(screen.getByText("Documents")).toBeInTheDocument();
  });

  it("creates new folder via NewFolder button", async () => {
    setupMock();
    mock.onPost("/fs/mkdir").reply((config) => {
      const body = JSON.parse(config.data as string);
      expect(body.path).toBe(`${TEST_HOME}\\test_new`);
      return [200, { path: `${TEST_HOME}\\test_new` }];
    });
    render(<DirectoryPicker open onSelect={() => {}} onClose={() => {}} allowCreate />);
    await screen.findByText("code");
    await userEvent.click(screen.getByRole("button", { name: /New folder|Новая|Нова папка/i }));
    const input = await screen.findByPlaceholderText(/folder name|имя папки/i);
    await userEvent.type(input, "test_new");
    await userEvent.click(screen.getByRole("button", { name: /^Create|Создать|Створити/i }));
    await waitFor(() => {
      expect(mock.history.post.length).toBeGreaterThan(0);
    });
  });

  it("recent paths shown when present in localStorage", async () => {
    localStorage.setItem("mnemos_recent_paths", JSON.stringify(["/tmp/a", "/tmp/b"]));
    setupMock();
    render(<DirectoryPicker open onSelect={() => {}} onClose={() => {}} />);
    expect(await screen.findByText("/tmp/a")).toBeInTheDocument();
    expect(screen.getByText("/tmp/b")).toBeInTheDocument();
  });

  it("calls onClose when Cancel clicked", async () => {
    setupMock();
    const onClose = vi.fn();
    render(<DirectoryPicker open onSelect={() => {}} onClose={onClose} />);
    await screen.findByText("code");
    await userEvent.click(screen.getByRole("button", { name: /Cancel|Отмена|Скасувати/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run failing tests**

```bash
pnpm test --run src/__tests__/DirectoryPicker.test.tsx 2>&1 | tail -15
```

Expected: import error.

- [ ] **Step 3: Implement DirectoryPicker**

Create `frontend/src/components/picker/DirectoryPicker.tsx`:
```tsx
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { browseDirectory, getHome, mkdir } from "@/api/fs.api";
import type { FsBrowse } from "@/types/Fs";
import { useRecentPaths } from "@/hooks/useRecentPaths";

interface Props {
  open: boolean;
  initialPath?: string;
  allowCreate?: boolean;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export function DirectoryPicker({ open, initialPath, allowCreate, onSelect, onClose }: Props) {
  const { t } = useTranslation();
  const { recent, addRecent } = useRecentPaths();
  const [cwd, setCwd] = useState<string>(initialPath ?? "");
  const [data, setData] = useState<FsBrowse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pathInputValue, setPathInputValue] = useState<string>(initialPath ?? "");
  const [filter, setFilter] = useState("");
  const [showNewFolder, setShowNewFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");

  // Initial load: navigate to initialPath or to home.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        if (initialPath) {
          await navigateTo(initialPath);
        } else {
          const home = await getHome();
          await navigateTo(home.home);
        }
      } catch (e) {
        if (!cancelled && axios.isAxiosError(e)) {
          setError(e.response?.data?.detail ?? e.message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function navigateTo(path: string) {
    setLoading(true);
    setError(null);
    try {
      const result = await browseDirectory(path);
      setCwd(result.cwd);
      setData(result);
      setPathInputValue(result.cwd);
      setFilter("");
    } catch (e) {
      if (axios.isAxiosError(e)) {
        setError(e.response?.data?.detail ?? e.message);
      }
    } finally {
      setLoading(false);
    }
  }

  function selectCurrent() {
    if (cwd) {
      addRecent(cwd);
      onSelect(cwd);
    }
  }

  async function handleMkdir() {
    if (!newFolderName.trim()) return;
    const sep = cwd.includes("\\") ? "\\" : "/";
    const target = `${cwd}${sep}${newFolderName.trim()}`;
    try {
      await mkdir(target);
      setShowNewFolder(false);
      setNewFolderName("");
      await navigateTo(target);
    } catch (e) {
      if (axios.isAxiosError(e)) {
        setError(e.response?.data?.detail ?? e.message);
      }
    }
  }

  const breadcrumbs = useMemo(() => {
    if (!cwd) return [] as { label: string; path: string }[];
    const sep = cwd.includes("\\") ? "\\" : "/";
    const parts = cwd.split(sep).filter(Boolean);
    const acc: { label: string; path: string }[] = [];
    let running = "";
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      if (i === 0 && cwd.includes("\\")) {
        running = part;
      } else if (i === 0 && !cwd.includes("\\")) {
        running = `/${part}`;
      } else {
        running += `${sep}${part}`;
      }
      acc.push({ label: part, path: running });
    }
    return acc;
  }, [cwd]);

  const visibleEntries = useMemo(() => {
    if (!data) return [];
    if (!filter) return data.entries;
    const f = filter.toLowerCase();
    return data.entries.filter((e) => e.name.toLowerCase().includes(f));
  }, [data, filter]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-2xl rounded-md border bg-[hsl(var(--background))] p-4 shadow-lg">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{t("picker.title")}</h2>
          <button onClick={onClose} className="text-sm text-[hsl(var(--muted-foreground))]" aria-label="Close">×</button>
        </div>

        <div className="mt-3 space-y-2">
          <input
            value={pathInputValue}
            onChange={(e) => setPathInputValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") navigateTo(pathInputValue); }}
            placeholder={t("picker.path_placeholder")}
            className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
          />

          <div className="flex flex-wrap gap-1 text-xs text-[hsl(var(--muted-foreground))]">
            {breadcrumbs.map((b, i) => (
              <span key={b.path}>
                {i > 0 && " > "}
                <button
                  onClick={() => navigateTo(b.path)}
                  className="hover:underline"
                >
                  {b.label}
                </button>
              </span>
            ))}
          </div>

          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("picker.filter_placeholder")}
            className="w-full rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm"
          />
        </div>

        {recent.length > 0 && (
          <div className="mt-3 border-t pt-2">
            <div className="text-xs font-medium text-[hsl(var(--muted-foreground))]">{t("picker.recent")}</div>
            <ul className="mt-1 space-y-0.5 text-xs">
              {recent.map((p) => (
                <li key={p}>
                  <button
                    onClick={() => navigateTo(p)}
                    className="text-left font-mono hover:underline"
                  >
                    {p}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-3 max-h-64 overflow-y-auto rounded-md border">
          {loading && <div className="p-3 text-sm text-[hsl(var(--muted-foreground))]">{t("picker.loading")}</div>}
          {error && <div className="p-3 text-sm text-red-700">{error}</div>}
          {!loading && !error && visibleEntries.length === 0 && (
            <div className="p-3 text-sm text-[hsl(var(--muted-foreground))]">{t("picker.empty")}</div>
          )}
          {!loading && !error && visibleEntries.map((e) => (
            <button
              key={e.path}
              onClick={() => navigateTo(e.path)}
              className="block w-full px-3 py-2 text-left text-sm hover:bg-[hsl(var(--muted))]"
            >
              📁 {e.name}
            </button>
          ))}
          {data?.truncated && (
            <div className="p-2 text-xs text-[hsl(var(--muted-foreground))]">
              {t("picker.truncated")}
            </div>
          )}
        </div>

        {allowCreate && (
          <div className="mt-2">
            {!showNewFolder ? (
              <button
                onClick={() => setShowNewFolder(true)}
                className="text-xs text-[hsl(var(--primary))] underline"
              >
                + {t("picker.new_folder")}
              </button>
            ) : (
              <div className="flex gap-2">
                <input
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  placeholder={t("picker.folder_name")}
                  className="flex-1 rounded-md border bg-[hsl(var(--background))] px-2 py-1 text-sm font-mono"
                />
                <Button size="sm" onClick={handleMkdir}>{t("picker.create")}</Button>
                <Button size="sm" variant="outline" onClick={() => { setShowNewFolder(false); setNewFolderName(""); }}>
                  {t("picker.cancel")}
                </Button>
              </div>
            )}
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>{t("picker.cancel")}</Button>
          <Button onClick={selectCurrent}>{t("picker.select")}</Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Add locale keys**

Edit each `frontend/public/locales/{en,ru,uk}.json`. Add new top-level `picker` namespace:

`en.json`:
```json
"picker": {
  "title": "Choose folder",
  "path_placeholder": "Type or paste path",
  "filter_placeholder": "Filter folders…",
  "recent": "Recent",
  "loading": "Loading…",
  "empty": "No subfolders",
  "truncated": "Showing first 100 — refine filter to narrow",
  "new_folder": "New folder",
  "folder_name": "Folder name",
  "create": "Create",
  "cancel": "Cancel",
  "select": "Select this folder"
}
```

`ru.json`:
```json
"picker": {
  "title": "Выбрать папку",
  "path_placeholder": "Введите или вставьте путь",
  "filter_placeholder": "Поиск по имени…",
  "recent": "Недавние",
  "loading": "Загрузка…",
  "empty": "Нет подпапок",
  "truncated": "Показаны первые 100 — уточните поиском",
  "new_folder": "Новая папка",
  "folder_name": "Имя папки",
  "create": "Создать",
  "cancel": "Отмена",
  "select": "Выбрать эту папку"
}
```

`uk.json`:
```json
"picker": {
  "title": "Вибрати папку",
  "path_placeholder": "Введіть або вставте шлях",
  "filter_placeholder": "Пошук за іменем…",
  "recent": "Нещодавні",
  "loading": "Завантаження…",
  "empty": "Немає підпапок",
  "truncated": "Показані перші 100 — уточніть фільтром",
  "new_folder": "Нова папка",
  "folder_name": "Ім'я папки",
  "create": "Створити",
  "cancel": "Скасувати",
  "select": "Вибрати цю папку"
}
```

- [ ] **Step 5: Run tests — must pass**

```bash
pnpm test --run src/__tests__/DirectoryPicker.test.tsx 2>&1 | tail -15
```

Expected: `7 passed`.

- [ ] **Step 6: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/components/picker/ frontend/src/__tests__/DirectoryPicker.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): DirectoryPicker modal — browse / breadcrumbs / recent / mkdir

Single-component picker covering all design §4 features: path input,
breadcrumbs, filter, recent (localStorage), new folder dialog,
truncation indicator, error display. Reusable for Onboarding (Phase 4)
and Settings (Plan B).

7 unit tests + 12 new locale keys (en/ru/uk).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Phase 3 verification

- [ ] **Step 1: Frontend tests**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run 2>&1 | tail -5
```

Expected: ~222 passed (Phase 2's 205 + 5 fs api + 5 useRecentPaths + 7 DirectoryPicker = 17 new ≈ 222).

- [ ] **Step 2: Frontend lint + tsc**

```bash
pnpm tsc --noEmit 2>&1 | tail -3 && pnpm lint 2>&1 | tail -5
```

Expected: tsc clean; lint pre-existing button.tsx warning only.

- [ ] **Step 3: Backend unaffected**

```bash
cd /d/code/claude-mnemos && python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: same as Phase 1 (no backend changes in Phase 2-3).

---

# Phase 4 — CWD mini-builder + Onboarding integration + display_name fallback

**Goal:** Wire DirectoryPicker into Onboarding form (Browse next to vault path), build CWD mini-builder using picker, apply `getProjectDisplayName` helper across UI components.

---

## Task 14: CwdBuilder component

**Files:**
- Create: `frontend/src/components/onboarding/CwdBuilder.tsx`
- Create: `frontend/src/__tests__/CwdBuilder.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/CwdBuilder.test.tsx`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { CwdBuilder } from "../components/onboarding/CwdBuilder";

let mock: MockAdapter;
beforeEach(() => {
  mock = new MockAdapter(axios);
  mock.onGet("/fs/home").reply(200, { home: "/home" });
  mock.onGet(/\/fs\/browse/).reply(200, {
    cwd: "/home",
    parent: null,
    entries: [{ name: "code", path: "/home/code" }],
    truncated: false,
  });
});

describe("CwdBuilder", () => {
  it("renders empty list when no patterns", () => {
    render(<CwdBuilder patterns={[]} onChange={() => {}} />);
    expect(screen.getByText(/Add folder|Добавить папку|Додати папку/i)).toBeInTheDocument();
  });

  it("renders existing patterns with recursive flag", () => {
    render(<CwdBuilder patterns={["/home/code/*", "/tmp"]} onChange={() => {}} />);
    expect(screen.getByText("/home/code")).toBeInTheDocument();
    expect(screen.getByText("/tmp")).toBeInTheDocument();
  });

  it("removes pattern when × clicked", async () => {
    const onChange = vi.fn();
    render(<CwdBuilder patterns={["/home/code/*"]} onChange={onChange} />);
    const removeBtn = screen.getByRole("button", { name: /Remove|Удалить|Видалити/i });
    await userEvent.click(removeBtn);
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("toggles recursive — appends or strips trailing /*", async () => {
    const onChange = vi.fn();
    render(<CwdBuilder patterns={["/home/code/*"]} onChange={onChange} />);
    const checkbox = screen.getByRole("checkbox");
    await userEvent.click(checkbox);  // turn off recursive
    expect(onChange).toHaveBeenCalledWith(["/home/code"]);
  });

  it("opens DirectoryPicker on Add folder click", async () => {
    render(<CwdBuilder patterns={[]} onChange={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /Add folder/i }));
    expect(await screen.findByText("code")).toBeInTheDocument();  // picker rendered
  });
});
```

- [ ] **Step 2: Run failing tests**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/CwdBuilder.test.tsx 2>&1 | tail -10
```

Expected: import error.

- [ ] **Step 3: Implement CwdBuilder**

Create `frontend/src/components/onboarding/CwdBuilder.tsx`:
```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { DirectoryPicker } from "@/components/picker/DirectoryPicker";

interface Props {
  patterns: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

const RECURSIVE_SUFFIX_RE = /[\\/]\*$/;

function isRecursive(pattern: string): boolean {
  return RECURSIVE_SUFFIX_RE.test(pattern);
}

function basePath(pattern: string): string {
  return pattern.replace(RECURSIVE_SUFFIX_RE, "");
}

function withRecursive(path: string, recursive: boolean): string {
  const base = basePath(path);
  if (!recursive) return base;
  const sep = base.includes("\\") ? "\\" : "/";
  return `${base}${sep}*`;
}

export function CwdBuilder({ patterns, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const [pickerOpen, setPickerOpen] = useState(false);

  const remove = (idx: number) => {
    const next = patterns.filter((_, i) => i !== idx);
    onChange(next);
  };

  const toggleRecursive = (idx: number) => {
    const cur = patterns[idx];
    const next = patterns.slice();
    next[idx] = withRecursive(basePath(cur), !isRecursive(cur));
    onChange(next);
  };

  const handleSelect = (path: string) => {
    setPickerOpen(false);
    onChange([...patterns, withRecursive(path, true)]);
  };

  return (
    <div className="space-y-2">
      {patterns.length === 0 ? (
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          {t("cwd_builder.empty")}
        </p>
      ) : (
        <ul className="space-y-1">
          {patterns.map((p, idx) => (
            <li key={`${p}-${idx}`} className="flex items-center gap-2 rounded-md border bg-[hsl(var(--background))] px-2 py-1 text-sm">
              <span className="font-mono">📁 {basePath(p)}</span>
              <label className="ml-auto inline-flex items-center gap-1 text-xs">
                <input
                  type="checkbox"
                  checked={isRecursive(p)}
                  onChange={() => toggleRecursive(idx)}
                  disabled={disabled}
                />
                {t("cwd_builder.recursive")}
              </label>
              <button
                type="button"
                onClick={() => remove(idx)}
                disabled={disabled}
                aria-label={t("cwd_builder.remove")}
                className="text-xs text-[hsl(var(--muted-foreground))] hover:text-red-700"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() => setPickerOpen(true)}
      >
        + {t("cwd_builder.add")}
      </Button>

      <DirectoryPicker
        open={pickerOpen}
        onSelect={handleSelect}
        onClose={() => setPickerOpen(false)}
      />
    </div>
  );
}
```

- [ ] **Step 4: Add locale keys**

Edit `frontend/public/locales/{en,ru,uk}.json`. Add `cwd_builder` namespace:

`en.json`:
```json
"cwd_builder": {
  "add": "Add folder",
  "remove": "Remove",
  "recursive": "Include subfolders",
  "empty": "No folders added — sessions must be ingested manually"
}
```

`ru.json`:
```json
"cwd_builder": {
  "add": "Добавить папку",
  "remove": "Удалить",
  "recursive": "Включая подпапки",
  "empty": "Не добавлено — сессии нужно ингестить вручную"
}
```

`uk.json`:
```json
"cwd_builder": {
  "add": "Додати папку",
  "remove": "Видалити",
  "recursive": "Включно з підпапками",
  "empty": "Не додано — сесії потрібно інгестувати вручну"
}
```

- [ ] **Step 5: Run tests — must pass**

```bash
pnpm test --run src/__tests__/CwdBuilder.test.tsx 2>&1 | tail -10
```

Expected: `5 passed`.

- [ ] **Step 6: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/components/onboarding/CwdBuilder.tsx frontend/src/__tests__/CwdBuilder.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): CwdBuilder component — list + add via picker

Replaces glob textarea: shows folders with toggleable 'recursive'
checkbox (drives \\* suffix). + Add folder opens DirectoryPicker.
× removes individual pattern. New locale keys.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: Wire picker + CwdBuilder into Onboarding

**Files:**
- Modify: `frontend/src/pages/Onboarding.tsx`
- Modify: `frontend/src/__tests__/Onboarding.test.tsx`

- [ ] **Step 1: Write failing tests**

Add to `frontend/src/__tests__/Onboarding.test.tsx`:
```typescript
  it("opens DirectoryPicker on Browse button click", async () => {
    apiMock.onGet("/fs/home").reply(200, { home: "/home" });
    apiMock.onGet(/\/fs\/browse/).reply(200, {
      cwd: "/home",
      parent: null,
      entries: [{ name: "code", path: "/home/code" }],
      truncated: false,
    });
    renderOnboarding();
    await userEvent.click(screen.getByRole("button", { name: /Browse|Обзор|Огляд/i }));
    expect(await screen.findByText("code")).toBeInTheDocument();  // picker open
  });

  it("Browse → Select sets vault input", async () => {
    apiMock.onGet("/fs/home").reply(200, { home: "/home" });
    apiMock.onGet(/\/fs\/browse/).reply(200, {
      cwd: "/home",
      parent: null,
      entries: [{ name: "code", path: "/home/code" }],
      truncated: false,
    });
    renderOnboarding();
    await userEvent.click(screen.getByRole("button", { name: /Browse|Обзор|Огляд/i }));
    await screen.findByText("code");
    await userEvent.click(screen.getByRole("button", { name: /Select|Выбрать|Вибрати/i }));

    const vaultInput = screen.getByLabelText(/vault|Path to vault/i) as HTMLInputElement;
    expect(vaultInput.value).toBe("/home");
  });

  it("CwdBuilder add folder appends to cwd_patterns on submit", async () => {
    apiMock.onGet("/fs/home").reply(200, { home: "/home" });
    apiMock.onGet(/\/fs\/browse/).reply(200, {
      cwd: "/home",
      parent: null,
      entries: [{ name: "code", path: "/home/code" }],
      truncated: false,
    });
    apiMock.onPost("/projects").reply((config) => {
      const body = JSON.parse(config.data as string);
      expect(body.cwd_patterns).toContain("/home/*");
      return [200, { name: "x", display_name: null, vault_root: "/home", cwd_patterns: ["/home/*"] }];
    });
    renderOnboarding();
    await userEvent.type(screen.getByLabelText(/Display name|Название/i), "Test");
    await userEvent.type(screen.getByLabelText(/vault|Path to vault/i), "/home");

    // Open advanced section + Add folder via builder
    await userEvent.click(screen.getByRole("button", { name: /Advanced|Расширенные|Розширені/i }));
    await userEvent.click(screen.getByRole("button", { name: /Add folder|Добавить|Додати/i }));
    await screen.findByText("code");
    await userEvent.click(screen.getByRole("button", { name: /Select|Выбрать|Вибрати/i }));

    await userEvent.click(screen.getByRole("button", { name: /Create|Создать|Створити/i }));
  });
```

- [ ] **Step 2: Run failing tests**

```bash
pnpm test --run src/__tests__/Onboarding.test.tsx 2>&1 | tail -10
```

Expected: assertions about Browse / CwdBuilder fail.

- [ ] **Step 3: Update Onboarding.tsx**

Modify `frontend/src/pages/Onboarding.tsx` (additive — keeping all existing sections):

Add imports:
```tsx
import { DirectoryPicker } from "@/components/picker/DirectoryPicker";
import { CwdBuilder } from "@/components/onboarding/CwdBuilder";
```

Replace the cwd textarea section in advanced block. Locate this:
```tsx
            <textarea id="onb-cwd" value={cwd} ... />
```

Replace cwd state from string → array, swap textarea for CwdBuilder. New state:
```tsx
  const [cwdPatterns, setCwdPatterns] = useState<string[]>([]);
  const [vaultPickerOpen, setVaultPickerOpen] = useState(false);
```

Drop the old `cwd` state + textarea entirely. The submit body becomes:
```tsx
    create.mutate(
      {
        name: slug,
        display_name: displayName.trim() || null,
        vault_root: vault.trim(),
        cwd_patterns: cwdPatterns,
      },
      ...
    );
```

Vault path section gets a Browse button next to input:
```tsx
      <div className="space-y-2">
        <label htmlFor="onb-vault" className="text-sm font-medium">{t("onboarding.vault_label")}</label>
        <div className="flex gap-2">
          <input
            id="onb-vault"
            type="text"
            value={vault}
            onChange={(e) => setVault(e.target.value)}
            disabled={create.isPending}
            className="flex-1 rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={create.isPending}
            onClick={() => setVaultPickerOpen(true)}
          >
            📁 {t("onboarding.vault_browse")}
          </Button>
        </div>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.vault_hint")}</p>
      </div>
```

Advanced section gets CwdBuilder:
```tsx
        {advancedOpen && (
          <div className="space-y-2 rounded-md border bg-[hsl(var(--muted))] p-3">
            <label className="text-sm font-medium">{t("onboarding.cwd_label")}</label>
            <CwdBuilder
              patterns={cwdPatterns}
              onChange={setCwdPatterns}
              disabled={create.isPending}
            />
            <p className="text-xs text-[hsl(var(--muted-foreground))]">{t("onboarding.cwd_hint")}</p>
          </div>
        )}
```

Add `<DirectoryPicker>` for vault selection at the end of the form (renders nothing when closed):
```tsx
      <DirectoryPicker
        open={vaultPickerOpen}
        initialPath={vault.trim() || undefined}
        allowCreate
        onSelect={(path) => { setVault(path); setVaultPickerOpen(false); }}
        onClose={() => setVaultPickerOpen(false)}
      />
```

- [ ] **Step 4: Add locale key**

Add to `frontend/public/locales/{en,ru,uk}.json` `onboarding` block:
```json
"vault_browse": "Browse"
```
(`Обзор` for ru, `Огляд` for uk)

- [ ] **Step 5: Run tests**

```bash
pnpm test --run src/__tests__/Onboarding.test.tsx 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/pages/Onboarding.tsx frontend/src/__tests__/Onboarding.test.tsx frontend/public/locales/ && git commit -m "feat(frontend): Onboarding wizard wires DirectoryPicker + CwdBuilder

Vault path now has Browse button opening DirectoryPicker (with allowCreate
for new folders). CWD textarea replaced with CwdBuilder. Submit body
includes display_name + slug + vault_root + cwd_patterns array.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: Apply getProjectDisplayName helper across UI

**Files:**
- Create: `frontend/src/lib/projectDisplayName.ts`
- Create: `frontend/src/__tests__/lib-projectDisplayName.test.ts`
- Modify: every component that currently displays `project.name` for a project (sidebar, breadcrumbs, switcher, page headers)

- [ ] **Step 1: Write failing test**

Create `frontend/src/__tests__/lib-projectDisplayName.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { getProjectDisplayName } from "../lib/projectDisplayName";

describe("getProjectDisplayName", () => {
  it("returns display_name when set", () => {
    expect(getProjectDisplayName({ name: "x", display_name: "Foo" })).toBe("Foo");
  });

  it("falls back to name when display_name is null", () => {
    expect(getProjectDisplayName({ name: "x", display_name: null })).toBe("x");
  });

  it("falls back to name when display_name is undefined", () => {
    expect(getProjectDisplayName({ name: "x" })).toBe("x");
  });

  it("falls back to name when display_name is empty string", () => {
    expect(getProjectDisplayName({ name: "x", display_name: "" })).toBe("x");
  });

  it("trims display_name whitespace", () => {
    expect(getProjectDisplayName({ name: "x", display_name: "  Foo  " })).toBe("Foo");
  });
});
```

- [ ] **Step 2: Run failing test**

```bash
pnpm test --run src/__tests__/lib-projectDisplayName.test.ts 2>&1 | tail -10
```

Expected: import error.

- [ ] **Step 3: Implement helper**

Create `frontend/src/lib/projectDisplayName.ts`:
```typescript
interface ProjectLike {
  name: string;
  display_name?: string | null;
}

export function getProjectDisplayName(project: ProjectLike): string {
  const trimmed = project.display_name?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : project.name;
}
```

- [ ] **Step 4: Find all usage sites**

```bash
grep -rn "project\.name\|\.name}\|switchProject\|\.name }>" /d/code/claude-mnemos/frontend/src/ --include="*.tsx" | grep -v "__tests__\|api\|types" | head -30
```

Identify components that render project name in user-facing UI: ProjectSwitcher, Sidebar, breadcrumbs, page headers.

- [ ] **Step 5: Apply helper in each component**

For each match, import the helper and replace `project.name` (in render) with `getProjectDisplayName(project)`. Keep `project.name` (slug) where it's used for URL/key purposes (e.g. `<Link to={`/project/${project.name}`}>`).

Example transformation:
```tsx
// Before
<span>{project.name}</span>

// After
import { getProjectDisplayName } from "@/lib/projectDisplayName";
<span>{getProjectDisplayName(project)}</span>
```

Do NOT replace in:
- URL params (`/project/${project.name}`)
- API request bodies
- Test fixtures
- File path computations

- [ ] **Step 6: Run tests**

```bash
pnpm test --run 2>&1 | tail -5
```

Expected: all pass; no regressions.

- [ ] **Step 7: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/lib/projectDisplayName.ts frontend/src/__tests__/lib-projectDisplayName.test.ts frontend/src/ && git commit -m "feat(frontend): getProjectDisplayName helper applied across UI

Single source of fallback logic: display_name.trim() || name. Used in
sidebar, project switcher, breadcrumbs, page headers. URL paths still
use project.name (slug) — only user-facing labels switched.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: Phase 4 verification

- [ ] **Step 1: Full test runs**

```bash
cd /d/code/claude-mnemos && python -m pytest --ignore=tests/slow 2>&1 | tail -3
cd frontend && pnpm test --run 2>&1 | tail -5
pnpm tsc --noEmit 2>&1 | tail -3
pnpm lint 2>&1 | tail -5
```

Expected: backend ~1486, frontend ~232 (Phase 3's 222 + 5 helper + 5 cwdbuilder + 3 Onboarding integration ≈ 235; allow ±5 variance). tsc/eslint clean.

- [ ] **Step 2: Frontend build**

```bash
cd /d/code/claude-mnemos/frontend && pnpm build 2>&1 | tail -5
```

Expected: succeeds, bundle written to `claude_mnemos/daemon/static/`.

- [ ] **Step 3: Zero-diff in untouchable files**

```bash
cd /d/code/claude-mnemos && git diff main -- claude_mnemos/ingest/ claude_mnemos/state/manifest.py claude_mnemos/core/metrics.py claude_mnemos/hooks/ claude_mnemos/state/jobs.py claude_mnemos/daemon/jobs/ claude_mnemos/state/settings.py | wc -l
```

Expected: `0`.

---

# Phase 5 — Manual e2e + finalize

## Task 18: Manual checklist + memory + merge

- [ ] **Step 1: Write manual checklist**

Create `docs/plans/2026-04-30-onboarding-polish-manual-checklist.md`:
```markdown
# Onboarding Polish — Manual E2E Checklist

These checks run by hand on Yarik's Win11 after merge.

## Prerequisites
- [ ] daemon restarted with new code (`mnemos daemon stop && mnemos daemon start`)
- [ ] dashboard reloaded (Ctrl+F5 to clear bundle cache)

## Display name + slug
- [ ] Open `/onboarding`
- [ ] Type "Конструктор сайтов" in Display name → slug field auto-fills with transliteration (likely `konstruktor-sajtov` or similar)
- [ ] Click «Edit slug» → slug input becomes editable; clear and type "custom-x" → display name typing no longer changes slug
- [ ] Click «Auto» → slug re-derives from current display name

## File picker
- [ ] Click «Browse» next to vault path → modal opens at home dir
- [ ] Listing shows subfolders only (no files)
- [ ] Click folder row → navigate inside; breadcrumbs update
- [ ] Click breadcrumb segment → navigate to ancestor
- [ ] Type path in PathInput → Enter → navigate to that path
- [ ] Type partial name in Filter → list narrows (case-insensitive substring)
- [ ] Recent shows nothing on first use
- [ ] Click «+ New folder» → input dialog → type "test_pick" → Create → folder created and navigated into
- [ ] Click «Select this folder» → modal closes; vault input shows selected path
- [ ] Reopen picker → Recent shows previously selected path
- [ ] Click recent path → navigate there
- [ ] Click «Cancel» → modal closes; vault input unchanged

## CWD mini-builder
- [ ] Open «Расширенные» (advanced) section
- [ ] Click «Add folder» → DirectoryPicker opens
- [ ] Select a folder → pattern added with «Include subfolders» checkbox checked (recursive)
- [ ] Toggle checkbox off → pattern updates (no \\* suffix)
- [ ] Click × → pattern removed

## Display_name fallback
- [ ] Sidebar shows display name for new project, falls back to slug for old projects
- [ ] Project switcher dropdown — same
- [ ] Page headers — same
- [ ] URLs still use slug (e.g. `/project/test-cli`)

## Submit flow
- [ ] Create project «My Test Project» with vault `/tmp/mtp` and 1 cwd pattern
- [ ] Sidebar shows «My Test Project» (display_name)
- [ ] Backend `mnemos project show my-test-project` (or auto-derived slug) shows display_name
- [ ] `~/.claude-mnemos/project-map.json` has display_name field set

## Existing projects (no migration)
- [ ] Sidebar still shows existing 4 projects (test-cli, p, claude-mnemos, x) by slug — display_name=null fallback
- [ ] No errors loading project-map.json
```

- [ ] **Step 2: Update memory**

Create `C:/Users/68664/.claude/projects/d-----------------OBSIDIAN--shared/memory/plan_onboarding_polish_complete.md`:
```markdown
---
name: Plan A — Onboarding polish завершён — снимок 2026-04-30
description: display_name + slug auto-derive (UTF-8 имена), DirectoryPicker modal, CWD mini-builder. Onboarding wizard rewritten. Existing 4 проекта работают через display_name fallback. Plan B (Settings UI) — следующий.
type: project
---

# Plan A — Onboarding polish — итог

[fill: merge sha + что добавилось + результаты]
```

(actually fill in this file with concrete data after merge)

Update `C:/Users/68664/.claude/projects/d-----------------OBSIDIAN--shared/memory/MEMORY.md` claude_mnemos line:
- bump to new merge sha
- new test counts
- mention DirectoryPicker / CwdBuilder / display_name

Add separate index line:
```
- [Plan A — Onboarding polish завершён — снимок 2026-04-30](plan_onboarding_polish_complete.md) — display_name+slug, DirectoryPicker, CwdBuilder, getProjectDisplayName fallback. Plan B (Settings UI) пишется следующим.
```

- [ ] **Step 3: Final code review**

Dispatch `code-reviewer` subagent over all 18 commits since main. Address any critical/important findings.

- [ ] **Step 4: Merge**

```bash
cd /d/code/claude-mnemos && git checkout main && git merge --no-ff feat/onboarding-polish -m "Merge feat/onboarding-polish: display_name + DirectoryPicker + CwdBuilder

Phase 1 — Backend:
  - ProjectMapEntry.display_name field (nullable, no migration)
  - CLI/REST plumbing for display_name (mnemos project add --display-name, POST /projects body)
  - /fs router: GET /home, GET /browse, POST /mkdir

Phase 2 — Frontend slugify:
  - @sindresorhus/slugify dep + deriveSlug() lib (Cyrillic→Latin)
  - Onboarding form: display_name + slug auto-derive + Edit slug toggle

Phase 3 — DirectoryPicker:
  - api/fs.api.ts + types/Fs.ts (zod)
  - useRecentPaths hook (localStorage)
  - DirectoryPicker modal: browse, breadcrumbs, path input, filter, recent, new folder

Phase 4 — Integration:
  - CwdBuilder component using DirectoryPicker
  - Onboarding wired with Browse button + CwdBuilder
  - getProjectDisplayName helper applied across UI components

Tests: backend ~1486 (+~21), frontend ~235 (+~39). ruff/tsc/eslint clean.
Zero diff in extraction/parser/metrics/hooks/jobs/settings. Existing
4 projects continue working with display_name=null fallback.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Verify merge**

```bash
git log --oneline -3
```

---

## Self-review

**Spec coverage:**
- §2 Scope «Включено» — display_name field (Task 1), CLI/REST plumbing (Task 2), /fs/{home,browse,mkdir} (Tasks 3-5), slugify (Task 7), DirectoryPicker (Task 12), CwdBuilder (Task 14), Onboarding integration (Tasks 8+15), display_name fallback helper (Task 16). All covered.
- §3 Architecture diagram → Tasks 3-5 (backend) + 10 + 12 (frontend modals) + 14-15 (integration).
- §4 Behavior — slug derivation in Task 7 + 8; DirectoryPicker behavior in Task 12; CWD builder in Task 14.
- §5 API specifics — /fs/browse Task 4 (truncation, sorting, errors); /fs/mkdir Task 5 (validation); /fs/home Task 3.
- §6 Tests — every task has TDD steps. Manual checklist Task 18.
- §7 Phases — 5 phases match plan structure (Tasks 1-6 = Phase 1; Tasks 7-9 = Phase 2; Tasks 10-13 = Phase 3; Tasks 14-17 = Phase 4; Task 18 = Phase 5).
- §8 Risks — addressed: slugify edge cases (Task 7 tests), 5s timeout (DirectoryPicker `axios` default), 403 path errors (Task 4 + DirectoryPicker error display), localStorage quota (try/catch in useRecentPaths Task 11).

**Placeholder scan:**
- Task 2 Step 3 says "Adapt to existing test harness — likely uses TestClient" with `...` placeholder. **This is a real gap** — engineer should match patterns from existing `test_routes_projects*.py`. Acceptable since plan can't predict harness without inspection. Engineer reads existing tests in Task 2 Step 1.
- Task 16 Step 4 says "find usage sites with grep" — engineer-driven inspection. Acceptable.
- Task 18 Step 2 has `[fill: ...]` — explicit placeholder for after-merge data. Acceptable as it's filled at merge time.

**Type/name consistency:**
- `display_name: str | None` — consistent across Tasks 1-2 (backend), 8 (frontend zod), 15 (submit body), 16 (helper).
- `deriveSlug` defined Task 7, used in Onboarding Task 8 + 15.
- `DirectoryPicker` props `{open, initialPath, allowCreate, onSelect, onClose}` — consistent across Tasks 12, 14, 15.
- `useRecentPaths` shape `{recent, addRecent}` — consistent.
- `getProjectDisplayName` signature consistent — Task 16.
- `/fs/browse` response schema (cwd, parent, entries, truncated) — consistent across Task 4 + 10 + 12.

**Plan complete and saved.**
