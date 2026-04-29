# Polish + infra cleanup Implementation Plan (Plan #14e)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** Stabilize the backend test suite (CLI pollution + 3 flaky tests), close `usage_timeline` UTC bug, extend metrics period parser to weeks/months/years, and clean frontend i18n / chart-color / period-pill debts from #14d.

**Architecture:** Pure cleanup. One autouse `tests/conftest.py` fixture forces CLI commands offline; `core/metrics.py::timeline` switches to UTC; `_parse_period` accepts `Nd|Nw|Nm|Ny`; flaky tests get poll-based waits + relaxed assertions. Frontend swaps hex chart colors for CSS vars, adds `1y` pill, localizes 3 raw `dt` labels.

**Tech Stack:** Python 3.12, pytest, FastAPI; React 19, Tailwind v4, recharts.

**Design doc:** `docs/plans/2026-04-29-14e-polish-infra-design.md`.

---

## Files map

**Modified (backend):**
- `tests/conftest.py` — add autouse `isolate_cli_state` fixture; keep existing `register_project`.
- `tests/test_cli.py` — drop per-file `project_env` fixture if it's now redundant (verify no test-specific overrides depend on it).
- `tests/test_cli_project.py` — remove per-file `_isolate_home`.
- `tests/test_cli_settings.py` — remove per-file `_isolate_home`.
- `claude_mnemos/core/metrics.py` — UTC anchor in `timeline`.
- `claude_mnemos/daemon/routes/metrics.py` — extend `_parse_period` to `Nd|Nw|Nm|Ny`.
- `tests/daemon/test_app_metrics.py` — assertion update if local-TZ-dependent.
- `tests/daemon/test_app_snapshots.py` — `test_delete_snapshot_traversal_rejected` → validator-direct test.
- `tests/daemon/test_watchdog_e2e.py` — replace fixed sleep + raise activity poll limit.

**Modified (frontend):**
- `frontend/src/index.css` — add `--chart-input/output/sessions` CSS vars (light + dark).
- `frontend/src/components/widgets/UsageTimelineChart.tsx` — `var(--chart-...)` colors.
- `frontend/src/components/ui/chart.tsx` — explanatory comment on `Partial<TooltipContentProps>`.
- `frontend/src/pages/Metrics.tsx` — `PERIODS = [..., "1y"]`.
- `frontend/src/__tests__/Metrics.test.tsx` — locale bundle adds `period_1y`.
- `frontend/src/pages/DeadLetterDetail.tsx` — `dt` labels via `t()`.
- `frontend/public/locales/{en,uk,ru}.json` — `dead_letter.created_at`/`started_at`/`finished_at`, `metrics.period_1y`.

---

## Task 1: Autouse `isolate_cli_state` fixture in tests/conftest.py

**Files:**
- Modify: `tests/conftest.py` (add fixture)
- Modify: `tests/test_cli.py`, `tests/test_cli_project.py`, `tests/test_cli_settings.py` (remove per-file overrides)

- [ ] **Step 1: Read existing per-file fixtures**

```bash
cd /d/code/claude-mnemos
grep -n "_isolate_home\|project_env\|MNEMOS_VAULT_ROOT" tests/test_cli.py tests/test_cli_project.py tests/test_cli_settings.py
```

Note what each fixture does (HOME, USERPROFILE, env deletes). Confirm none of them set `MNEMOS_DAEMON_URL`.

- [ ] **Step 2: Add autouse fixture to tests/conftest.py**

Append below the existing `register_project` fixture in `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def isolate_cli_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate every test from real user state.

    - HOME/USERPROFILE → tmp_path so Path.home() doesn't read ~/.claude-mnemos.
    - MNEMOS_DAEMON_URL → dead URL so CLI write commands skip the daemon-first
      branch (which on dev machines hits the running daemon and pollutes the
      real project map). Tests that need a real-daemon transport use ASGI
      directly and ignore this env var.
    - Drop env vars that vary per developer.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("MNEMOS_DAEMON_URL", "http://127.0.0.1:1")
    monkeypatch.delenv("MNEMOS_VAULT_ROOT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
```

- [ ] **Step 3: Run the previously-failing tests**

```bash
python -m pytest tests/test_cli.py tests/test_cli_project.py tests/test_cli_settings.py -x --tb=short 2>&1 | tail -10
```

