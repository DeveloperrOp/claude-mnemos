# DirectoryPicker Improvements — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрыть 3 UX-bug'а в DirectoryPicker:
1. Нет навигации между дисками на Windows (юзер залип в home)
2. Нет «New folder» button в CwdBuilder picker'е (только в Onboarding)
3. Нет file picker для Prompts paths (`custom_system_path` / `custom_extract_user_path`)

**Architecture:** Extend existing DirectoryPicker — добавить drives view + file mode. Backend новый endpoint `/fs/drives` + `/fs/browse?include_files=true`. CwdBuilder получает `allowCreate=true`. PromptsSection получает Browse buttons с `mode="file"`.

**Tech Stack:** React 19 + zod, FastAPI + Pydantic v2.

**Branch:** `feat/picker-improvements` (from main `369e650`).

**Critical safety:** Backend baseline 1495 → ~1500. Frontend 288 → ~298. ruff/tsc/eslint clean. Zero-diff в `extraction.py / parser.py / metrics.py / hooks/ / state/jobs.py / daemon/jobs/ / state/manifest.py / state/settings.py`.

---

## File Structure

### Modified backend
```
claude_mnemos/daemon/routes/fs.py        # +GET /fs/drives, +include_files param на /fs/browse
tests/daemon/routes/test_fs.py           # +tests for drives + files
```

### Modified frontend
```
frontend/src/types/Fs.ts                                # +FsEntry.type, FsDrives schema
frontend/src/api/fs.api.ts                              # +listDrives, +include_files param
frontend/src/components/picker/DirectoryPicker.tsx      # +drives view, +mode="file"
frontend/src/components/onboarding/CwdBuilder.tsx       # allowCreate={true}
frontend/src/components/settings/sections/PromptsSection.tsx  # +Browse buttons (mode="file")
frontend/src/__tests__/api-fs.test.ts                   # +listDrives test
frontend/src/__tests__/DirectoryPicker.test.tsx         # +drives mode + file mode tests
frontend/public/locales/{en,ru,uk}.json                 # +picker.computer, picker.select_file
```

### Untouched
```
ingest/, hooks/, jobs/, manifest.py, metrics.py, state/settings.py
```

---

## Task 1: Backend — /fs/drives + include_files param

**Files:**
- Modify: `claude_mnemos/daemon/routes/fs.py`
- Modify: `tests/daemon/routes/test_fs.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/daemon/routes/test_fs.py`:
```python
def test_get_fs_drives_unix_returns_root(monkeypatch) -> None:
    """On Unix, /fs/drives returns single root entry."""
    monkeypatch.setattr("claude_mnemos.daemon.routes.fs.sys.platform", "linux")
    resp = _client().get("/fs/drives")
    assert resp.status_code == 200
    body = resp.json()
    assert body["drives"] == [{"name": "/", "path": "/"}]


def test_get_fs_drives_windows_returns_drive_letters(monkeypatch, tmp_path) -> None:
    """On Windows, /fs/drives returns letter-drive list filtered by exists()."""
    monkeypatch.setattr("claude_mnemos.daemon.routes.fs.sys.platform", "win32")
    # Stub Path.exists to make C:, D: exist
    real_exists = Path.exists
    def fake_exists(self):
        s = str(self)
        if s in ("C:\\", "D:\\"):
            return True
        return real_exists(self)
    monkeypatch.setattr(Path, "exists", fake_exists)
    resp = _client().get("/fs/drives")
    assert resp.status_code == 200
    drives = [d["path"] for d in resp.json()["drives"]]
    assert "C:\\" in drives
    assert "D:\\" in drives


def test_get_fs_browse_with_include_files_returns_files_too(tmp_path: Path) -> None:
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file.md").write_text("hello")
    (tmp_path / "image.png").write_bytes(b"\x00")

    resp = _client().get(f"/fs/browse?path={tmp_path}&include_files=true")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    types = {e["name"]: e["type"] for e in entries}
    assert types == {"subdir": "directory", "file.md": "file", "image.png": "file"}


def test_get_fs_browse_without_include_files_returns_only_directories(tmp_path: Path) -> None:
    """Default behaviour unchanged — only directories."""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file.md").write_text("hi")
    resp = _client().get(f"/fs/browse?path={tmp_path}")
    body = resp.json()
    names = [e["name"] for e in body["entries"]]
    assert names == ["subdir"]
    # type field present (default "directory") for backward-compat
    types = {e["type"] for e in body["entries"]}
    assert types == {"directory"}
```

- [ ] **Step 2: Run failing tests**

