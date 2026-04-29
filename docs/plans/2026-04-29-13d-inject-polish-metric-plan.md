# SessionStart inject polish + §15 compression_ratio metric Implementation Plan (Plan #13d)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** Close 4 small tech debts from #13c (log timestamps, SKIP_SOURCES comment, slug helper dedup, double `read_page` perf) and ship spec §15 compression_ratio metric (per-vault `.inject-metrics.json` + hook write + aggregator + daemon route extension + dashboard surface).

**Architecture:** New `claude_mnemos/state/inject_metrics.py` mirrors `state/activity.py` patterns (Pydantic models, `load`/`save`/`append`, atomic write). `build_page_graph_with_pages` returns a `(graph, parsed_pages)` tuple eliminating double `read_page`. `build_adaptive_context_with_stats` returns `(markdown, InjectStats)`; backward-compat wrapper preserves old API. Hook writes event after every successful inject. `compression_summary(vault, period_days)` aggregates ratio. `/metrics/usage` response extended with `avg_compression_ratio` + `inject_events_count`. `UsageWidget` renders the new fields. Activity entry on inject and timeline endpoint deferred.

**Tech Stack:** Python 3.12, Pydantic v2, pytest. React 19, zod, recharts. Reuses `core/wikilinks.py`, `core/page_io.py`, `state/activity.py` template, `core/metrics.py`. **No new deps** (uuid for IDs, no ULID).

**Design doc:** `docs/plans/2026-04-29-13d-inject-polish-metric-design.md` — read before each task.

---

## Files map

**Create:**
- `claude_mnemos/state/inject_metrics.py` — `InjectMetricEvent`, `InjectMetricsLog`, `INJECT_METRICS_FILENAME`, `MAX_EVENTS`, `RETENTION_DAYS`.
- `tests/test_inject_metrics.py` — load/save/append/cleanup/corrupt tests.
- `tests/test_compression_summary.py` — aggregator tests.

**Modified:**
- `claude_mnemos/core/page_io.py` — add `slug_from_page_path` helper.
- `claude_mnemos/core/graph.py` — add `build_page_graph_with_pages`; replace `_slug_for` with `page_io.slug_from_page_path` import.
- `claude_mnemos/core/session_start.py` — refactor with `InjectStats` + `_with_stats` variant; remove `page_slug_from_path` duplicate; thread parsed pages.
- `claude_mnemos/core/metrics.py` — add `CompressionSummary` + `compression_summary()`.
- `claude_mnemos/daemon/routes/metrics.py` — extend `usage_route` response with two new fields.
- `claude_mnemos/daemon/schemas.py` — extend `UsageSummary`/usage response shape.
- `hooks/session_start.py` — add timestamp to `_log`, `SKIP_SOURCES` comment, call `_with_stats`, write event.
- `frontend/src/types/UsageSummary.ts` — extend zod schema with new fields.
- `frontend/src/components/widgets/UsageWidget.tsx` — render new fields.
- `frontend/public/locales/{en,uk,ru}.json` — `metrics.inject_events`, `metrics.avg_compression`.
- `tests/test_session_start.py`, `tests/test_graph.py`, `tests/test_session_start_hook.py` — updated for new signatures.

---

## Task 1: Hook polish — log timestamps + SKIP_SOURCES comment

**Files:**
- Modify: `hooks/session_start.py`

- [ ] **Step 1: Read current hook**

```bash
sed -n '40,65p' /d/code/claude-mnemos/hooks/session_start.py
```

Confirm: `_log` writes plain `f"{msg}\n"`. `SKIP_SOURCES = frozenset({"resume", "compact", "edit"})` has no comment.

- [ ] **Step 2: Add timestamp to `_log`**

Edit `hooks/session_start.py`. Find:

```python
def _log(msg: str) -> None:
    """Append a line to ~/.claude-mnemos/inject.log. Never raise."""
    try:
        log_path = Path.home() / ".claude-mnemos" / "inject.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except Exception:  # noqa: BLE001
        pass
```

Replace with:

```python
def _log(msg: str) -> None:
    """Append a line to ~/.claude-mnemos/inject.log. Never raise."""
    try:
        from datetime import UTC, datetime
        ts = datetime.now(UTC).isoformat()
        log_path = Path.home() / ".claude-mnemos" / "inject.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except Exception:  # noqa: BLE001
        pass
```

(Inline import of `datetime` keeps the import-cost out of fast-path; this function only fires on error.)

- [ ] **Step 3: Add `SKIP_SOURCES` comment**

Find:

```python
SKIP_SOURCES = frozenset({"resume", "compact", "edit"})
```

Replace with:

```python
# SessionStart payload `source` field — sources we silently skip:
#   resume:  Claude is restoring an existing session; it already has prior
#            context (re-injecting would duplicate).
#   compact: Claude just ran context compaction; injecting would undo what
#            the user asked for.
#   edit:    PostToolUse-triggered partial source — not a fresh session, the
#            model is mid-flight and any inject would land in an unpredictable
#            position.
SKIP_SOURCES = frozenset({"resume", "compact", "edit"})
```

- [ ] **Step 4: Smoke check the hook still parses**

```bash
python -m py_compile /d/code/claude-mnemos/hooks/session_start.py
```

Expected: no output.

- [ ] **Step 5: Run hook integration tests**

```bash
cd /d/code/claude-mnemos
python -m pytest tests/test_session_start_hook.py -v 2>&1 | tail -10
```