Expected: all PASS. If something still fails, read the error and debug — the autouse fixture should make the offline branch route writes to `tmp_path/.claude-mnemos/` which is tmp.

- [ ] **Step 4: Remove per-file `_isolate_home` from test_cli_project.py**

```bash
grep -n "_isolate_home" tests/test_cli_project.py
```

Delete the fixture definition (likely lines 14-18) AND any explicit `_isolate_home` parameter in test signatures (the autouse fixture replaces it).

If any test signature looked like `def test_x(_isolate_home, ...)`, change to `def test_x(...)`.

- [ ] **Step 5: Remove per-file `_isolate_home` from test_cli_settings.py**

Same pattern. Delete fixture (likely lines 10-14) + parameter references.

- [ ] **Step 6: Inspect test_cli.py `project_env` fixture**

Read `tests/test_cli.py` lines 12-38. If `project_env` only sets the same env vars as the autouse fixture, delete it + its parameter references. If it has unique behavior (e.g., calls `register_project`), keep that part and remove only the env duplication.

- [ ] **Step 7: Run the full CLI test suite**

```bash
python -m pytest tests/test_cli.py tests/test_cli_project.py tests/test_cli_settings.py 2>&1 | tail -5
```

Expected: 0 failures, 0 errors.

- [ ] **Step 8: Run the wider test suite to check no regression**

```bash
python -m pytest tests/ -k "not slow" --ignore=tests/daemon/integration --tb=line 2>&1 | tail -5
```

Expected: failures count drops dramatically (from 12+16 to whatever remains, ideally just the 3 known flakies which Tasks 4-5 fix).

- [ ] **Step 9: Commit**

```bash
git add tests/conftest.py tests/test_cli.py tests/test_cli_project.py tests/test_cli_settings.py
git commit -m "test: #14e autouse isolate_cli_state — force CLI commands offline (drop daemon-first leak)"
```

---

## Task 2: Backend `timeline()` UTC anchor fix

**Files:**
- Modify: `claude_mnemos/core/metrics.py`
- Modify: `tests/daemon/test_app_metrics.py` (assertions if needed)

- [ ] **Step 1: Read current `timeline()` implementation**

```bash
sed -n '155,200p' /d/code/claude-mnemos/claude_mnemos/core/metrics.py
```

Confirm: line 167 is `today = today or date_class.today()`. The seeded record uses `datetime.now(UTC).date()`. Mixing local + UTC is the bug.

- [ ] **Step 2: Add UTC import + replace `date.today()`**

Edit `claude_mnemos/core/metrics.py`. At top of file, change:

```python
from datetime import date as date_class
from datetime import datetime, timedelta
```

to:

```python
from datetime import UTC, date as date_class
from datetime import datetime, timedelta
```

In `timeline()`, change:

```python
today = today or date_class.today()
```

to:

```python
today = today or datetime.now(UTC).date()
```

- [ ] **Step 3: Run the existing test**

```bash
cd /d/code/claude-mnemos
python -m pytest tests/daemon/test_app_metrics.py::test_usage_timeline -v 2>&1 | tail -15
```

Expected: PASS (regardless of local TZ now).

- [ ] **Step 4: Run on UTC+3 (simulate Moscow)**

```bash
TZ='Europe/Moscow' python -m pytest tests/daemon/test_app_metrics.py::test_usage_timeline -v 2>&1 | tail -10
```

Expected: PASS. (On Windows where TZ env may not work, just confirm Step 3.)

- [ ] **Step 5: Run all metrics tests**

```bash
python -m pytest tests/daemon/test_app_metrics.py 2>&1 | tail -5
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/core/metrics.py
git commit -m "fix(metrics): timeline anchors today on UTC (matches IngestRecord.ingested_at)"
```

---

## Task 3: Backend `_parse_period` extension (Nd|Nw|Nm|Ny)

**Files:**
- Modify: `claude_mnemos/daemon/routes/metrics.py`
- Modify: `tests/daemon/test_app_metrics.py` (add coverage)

- [ ] **Step 1: Failing test for new units**

Add to `tests/daemon/test_app_metrics.py` (or create new test class if file lacks parser tests). Find existing tests near line ~50, add:

```python
def test_parse_period_accepts_weeks():
    from claude_mnemos.daemon.routes.metrics import _parse_period
    assert _parse_period("1w") == 7
    assert _parse_period("4w") == 28


def test_parse_period_accepts_months():
    from claude_mnemos.daemon.routes.metrics import _parse_period
    assert _parse_period("1m") == 30
    assert _parse_period("3m") == 90


def test_parse_period_accepts_years():
    from claude_mnemos.daemon.routes.metrics import _parse_period
    assert _parse_period("1y") == 365


def test_parse_period_accepts_days_unchanged():
    from claude_mnemos.daemon.routes.metrics import _parse_period
    assert _parse_period("30d") == 30
    assert _parse_period("1d") == 1


def test_parse_period_rejects_garbage():
    from fastapi import HTTPException
    from claude_mnemos.daemon.routes.metrics import _parse_period
    import pytest as pt
    for bad in ("0d", "-1d", "abc", "30x", "30dd", ""):
        with pt.raises(HTTPException) as exc:
            _parse_period(bad)
        assert exc.value.status_code == 400
```

- [ ] **Step 2: Run** → expect FAIL on weeks/months/years.

```bash
python -m pytest tests/daemon/test_app_metrics.py::test_parse_period_accepts_weeks -v
```

- [ ] **Step 3: Replace `_parse_period` body**

Edit `claude_mnemos/daemon/routes/metrics.py` lines 26-43:

```python
import re

_PERIOD_RE = re.compile(r"^(?P<n>\d+)(?P<unit>[dwmy])$")
_PERIOD_UNIT_DAYS = {"d": 1, "w": 7, "m": 30, "y": 365}


def _parse_period(period: str) -> int:
    """Parse ``"Nd"`` / ``"Nw"`` / ``"Nm"`` / ``"Ny"`` → number of days.

    Raises HTTP 400 on anything else. Months and years use approximations
    (30 / 365) — sufficient for dashboard windowing, where exact calendar
    boundaries are not load-bearing.
    """
    m = _PERIOD_RE.match(period)
    if m:
        n = int(m.group("n"))
        unit = m.group("unit")
        if n > 0:
            return n * _PERIOD_UNIT_DAYS[unit]
    raise HTTPException(
        status_code=400,
        detail={"error": "invalid_period_format", "expected": "Nd|Nw|Nm|Ny", "got": period},
    )
```

Add `import re` at the top of the file if missing.

- [ ] **Step 4: Run** → expect PASS.

```bash
python -m pytest tests/daemon/test_app_metrics.py -k "parse_period" -v 2>&1 | tail -10
```

- [ ] **Step 5: Run all metrics route tests**

```bash
python -m pytest tests/daemon/test_app_metrics.py 2>&1 | tail -5
```

Expected: all PASS, including pre-existing `Nd` tests (backwards-compatible).

- [ ] **Step 6: Commit**

```bash
git add claude_mnemos/daemon/routes/metrics.py tests/daemon/test_app_metrics.py
git commit -m "feat(metrics): _parse_period accepts Nd|Nw|Nm|Ny (1y unlocks frontend year-pill)"
```

---

## Task 4: Backend traversal test fix

**Files:**
- Modify: `tests/daemon/test_app_snapshots.py`

- [ ] **Step 1: Read current test**

```bash
grep -n "test_delete_snapshot_traversal_rejected" tests/daemon/test_app_snapshots.py
```

Read the test body (likely ~10 lines). It issues a DELETE request with `..%2Fetc-passwd` in the URL and asserts on `status_code in (400, 404)`.

- [ ] **Step 2: Replace HTTP-level test with validator-direct test**

Replace the test body with a unit test against `_validate_snapshot_name`:

```python
def test_delete_snapshot_traversal_rejected():
    """Validator rejects path-traversal segments. Tested at the validator
    level rather than over HTTP because httpx percent-decodes the URL
    before the ASGI app sees it, which makes the routing path the actual
    test variable instead of the validator behaviour we care about.
    """
    from fastapi import HTTPException
    import pytest as pt
    from claude_mnemos.daemon.routes.snapshots import _validate_snapshot_name

    bad_names = ["../etc-passwd", "../../foo", "foo/../bar", "/abs/path"]
    for name in bad_names:
        with pt.raises(HTTPException) as exc:
            _validate_snapshot_name(name)
        assert exc.value.status_code == 400, f"expected 400 for {name!r}"
```