```bash
cd /d/code/claude-mnemos && python -m pytest tests/daemon/routes/test_fs.py -v 2>&1 | tail -10
```

Expected: 4 new failures (404 on /fs/drives + missing fields/params).

- [ ] **Step 3: Implement endpoints**

In `claude_mnemos/daemon/routes/fs.py`:

Add `import sys` at top. Modify `/browse` to accept `include_files: bool` query param + add `type` field:

```python
@router.get("/browse")
def browse(path: str, include_files: bool = False) -> dict[str, object]:
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
        children = list(resolved.iterdir())
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail=f"permission denied: {exc}"
        ) from exc

    if include_files:
        children = [c for c in children if c.is_dir() or c.is_file()]
    else:
        children = [c for c in children if c.is_dir()]

    children.sort(key=lambda c: (not c.is_dir(), c.name.casefold()))
    truncated = len(children) > LIST_LIMIT
    children = children[:LIST_LIMIT]

    parent_path = resolved.parent
    parent_str = str(parent_path) if parent_path != resolved else None

    return {
        "cwd": str(resolved),
        "parent": parent_str,
        "entries": [
            {"name": c.name, "path": str(c), "type": "directory" if c.is_dir() else "file"}
            for c in children
        ],
        "truncated": truncated,
    }
```

Add new `/drives` endpoint after `/browse`:
```python
@router.get("/drives")
def drives() -> dict[str, list[dict[str, str]]]:
    """List top-level filesystem roots.

    On Windows, returns each existing drive letter (C:\\, D:\\, ...).
    On POSIX, returns a single root entry.
    """
    if sys.platform == "win32":
        result = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive_path = Path(f"{letter}:\\")
            if drive_path.exists():
                result.append({"name": f"{letter}:", "path": str(drive_path)})
        return {"drives": result}
    return {"drives": [{"name": "/", "path": "/"}]}
```

- [ ] **Step 4: Run tests — must pass**

```bash
python -m pytest tests/daemon/routes/test_fs.py -v 2>&1 | tail -15
```

Expected: all pass (existing + 4 new).

- [ ] **Step 5: Run all backend tests**

```bash
python -m pytest --ignore=tests/slow 2>&1 | tail -3
```

