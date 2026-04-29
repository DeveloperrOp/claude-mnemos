# Plan #14e — Polish & infra cleanup (design)

**Date:** 2026-04-29
**Status:** Design
**Goal:** Close out frontend polish debts from #14d and stabilize backend test infrastructure (CLI test pollution + 3 flaky tests). Last cleanup pass before #13c (SessionStart adaptive context inject — the final spec-v0.2 feature).

---

## 1. Background

After Plans #14a–#14d the dashboard is feature-complete; the only remaining items are:

**Frontend tech debt (from #14d code review and follow-ups):**
- `DeadLetterDetail.tsx` `dt` labels (`created_at`, `started_at`, `finished_at`) render as raw English keys, not via `t()`.
- Hardcoded hex colors in `UsageTimelineChart` series (`#3b82f6`, `#10b981`, `#f59e0b`) — break theme parity if the user toggles dark mode.
- `Partial<TooltipContentProps<...>>` widening in `chart.tsx` is undocumented; future readers will likely "clean it up" and break `<ChartTooltipContent />` JSX usage.
- Backend metrics `_parse_period` accepts only `Nd`. Frontend pills are hardcoded `7d/30d/90d`. Spec §15 wants weeks/months too — extend both.

**Backend test infrastructure (long-standing since #13b-α/β1):**
- 12 `FAILED` + 16 `ERROR` results on `pytest tests/ -k "not slow" --ignore=tests/daemon/integration`. Recon **disproved** the original "HOME isolation" hypothesis. Real cause: CLI write commands (`mnemos project add`, `mnemos settings set`) try the daemon REST API first and only fall back to direct disk writes on `httpx.ConnectError`. On dev machines running the daemon, those writes leak into the real `~/.claude-mnemos/project-map.json` and tests cross-pollute. Production-side `home_config_dir()` lives in one place (`state/projects.py:42`); the leak point is the daemon-first branch in `cli_project.py` / `cli_settings.py`.
- Three flaky tests, all with distinct root causes (not the same race):
  - `test_watchdog_e2e_external_modify_detected` — fixed `time.sleep(1.0)` between seed and modify; `limit=20` activity-poll bound.
  - `test_usage_timeline` — timezone bug in `core/metrics.py::timeline` mixing `date.today()` (local) and UTC `.date()`. Real production bug, not test flake.
  - `test_delete_snapshot_traversal_rejected` — httpx 0.28 percent-decodes `%2F` before sending; ASGI normalizes `..` away; route resolves to `/snapshots/{project}` (POST/GET only) → 405, not 400/404. Test assertion too strict.

### What's deliberately out of scope

- **Help GitHub links** — `https://github.com/` placeholders. Defer until the repo is published.
- **Onboarding "first ingest" step** — feature decision, not polish.
- **ProjectPatch / ProjectDelete UI** — full feature, needs its own design.
- **General test speedup / parallelization** — out of scope.
- **Backend XDG path migration** — the codebase uses `~/.claude-mnemos/` by design; not changing.

---

## 2. Architecture

### 2.1 Backend — global test isolation autouse fixture

Replace the per-file `_isolate_home` fixtures (`tests/test_cli.py`, `tests/test_cli_project.py`, `tests/test_cli_settings.py`) with one autouse fixture in `tests/conftest.py` that applies to **every** CLI-touching test. Recon confirmed the `home_config_dir()` indirection works correctly when `HOME` / `USERPROFILE` is patched — the gap is `MNEMOS_DAEMON_URL`.

The fixture sets:

```python
@pytest.fixture(autouse=True)
def isolate_cli_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("MNEMOS_DAEMON_URL", "http://127.0.0.1:1")  # force ConnectError → offline branch
    monkeypatch.delenv("MNEMOS_VAULT_ROOT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
```

Constraints:
- It must NOT break the daemon-test files in `tests/daemon/` that *want* a real daemon. They run via `httpx.AsyncClient(transport=ASGITransport(app=app))` — they don't read `MNEMOS_DAEMON_URL`, so safe.
- The autouse fixture goes in `tests/conftest.py` (top-level). It propagates to all `tests/**/*.py` automatically.
- Per-file `_isolate_home` fixtures get deleted (no longer needed).

### 2.2 Backend — `usage_timeline` UTC bug fix

`core/metrics.py::timeline` currently:

```python
today = date.today()                                  # local TZ
...
bucket = (today - rec.ingested_at.date()).days        # UTC date
```

This is wrong. `IngestRecord.ingested_at` is `datetime.now(UTC)` (UTC-aware), so `.date()` gives a UTC calendar date. Mixing with `date.today()` (local) creates a 1-day skew when local TZ differs from UTC, depending on the time of day.

Fix: use UTC throughout.

```python
from datetime import UTC, date, datetime, timedelta

def timeline(...):
    today = datetime.now(UTC).date()  # UTC anchor
    ...
```

This eliminates the flake AND closes a real production bug (timeline charts render the wrong day for non-UTC users).

### 2.3 Backend — `test_delete_snapshot_traversal_rejected` fix

The route handler validation works correctly (`_validate_snapshot_name` rejects `..` segments). The flake comes from httpx percent-decoding the test URL before the ASGI app sees it, which routes the DELETE request to `/snapshots/{project}` (no DELETE handler) → 405.

Two clean options:

**Option A (preferred):** test the validator directly. Move the assertion off the HTTP surface:

```python
def test_validate_snapshot_name_rejects_traversal():
    from claude_mnemos.daemon.routes.snapshots import _validate_snapshot_name
    with pytest.raises(HTTPException) as exc:
        _validate_snapshot_name("../etc-passwd")
    assert exc.value.status_code == 400
```

This is the correct level of abstraction — the test is about validator behavior, not URL routing.

**Option B (fallback if validator is private):** widen the assertion to accept `405`:

```python
assert response.status_code in (400, 404, 405)
```

Recommend Option A; fall back to B only if the validator can't be cleanly imported.

### 2.4 Backend — `test_watchdog_e2e_external_modify_detected` fix

Two compounding races:
- Fixed `time.sleep(1.0)` between seed write and external modify.
- `limit=20` cap on the activity poll — if more than 20 entries accumulate, the human_edit row gets pushed off.

Fix:
- Replace fixed sleep with a poll-based `_wait_for(daemon_observed_seed, timeout=5.0)` that hits `/activity?limit=200&op_type=ingest` and waits for the seed write's activity entry to appear (i.e., the daemon has finished processing it before we issue the modify).
- Bump the polling `limit` from 20 to 200 in the human-edit poll.

### 2.5 Backend — period parser extension

`core/metrics.py::_parse_period` accepts `Nd` only. Spec §15 mentions weeks/months. Extend:

```python
import re

_PERIOD_RE = re.compile(r"^(?P<n>\d+)(?P<unit>[dwm])$")

def _parse_period(s: str) -> int:
    """Return number of days for a period string."""
    m = _PERIOD_RE.match(s)
    if not m:
        raise HTTPException(400, "invalid_period_format")
    n = int(m.group("n"))
    unit = m.group("unit")
    if unit == "d": return n
    if unit == "w": return n * 7
    if unit == "m": return n * 30  # calendar-month approximation
    raise HTTPException(400, "invalid_period_format")
```

This unlocks `1w`, `2w`, `1m`, `3m`, `6m`, `12m` etc. Frontend pills follow.

### 2.6 Frontend — DeadLetterDetail dt-label localization

3 raw labels (`kind`, `created_at`, `started_at`, `finished_at`, `error`, `traceback`, `payload`) — actually some already use `t()`. Fix the unlocalized ones. Add 3 new locale keys (en/uk/ru): `dead_letter.created_at`, `dead_letter.started_at`, `dead_letter.finished_at`. Replace raw `<dt>created_at</dt>` strings with `<dt>{t("dead_letter.created_at")}</dt>`.

### 2.7 Frontend — chart series colors via CSS vars

Define 3 series colors in `frontend/src/index.css` as CSS custom properties under `:root` and `.dark`:

```css
:root {
  --chart-input: #3b82f6;
  --chart-output: #10b981;
  --chart-sessions: #f59e0b;
}
.dark {
  --chart-input: #60a5fa;
  --chart-output: #34d399;
  --chart-sessions: #fbbf24;
}
```

Then in `UsageTimelineChart.tsx` reference via `fill="hsl(var(...))"` won't work (these are hex strings, not HSL channels). Cleanest: use a small helper that reads the computed style:

```tsx
const useCssVar = (name: string): string => {
  return useMemo(() => {
    if (typeof window === "undefined") return "";
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "";
  }, [name]);
};
```

Or simpler: since recharts color props accept any CSS color string, render the chart with `fill="var(--chart-input)"` — recharts passes the value through to SVG, and the browser resolves it. Verified pattern (works in recharts 2.x and 3.x).

Skip the React hook; just use `var(--chart-...)` strings directly.

### 2.8 Frontend — period pills extended

After §2.5 backend lands, frontend Metrics page extends pills from `7d|30d|90d` to `7d|30d|90d|1y` (1y = 365d server-side math). Spec keeps pills compact; `1y` is the most common "see all my history" option.

Add locale `metrics.period_1y`: en `"1 year"`, uk `"1 рік"`, ru `"1 год"`.

The page state type changes from `"7d" | "30d" | "90d"` to `"7d" | "30d" | "90d" | "1y"`. Tests update.

### 2.9 Frontend — `Partial<TooltipContentProps>` comment

`frontend/src/components/ui/chart.tsx` — add a 2-line comment above the export explaining why the prop type is widened to `Partial<>` (recharts v3 makes all fields required at type level but injects them at runtime; widening lets `<ChartTooltipContent />` be used as a JSX child of `<ChartTooltip content={...}>` without TS complaints).

---

## 3. Risks

- **Autouse fixture breaks daemon tests.** Mitigation: daemon tests use ASGITransport — they don't read `MNEMOS_DAEMON_URL`, so the env override is invisible to them. Confirmed in recon.
- **Period parser change breaks existing API calls.** Mitigation: existing `Nd` callers still work (`_PERIOD_RE` matches `30d`); only new units unlock. Backwards-compatible.
- **`var(--chart-input)` doesn't resolve in jsdom.** Tests assert on legend labels (text), not colors — so jsdom doesn't matter. Real browser renders correctly.
- **Removing per-file `_isolate_home` fixtures.** Some tests may import them by name. Mitigation: grep before deletion.
- **Timezone fix changes test seed expectations.** `_seed` in `test_app_metrics.py` writes UTC; with timeline now anchored on UTC, the test will pass on any local TZ. May need to update the test if it currently asserts on local-TZ math.

---

## 4. Acceptance criteria

1. ✅ `pytest tests/ -k "not slow" --ignore=tests/daemon/integration` passes 0 failures, 0 errors on dev machine while daemon is running.
2. ✅ `test_watchdog_e2e_external_modify_detected` passes consistently (run 5x in a row).
3. ✅ `test_usage_timeline` passes consistently (Moscow time, late evening).
4. ✅ `test_delete_snapshot_traversal_rejected` passes (validator-direct or widened assertion).
5. ✅ `_parse_period("1w")`, `_parse_period("3m")`, `_parse_period("1y")` work.
6. ✅ Per-file `_isolate_home` fixtures removed; one autouse `tests/conftest.py` fixture covers all.
7. ✅ Frontend `DeadLetterDetail` `dt` labels render via `t()`.
8. ✅ Frontend chart series use `var(--chart-*)` CSS vars (theme-aware).
9. ✅ Frontend Metrics page has `1y` pill.
10. ✅ `chart.tsx` `Partial<TooltipContentProps>` has explanatory comment.
11. ✅ Backend pytest unchanged baseline holds (no regressions).
12. ✅ Frontend Vitest passes; tsc + ESLint clean.

---

## 5. Out of scope / deferred

- Help GitHub links (defer until repo public).
- Onboarding first-ingest step.
- ProjectPatch / ProjectDelete UI.
- Backend XDG migration.
- `_parse_period("Nh")` for hours.
- Real-time chart streaming.

These either aren't polish or need their own design.

---

## 6. File map

**Modified:**
- `tests/conftest.py` — add autouse `isolate_cli_state` fixture.
- `tests/test_cli.py` — remove `project_env` fixture (or simplify to test-specific overrides).
- `tests/test_cli_project.py` — remove per-file `_isolate_home`.
- `tests/test_cli_settings.py` — remove per-file `_isolate_home`.
- `claude_mnemos/core/metrics.py` — UTC anchor + extended `_parse_period`.
- `tests/daemon/test_app_metrics.py` — update `test_usage_timeline` assertions if they encoded local-TZ behavior.
- `tests/daemon/test_app_snapshots.py` — `test_delete_snapshot_traversal_rejected` → either validator-direct or widened.
- `tests/daemon/test_watchdog_e2e.py` — replace fixed sleep with poll-wait; bump activity poll limit.
- `frontend/src/index.css` — add `--chart-*` CSS vars (light + dark).
- `frontend/src/components/widgets/UsageTimelineChart.tsx` — replace hex with `var(--chart-*)`.
- `frontend/src/components/ui/chart.tsx` — comment on `Partial<TooltipContentProps>`.
- `frontend/src/pages/Metrics.tsx` — `PERIODS = [..., "1y"]`.
- `frontend/src/__tests__/Metrics.test.tsx` — locale bundle adds `period_1y`.
- `frontend/src/pages/DeadLetterDetail.tsx` — `dt` labels via `t()`.
- `frontend/public/locales/{en,uk,ru}.json` — add `dead_letter.created_at` etc., `metrics.period_1y`.

**Backend tests verified clean:** `pytest tests/ -k "not slow" --ignore=tests/daemon/integration` returns 0 failures/0 errors.

---

## 7. Spec coverage map

| § | Plan tasks |
|---|---|
| 2.1 conftest autouse | Task 1 |
| 2.2 timeline UTC | Task 2 |
| 2.3 traversal test | Task 3 |
| 2.4 watchdog flaky | Task 4 |
| 2.5 period parser | Task 5 |
| 2.6 dt labels i18n | Task 6 |
| 2.7 chart CSS vars | Task 7 |
| 2.8 1y pill | Task 8 |
| 2.9 chart comment | Task 9 |
| 4 ACs | Task 10 (final verification) |

Roughly 10 tasks. Smaller than #14b/c/d but with backend changes for the first time in this series.

---

(end of design)