If `_validate_snapshot_name` is private (single underscore — Python convention is "internal but importable"), import works. If it's been renamed since recon, grep:

```bash
grep -n "def _validate_snapshot_name\|def validate_snapshot_name" claude_mnemos/daemon/routes/snapshots.py
```

Use whichever name actually exists.

- [ ] **Step 3: Run**

```bash
python -m pytest tests/daemon/test_app_snapshots.py::test_delete_snapshot_traversal_rejected -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 4: Run all snapshot tests**

```bash
python -m pytest tests/daemon/test_app_snapshots.py 2>&1 | tail -5
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/daemon/test_app_snapshots.py
git commit -m "test: #14e snapshot traversal — test validator directly, not via httpx URL normalization"
```

---

## Task 5: Backend watchdog flaky test fix

**Files:**
- Modify: `tests/daemon/test_watchdog_e2e.py`

- [ ] **Step 1: Read current test**

```bash
grep -n "test_watchdog_e2e_external_modify_detected\|_wait_for\|time.sleep" tests/daemon/test_watchdog_e2e.py
```

Locate:
- The `time.sleep(1.0)` between seed write and external modify (~line 121).
- The `_wait_for(...)` helper and the `limit=20` activity poll (~line 130).

- [ ] **Step 2: Define a "seed-observed" wait predicate**

Just above the `time.sleep(1.0)` line, replace it with a poll that checks `/activity?limit=200&op_type=ingest` for a record matching the seed's session_id.

The exact code depends on the test's existing helpers. Pattern:

```python
def _seed_was_ingested():
    r = client.get("/activity", params={"limit": 200, "op_type": "ingest"})
    if r.status_code != 200:
        return False
    for entry in r.json().get("entries", []):
        if entry.get("session_id") == seed_session_id:
            return True
    return False

# Replace: time.sleep(1.0)
_wait_for(_seed_was_ingested, timeout=5.0, msg="daemon never ingested seed")
```

If the test has its own naming for client / response shape, follow that.

- [ ] **Step 3: Bump the human-edit poll limit**

Find the `_wait_for(has_human_edit, ...)` call and the `client.get("/activity", params={"limit": 20})` inside `has_human_edit`. Change `limit=20` to `limit=200` so accumulated activity entries don't push the human_edit row off the tail.

- [ ] **Step 4: Run the flaky test 5 times in a row**

```bash
for i in 1 2 3 4 5; do
  python -m pytest tests/daemon/test_watchdog_e2e.py::test_watchdog_e2e_external_modify_detected -v 2>&1 | tail -3
done
```

Expected: 5 PASSes. If any fail, read the error and tighten the wait predicate.

- [ ] **Step 5: Run all watchdog tests**

```bash
python -m pytest tests/daemon/test_watchdog_e2e.py 2>&1 | tail -5
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/daemon/test_watchdog_e2e.py
git commit -m "test: #14e watchdog_e2e — poll-based wait + bigger activity limit (close two races)"
```

---

## Task 6: Frontend DeadLetterDetail dt-label localization

**Files:**
- Modify: `frontend/src/pages/DeadLetterDetail.tsx`
- Modify: `frontend/public/locales/{en,uk,ru}.json` (add 3 keys)

- [ ] **Step 1: Read current file**

Look for the `<dl>` block in `frontend/src/pages/DeadLetterDetail.tsx`. Identify which `<dt>` elements render raw English (likely `created_at`, `started_at`, `finished_at` — check exactly).

- [ ] **Step 2: Add locale keys**

Append to `dead_letter` block in each locale:

- en.json:
```json
"created_at": "Created at",
"started_at": "Started at"
```
(`finished_at` already exists from Task 6 of #14b-2 / earlier — verify with `grep`. If missing, add `"finished_at": "Finished at"`. The plan from Task 6 of #14b-2 uses `dead_letter.finished_at: "finished"` — keep whatever's there or rename if you prefer.)

- uk.json: `"created_at": "Створено"`, `"started_at": "Розпочато"`
- ru.json: `"created_at": "Создано"`, `"started_at": "Начато"`

- [ ] **Step 3: Replace raw labels with t() calls**

In `frontend/src/pages/DeadLetterDetail.tsx`, find `<dt>created_at</dt>` (and `started_at`, `finished_at` if raw). Change to:

```tsx
<dt className="text-[hsl(var(--muted-foreground))]">{t("dead_letter.created_at")}</dt>
<dt className="text-[hsl(var(--muted-foreground))]">{t("dead_letter.started_at")}</dt>
<dt className="text-[hsl(var(--muted-foreground))]">{t("dead_letter.finished_at")}</dt>
```

(`kind` is likely already wrapped — only fix raw ones.)

- [ ] **Step 4: Run all tests + tsc**

```bash
cd frontend && pnpm test && pnpm typecheck
```

The existing `DeadLetterDetail.test.tsx` may need its bundle to include the new keys. If the test-bundle's `addResourceBundle` for `dead_letter` doesn't have `created_at`/`started_at`, add them so missing-key warnings don't fire.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/DeadLetterDetail.tsx frontend/public/locales/ frontend/src/__tests__/DeadLetterDetail.test.tsx
git commit -m "i18n(frontend): #14e DeadLetterDetail dt-labels via t()"
```