Expected: ~1499-1500 passed (1495 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/fs.py tests/daemon/routes/test_fs.py && git commit -m "feat(fs): GET /fs/drives + /fs/browse?include_files for file picker

drives endpoint returns drive letters on Windows (filtered by exists()),
single root '/' on POSIX. browse endpoint accepts include_files=true to
return file entries alongside directories; type field added to every
entry ('directory' or 'file'). Default behaviour preserved for existing
DirectoryPicker callers — only directories returned without the flag.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Frontend types + api updates

**Files:**
- Modify: `frontend/src/types/Fs.ts`
- Modify: `frontend/src/api/fs.api.ts`
- Modify: `frontend/src/__tests__/api-fs.test.ts`

- [ ] **Step 1: Add `type` to FsEntry, add FsDrives schema, update browseDirectory + listDrives**

Modify `frontend/src/types/Fs.ts`:
```typescript
export const FsEntrySchema = z.object({
  name: z.string(),
  path: z.string(),
  type: z.enum(["directory", "file"]).default("directory"),
});
export type FsEntry = z.infer<typeof FsEntrySchema>;

// FsBrowseSchema unchanged structurally (entries now have type field via permissive default)

export const FsDriveSchema = z.object({
  name: z.string(),
  path: z.string(),
});
export type FsDrive = z.infer<typeof FsDriveSchema>;

export const FsDrivesSchema = z.object({
  drives: z.array(FsDriveSchema),
});
export type FsDrives = z.infer<typeof FsDrivesSchema>;
```

Modify `frontend/src/api/fs.api.ts`:
```typescript
import {
  FsBrowseSchema,
  FsDrivesSchema,
  FsHomeSchema,
  FsMkdirResponseSchema,
  type FsBrowse,
  type FsDrives,
  type FsHome,
  type FsMkdirResponse,
} from "@/types/Fs";

export async function browseDirectory(
  path: string,
  opts?: { includeFiles?: boolean },
): Promise<FsBrowse> {
  const params: Record<string, string | boolean> = { path };
  if (opts?.includeFiles) params.include_files = true;
  const { data } = await apiClient.get("/fs/browse", { params });
  return FsBrowseSchema.parse(data);
}

export async function listDrives(): Promise<FsDrives> {
  const { data } = await apiClient.get("/fs/drives");
  return FsDrivesSchema.parse(data);
}
```

Keep `getHome`, `mkdir` unchanged.

- [ ] **Step 2: Add test for listDrives + includeFiles**

Append to `frontend/src/__tests__/api-fs.test.ts`:
```typescript
it("listDrives returns array of drives", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValueOnce({
    data: { drives: [{ name: "C:", path: "C:\\" }, { name: "D:", path: "D:\\" }] },
  });
  const result = await listDrives();
  expect(result.drives).toHaveLength(2);
  expect(result.drives[0].path).toBe("C:\\");
});

it("browseDirectory passes include_files when opts.includeFiles=true", async () => {
  const spy = vi.spyOn(apiClient, "get").mockResolvedValueOnce({
    data: { cwd: "/tmp", parent: null, entries: [], truncated: false },
  });
  await browseDirectory("/tmp", { includeFiles: true });
  expect(spy).toHaveBeenCalledWith("/fs/browse", { params: { path: "/tmp", include_files: true } });
});
```

- [ ] **Step 3: Run tests**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run src/__tests__/api-fs.test.ts 2>&1 | tail -10
```

Expected: existing 5 tests + 2 new pass.

- [ ] **Step 4: Commit**

```bash
cd /d/code/claude-mnemos && git add frontend/src/types/Fs.ts frontend/src/api/fs.api.ts frontend/src/__tests__/api-fs.test.ts && git commit -m "feat(frontend): listDrives() + browseDirectory includeFiles option

zod schemas for /fs/drives. FsEntry gets type field ('directory'|'file').
browseDirectory takes optional { includeFiles: true }.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: DirectoryPicker — drives view + file mode

**Files:**
- Modify: `frontend/src/components/picker/DirectoryPicker.tsx`
- Modify: `frontend/src/__tests__/DirectoryPicker.test.tsx`
- Modify: locales

- [ ] **Step 1: Extend DirectoryPicker**

Add props:
```typescript
interface Props {
  open: boolean;
  initialPath?: string;
  allowCreate?: boolean;
  mode?: "directory" | "file";  // NEW — default "directory"
  fileExtensions?: string[];     // NEW — filter file entries (e.g. [".md", ".txt"])
  onSelect: (path: string) => void;
  onClose: () => void;
}
```

Add new state for drives view:
```typescript
const [drivesView, setDrivesView] = useState(false);
const [drives, setDrives] = useState<FsDrive[]>([]);
```

Add `goToDrives()` function:
```typescript
async function goToDrives() {
  setDrivesView(true);
  setLoading(true);
  setError(null);
  try {
    const result = await listDrives();
    setDrives(result.drives);
  } catch (e) {
    if (axios.isAxiosError(e)) setError(e.response?.data?.detail ?? e.message);
  } finally {
    setLoading(false);
  }
}
```

Modify `navigateTo` to clear `drivesView` (we exited drives view).

Modify `browseDirectory` call inside navigateTo to pass `includeFiles` based on `mode`:
```typescript
const result = await browseDirectory(path, { includeFiles: mode === "file" });
```

Modify entry rendering to handle `type`:
```typescript
{!loading && !error && !drivesView && visibleEntries.map((e) => {
  const isDir = e.type === "directory";
  const isFile = e.type === "file";
  // Filter files by extension if fileExtensions provided
  if (mode === "file" && isFile && fileExtensions && fileExtensions.length > 0) {
    if (!fileExtensions.some(ext => e.name.toLowerCase().endsWith(ext.toLowerCase()))) {
      return null;
    }
  }
  return (
    <button
      key={e.path}
      onClick={() => {
        if (isDir) {
          navigateTo(e.path);
        } else if (isFile && mode === "file") {
          // File click — select immediately and close
          addRecent(e.path);
          onSelect(e.path);
        }
      }}
      className="block w-full px-3 py-2 text-left text-sm hover:bg-[hsl(var(--muted))]"
    >
      {isDir ? "📁" : "📄"} {e.name}
    </button>
  );
})}
```

Add drives rendering when `drivesView` is true:
```typescript
{!loading && !error && drivesView && drives.map((d) => (
  <button
    key={d.path}
    onClick={() => navigateTo(d.path)}
    className="block w-full px-3 py-2 text-left text-sm hover:bg-[hsl(var(--muted))]"
  >
    💿 {d.name}
  </button>
))}
```

Add «Computer» button in header (visible when `!drivesView`):
```typescript
<button
  type="button"
  onClick={goToDrives}
  className="text-xs text-[hsl(var(--primary))] underline"
>
  🖥 {t("picker.computer")}
</button>
```

Adjust «Select» button label based on mode + drivesView:
- If `drivesView` → hide select (juzer must navigate into a drive first)
- If `mode === "file"` → label `t("picker.select_file")` and disabled (file selected on row click)

Update Russian/Ukrainian/English locales:
```json
"picker.computer": "Computer" / "Мій комп'ютер" / "Мій комп'ютер"
"picker.select_file": "Click a file to select"
```

- [ ] **Step 2: Add tests**

Append to `frontend/src/__tests__/DirectoryPicker.test.tsx`:
```typescript
it("Computer button opens drives view", async () => {
  setupMock();
  vi.spyOn(apiClient, "get").mockImplementation(async (url) => {
    if (url === "/fs/drives") return { data: { drives: [{ name: "C:", path: "C:\\" }, { name: "D:", path: "D:\\" }] } } as any;
    if (url === "/fs/home") return { data: { home: TEST_HOME } } as any;
    if (url === "/fs/browse") return { data: { cwd: TEST_HOME, parent: null, entries: [], truncated: false } } as any;
    return { data: {} } as any;
  });
  render(<DirectoryPicker open onSelect={() => {}} onClose={() => {}} />);
  await screen.findByText(/Choose folder|Вибрати папку/i);
  await userEvent.click(screen.getByRole("button", { name: /Computer|Мій комп/i }));
  expect(await screen.findByText(/💿\s*C:/)).toBeInTheDocument();
  expect(screen.getByText(/💿\s*D:/)).toBeInTheDocument();
});

it("file mode lists files alongside folders", async () => {
  vi.spyOn(apiClient, "get").mockImplementation(async (url, config) => {
    if (url === "/fs/home") return { data: { home: "/x" } } as any;
    if (url === "/fs/browse") {
      // verify include_files=true was passed
      expect(config?.params?.include_files).toBe(true);
      return {
        data: {
          cwd: "/x",
          parent: null,
          entries: [
            { name: "subdir", path: "/x/subdir", type: "directory" },
            { name: "prompt.md", path: "/x/prompt.md", type: "file" },
          ],
          truncated: false,
        },
      } as any;
    }
    return { data: {} } as any;
  });
  render(<DirectoryPicker open mode="file" onSelect={() => {}} onClose={() => {}} />);
  expect(await screen.findByText(/📁\s*subdir/)).toBeInTheDocument();
  expect(screen.getByText(/📄\s*prompt\.md/)).toBeInTheDocument();
});

it("file mode click on file calls onSelect immediately", async () => {
  const onSelect = vi.fn();
  vi.spyOn(apiClient, "get").mockImplementation(async (url) => {
    if (url === "/fs/home") return { data: { home: "/x" } } as any;
    if (url === "/fs/browse") return {
      data: {
        cwd: "/x", parent: null,
        entries: [{ name: "prompt.md", path: "/x/prompt.md", type: "file" }],
        truncated: false,
      },
    } as any;
    return { data: {} } as any;
  });
  render(<DirectoryPicker open mode="file" onSelect={onSelect} onClose={() => {}} />);
  await userEvent.click(await screen.findByText(/prompt\.md/));
  expect(onSelect).toHaveBeenCalledWith("/x/prompt.md");
});

it("file mode filters by fileExtensions prop", async () => {
  vi.spyOn(apiClient, "get").mockImplementation(async (url) => {
    if (url === "/fs/home") return { data: { home: "/x" } } as any;
    if (url === "/fs/browse") return {
      data: {
        cwd: "/x", parent: null,
        entries: [
          { name: "prompt.md", path: "/x/prompt.md", type: "file" },
          { name: "image.png", path: "/x/image.png", type: "file" },
        ],
        truncated: false,
      },
    } as any;
    return { data: {} } as any;
  });
  render(<DirectoryPicker open mode="file" fileExtensions={[".md"]} onSelect={() => {}} onClose={() => {}} />);
  expect(await screen.findByText(/prompt\.md/)).toBeInTheDocument();
  expect(screen.queryByText(/image\.png/)).not.toBeInTheDocument();
});
```

- [ ] **Step 3: Run tests + commit**

```bash
pnpm test --run src/__tests__/DirectoryPicker.test.tsx 2>&1 | tail -10
```

Expected: 11+ pass (7 existing + 4 new).

```bash
cd /d/code/claude-mnemos && git add frontend/src/components/picker/DirectoryPicker.tsx frontend/src/__tests__/DirectoryPicker.test.tsx frontend/public/locales/ && git commit -m "feat(picker): drives view + file mode + extension filter

Computer button → drives view (lists drive letters on Win, '/' on POSIX).
mode='file' shows files alongside folders + click on file selects immediately.
fileExtensions prop filters listing by extension whitelist.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: CwdBuilder allowCreate + PromptsSection file Browse

**Files:**
- Modify: `frontend/src/components/onboarding/CwdBuilder.tsx`
- Modify: `frontend/src/components/settings/sections/PromptsSection.tsx`
- Modify: tests

- [ ] **Step 1: CwdBuilder — pass allowCreate=true**

Find existing `<DirectoryPicker open={pickerOpen} ... />` invocation in CwdBuilder. Add `allowCreate`:
```tsx
<DirectoryPicker
  open={pickerOpen}
  allowCreate
  onSelect={handleSelect}
  onClose={() => setPickerOpen(false)}
/>
```

CwdBuilder existing tests pass (no behaviour change visible to them).

- [ ] **Step 2: PromptsSection — add Browse buttons**

Modify `frontend/src/components/settings/sections/PromptsSection.tsx`. Currently has two text inputs for `custom_system_path` + `custom_extract_user_path`. Wrap each in flex container with Browse button:

```tsx
import { useState } from "react";
import { DirectoryPicker } from "@/components/picker/DirectoryPicker";

// inside component:
const [pickingSystem, setPickingSystem] = useState(false);
const [pickingExtract, setPickingExtract] = useState(false);

// JSX (replace existing input with flex+Browse):
<div className="flex gap-2">
  <input
    type="text"
    value={systemPath ?? ""}
    onChange={(e) => setSystemPath(e.target.value || null)}
    className="flex-1 rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm font-mono"
    placeholder={t("settings.section.prompts.path_placeholder")}
  />
  <Button
    type="button"
    variant="outline"
    size="sm"
    onClick={() => setPickingSystem(true)}
  >
    📁 {t("settings.section.prompts.browse")}
  </Button>
</div>

<DirectoryPicker
  open={pickingSystem}
  mode="file"
  fileExtensions={[".md", ".txt"]}
  onSelect={(path) => { setSystemPath(path); setPickingSystem(false); }}
  onClose={() => setPickingSystem(false)}
/>

// same pattern for extractPath / pickingExtract
```

- [ ] **Step 3: Update PromptsSection test**

Add test:
```typescript
it("Browse button opens file picker; selecting a file fills input", async () => {
  // mock /fs/home, /fs/browse with files, etc.
  // click Browse → click file row → input value updated
});
```

- [ ] **Step 4: Add locale keys**

```json
"settings.section.prompts.browse": "Browse" / "Обзор" / "Огляд"
"settings.section.prompts.path_placeholder": "/path/to/custom/prompt.md"
```

- [ ] **Step 5: Run tests + commit**

```bash
cd /d/code/claude-mnemos/frontend && pnpm test --run 2>&1 | tail -5
```

Expected: all pass.

```bash
cd /d/code/claude-mnemos && git add frontend/src/components/onboarding/CwdBuilder.tsx frontend/src/components/settings/sections/PromptsSection.tsx frontend/src/__tests__/ frontend/public/locales/ && git commit -m "feat(picker): CwdBuilder allowCreate + PromptsSection file Browse

CwdBuilder: + Add folder dialog now allows creating new folders.
PromptsSection: each path field has Browse button opening DirectoryPicker
in file mode with .md/.txt extension filter.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Final verification + manual test + merge

```bash
cd /d/code/claude-mnemos
python -m pytest --ignore=tests/slow 2>&1 | tail -3
python -m ruff check . 2>&1 | tail -3
cd frontend && pnpm test --run 2>&1 | tail -5
pnpm tsc --noEmit 2>&1 | tail -3
pnpm lint 2>&1 | tail -3
pnpm build 2>&1 | tail -3
git diff main -- claude_mnemos/ingest/ claude_mnemos/state/manifest.py claude_mnemos/core/metrics.py claude_mnemos/hooks/ claude_mnemos/state/jobs.py claude_mnemos/daemon/jobs/ claude_mnemos/state/settings.py 2>&1 | wc -l
```

Expected: backend ~1499, frontend ~298, all clean, build succeeds, zero-diff `0`.

Merge to main:
```bash
cd /d/code/claude-mnemos && git checkout main && git merge --no-ff feat/picker-improvements -m "Merge feat/picker-improvements: drives + file mode + allowCreate

3 fixes:
1. /fs/drives endpoint + Computer button in DirectoryPicker — Win drive
   navigation working (was: stuck in home folder)
2. mode='file' for DirectoryPicker — file picker для PromptsSection
   custom_system_path / custom_extract_user_path with .md/.txt filter
3. CwdBuilder picker now allows creating new folders (allowCreate=true)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```