Expected: 5 PASS (the existing tests don't pin log format).

- [ ] **Step 6: Commit**

```bash
git add hooks/session_start.py
git commit -m "chore(hooks): #13d inject log ISO timestamps + SKIP_SOURCES rationale comment"
```

---

## Task 2: Slug helper dedup — single canonical path-slug helper

**Files:**
- Modify: `claude_mnemos/core/page_io.py` (add helper)
- Modify: `claude_mnemos/core/graph.py` (drop `_slug_for`, import from page_io)
- Modify: `claude_mnemos/core/session_start.py` (drop `page_slug_from_path`, import from page_io)
- Modify: `tests/test_session_start.py` (re-import path)
- Modify: `tests/test_graph.py` (re-import path if test imports the private helper)

- [ ] **Step 1: Read current duplicates**

```bash
grep -n "_slug_for\|page_slug_from_path" /d/code/claude-mnemos/claude_mnemos/core/graph.py /d/code/claude-mnemos/claude_mnemos/core/session_start.py
```

Confirm: `core/graph.py` has `_slug_for(vault, page_path)` (private); `core/session_start.py` has public `page_slug_from_path(vault, page_path)` — same impl.

- [ ] **Step 2: Add canonical helper to `core/page_io.py`**

Edit `claude_mnemos/core/page_io.py`. After existing imports + before `class PageParseError`, add:

```python
def slug_from_page_path(vault: Path, page_path: Path) -> str:
    """Slug = relative path under ``vault/wiki/`` without ``.md`` suffix.

    Example: ``vault/wiki/concepts/foo.md`` → ``concepts/foo``.
    Always uses forward slashes (Windows-safe).
    """
    rel = page_path.relative_to(vault / "wiki")
    return str(rel.with_suffix("")).replace("\\", "/")
```

- [ ] **Step 3: Drop `_slug_for` in `core/graph.py`, import from `page_io`**

Edit `claude_mnemos/core/graph.py`. Replace:

```python
from claude_mnemos.core.page_io import PageParseError, read_page
from claude_mnemos.core.wikilinks import extract_wikilinks


def _slug_for(vault: Path, page_path: Path) -> str:
    """Return the slug for a vault-relative page (path under ``wiki/`` w/o .md)."""
    rel = page_path.relative_to(vault / "wiki")
    return str(rel.with_suffix("")).replace("\\", "/")
```

with:

```python
from claude_mnemos.core.page_io import PageParseError, read_page, slug_from_page_path
from claude_mnemos.core.wikilinks import extract_wikilinks
```

Then in `build_page_graph` body, replace `slug = _slug_for(vault, page_path)` with `slug = slug_from_page_path(vault, page_path)`.

- [ ] **Step 4: Drop `page_slug_from_path` in `core/session_start.py`, import from `page_io`**

Edit `claude_mnemos/core/session_start.py`. Find:

```python
def page_slug_from_path(vault: Path, page_path: Path) -> str:
    """Slug = relative path under ``vault/wiki/`` without ``.md`` suffix.

    Example: ``vault/wiki/concepts/foo.md`` → ``concepts/foo``.
    Always uses forward slashes (Windows safe).
    """
    rel = page_path.relative_to(vault / "wiki")
    return str(rel.with_suffix("")).replace("\\", "/")
```

Delete this function. Then in the imports section near top, replace existing `page_io` import line with:

```python
from claude_mnemos.core.page_io import ParsedPage, PageParseError, read_page, slug_from_page_path
```

(Or whatever the existing import line is — preserve other names being imported.) Add `slug_from_page_path` to the export list at module level if there's one (module-level functions are public via name; nothing else needed).

- [ ] **Step 5: Update test imports**

Find imports of `page_slug_from_path` in tests:

```bash
grep -rn "page_slug_from_path" /d/code/claude-mnemos/tests/
```

Likely in `tests/test_session_start.py`. Change the import:

```python
from claude_mnemos.core.session_start import (
    FLAVOR_WEIGHTS,
    build_adaptive_context,
    page_summary,
    score_page,
)
from claude_mnemos.core.page_io import slug_from_page_path
```

(Drop `page_slug_from_path` from the session_start import; pull `slug_from_page_path` from page_io.) Replace any reference in test body from `page_slug_from_path(...)` to `slug_from_page_path(...)`.

- [ ] **Step 6: Run tests**

```bash
cd /d/code/claude-mnemos
python -m pytest tests/test_session_start.py tests/test_graph.py tests/test_page_io.py -v 2>&1 | tail -15
```

Expected: all PASS. (`test_page_io.py` may not exist — that's fine.)

- [ ] **Step 7: Run wider suite to confirm no regression**

```bash
python -m pytest tests/ -k "not slow" --ignore=tests/daemon/integration --tb=line 2>&1 | tail -3
```

Expected: 1269 passed (or 1268 if `page_slug_from_path` had its own test that's now gone — adjust the count tolerance).

- [ ] **Step 8: Commit**

```bash
git add claude_mnemos/core/page_io.py claude_mnemos/core/graph.py claude_mnemos/core/session_start.py tests/test_session_start.py tests/test_graph.py
git commit -m "refactor(core): #13d single canonical slug_from_page_path in page_io"
```

---

## Task 3: `build_page_graph_with_pages` — thread parsed pages through

**Files:**
- Modify: `claude_mnemos/core/graph.py` (add new function alongside existing `build_page_graph`)
- Modify: `tests/test_graph.py` (add tests for new variant)

- [ ] **Step 1: Failing test**

Append to `tests/test_graph.py`:

```python
from claude_mnemos.core.graph import build_page_graph_with_pages


def test_build_page_graph_with_pages_returns_pair(tmp_path: Path) -> None:
    _write_page(tmp_path, "concepts/a", body="See [[concepts/b]]")
    _write_page(tmp_path, "concepts/b", body="bravo")
    graph, pages = build_page_graph_with_pages(tmp_path)
    assert "concepts/b" in graph["concepts/a"]
    assert "concepts/a" in pages
    assert "concepts/b" in pages
    assert pages["concepts/a"].body == "See [[concepts/b]]"


def test_build_page_graph_with_pages_skips_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "wiki" / "broken.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("not yaml frontmatter\nbody only\n", encoding="utf-8")
    _write_page(tmp_path, "concepts/a")
    graph, pages = build_page_graph_with_pages(tmp_path)
    assert "concepts/a" in pages
    assert "broken" not in pages
    # graph also skips broken
    assert "broken" not in graph


def test_build_page_graph_with_pages_empty_vault(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir()
    graph, pages = build_page_graph_with_pages(tmp_path)
    assert graph == {}
    assert pages == {}
```

- [ ] **Step 2: Run** → expect FAIL (ImportError).

```bash
python -m pytest tests/test_graph.py::test_build_page_graph_with_pages_returns_pair -v 2>&1 | tail -5
```

- [ ] **Step 3: Implement `build_page_graph_with_pages`**

Append to `claude_mnemos/core/graph.py` (after existing `build_page_graph`):

```python
def build_page_graph_with_pages(
    vault: Path,
) -> tuple[dict[str, set[str]], dict[str, "ParsedPage"]]:
    """Same undirected adjacency as :func:`build_page_graph`, plus a
    ``slug → ParsedPage`` map for every page that parsed successfully.

    Use this variant when you also need page bodies (e.g. for scoring) —
    avoids re-reading every file. Pages with malformed frontmatter are
    skipped from BOTH the graph and the pages map.
    """
    graph: dict[str, set[str]] = {}
    pages: dict[str, "ParsedPage"] = {}
    wiki_root = vault / "wiki"
    if not wiki_root.is_dir():
        return graph, pages

    for page_path in wiki_root.rglob("*.md"):
        try:
            parsed = read_page(page_path)
        except PageParseError:
            continue
        slug = slug_from_page_path(vault, page_path)
        graph.setdefault(slug, set())
        pages[slug] = parsed

        for link in extract_wikilinks(parsed.body):
            target = link.target.strip()
            if not target:
                continue
            graph[slug].add(target)
            graph.setdefault(target, set()).add(slug)

        for related in parsed.frontmatter.related:
            r = related.strip()
            if not r:
                continue
            graph[slug].add(r)
            graph.setdefault(r, set()).add(slug)

    return graph, pages
```

Add the import for `ParsedPage` to the imports near the top of the file:

```python
from claude_mnemos.core.page_io import ParsedPage, PageParseError, read_page, slug_from_page_path
```

(`ParsedPage` may already be imported — verify; if so, no change.)

- [ ] **Step 4: Run** → expect PASS.

```bash
python -m pytest tests/test_graph.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/graph.py tests/test_graph.py
git commit -m "feat(core): #13d build_page_graph_with_pages — also returns parsed-pages map"
```

---

## Task 4: `build_adaptive_context_with_stats` — instrumented variant

**Files:**
- Modify: `claude_mnemos/core/session_start.py` (add `InjectStats`, refactor `build_adaptive_context`)
- Modify: `tests/test_session_start.py` (add tests for stats; existing tests still pass via wrapper)

- [ ] **Step 1: Failing test**

Append to `tests/test_session_start.py`:

```python
from claude_mnemos.core.session_start import (
    InjectStats,
    build_adaptive_context_with_stats,
)


def test_build_adaptive_context_with_stats_returns_pair(tmp_path: Path) -> None:
    _write_full_page(tmp_path, "concepts/a", body="alpha body")
    _seed_manifest(tmp_path, sessions=[("s1", ["wiki/concepts/a.md"])])
    context, stats = build_adaptive_context_with_stats(
        tmp_path, cwd=tmp_path, max_chars=2000,
    )
    assert "concepts/a" in context
    assert isinstance(stats, InjectStats)
    assert stats.tokens_actual > 0
    assert stats.tokens_full >= stats.tokens_actual
    assert stats.candidates_total >= 1
    assert stats.candidates_packed >= 1


def test_build_adaptive_context_with_stats_empty_vault(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir()
    context, stats = build_adaptive_context_with_stats(
        tmp_path, cwd=tmp_path, max_chars=1000,
    )
    assert context == ""
    assert stats.mode == "empty"
    assert stats.tokens_full == 0
    assert stats.tokens_actual == 0
    assert stats.candidates_total == 0
    assert stats.candidates_packed == 0


def test_build_adaptive_context_with_stats_full_mode(tmp_path: Path) -> None:
    """When all candidates fit under budget, mode == 'full'."""
    _write_full_page(tmp_path, "concepts/a", body="short body")
    _seed_manifest(tmp_path, sessions=[("s1", ["wiki/concepts/a.md"])])
    _, stats = build_adaptive_context_with_stats(
        tmp_path, cwd=tmp_path, max_chars=10_000,
    )
    assert stats.mode == "full"
    assert stats.tokens_full == stats.tokens_actual


def test_build_adaptive_context_with_stats_trimmed_mode(tmp_path: Path) -> None:
    """When budget is too small for all candidates, mode == 'trimmed'."""
    for i in range(20):
        _write_full_page(tmp_path, f"concepts/p{i}", body="x" * 5000)
    pages_seeded = [f"wiki/concepts/p{i}.md" for i in range(20)]
    _seed_manifest(tmp_path, sessions=[("s1", pages_seeded)])
    _, stats = build_adaptive_context_with_stats(
        tmp_path, cwd=tmp_path, max_chars=3000,
    )
    assert stats.mode == "trimmed"
    assert stats.tokens_full > stats.tokens_actual
    assert stats.candidates_packed < stats.candidates_total


def test_build_adaptive_context_wrapper_drops_stats(tmp_path: Path) -> None:
    """Backward-compat wrapper still returns plain string."""
    _write_full_page(tmp_path, "concepts/a", body="alpha")
    _seed_manifest(tmp_path, sessions=[("s1", ["wiki/concepts/a.md"])])
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=2000)
    assert isinstance(out, str)
    assert "concepts/a" in out
```

- [ ] **Step 2: Run** → expect FAIL (ImportError on `InjectStats`).

```bash
python -m pytest tests/test_session_start.py -k "with_stats or wrapper" -v 2>&1 | tail -10
```

- [ ] **Step 3: Refactor `build_adaptive_context`**

Edit `claude_mnemos/core/session_start.py`. Add at top after existing imports:

```python
import math
from dataclasses import dataclass
from typing import Literal
```

(`math` and `dataclass` may already be imported — preserve.) Add type alias:

```python
InjectMode = Literal["empty", "full", "trimmed"]


@dataclass(frozen=True)
class InjectStats:
    """Counts emitted alongside the inject context for telemetry (§15)."""
    tokens_full: int       # ceil(chars_full / 4)
    tokens_actual: int     # ceil(chars_actual / 4)
    candidates_total: int
    candidates_packed: int
    mode: InjectMode


_EMPTY_STATS = InjectStats(
    tokens_full=0,
    tokens_actual=0,
    candidates_total=0,
    candidates_packed=0,
    mode="empty",
)
```

Then **replace the entire `build_adaptive_context` body** with:

```python
def build_adaptive_context_with_stats(
    vault: Path,
    *,
    cwd: Path,
    max_chars: int = 40_000,
    recent_sessions: int = DEFAULT_RECENT_SESSIONS,
    graph_hops: int = DEFAULT_GRAPH_HOPS,
) -> tuple[str, InjectStats]:
    """Same as :func:`build_adaptive_context` but also returns
    :class:`InjectStats` for telemetry. Uses the parsed-pages map from
    :func:`build_page_graph_with_pages` to avoid double-reading files.
    """
    wiki_root = vault / "wiki"
    if not wiki_root.is_dir():
        return "", _EMPTY_STATS

    seeds = _seeds_from_manifest(vault, recent=recent_sessions)
    if not seeds:
        return "", _EMPTY_STATS

    graph, pages = build_page_graph_with_pages(vault)
    candidates = pages_within_k_hops(graph, seeds, k=graph_hops)
    if not candidates:
        return "", _EMPTY_STATS

    cwd_seg = _cwd_segment(cwd)
    now = datetime.now(UTC)

    scored: list[tuple[float, str, ParsedPage]] = []
    for slug, hop in candidates.items():
        parsed = pages.get(slug)
        if parsed is None:
            # graph contains slugs without their own files (wikilink targets);
            # only score actual pages we have parsed.
            continue
        score = score_page(
            parsed,
            hop_distance=hop,
            cwd_segment=cwd_seg,
            now=now,
        )
        scored.append((score, slug, parsed))

    if not scored:
        return "", _EMPTY_STATS

    scored.sort(key=lambda t: t[0], reverse=True)

    header = "# Project context (mnemos)\n\nRecent sessions touched these pages:\n"
    if len(header) >= max_chars:
        return "", _EMPTY_STATS

    full_body_quota = 3
    blocks: list[tuple[str, str]] = []  # (slug, block)
    for i, (_score, slug, parsed) in enumerate(scored):
        if i < full_body_quota:
            block = f"\n## [[{slug}]]\n\n{parsed.body}\n"
        else:
            summary = page_summary(parsed, max_chars=SUMMARY_CHARS)
            block = f"\n- [[{slug}]] — {summary}\n"
        blocks.append((slug, block))

    chars_full = len(header) + sum(len(b) for _, b in blocks)

    parts: list[str] = [header]
    used = len(header)
    packed = 0
    for _slug, block in blocks:
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
        packed += 1

    chars_actual = used  # final emitted length (before strip; strip diff is tiny)
    context = "".join(parts).strip() + "\n"
    # Strip can shave a few chars; recompute actual on emitted string.
    chars_actual = len(context)

    if packed == len(blocks):
        mode: InjectMode = "full"
    else:
        mode = "trimmed"

    stats = InjectStats(
        tokens_full=_ceil_div(chars_full, 4),
        tokens_actual=_ceil_div(chars_actual, 4),
        candidates_total=len(scored),
        candidates_packed=packed,
        mode=mode,
    )
    return context, stats


def _ceil_div(n: int, divisor: int) -> int:
    if n <= 0:
        return 0
    return (n + divisor - 1) // divisor


def build_adaptive_context(
    vault: Path,
    *,
    cwd: Path,
    max_chars: int = 40_000,
    recent_sessions: int = DEFAULT_RECENT_SESSIONS,
    graph_hops: int = DEFAULT_GRAPH_HOPS,
) -> str:
    """Backward-compatible wrapper — drops the stats. New code should call
    :func:`build_adaptive_context_with_stats` directly.
    """
    context, _ = build_adaptive_context_with_stats(
        vault,
        cwd=cwd,
        max_chars=max_chars,
        recent_sessions=recent_sessions,
        graph_hops=graph_hops,
    )
    return context
```

Replace `build_page_graph(vault)` call with `build_page_graph_with_pages(vault)` and update the import line near top:

```python
from claude_mnemos.core.graph import build_page_graph_with_pages, pages_within_k_hops
```

(Drop unused `build_page_graph` from the import if it's no longer used in this file.)

- [ ] **Step 4: Run** → expect PASS.

```bash
python -m pytest tests/test_session_start.py -v 2>&1 | tail -20
```

All session_start tests pass (existing + new 5).

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/session_start.py tests/test_session_start.py
git commit -m "feat(core): #13d build_adaptive_context_with_stats — return InjectStats + drop double read_page"
```

---

## Task 5: `state/inject_metrics.py` — per-vault state file

**Files:**
- Create: `claude_mnemos/state/inject_metrics.py`
- Create: `tests/test_inject_metrics.py`

- [ ] **Step 1: Failing test**

`tests/test_inject_metrics.py`:

```python
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_mnemos.state.inject_metrics import (
    INJECT_METRICS_FILENAME,
    MAX_EVENTS,
    RETENTION_DAYS,
    InjectMetricEvent,
    InjectMetricsCorruptError,
    InjectMetricsLog,
)


def _make_event(*, idx: int = 0, ts: datetime | None = None) -> InjectMetricEvent:
    return InjectMetricEvent(
        id=f"evt-{idx:06d}",
        timestamp=ts or datetime.now(UTC),
        session_id=f"s-{idx}",
        operation="session_start",
        mode="full",
        tokens_full=1000,
        tokens_actual=200,
        candidates_total=10,
        candidates_packed=10,
    )


def test_load_empty_vault_returns_empty_log(tmp_path: Path) -> None:
    log = InjectMetricsLog.load(tmp_path)
    assert log.events == []


def test_save_and_reload_roundtrip(tmp_path: Path) -> None:
    log = InjectMetricsLog()
    log.events.append(_make_event(idx=1))
    log.save(tmp_path)

    fresh = InjectMetricsLog.load(tmp_path)
    assert len(fresh.events) == 1
    assert fresh.events[0].id == "evt-000001"


def test_append_to_vault_persists(tmp_path: Path) -> None:
    InjectMetricsLog.append_to_vault(tmp_path, _make_event(idx=1))
    InjectMetricsLog.append_to_vault(tmp_path, _make_event(idx=2))
    log = InjectMetricsLog.load(tmp_path)
    assert [e.id for e in log.events] == ["evt-000001", "evt-000002"]


def test_append_rejects_duplicate_id(tmp_path: Path) -> None:
    InjectMetricsLog.append_to_vault(tmp_path, _make_event(idx=1))
    with pytest.raises(ValueError):
        InjectMetricsLog.append_to_vault(tmp_path, _make_event(idx=1))


def test_save_drops_events_older_than_retention(tmp_path: Path) -> None:
    log = InjectMetricsLog()
    old_ts = datetime.now(UTC) - timedelta(days=RETENTION_DAYS + 5)
    log.events.append(_make_event(idx=0, ts=old_ts))
    log.events.append(_make_event(idx=1))  # fresh
    log.save(tmp_path)

    fresh = InjectMetricsLog.load(tmp_path)
    assert len(fresh.events) == 1
    assert fresh.events[0].id == "evt-000001"


def test_save_caps_at_max_events(tmp_path: Path) -> None:
    log = InjectMetricsLog()
    for i in range(MAX_EVENTS + 50):
        log.events.append(_make_event(idx=i))
    log.save(tmp_path)

    fresh = InjectMetricsLog.load(tmp_path)
    assert len(fresh.events) == MAX_EVENTS
    # oldest dropped: first kept index = 50
    assert fresh.events[0].id == f"evt-{50:06d}"


def test_load_corrupt_raises(tmp_path: Path) -> None:
    (tmp_path / INJECT_METRICS_FILENAME).write_text("not json", encoding="utf-8")
    with pytest.raises(InjectMetricsCorruptError):
        InjectMetricsLog.load(tmp_path)


def test_load_invalid_schema_raises(tmp_path: Path) -> None:
    (tmp_path / INJECT_METRICS_FILENAME).write_text(
        json.dumps({"version": 1, "events": [{"id": "x"}]}),  # missing required fields
        encoding="utf-8",
    )
    with pytest.raises(InjectMetricsCorruptError):
        InjectMetricsLog.load(tmp_path)
```

- [ ] **Step 2: Run** → expect FAIL.

```bash
python -m pytest tests/test_inject_metrics.py -v 2>&1 | tail -15
```

- [ ] **Step 3: Implement `claude_mnemos/state/inject_metrics.py`**

```python
"""Per-vault inject-metrics log (Plan #13d, spec §15).

Records every SessionStart inject event so the dashboard can compute
``avg_compression_ratio = mean(tokens_full / tokens_actual)`` and per-period
event counts. Mirrors the patterns in :mod:`claude_mnemos.state.activity`.

Per-vault file ``.inject-metrics.json`` (mnemos convention overrides spec's
literal ``state/inject-metrics.json`` global path; consistent with the
multi-vault refactor in Plan #13b-β1 where every state file lives at vault
root).

Retention: events older than ``RETENTION_DAYS`` (365) are dropped on every
save. Hard cap ``MAX_EVENTS`` (10000) — oldest dropped when exceeded — to
bound disk on extreme usage.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claude_mnemos.core.atomic import atomic_write

INJECT_METRICS_FILENAME = ".inject-metrics.json"
RETENTION_DAYS = 365
MAX_EVENTS = 10_000


InjectMode = Literal["full", "trimmed", "empty"]
InjectOperation = Literal["session_start"]


class InjectMetricsCorruptError(ValueError):
    """Raised when the inject-metrics log file is unreadable / fails schema."""


class InjectMetricEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    timestamp: datetime
    session_id: str | None
    operation: InjectOperation
    mode: InjectMode
    tokens_full: int = Field(ge=0)
    tokens_actual: int = Field(ge=0)
    candidates_total: int = Field(ge=0)
    candidates_packed: int = Field(ge=0)


class InjectMetricsLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    events: list[InjectMetricEvent] = Field(default_factory=list)

    @classmethod
    def load(cls, vault_root: Path) -> InjectMetricsLog:
        path = vault_root / INJECT_METRICS_FILENAME
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InjectMetricsCorruptError(
                f"inject-metrics log at {path} is not valid JSON: {exc}"
            ) from exc
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise InjectMetricsCorruptError(
                f"inject-metrics log at {path} fails schema: {exc}"
            ) from exc

    def serialize_to_string(self) -> str:
        return (
            json.dumps(
                self.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=False,
            )
            + "\n"
        )

    def save(self, vault_root: Path) -> None:
        """Apply retention + cap, then atomically write."""
        self._apply_retention()
        self._apply_cap()
        path = vault_root / INJECT_METRICS_FILENAME
        atomic_write(path, self.serialize_to_string())

    def append(self, event: InjectMetricEvent) -> None:
        if any(e.id == event.id for e in self.events):
            raise ValueError(
                f"inject-metrics log already contains event id {event.id}"
            )
        self.events.append(event)

    @classmethod
    def append_to_vault(cls, vault_root: Path, event: InjectMetricEvent) -> None:
        """Convenience: load → append → save."""
        log = cls.load(vault_root)
        log.append(event)
        log.save(vault_root)

    def _apply_retention(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
        self.events = [e for e in self.events if e.timestamp >= cutoff]

    def _apply_cap(self) -> None:
        if len(self.events) > MAX_EVENTS:
            # Keep the most-recent MAX_EVENTS by drop-from-head (events list
            # is ingest-order, not necessarily timestamp-sorted, but for our
            # use case the difference is negligible).
            self.events = self.events[-MAX_EVENTS:]
```

- [ ] **Step 4: Run** → expect PASS.

```bash
python -m pytest tests/test_inject_metrics.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/state/inject_metrics.py tests/test_inject_metrics.py
git commit -m "feat(state): #13d InjectMetricsLog — per-vault .inject-metrics.json with retention"
```

---

## Task 6: Hook writes inject events

**Files:**
- Modify: `hooks/session_start.py`
- Modify: `tests/test_session_start_hook.py`

- [ ] **Step 1: Failing test — extend hook tests**

Append to `tests/test_session_start_hook.py`:

```python
from claude_mnemos.state.inject_metrics import InjectMetricsLog


def test_hook_writes_inject_event(tmp_path: Path, register_project) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cwd = tmp_path / "code" / "alpha"
    cwd.mkdir(parents=True)
    register_project("alpha", vault, cwd_patterns=[str(cwd)])

    _write_full_page(vault, "concepts/a", body="alpha context body")
    _seed_manifest(vault, pages=["wiki/concepts/a.md"])

    payload = {"cwd": str(cwd), "session_id": "test-sess-1", "source": "startup"}
    rc, stdout, _ = _run_hook(payload)
    assert rc == 0
    assert stdout

    log = InjectMetricsLog.load(vault)
    assert len(log.events) == 1
    evt = log.events[0]
    assert evt.session_id == "test-sess-1"
    assert evt.operation == "session_start"
    assert evt.mode in ("full", "trimmed")
    assert evt.tokens_actual > 0
    assert evt.tokens_full >= evt.tokens_actual


def test_hook_does_not_write_event_on_skip(tmp_path: Path, register_project) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cwd = tmp_path / "code" / "alpha"
    cwd.mkdir(parents=True)
    register_project("alpha", vault, cwd_patterns=[str(cwd)])

    _write_full_page(vault, "concepts/a")
    _seed_manifest(vault, pages=["wiki/concepts/a.md"])

    payload = {"cwd": str(cwd), "source": "resume"}
    rc, stdout, _ = _run_hook(payload)
    assert rc == 0
    assert stdout == ""

    log = InjectMetricsLog.load(vault)
    assert log.events == []
```

- [ ] **Step 2: Run** → expect FAIL.

```bash
python -m pytest tests/test_session_start_hook.py::test_hook_writes_inject_event -v 2>&1 | tail -10
```

- [ ] **Step 3: Update hook to call `_with_stats` and write event**

Edit `hooks/session_start.py`. Find:

```python
    try:
        context = build_adaptive_context(
            Path(project.vault_root),
            cwd=cwd,
            max_chars=DEFAULT_MAX_CHARS,
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"build failed: {exc}")
        return 0

    if not context:
        return 0

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(output))
    sys.stdout.flush()
    return 0
```

Replace with:

```python
    try:
        from claude_mnemos.core.session_start import (
            build_adaptive_context_with_stats,
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"import failed: {exc}")
        return 0

    try:
        context, stats = build_adaptive_context_with_stats(
            Path(project.vault_root),
            cwd=cwd,
            max_chars=DEFAULT_MAX_CHARS,
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"build failed: {exc}")
        return 0

    if not context:
        return 0

    # Best-effort metric write — failure does not block the inject.
    try:
        from datetime import UTC, datetime
        from uuid import uuid4
        from claude_mnemos.state.inject_metrics import (
            InjectMetricEvent,
            InjectMetricsLog,
        )
        event = InjectMetricEvent(
            id=uuid4().hex,
            timestamp=datetime.now(UTC),
            session_id=payload.get("session_id"),
            operation="session_start",
            mode=stats.mode,
            tokens_full=stats.tokens_full,
            tokens_actual=stats.tokens_actual,
            candidates_total=stats.candidates_total,
            candidates_packed=stats.candidates_packed,
        )
        InjectMetricsLog.append_to_vault(Path(project.vault_root), event)
    except Exception as exc:  # noqa: BLE001
        _log(f"metric write failed: {exc}")

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(output))
    sys.stdout.flush()
    return 0
```

(The earlier import block of `build_adaptive_context` should be removed — duplicate import alias gone. The new block imports `_with_stats` directly.)

- [ ] **Step 4: Run** → expect PASS.

```bash
python -m pytest tests/test_session_start_hook.py -v 2>&1 | tail -15
```

All 7 hook tests pass (5 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add hooks/session_start.py tests/test_session_start_hook.py
git commit -m "feat(hooks): #13d hook writes InjectMetricEvent to .inject-metrics.json"
```

---

## Task 7: `compression_summary` aggregator in core/metrics.py

**Files:**
- Modify: `claude_mnemos/core/metrics.py` (add `CompressionSummary` + function)
- Create: `tests/test_compression_summary.py`

- [ ] **Step 1: Failing test**

`tests/test_compression_summary.py`:

```python
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from claude_mnemos.core.metrics import CompressionSummary, compression_summary
from claude_mnemos.state.inject_metrics import (
    InjectMetricEvent,
    InjectMetricsLog,
)


def _make_event(
    *,
    idx: int,
    ts: datetime,
    tokens_full: int = 1000,
    tokens_actual: int = 200,
    session_id: str | None = None,
) -> InjectMetricEvent:
    return InjectMetricEvent(
        id=f"evt-{idx:06d}",
        timestamp=ts,
        session_id=session_id or f"s-{idx}",
        operation="session_start",
        mode="full",
        tokens_full=tokens_full,
        tokens_actual=tokens_actual,
        candidates_total=10,
        candidates_packed=10,
    )


def _seed(vault: Path, events: list[InjectMetricEvent]) -> None:
    log = InjectMetricsLog(events=events)
    log.save(vault)


def test_compression_summary_empty(tmp_path: Path) -> None:
    out = compression_summary(tmp_path, period_days=30)
    assert isinstance(out, CompressionSummary)
    assert out.events_count == 0
    assert out.sessions_covered == 0
    assert out.avg_compression_ratio is None
    assert out.total_tokens_full == 0
    assert out.total_tokens_actual == 0


def test_compression_summary_one_event(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _seed(tmp_path, [_make_event(idx=1, ts=now, tokens_full=1000, tokens_actual=200)])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 1
    assert out.sessions_covered == 1
    assert out.avg_compression_ratio == 5.0
    assert out.total_tokens_full == 1000
    assert out.total_tokens_actual == 200


def test_compression_summary_avg_is_mean_of_ratios(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _seed(tmp_path, [
        _make_event(idx=1, ts=now, tokens_full=1000, tokens_actual=200),  # ratio 5
        _make_event(idx=2, ts=now, tokens_full=600, tokens_actual=200),   # ratio 3
    ])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 2
    assert out.avg_compression_ratio == 4.0  # mean of 5 and 3


def test_compression_summary_excludes_old_events(tmp_path: Path) -> None:
    today = datetime.now(UTC)
    old = today - timedelta(days=60)
    _seed(tmp_path, [
        _make_event(idx=1, ts=old, tokens_full=999, tokens_actual=99),
        _make_event(idx=2, ts=today, tokens_full=1000, tokens_actual=200),
    ])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 1
    assert out.avg_compression_ratio == 5.0


def test_compression_summary_skips_zero_actual(tmp_path: Path) -> None:
    """Events with tokens_actual == 0 are counted in events_count but
    excluded from avg_compression_ratio (avoid division by zero)."""
    now = datetime.now(UTC)
    _seed(tmp_path, [
        _make_event(idx=1, ts=now, tokens_full=500, tokens_actual=0),
        _make_event(idx=2, ts=now, tokens_full=1000, tokens_actual=200),
    ])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 2  # both counted
    assert out.avg_compression_ratio == 5.0  # only the valid one
    assert out.total_tokens_full == 1500
    assert out.total_tokens_actual == 200


def test_compression_summary_all_zero_actual_returns_none(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _seed(tmp_path, [_make_event(idx=1, ts=now, tokens_full=500, tokens_actual=0)])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 1
    assert out.avg_compression_ratio is None


def test_compression_summary_sessions_covered_counts_unique(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _seed(tmp_path, [
        _make_event(idx=1, ts=now, session_id="s-shared"),
        _make_event(idx=2, ts=now, session_id="s-shared"),
        _make_event(idx=3, ts=now, session_id="s-other"),
    ])
    out = compression_summary(tmp_path, period_days=30)
    assert out.events_count == 3
    assert out.sessions_covered == 2
```

- [ ] **Step 2: Run** → expect FAIL.

```bash
python -m pytest tests/test_compression_summary.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement aggregator**

Edit `claude_mnemos/core/metrics.py`. Add at top, after existing imports:

```python
from claude_mnemos.state.inject_metrics import InjectMetricsLog
```

Add the model class (anywhere in the existing model section, e.g. after `SessionMetric`):

```python
class CompressionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_days: int
    events_count: int
    sessions_covered: int
    avg_compression_ratio: float | None
    total_tokens_full: int
    total_tokens_actual: int
```

Add the aggregator function (anywhere after `timeline()`):

```python
def compression_summary(
    vault: Path,
    *,
    period_days: int = 30,
    today: date_class | None = None,
) -> CompressionSummary:
    """Aggregate inject-metric events over the last ``period_days`` days.

    ``avg_compression_ratio`` is the mean of ``tokens_full / tokens_actual``
    over events with ``tokens_actual > 0``. Returns ``None`` when no such
    events exist (no division by zero).

    Total token counts include all events in the window — even those with
    ``tokens_actual == 0`` — so the totals match the dashboard's "tokens
    saved" framing.
    """
    today = today or datetime.now(UTC).date()
    cutoff_dt = datetime.combine(today - timedelta(days=period_days), datetime.min.time(), UTC)

    log = InjectMetricsLog.load(vault)
    events = [e for e in log.events if e.timestamp >= cutoff_dt]

    valid = [e for e in events if e.tokens_actual > 0]
    if valid:
        avg = sum(e.tokens_full / e.tokens_actual for e in valid) / len(valid)
    else:
        avg = None

    sessions_covered = len({e.session_id for e in events if e.session_id})

    return CompressionSummary(
        period_days=period_days,
        events_count=len(events),
        sessions_covered=sessions_covered,
        avg_compression_ratio=avg,
        total_tokens_full=sum(e.tokens_full for e in events),
        total_tokens_actual=sum(e.tokens_actual for e in events),
    )
```

(`date_class` is already imported in this file from earlier UTC fix — confirm; if not, add to import block.)

- [ ] **Step 4: Run** → expect PASS.

```bash
python -m pytest tests/test_compression_summary.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/metrics.py tests/test_compression_summary.py
git commit -m "feat(metrics): #13d compression_summary — avg_compression_ratio over period"
```

---

## Task 8: Daemon `/metrics/usage` extension

**Files:**
- Modify: `claude_mnemos/daemon/routes/metrics.py`
- Modify: `claude_mnemos/daemon/schemas.py` (or wherever `usage_route` response is shaped)
- Modify: `tests/daemon/test_app_metrics.py` (extend usage tests)

- [ ] **Step 1: Failing test**

Append to `tests/daemon/test_app_metrics.py`:

```python
def test_usage_includes_compression_fields(client_factory, register_project, tmp_path):
    """/metrics/usage response includes avg_compression_ratio + inject_events_count."""
    from datetime import UTC, datetime
    from claude_mnemos.state.inject_metrics import (
        InjectMetricEvent,
        InjectMetricsLog,
    )

    vault = tmp_path / "vault"
    vault.mkdir()
    register_project("alpha", vault, cwd_patterns=[])

    log = InjectMetricsLog()
    log.events.append(InjectMetricEvent(
        id="e1",
        timestamp=datetime.now(UTC),
        session_id="s1",
        operation="session_start",
        mode="full",
        tokens_full=1000,
        tokens_actual=200,
        candidates_total=5,
        candidates_packed=5,
    ))
    log.save(vault)

    client = client_factory()
    r = client.get("/metrics/usage", params={"period": "30d"})
    assert r.status_code == 200
    data = r.json()
    assert "avg_compression_ratio" in data
    assert "inject_events_count" in data
    assert data["avg_compression_ratio"] == 5.0
    assert data["inject_events_count"] == 1


def test_usage_compression_null_when_no_events(client_factory, register_project, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    register_project("alpha", vault, cwd_patterns=[])

    client = client_factory()
    r = client.get("/metrics/usage", params={"period": "30d"})
    assert r.status_code == 200
    data = r.json()
    assert data["avg_compression_ratio"] is None
    assert data["inject_events_count"] == 0
```

(The `client_factory` and `register_project` fixtures should already exist in this file's conftest. If not, copy the pattern from existing tests in the file.)

- [ ] **Step 2: Run** → expect FAIL.

```bash
python -m pytest tests/daemon/test_app_metrics.py::test_usage_includes_compression_fields -v 2>&1 | tail -10
```

- [ ] **Step 3: Read the existing usage route**

```bash
grep -n "def usage_route\|avg_compression\|inject_events" /d/code/claude-mnemos/claude_mnemos/daemon/routes/metrics.py
sed -n '40,80p' /d/code/claude-mnemos/claude_mnemos/daemon/routes/metrics.py
```

Identify how the route currently builds the response. Likely uses `usage_summary(vault, period_days=days)` per runtime, then aggregates.

- [ ] **Step 4: Extend the response**

Edit `claude_mnemos/daemon/routes/metrics.py::usage_route`. After the existing aggregation, add compression fields:

```python
# (existing code that builds totals across runtimes)

# §15 compression metric (Plan #13d) — aggregate across all mounted vaults.
from claude_mnemos.core.metrics import compression_summary

compression_per_vault: list[CompressionSummary] = []
for runtime in await all_runtimes(request):
    compression_per_vault.append(
        compression_summary(runtime.vault_root, period_days=days)
    )

total_events = sum(c.events_count for c in compression_per_vault)
# Weighted-by-events average across vaults to avoid empty vaults skewing.
weighted_sum = sum(
    (c.avg_compression_ratio or 0.0) * c.events_count
    for c in compression_per_vault
    if c.avg_compression_ratio is not None
)
events_with_ratio = sum(
    c.events_count
    for c in compression_per_vault
    if c.avg_compression_ratio is not None
)
avg_ratio = (weighted_sum / events_with_ratio) if events_with_ratio > 0 else None

response = {
    # ... existing fields ...
    "avg_compression_ratio": avg_ratio,
    "inject_events_count": total_events,
}
return response
```

(Adapt to actual existing response-building style — may use a Pydantic model. If so, extend the model in `schemas.py` to include the two new fields.)

- [ ] **Step 5: Update response Pydantic shape (if using one)**

Find the `UsageResponse`/`UsageSummary` Pydantic model in `claude_mnemos/daemon/schemas.py`. Add two fields:

```python
class UsageSummary(BaseModel):  # or whatever it's called
    # ... existing fields ...
    avg_compression_ratio: float | None = None
    inject_events_count: int = 0
```

- [ ] **Step 6: Run** → expect PASS.

```bash
python -m pytest tests/daemon/test_app_metrics.py -v 2>&1 | tail -15
```

All metrics tests pass.

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/daemon/routes/metrics.py claude_mnemos/daemon/schemas.py tests/daemon/test_app_metrics.py
git commit -m "feat(daemon): #13d /metrics/usage exposes avg_compression_ratio + inject_events_count"
```

---

## Task 9: Frontend — UsageSummary schema + UsageWidget render

**Files:**
- Modify: `frontend/src/types/UsageSummary.ts`
- Modify: `frontend/src/components/widgets/UsageWidget.tsx`
- Modify: `frontend/public/locales/{en,uk,ru}.json`
- Modify: `frontend/src/__tests__/UsageWidget.test.tsx` (or similar)

- [ ] **Step 1: Failing test**

Read existing `frontend/src/__tests__/UsageWidget.test.tsx`. Append two tests:

```tsx
it("renders inject events + compression ratio when present", () => {
  const data: UsageSummary = {
    period: "30d",
    period_days: 30,
    sessions_covered: 12,
    tokens_input: 100,
    tokens_output: 200,
    tokens_injected: 50,
    raw_bytes_total: 1024,
    tokens_per_byte: 0.293,
    avg_compression_ratio: 6.3,
    inject_events_count: 47,
  };
  render(<UsageWidget summary={data} />);
  expect(screen.getByText(/47/)).toBeInTheDocument();
  expect(screen.getByText(/6\.3/)).toBeInTheDocument();
});

it("renders zero events without ratio text", () => {
  const data: UsageSummary = {
    period: "30d",
    period_days: 30,
    sessions_covered: 0,
    tokens_input: 0,
    tokens_output: 0,
    tokens_injected: 0,
    raw_bytes_total: 0,
    tokens_per_byte: null,
    avg_compression_ratio: null,
    inject_events_count: 0,
  };
  render(<UsageWidget summary={data} />);
  expect(screen.getByText(/0 events/i)).toBeInTheDocument();
});
```

(Adapt prop names + the Card/render shape to actual `<UsageWidget>` API. Read it first.)

- [ ] **Step 2: Extend `UsageSummary` zod schema**

Edit `frontend/src/types/UsageSummary.ts`. Find `UsageSummarySchema = z.object({...})` and add two fields:

```ts
export const UsageSummarySchema = z.object({
  period: z.string(),
  period_days: z.number().int().nonnegative(),
  sessions_covered: z.number().int().nonnegative(),
  tokens_input: z.number().int().nonnegative(),
  tokens_output: z.number().int().nonnegative(),
  tokens_injected: z.number().int().nonnegative(),
  raw_bytes_total: z.number().int().nonnegative(),
  tokens_per_byte: z.number().nullable(),
  avg_compression_ratio: z.number().nullable().default(null),
  inject_events_count: z.number().int().nonnegative().default(0),
});
```

The `.default()` calls let older daemon responses (without these fields) parse without breaking.

- [ ] **Step 3: Add locale keys**

Append to each locale's `metrics` block:

- en.json: `"inject_events": "{{count}} inject events"`, `"avg_compression": "{{ratio}}× avg compression"`
- uk.json: `"inject_events": "{{count}} ін'єкцій"`, `"avg_compression": "{{ratio}}× середнє стиснення"`
- ru.json: `"inject_events": "{{count}} инъекций"`, `"avg_compression": "{{ratio}}× среднее сжатие"`

- [ ] **Step 4: Render in `UsageWidget`**

Read `frontend/src/components/widgets/UsageWidget.tsx`. Find the JSX block where existing stats render. Add a new line below them:

```tsx
<div className="text-xs text-[hsl(var(--muted-foreground))]">
  {t("metrics.inject_events", { count: summary.inject_events_count })}
  {summary.avg_compression_ratio !== null && (
    <>
      {" · "}
      {t("metrics.avg_compression", {
        ratio: summary.avg_compression_ratio.toFixed(1),
      })}
    </>
  )}
</div>
```

- [ ] **Step 5: Run tests + tsc**

```bash
cd frontend && pnpm test UsageWidget && pnpm typecheck
```

Expected: 2 new tests pass; existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/UsageSummary.ts frontend/src/components/widgets/UsageWidget.tsx frontend/src/__tests__/UsageWidget.test.tsx frontend/public/locales/
git commit -m "feat(frontend): #13d UsageWidget shows inject events + avg compression ratio"
```

---

## Task 10: Final verification + acceptance walkthrough

- [ ] **Step 1: Backend full suite**

```bash
cd /d/code/claude-mnemos
python -m pytest tests/ -k "not slow" --ignore=tests/daemon/integration --tb=line 2>&1 | tail -3
```

Expected: ~1295 passed (1269 baseline + ~26 new). 0 failed.

- [ ] **Step 2: ruff clean**

```bash
ruff check claude_mnemos/ tests/ hooks/ 2>&1 | tail -3
```

Expected: all checks passed (or only the pre-existing ones).

- [ ] **Step 3: Frontend full suite**

```bash
cd /d/code/claude-mnemos/frontend
pnpm test
pnpm typecheck
pnpm lint
```

Expected: 174+2 = 176 tests pass; tsc clean; lint only pre-existing 2 warnings.

- [ ] **Step 4: Acceptance criteria walk-through (design §6)**

1. ✅ `~/.claude-mnemos/inject.log` lines have ISO8601 prefix.
2. ✅ `SKIP_SOURCES` has explanatory comment.
3. ✅ Single canonical `slug_from_page_path`.
4. ✅ `_with_stats` returns `(str, InjectStats)`; backward-compat wrapper preserved.
5. ✅ `build_page_graph_with_pages` returns parsed-pages dict.
6. ✅ `.inject-metrics.json` per-vault state file.
7. ✅ Hook writes event after every successful inject; metric-write failure does not block emit.
8. ✅ `compression_summary` returns correct ratio; UTC-anchored.
9. ✅ `/metrics/usage` includes `avg_compression_ratio` + `inject_events_count`.
10. ✅ `<UsageWidget>` displays both fields; null ratio → "0 events" only.
11. ✅ ~26 backend + 2 frontend new tests; all pass.
12. ✅ Backend baseline holds.
13. ✅ Frontend baseline holds.
14. ✅ ruff + tsc + ESLint clean.
15. ⚠️ Manual smoke: open a session in a matched cwd, verify `.inject-metrics.json` gets a new event, dashboard `/metrics` shows updated count. Not part of pytest.

- [ ] **Step 5: Branch summary**

```bash
git log --oneline main..HEAD
git status
```

~10 commits, working tree clean.

- [ ] **Step 6: Optional commit if anything dangling**

If any small fix-up emerged during verification, commit. Otherwise verification-only.

---

## Spec coverage map

| Design § | Plan task |
|---|---|
| 2.8(1) timestamp | 1 |
| 2.8(2) skip-sources comment | 1 |
| 2.8(3) slug dedup | 2 |
| 2.3 graph_with_pages | 3 |
| 2.2 with_stats variant | 4 |
| 2.1 inject_metrics state | 5 |
| 2.4 hook writes event | 6 |
| 2.5 compression_summary | 7 |
| 2.6 /metrics/usage extension | 8 |
| 2.7 frontend UsageWidget | 9 |
| §6 ACs | 10 |