---

## Task 7: Frontend chart series CSS vars

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/components/widgets/UsageTimelineChart.tsx`

- [ ] **Step 1: Add CSS variables to index.css**

In `frontend/src/index.css`, find the `:root` block (or the equivalent shadcn theme block). Append:

```css
:root {
  /* ...existing vars... */
  --chart-input: #3b82f6;
  --chart-output: #10b981;
  --chart-sessions: #f59e0b;
}

.dark {
  /* ...existing vars... */
  --chart-input: #60a5fa;
  --chart-output: #34d399;
  --chart-sessions: #fbbf24;
}
```

- [ ] **Step 2: Replace hex colors in UsageTimelineChart**

Edit `frontend/src/components/widgets/UsageTimelineChart.tsx`. Find the three color attributes and change:

```tsx
<Bar yAxisId="tokens" dataKey="tokens_input" stackId="t" name={t("metrics.timeline_legend_input")} fill="#3b82f6" />
<Bar yAxisId="tokens" dataKey="tokens_output" stackId="t" name={t("metrics.timeline_legend_output")} fill="#10b981" />
<Line yAxisId="sessions" type="monotone" dataKey="sessions" name={t("metrics.timeline_legend_sessions")} stroke="#f59e0b" strokeWidth={2} />
```

to:

```tsx
<Bar yAxisId="tokens" dataKey="tokens_input" stackId="t" name={t("metrics.timeline_legend_input")} fill="var(--chart-input)" />
<Bar yAxisId="tokens" dataKey="tokens_output" stackId="t" name={t("metrics.timeline_legend_output")} fill="var(--chart-output)" />
<Line yAxisId="sessions" type="monotone" dataKey="sessions" name={t("metrics.timeline_legend_sessions")} stroke="var(--chart-sessions)" strokeWidth={2} />
```

- [ ] **Step 3: Run all tests + tsc + build**

```bash
cd frontend && pnpm test && pnpm typecheck && pnpm build
```

Tests don't assert on colors, so they should still pass. Build should succeed.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/index.css frontend/src/components/widgets/UsageTimelineChart.tsx
git commit -m "style(frontend): #14e chart series colors via CSS vars (theme-aware)"
```

---

## Task 8: Frontend Metrics 1y pill

**Files:**
- Modify: `frontend/src/pages/Metrics.tsx`
- Modify: `frontend/src/__tests__/Metrics.test.tsx`
- Modify: `frontend/public/locales/{en,uk,ru}.json` (add `metrics.period_1y`)

- [ ] **Step 1: Add locale key**

Append to each locale's `metrics` block:

- en.json: `"period_1y": "1 year"`
- uk.json: `"period_1y": "1 рік"`
- ru.json: `"period_1y": "1 год"`

- [ ] **Step 2: Extend PERIODS in Metrics.tsx**

Edit `frontend/src/pages/Metrics.tsx`:

```tsx
const PERIODS = ["7d", "30d", "90d", "1y"] as const;
```

(was `["7d", "30d", "90d"]`.)

The existing render code `{t(\`metrics.period_${p}\`)}` already handles the new key automatically.

- [ ] **Step 3: Update Metrics test bundle**

In `frontend/src/__tests__/Metrics.test.tsx`, find `addResourceBundle({metrics: {...}})` and add:

```ts
period_1y: "1 year",
```

- [ ] **Step 4: Run tests + tsc**

```bash
cd frontend && pnpm test Metrics && pnpm typecheck
```

Existing tests should still pass. The "renders title + period filter + 3 blocks" test still works (4 pills now, all rendered). The "clicking period pill changes timeline query" test still works (it clicks "7 days").

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Metrics.tsx frontend/src/__tests__/Metrics.test.tsx frontend/public/locales/
git commit -m "feat(frontend): #14e Metrics 1y period pill"
```

---

## Task 9: Frontend chart.tsx Partial<TooltipContentProps> comment

**Files:**
- Modify: `frontend/src/components/ui/chart.tsx`

- [ ] **Step 1: Read the current chart.tsx**

Find `function ChartTooltipContent({ active, payload, label }: Partial<TooltipContentProps<number, string>>)`.

- [ ] **Step 2: Add explanatory comment**

Above the `function ChartTooltipContent` line, add:

```tsx
// recharts v3 types `TooltipContentProps` as fully required, but recharts
// injects `active`/`payload`/`label` only at runtime (when used as `content={...}`
// on a `<Tooltip>` element). We widen the prop type to `Partial<>` so the
// component can be used as a JSX child without TS complaining about missing
// required props. Don't remove the `Partial<>` — the JSX usage breaks without it.
```

- [ ] **Step 3: Run typecheck + tests**

```bash
cd frontend && pnpm typecheck && pnpm test
```

No code change, so all tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ui/chart.tsx
git commit -m "docs(frontend): #14e chart.tsx — explain Partial<TooltipContentProps> widening"
```

---

## Task 10: Final verification + acceptance walkthrough

- [ ] **Step 1: Backend full suite**

```bash
cd /d/code/claude-mnemos
python -m pytest tests/ -k "not slow" --ignore=tests/daemon/integration --tb=line 2>&1 | tail -10
```

Expected: 0 failures, 0 errors. (Was 12 failed + 16 errors on main before this plan.)

- [ ] **Step 2: Backend flaky tests — repeat run**

```bash
for i in 1 2 3 4 5; do
  python -m pytest tests/daemon/test_watchdog_e2e.py tests/daemon/test_app_metrics.py::test_usage_timeline tests/daemon/test_app_snapshots.py::test_delete_snapshot_traversal_rejected --tb=line 2>&1 | tail -2
done
```

Expected: 5 consistent PASSes.

- [ ] **Step 3: Frontend full check**

```bash
cd frontend
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

Expected: all green. Vitest count unchanged or +5 (parser tests if those count toward frontend vitest — they don't, they're pytest). Bundle still under 280 KB initial.

- [ ] **Step 4: Acceptance criteria walk-through (design §4)**

1. ✅ Backend pytest 0 failures/0 errors with daemon running.
2. ✅ Watchdog test 5/5 consistent.
3. ✅ Timeline test passes (UTC-anchored).
4. ✅ Traversal test passes (validator-direct).
5. ✅ `_parse_period("1w"/"3m"/"1y")` works.
6. ✅ Per-file `_isolate_home` removed; one autouse fixture.
7. ✅ DeadLetterDetail dt-labels via t().
8. ✅ Chart series use CSS vars.
9. ✅ Metrics has 1y pill.
10. ✅ chart.tsx has explanatory comment on Partial<>.
11. ✅ Backend pytest baseline holds.
12. ✅ Vitest + tsc + ESLint clean.

- [ ] **Step 5: Branch summary**

```bash
git log --oneline main..HEAD
git status
```

~10 commits, working tree clean.

- [ ] **Step 6: Optional commit if anything dangling**

If `pnpm-lock.yaml` updated or any small fixup, commit. Otherwise verification-only.

---

## Spec coverage map

| Design § | Plan task |
|---|---|
| 2.1 conftest autouse | 1 |
| 2.2 timeline UTC | 2 |
| 2.5 period parser | 3 |
| 2.3 traversal test | 4 |
| 2.4 watchdog flaky | 5 |
| 2.6 dt labels i18n | 6 |
| 2.7 chart CSS vars | 7 |
| 2.8 1y pill | 8 |
| 2.9 chart comment | 9 |
| 4 ACs | 10 |
