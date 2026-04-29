# SessionStart adaptive context inject Implementation Plan (Plan #13c)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** When a Claude Code session starts in a CWD matched to a mnemos project, inject the most relevant vault pages (frontmatter weights + ontology graph + recent sessions + cwd-grep) into Claude's context so the model has prior project memory without the user re-explaining.

**Architecture:** New `claude_mnemos/core/graph.py` builds an undirected wikilink adjacency map. New `claude_mnemos/core/session_start.py::build_adaptive_context()` ranks pages via a weighted score (confidence + flavor + recency + graph proximity + cwd match - stale penalty) and packs the top-K under a char budget. New `hooks/session_start.py` reads stdin payload, calls the builder, emits `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ...}}` to stdout. Source-field branching (`resume`/`compact`/`edit` skip). Recursion guard via `MNEMOS_INJECT_RUNNING`. Backend-only — no frontend changes.

**Tech Stack:** Python 3.12, Pydantic v2, pytest. Reuses `core/wikilinks.py`, `core/page_io.py`, `state/manifest.py`, `mapping/resolver.py`. **Reference impl** for hook contract: `d:/Обсидиан мозги/OBSIDIAN/.shared/hooks/session-start.py` (working in production for the user — port the JSON shape).

**Design doc:** `docs/plans/2026-04-29-13c-session-start-inject-design.md` — read before each task.

---

## Files map

**Create:**
- `claude_mnemos/core/graph.py` — undirected page adjacency + BFS K-hop traversal
- `claude_mnemos/core/session_start.py` — `build_adaptive_context()` + scoring + format
- `hooks/session_start.py` — Claude Code SessionStart hook entry
- `tests/test_graph.py` — graph helper unit tests
- `tests/test_session_start.py` — scoring + builder unit tests
- `tests/test_session_start_hook.py` — hook subprocess integration tests

**Modified:**
- `claude_mnemos/state/activity.py` — extend `ActivityOperationType` with `"session_start_inject"`
- `hooks/hooks.json` — register SessionStart entry alongside existing SessionEnd

---

## Task 1: Extend ActivityOperationType with session_start_inject

**Files:**
- Modify: `claude_mnemos/state/activity.py`
- Modify: `tests/test_activity.py` (add coverage if file exists, else skip)

- [ ] **Step 1: Read current ActivityOperationType definition**

```bash
sed -n '14,28p' /d/code/claude-mnemos/claude_mnemos/state/activity.py
```

Confirm: `ActivityOperationType = Literal["ingest_extracted", ..., "trash_emptied"]`.

- [ ] **Step 2: Failing test (if test_activity.py exists)**

```bash
ls /d/code/claude-mnemos/tests/test_activity.py
```

If file exists, add a test confirming the new literal accepts:

```python
def test_session_start_inject_accepted_as_op_type():
    from datetime import datetime, UTC
    from claude_mnemos.state.activity import ActivityEntry

    entry = ActivityEntry(
        id="op-test-1",
        timestamp=datetime.now(UTC),
        operation_type="session_start_inject",
        status="success",
        snapshot_path=None,
        can_undo=False,
    )
    assert entry.operation_type == "session_start_inject"
```

If `tests/test_activity.py` doesn't exist, skip this step and verify by importing in Step 4.

- [ ] **Step 3: Run** → expect FAIL with literal validation error.

```bash
cd /d/code/claude-mnemos
python -m pytest tests/test_activity.py -k "session_start_inject" -v 2>&1 | tail -10
```

- [ ] **Step 4: Add the literal**

Edit `claude_mnemos/state/activity.py`. Find the `ActivityOperationType = Literal[...]` block (lines 15-27). Append `"session_start_inject"` after `"trash_emptied"`:

```python
ActivityOperationType = Literal[
    "ingest_extracted",
    "ingest_raw_only",
    "manual_restore",
    "ontology_apply",
    "human_edit_detected",
    "lint_fix",
    "manual_edit",
    "manual_delete",
    "manual_restore_trash",
    "trash_dismissed",
    "trash_emptied",
    "session_start_inject",
]
```

- [ ] **Step 5: Run all activity tests**

```bash
python -m pytest tests/test_activity.py 2>&1 | tail -5
```

Expected: all PASS.

- [ ] **Step 6: Run wider suite to confirm no regression**

```bash
python -m pytest tests/ -k "not slow" --ignore=tests/daemon/integration --tb=line 2>&1 | tail -3
```

Expected: 1235 passed (baseline) or higher.

- [ ] **Step 7: Commit**

```bash
git add claude_mnemos/state/activity.py tests/test_activity.py
git commit -m "feat(activity): #13c add session_start_inject op type"
```

---

## Task 2: core/graph.py — build_page_graph

**Files:**
- Create: `claude_mnemos/core/graph.py`
- Create: `tests/test_graph.py`

- [ ] **Step 1: Failing test**

`tests/test_graph.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos.core.graph import build_page_graph


def _write_page(vault: Path, slug: str, body: str = "", related: list[str] | None = None) -> None:
    """Write a wiki page with minimal frontmatter at vault/wiki/<slug>.md."""
    page_path = vault / "wiki" / f"{slug}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    related_str = ""
    if related:
        related_str = "related:\n" + "\n".join(f"  - {r}" for r in related) + "\n"
    fm = (
        "---\n"
        f"title: {slug}\n"
        "type: concept\n"
        "status: draft\n"
        "confidence: 0.7\n"
        "flavor: []\n"
        "sources: []\n"
        f"{related_str}"
        + ("related: []\n" if not related else "")
        + "created: 2026-04-29\n"
        "updated: 2026-04-29\n"
        "agent_written: true\n"
        "---\n"
    )
    page_path.write_text(fm + body, encoding="utf-8")


def test_build_page_graph_empty_vault(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir()
    graph = build_page_graph(tmp_path)
    assert graph == {}


def test_build_page_graph_isolated_page(tmp_path: Path) -> None:
    _write_page(tmp_path, "concepts/a", body="no links")
    graph = build_page_graph(tmp_path)
    assert "concepts/a" in graph
    assert graph["concepts/a"] == set()


def test_build_page_graph_body_wikilinks_undirected(tmp_path: Path) -> None:
    _write_page(tmp_path, "concepts/a", body="See [[concepts/b]] for details.")
    _write_page(tmp_path, "concepts/b")
    graph = build_page_graph(tmp_path)
    assert "concepts/b" in graph["concepts/a"]
    assert "concepts/a" in graph["concepts/b"]


def test_build_page_graph_frontmatter_related(tmp_path: Path) -> None:
    _write_page(tmp_path, "concepts/a", related=["concepts/b"])
    _write_page(tmp_path, "concepts/b")
    graph = build_page_graph(tmp_path)
    assert "concepts/b" in graph["concepts/a"]
    assert "concepts/a" in graph["concepts/b"]


def test_build_page_graph_unknown_target_does_not_crash(tmp_path: Path) -> None:
    _write_page(tmp_path, "concepts/a", body="See [[concepts/missing]]")
    graph = build_page_graph(tmp_path)
    # missing target shows up but has no neighbors of its own
    assert "concepts/missing" in graph["concepts/a"]


def test_build_page_graph_skips_invalid_frontmatter(tmp_path: Path) -> None:
    bad = tmp_path / "wiki" / "broken.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("not yaml frontmatter\nbody only\n", encoding="utf-8")
    # also write a valid page
    _write_page(tmp_path, "concepts/a")
    graph = build_page_graph(tmp_path)
    assert "concepts/a" in graph
    assert "broken" not in graph
```

- [ ] **Step 2: Run** → expect FAIL.

```bash
cd /d/code/claude-mnemos
python -m pytest tests/test_graph.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement `build_page_graph`**

Create `claude_mnemos/core/graph.py`:

```python
"""Undirected page adjacency graph for adaptive context inject (Plan #13c).

Slugs are relative paths under ``wiki/`` without the ``.md`` suffix
(e.g. ``concepts/foo``). Edges are derived from:

- Body wikilinks ``[[target]]`` — via :mod:`claude_mnemos.core.wikilinks`.
- Frontmatter ``related: [...]`` lists.

The resulting graph is undirected: if A → B is found in either direction,
both neighbors entries point to each other. Targets that don't have their
own page entry still appear as keys (with no neighbors), so callers can
treat the graph as "every slug ever mentioned anywhere".

Pages with malformed frontmatter are skipped silently — graph construction
must never raise on a bad page.
"""

from __future__ import annotations

from pathlib import Path

from claude_mnemos.core.page_io import PageParseError, read_page
from claude_mnemos.core.wikilinks import extract_wikilinks


def _slug_for(vault: Path, page_path: Path) -> str:
    """Return the slug for a vault-relative page (path under ``wiki/`` w/o .md)."""
    rel = page_path.relative_to(vault / "wiki")
    return str(rel.with_suffix("")).replace("\\", "/")


def build_page_graph(vault: Path) -> dict[str, set[str]]:
    """Walk ``vault/wiki/**/*.md`` and return slug → set of neighbor slugs.

    Bidirectional. Bad pages are skipped. Targets not present as their own
    pages still appear as keys (empty neighbor set).
    """
    graph: dict[str, set[str]] = {}
    wiki_root = vault / "wiki"
    if not wiki_root.is_dir():
        return graph

    for page_path in wiki_root.rglob("*.md"):
        try:
            parsed = read_page(page_path)
        except PageParseError:
            continue
        slug = _slug_for(vault, page_path)
        graph.setdefault(slug, set())

        # Body wikilinks
        for link in extract_wikilinks(parsed.body):
            target = link.target.strip()
            if not target:
                continue
            graph[slug].add(target)
            graph.setdefault(target, set()).add(slug)

        # Frontmatter related[]
        for related in parsed.frontmatter.related:
            r = related.strip()
            if not r:
                continue
            graph[slug].add(r)
            graph.setdefault(r, set()).add(slug)

    return graph
```

- [ ] **Step 4: Run** → expect PASS.

```bash
python -m pytest tests/test_graph.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/graph.py tests/test_graph.py
git commit -m "feat(core): #13c build_page_graph — undirected wikilink adjacency"
```

---

## Task 3: core/graph.py — pages_within_k_hops

**Files:**
- Modify: `claude_mnemos/core/graph.py` (append BFS helper)
- Modify: `tests/test_graph.py` (append BFS tests)

- [ ] **Step 1: Failing test**

Append to `tests/test_graph.py`:

```python
from claude_mnemos.core.graph import pages_within_k_hops


def test_pages_within_k_hops_seeds_only_at_k0() -> None:
    graph = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}}
    out = pages_within_k_hops(graph, {"a"}, k=0)
    assert out == {"a": 0}


def test_pages_within_k_hops_one_hop() -> None:
    graph = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}}
    out = pages_within_k_hops(graph, {"a"}, k=1)
    assert out == {"a": 0, "b": 1}


def test_pages_within_k_hops_two_hops() -> None:
    graph = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}}
    out = pages_within_k_hops(graph, {"a"}, k=2)
    assert out == {"a": 0, "b": 1, "c": 2}


def test_pages_within_k_hops_multiple_seeds() -> None:
    graph = {"a": {"x"}, "b": {"y"}, "x": {"a"}, "y": {"b"}}
    out = pages_within_k_hops(graph, {"a", "b"}, k=1)
    assert out == {"a": 0, "b": 0, "x": 1, "y": 1}


def test_pages_within_k_hops_seed_not_in_graph_skipped() -> None:
    graph = {"a": {"b"}, "b": {"a"}}
    out = pages_within_k_hops(graph, {"missing"}, k=2)
    assert out == {}


def test_pages_within_k_hops_min_distance_wins() -> None:
    # diamond: a→b, a→c, b→d, c→d. d is reachable in 2 hops via either path.
    graph = {"a": {"b", "c"}, "b": {"a", "d"}, "c": {"a", "d"}, "d": {"b", "c"}}
    out = pages_within_k_hops(graph, {"a"}, k=2)
    assert out["d"] == 2
```

- [ ] **Step 2: Run** → expect FAIL.

```bash
python -m pytest tests/test_graph.py::test_pages_within_k_hops_one_hop -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement `pages_within_k_hops`**

Append to `claude_mnemos/core/graph.py`:

```python
def pages_within_k_hops(
    graph: dict[str, set[str]],
    seeds: set[str],
    *,
    k: int = 2,
) -> dict[str, int]:
    """BFS from each seed; return slug → minimum hop distance for all
    reachable pages within ``k`` hops. Seeds map to 0.

    Seeds not present in ``graph`` are silently skipped. The minimum-distance
    win is intentional: when a slug is reachable from multiple seeds, the
    closest seed determines its hop value.
    """
    distances: dict[str, int] = {}
    frontier: list[str] = []
    for s in seeds:
        if s in graph:
            distances[s] = 0
            frontier.append(s)

    for hop in range(1, k + 1):
        next_frontier: list[str] = []
        for node in frontier:
            for neighbor in graph.get(node, set()):
                if neighbor in distances:
                    continue
                distances[neighbor] = hop
                next_frontier.append(neighbor)
        if not next_frontier:
            break
        frontier = next_frontier

    return distances
```

- [ ] **Step 4: Run** → expect PASS.

```bash
python -m pytest tests/test_graph.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/graph.py tests/test_graph.py
git commit -m "feat(core): #13c pages_within_k_hops — BFS K-hop traversal"
```

---

## Task 4: core/session_start.py — slug + summary helpers

**Files:**
- Create: `claude_mnemos/core/session_start.py` (initial helpers)
- Create: `tests/test_session_start.py` (initial helper tests)

- [ ] **Step 1: Failing test**

`tests/test_session_start.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from claude_mnemos.core.session_start import (
    page_slug_from_path,
    page_summary,
)
from claude_mnemos.core.page_io import ParsedPage
from claude_mnemos.core.models import WikiPageFrontmatter
from datetime import date


def _make_parsed(slug: str, body: str, *, confidence: float = 0.7) -> ParsedPage:
    fm = WikiPageFrontmatter(
        title=slug,
        type="concept",
        status="draft",
        confidence=confidence,
        flavor=[],
        sources=[],
        related=[],
        created=date(2026, 4, 29),
        updated=date(2026, 4, 29),
        agent_written=True,
    )
    return ParsedPage(frontmatter=fm, extra_fm={}, body=body)


def test_page_slug_from_path_strips_wiki_prefix_and_md(tmp_path: Path) -> None:
    page = tmp_path / "wiki" / "concepts" / "foo.md"
    page.parent.mkdir(parents=True)
    page.write_text("", encoding="utf-8")
    assert page_slug_from_path(tmp_path, page) == "concepts/foo"


def test_page_summary_returns_first_n_chars() -> None:
    parsed = _make_parsed("foo", "Hello world. " * 50)
    summary = page_summary(parsed, max_chars=80)
    assert len(summary) <= 80
    assert summary.startswith("Hello world.")


def test_page_summary_strips_leading_whitespace() -> None:
    parsed = _make_parsed("foo", "\n\n   Hello world\n\nMore content")
    summary = page_summary(parsed, max_chars=200)
    assert summary.startswith("Hello world")


def test_page_summary_empty_body_returns_empty() -> None:
    parsed = _make_parsed("foo", "")
    assert page_summary(parsed, max_chars=200) == ""
```

- [ ] **Step 2: Run** → expect FAIL.

```bash
python -m pytest tests/test_session_start.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement helpers**

Create `claude_mnemos/core/session_start.py`:

```python
"""SessionStart adaptive context inject (Plan #13c, spec §5.2 / §9.2).

Builder for the ``additionalContext`` block that the SessionStart hook emits
at session start. Combines frontmatter weights, recency, ontology graph
proximity to recent-session pages, and cwd-grep boosts to rank vault pages.

Token budgeting uses a 4-chars≈1-token approximation. No tokenizer dep.

Pure functions: no I/O beyond reading the vault's manifest + page files.
Hook entrypoint lives in ``hooks/session_start.py``.
"""

from __future__ import annotations

from pathlib import Path

from claude_mnemos.core.page_io import ParsedPage


def page_slug_from_path(vault: Path, page_path: Path) -> str:
    """Slug = relative path under ``vault/wiki/`` without ``.md`` suffix.

    Example: ``vault/wiki/concepts/foo.md`` → ``concepts/foo``.
    Always uses forward slashes (Windows safe).
    """
    rel = page_path.relative_to(vault / "wiki")
    return str(rel.with_suffix("")).replace("\\", "/")


def page_summary(parsed: ParsedPage, *, max_chars: int = 200) -> str:
    """Return the first non-empty ``max_chars`` characters of the page body.

    Strips leading whitespace. Used for short blurbs in the inject manifest.
    """
    body = parsed.body.lstrip()
    if not body:
        return ""
    return body[:max_chars]
```

- [ ] **Step 4: Run** → expect PASS.

```bash
python -m pytest tests/test_session_start.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/session_start.py tests/test_session_start.py
git commit -m "feat(core): #13c session_start helpers — page_slug + page_summary"
```

---

## Task 5: core/session_start.py — score_page

**Files:**
- Modify: `claude_mnemos/core/session_start.py` (append scoring)
- Modify: `tests/test_session_start.py` (append scoring tests)

- [ ] **Step 1: Failing test**

Append to `tests/test_session_start.py`:

```python
from datetime import datetime, UTC
from claude_mnemos.core.session_start import score_page, FLAVOR_WEIGHTS


def _make_parsed_full(
    *, confidence: float = 0.7,
    flavor: list[str] | None = None,
    status: str = "draft",
    body: str = "",
    last_human_edit: datetime | None = None,
) -> ParsedPage:
    fm = WikiPageFrontmatter(
        title="x",
        type="concept",
        status=status,  # type: ignore[arg-type]
        confidence=confidence,
        flavor=flavor or [],  # type: ignore[arg-type]
        sources=[],
        related=[],
        created=date(2026, 4, 29),
        updated=date(2026, 4, 29),
        agent_written=True,
        last_human_edit=last_human_edit,
    )
    return ParsedPage(frontmatter=fm, extra_fm={}, body=body)


def test_score_page_higher_confidence_wins() -> None:
    a = _make_parsed_full(confidence=0.9)
    b = _make_parsed_full(confidence=0.3)
    score_a = score_page(a, hop_distance=2, cwd_segment="zzz", now=datetime(2026, 4, 29, tzinfo=UTC))
    score_b = score_page(b, hop_distance=2, cwd_segment="zzz", now=datetime(2026, 4, 29, tzinfo=UTC))
    assert score_a > score_b


def test_score_page_decision_flavor_outranks_reference() -> None:
    decision = _make_parsed_full(flavor=["decision"])
    reference = _make_parsed_full(flavor=["reference"])
    now = datetime(2026, 4, 29, tzinfo=UTC)
    s_decision = score_page(decision, hop_distance=2, cwd_segment="zzz", now=now)
    s_reference = score_page(reference, hop_distance=2, cwd_segment="zzz", now=now)
    assert s_decision > s_reference


def test_score_page_closer_hop_wins() -> None:
    parsed = _make_parsed_full()
    now = datetime(2026, 4, 29, tzinfo=UTC)
    s_close = score_page(parsed, hop_distance=0, cwd_segment="zzz", now=now)
    s_far = score_page(parsed, hop_distance=2, cwd_segment="zzz", now=now)
    assert s_close > s_far


def test_score_page_cwd_segment_in_body_boosts() -> None:
    matched = _make_parsed_full(body="Working on the foo project today.")
    unmatched = _make_parsed_full(body="No mention of the cwd here.")
    now = datetime(2026, 4, 29, tzinfo=UTC)
    s_match = score_page(matched, hop_distance=2, cwd_segment="foo", now=now)
    s_no_match = score_page(unmatched, hop_distance=2, cwd_segment="foo", now=now)
    assert s_match > s_no_match


def test_score_page_stale_status_penalized() -> None:
    fresh = _make_parsed_full(status="reviewed")
    stale = _make_parsed_full(status="stale")
    archived = _make_parsed_full(status="archived")
    now = datetime(2026, 4, 29, tzinfo=UTC)
    s_fresh = score_page(fresh, hop_distance=2, cwd_segment="zzz", now=now)
    s_stale = score_page(stale, hop_distance=2, cwd_segment="zzz", now=now)
    s_archived = score_page(archived, hop_distance=2, cwd_segment="zzz", now=now)
    assert s_fresh > s_stale
    assert s_fresh > s_archived


def test_score_page_recency_decay() -> None:
    fresh = _make_parsed_full(last_human_edit=datetime(2026, 4, 29, tzinfo=UTC))
    old = _make_parsed_full(last_human_edit=datetime(2025, 1, 1, tzinfo=UTC))
    now = datetime(2026, 4, 29, tzinfo=UTC)
    s_fresh = score_page(fresh, hop_distance=2, cwd_segment="zzz", now=now)
    s_old = score_page(old, hop_distance=2, cwd_segment="zzz", now=now)
    assert s_fresh > s_old


def test_flavor_weights_decision_max() -> None:
    assert FLAVOR_WEIGHTS["decision"] >= FLAVOR_WEIGHTS["reference"]
    assert FLAVOR_WEIGHTS["lesson"] >= FLAVOR_WEIGHTS["reference"]
```

- [ ] **Step 2: Run** → expect FAIL.

```bash
python -m pytest tests/test_session_start.py -k "score" -v 2>&1 | tail -15
```

- [ ] **Step 3: Implement scoring**

Append to `claude_mnemos/core/session_start.py`:

```python
import math
from datetime import datetime

# Score weight constants (module-level for easy tuning).
W_CONFIDENCE = 1.0
W_FLAVOR = 0.5
W_RECENCY = 0.3
W_PROXIMITY = 0.4
W_CWD_MATCH = 0.6
W_STALE_PENALTY = 0.5

FLAVOR_WEIGHTS: dict[str, float] = {
    "decision": 1.0,
    "lesson": 1.0,
    "pattern": 0.7,
    "mistake": 0.5,
    "reference": 0.4,
}

RECENCY_HALF_LIFE_DAYS = 30


def _flavor_weight(flavors: list[str]) -> float:
    """Max weight across all flavors on the page (or 0 if none)."""
    if not flavors:
        return 0.0
    return max(FLAVOR_WEIGHTS.get(f, 0.0) for f in flavors)


def _recency_decay(last_edit: datetime | None, now: datetime) -> float:
    """Exponential decay over RECENCY_HALF_LIFE_DAYS. Returns 0..1.

    Pages with no last_human_edit get a neutral 0 (not penalized, not boosted).
    """
    if last_edit is None:
        return 0.0
    days = (now - last_edit).total_seconds() / 86400.0
    if days < 0:
        return 1.0  # future-dated edit; treat as fresh
    return math.exp(-days / RECENCY_HALF_LIFE_DAYS * math.log(2))


def _proximity(hop_distance: int) -> float:
    """1.0 at hop 0, 0.5 at hop 1, 0.2 at hop 2, 0 beyond."""
    if hop_distance <= 0:
        return 1.0
    if hop_distance == 1:
        return 0.5
    if hop_distance == 2:
        return 0.2
    return 0.0


def _stale_penalty(status: str) -> float:
    if status == "stale":
        return 1.0
    if status == "archived":
        return 0.7
    return 0.0


def score_page(
    parsed: ParsedPage,
    *,
    hop_distance: int,
    cwd_segment: str,
    now: datetime,
) -> float:
    """Return a relevance score for ``parsed`` page.

    Higher = more relevant. Components:

    - confidence (0..1, weight W_CONFIDENCE)
    - flavor weight (W_FLAVOR × max flavor weight)
    - recency decay (W_RECENCY × exp-decay over 30 days)
    - graph proximity (W_PROXIMITY × hop-based score)
    - cwd-segment match in body (W_CWD_MATCH × 1.0 if substring found)
    - stale penalty (subtracted: W_STALE_PENALTY × 1.0 if status=stale, 0.7 if archived)

    All weights are module-level constants for easy tuning.
    """
    fm = parsed.frontmatter
    score = 0.0
    score += W_CONFIDENCE * fm.confidence
    score += W_FLAVOR * _flavor_weight(list(fm.flavor))
    score += W_RECENCY * _recency_decay(fm.last_human_edit, now)
    score += W_PROXIMITY * _proximity(hop_distance)
    if cwd_segment and cwd_segment in parsed.body:
        score += W_CWD_MATCH
    score -= W_STALE_PENALTY * _stale_penalty(fm.status)
    return score
```

- [ ] **Step 4: Run** → expect PASS.

```bash
python -m pytest tests/test_session_start.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/session_start.py tests/test_session_start.py
git commit -m "feat(core): #13c score_page — confidence + flavor + recency + proximity + cwd_match"
```

---

## Task 6: core/session_start.py — build_adaptive_context

**Files:**
- Modify: `claude_mnemos/core/session_start.py` (append builder)
- Modify: `tests/test_session_start.py` (append builder tests)

- [ ] **Step 1: Failing test**

Append to `tests/test_session_start.py`:

```python
from claude_mnemos.core.session_start import build_adaptive_context
from claude_mnemos.state.manifest import IngestRecord, Manifest
from claude_mnemos.core.atomic import atomic_write


def _seed_manifest(vault: Path, *, sessions: list[tuple[str, list[str]]]) -> None:
    """Seed vault/.manifest.json with ingest records.

    Each tuple is ``(session_id, created_pages)``.
    """
    records: dict[str, IngestRecord] = {}
    for sid, pages in sessions:
        records[sid] = IngestRecord(
            session_id=sid,
            ingested_at=datetime.now(UTC),
            raw_path=f"raw/{sid}.md",
            source_path=None,
            created_pages=pages,
            skipped_collisions=[],
            model=None,
            input_tokens=None,
            output_tokens=None,
        )
    manifest = Manifest(ingested=records)
    atomic_write(vault / ".manifest.json", manifest.serialize_to_string())


def _write_full_page(
    vault: Path,
    slug: str,
    body: str = "",
    *,
    confidence: float = 0.7,
    flavor: list[str] | None = None,
    related: list[str] | None = None,
    status: str = "draft",
) -> None:
    page_path = vault / "wiki" / f"{slug}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    flavor_str = "[]" if not flavor else "[" + ", ".join(flavor) + "]"
    related_str = "[]" if not related else "[" + ", ".join(related) + "]"
    fm = (
        "---\n"
        f"title: {slug}\n"
        "type: concept\n"
        f"status: {status}\n"
        f"confidence: {confidence}\n"
        f"flavor: {flavor_str}\n"
        "sources: []\n"
        f"related: {related_str}\n"
        "created: 2026-04-29\n"
        "updated: 2026-04-29\n"
        "agent_written: true\n"
        "---\n"
    )
    page_path.write_text(fm + body, encoding="utf-8")


def test_build_adaptive_context_empty_vault_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "wiki").mkdir()
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=1000)
    assert out == ""


def test_build_adaptive_context_no_manifest_returns_empty(tmp_path: Path) -> None:
    _write_full_page(tmp_path, "concepts/a", body="hello")
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=1000)
    # No manifest → no seeds → no candidates → empty
    assert out == ""


def test_build_adaptive_context_includes_seeded_pages(tmp_path: Path) -> None:
    _write_full_page(tmp_path, "concepts/a", body="alpha body")
    _seed_manifest(tmp_path, sessions=[("s1", ["wiki/concepts/a.md"])])
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=2000)
    assert "concepts/a" in out


def test_build_adaptive_context_respects_char_budget(tmp_path: Path) -> None:
    # Many big pages — output must stay under budget.
    for i in range(20):
        _write_full_page(tmp_path, f"concepts/p{i}", body="x" * 5000)
    pages_seeded = [f"wiki/concepts/p{i}.md" for i in range(20)]
    _seed_manifest(tmp_path, sessions=[("s1", pages_seeded)])
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=3000)
    assert len(out) <= 3500  # allow small slack for headers/formatting


def test_build_adaptive_context_graph_expansion(tmp_path: Path) -> None:
    # a links to b; only a is seeded; b should appear via 1-hop expansion.
    _write_full_page(tmp_path, "concepts/a", body="See [[concepts/b]]")
    _write_full_page(tmp_path, "concepts/b", body="bravo body")
    _seed_manifest(tmp_path, sessions=[("s1", ["wiki/concepts/a.md"])])
    out = build_adaptive_context(tmp_path, cwd=tmp_path, max_chars=3000)
    assert "concepts/a" in out
    assert "concepts/b" in out
```

- [ ] **Step 2: Run** → expect FAIL.

```bash
python -m pytest tests/test_session_start.py -k "build_adaptive_context" -v 2>&1 | tail -15
```

- [ ] **Step 3: Implement `build_adaptive_context`**

Append to `claude_mnemos/core/session_start.py`:

```python
from datetime import UTC

from claude_mnemos.core.graph import build_page_graph, pages_within_k_hops
from claude_mnemos.core.page_io import PageParseError, read_page
from claude_mnemos.state.manifest import Manifest

# Defaults
DEFAULT_RECENT_SESSIONS = 10
DEFAULT_GRAPH_HOPS = 2
SUMMARY_CHARS = 200


def _seeds_from_manifest(vault: Path, *, recent: int) -> set[str]:
    """Collect slugs from the last ``recent`` ingest records' ``created_pages``.

    ``created_pages`` entries are stored as paths like ``wiki/concepts/foo.md``;
    we strip the ``wiki/`` prefix and ``.md`` suffix to match graph slugs.
    """
    try:
        manifest = Manifest.load(vault)
    except Exception:  # noqa: BLE001
        return set()
    records = list(manifest.ingested.values())
    records.sort(key=lambda r: r.ingested_at, reverse=True)
    seeds: set[str] = set()
    for rec in records[:recent]:
        for page_ref in rec.created_pages:
            # page_ref like "wiki/concepts/foo.md"
            ref = page_ref.replace("\\", "/")
            if ref.startswith("wiki/"):
                ref = ref[len("wiki/"):]
            if ref.endswith(".md"):
                ref = ref[:-3]
            seeds.add(ref)
    return seeds


def _cwd_segment(cwd: Path) -> str:
    """Last path segment of cwd, used for body-grep boosts."""
    name = cwd.name
    return name.lower().strip()


def build_adaptive_context(
    vault: Path,
    *,
    cwd: Path,
    max_chars: int = 40_000,
    recent_sessions: int = DEFAULT_RECENT_SESSIONS,
    graph_hops: int = DEFAULT_GRAPH_HOPS,
) -> str:
    """Build the additionalContext markdown block to inject at SessionStart.

    Returns an empty string if vault has no manifest or yields no candidates —
    callers (i.e. the hook) emit nothing in that case.

    Algorithm:
    1. Read last N sessions' created_pages → seed slugs.
    2. Build vault-wide page graph; BFS K hops from seeds → candidate set.
    3. Score each candidate (confidence + flavor + recency + proximity + cwd match - stale).
    4. Greedy pack top-K under ``max_chars`` budget. Top 3 get full body if room;
       others get title + 200-char summary.
    5. Format as a markdown block.
    """
    wiki_root = vault / "wiki"
    if not wiki_root.is_dir():
        return ""

    seeds = _seeds_from_manifest(vault, recent=recent_sessions)
    if not seeds:
        return ""

    graph = build_page_graph(vault)
    candidates = pages_within_k_hops(graph, seeds, k=graph_hops)
    if not candidates:
        return ""

    cwd_seg = _cwd_segment(cwd)
    now = datetime.now(UTC)

    scored: list[tuple[float, str, "ParsedPage"]] = []
    for slug, hop in candidates.items():
        page_path = wiki_root / f"{slug}.md"
        if not page_path.is_file():
            continue
        try:
            parsed = read_page(page_path)
        except PageParseError:
            continue
        score = score_page(
            parsed,
            hop_distance=hop,
            cwd_segment=cwd_seg,
            now=now,
        )
        scored.append((score, slug, parsed))

    if not scored:
        return ""

    scored.sort(key=lambda t: t[0], reverse=True)

    # Greedy pack under char budget.
    header = "# Project context (mnemos)\n\nRecent sessions touched these pages:\n"
    parts: list[str] = [header]
    used = len(header)
    full_body_quota = 3
    for i, (_score, slug, parsed) in enumerate(scored):
        if i < full_body_quota:
            block = f"\n## [[{slug}]]\n\n{parsed.body}\n"
        else:
            summary = page_summary(parsed, max_chars=SUMMARY_CHARS)
            block = f"\n- [[{slug}]] — {summary}\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)

    return "".join(parts).strip() + "\n"
```

- [ ] **Step 4: Run** → expect PASS.

```bash
python -m pytest tests/test_session_start.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add claude_mnemos/core/session_start.py tests/test_session_start.py
git commit -m "feat(core): #13c build_adaptive_context — seed → graph → score → pack"
```

---

## Task 7: hooks/session_start.py — hook entry point

**Files:**
- Create: `hooks/session_start.py`

- [ ] **Step 1: Read existing SessionEnd hook for the pattern**

```bash
cat /d/code/claude-mnemos/hooks/session_end.py | head -90
```

Note the structure: sys.path setup, imports, recursion guard, error handling, exit codes.

- [ ] **Step 2: Implement `hooks/session_start.py`**

```python
"""SessionStart hook for claude-mnemos plugin (Plan #13c).

When Claude Code starts a session, this hook resolves the cwd → project
via ``ProjectResolver``, calls ``build_adaptive_context`` to assemble a
relevant-pages markdown block, and emits it to stdout as JSON for Claude
Code to inject into the model's system prompt.

Output shape (Claude Code v1 contract):
    {"hookSpecificOutput": {"hookEventName": "SessionStart",
                            "additionalContext": "<markdown>"}}

Skip conditions (silent, exit 0, no stdout):
- Recursion guard (``MNEMOS_INJECT_RUNNING=1``)
- Source field is ``resume``, ``compact``, or ``edit``
- Invalid stdin payload
- cwd missing or not in any project
- ``build_adaptive_context`` returns empty string
- Any exception during build (logged to ``~/.claude-mnemos/inject.log``)

Hook never blocks: returns 0 unconditionally.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Hook lives outside the package; allow it to import claude_mnemos.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

RECURSION_ENV = "MNEMOS_INJECT_RUNNING"
SKIP_SOURCES = frozenset({"resume", "compact", "edit"})
DEFAULT_MAX_CHARS = 40_000


def _log(msg: str) -> None:
    """Append a line to ~/.claude-mnemos/inject.log. Never raise."""
    try:
        log_path = Path.home() / ".claude-mnemos" / "inject.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    if os.environ.get(RECURSION_ENV) == "1":
        return 0
    os.environ[RECURSION_ENV] = "1"

    try:
        payload = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001
        _log(f"stdin parse failed: {exc}")
        return 0

    if not isinstance(payload, dict):
        return 0

    source = payload.get("source")
    if source in SKIP_SOURCES:
        return 0

    cwd_str = payload.get("cwd")
    if not cwd_str:
        return 0

    try:
        from claude_mnemos.core.session_start import build_adaptive_context
        from claude_mnemos.mapping.resolver import (
            ProjectResolver,
            ResolverAmbiguityError,
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"import failed: {exc}")
        return 0

    cwd = Path(cwd_str)
    try:
        project = ProjectResolver().resolve_by_cwd(cwd)
    except ResolverAmbiguityError as exc:
        _log(f"resolve ambiguous: {exc}")
        return 0
    except Exception as exc:  # noqa: BLE001
        _log(f"resolve failed: {exc}")
        return 0

    if project is None:
        return 0

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


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Verify file is syntactically valid**

```bash
python -m py_compile /d/code/claude-mnemos/hooks/session_start.py
```

Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add hooks/session_start.py
git commit -m "feat(hooks): #13c hooks/session_start.py — emit additionalContext on session start"
```

---

## Task 8: hooks/hooks.json — register SessionStart

**Files:**
- Modify: `hooks/hooks.json`

- [ ] **Step 1: Read current hooks.json**

```bash
cat /d/code/claude-mnemos/hooks/hooks.json
```

Confirm the existing shape — `{"hooks": {"SessionEnd": [{...}]}}`.

- [ ] **Step 2: Add SessionStart entry**

Replace the file content with:

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/session_end.py",
        "timeout_seconds": 15,
        "blocking": false
      }
    ],
    "SessionStart": [
      {
        "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py",
        "timeout_seconds": 15,
        "blocking": false
      }
    ]
  }
}
```

- [ ] **Step 3: Validate JSON syntax**

```bash
python -c "import json; json.load(open('/d/code/claude-mnemos/hooks/hooks.json'))"
```

Expected: no output (valid JSON).

- [ ] **Step 4: Commit**

```bash
git add hooks/hooks.json
git commit -m "feat(hooks): #13c register SessionStart hook in hooks.json"
```

---

## Task 9: Hook integration test (subprocess)

**Files:**
- Create: `tests/test_session_start_hook.py`

- [ ] **Step 1: Write subprocess integration test**

`tests/test_session_start_hook.py`:

```python
"""Integration tests for hooks/session_start.py — subprocess-driven."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path

import pytest

from claude_mnemos.core.atomic import atomic_write
from claude_mnemos.state.manifest import IngestRecord, Manifest
from claude_mnemos.state.projects import ProjectMapEntry, ProjectStore

HOOK_PATH = Path(__file__).resolve().parent.parent / "hooks" / "session_start.py"


def _write_full_page(vault: Path, slug: str, body: str = "") -> None:
    page_path = vault / "wiki" / f"{slug}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        "---\n"
        f"title: {slug}\n"
        "type: concept\n"
        "status: draft\n"
        "confidence: 0.7\n"
        "flavor: []\n"
        "sources: []\n"
        "related: []\n"
        "created: 2026-04-29\n"
        "updated: 2026-04-29\n"
        "agent_written: true\n"
        "---\n"
    )
    page_path.write_text(fm + body, encoding="utf-8")


def _seed_manifest(vault: Path, *, pages: list[str]) -> None:
    rec = IngestRecord(
        session_id="s1",
        ingested_at=datetime.now(UTC),
        raw_path="raw/s1.md",
        source_path=None,
        created_pages=pages,
        skipped_collisions=[],
        model=None,
        input_tokens=None,
        output_tokens=None,
    )
    manifest = Manifest(ingested={"s1": rec})
    atomic_write(vault / ".manifest.json", manifest.serialize_to_string())


def _run_hook(payload: dict, env_extra: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run the hook as a subprocess; return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_hook_emits_context_on_cwd_match(tmp_path: Path, register_project) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cwd = tmp_path / "code" / "alpha"
    cwd.mkdir(parents=True)
    register_project("alpha", vault, cwd_patterns=[str(cwd)])

    _write_full_page(vault, "concepts/a", body="alpha context body")
    _seed_manifest(vault, pages=["wiki/concepts/a.md"])

    payload = {"cwd": str(cwd), "session_id": "test", "source": "startup"}
    rc, stdout, _ = _run_hook(payload)
    assert rc == 0
    assert stdout, f"expected non-empty stdout; got {stdout!r}"
    out = json.loads(stdout)
    hsi = out["hookSpecificOutput"]
    assert hsi["hookEventName"] == "SessionStart"
    assert "additionalContext" in hsi
    assert "concepts/a" in hsi["additionalContext"]


def test_hook_silent_skip_on_resume(tmp_path: Path, register_project) -> None:
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


def test_hook_silent_skip_when_recursion_flag_set(tmp_path: Path, register_project) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    cwd = tmp_path / "code" / "alpha"
    cwd.mkdir(parents=True)
    register_project("alpha", vault, cwd_patterns=[str(cwd)])

    _write_full_page(vault, "concepts/a")
    _seed_manifest(vault, pages=["wiki/concepts/a.md"])

    payload = {"cwd": str(cwd), "source": "startup"}
    rc, stdout, _ = _run_hook(payload, env_extra={"MNEMOS_INJECT_RUNNING": "1"})
    assert rc == 0
    assert stdout == ""


def test_hook_silent_skip_on_unmatched_cwd(tmp_path: Path) -> None:
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    payload = {"cwd": str(cwd), "source": "startup"}
    rc, stdout, _ = _run_hook(payload)
    assert rc == 0
    assert stdout == ""


def test_hook_silent_skip_on_invalid_stdin(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input="not json",
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=15,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""
```

- [ ] **Step 2: Run**

```bash
cd /d/code/claude-mnemos
python -m pytest tests/test_session_start_hook.py -v 2>&1 | tail -15
```

Expected: 5 tests PASS. The hook reads from `~/.claude-mnemos/project-map.json`, which the autouse `isolate_cli_state` fixture isolates to `tmp_path`. The `register_project` fixture writes the entry there.

- [ ] **Step 3: Commit**

```bash
git add tests/test_session_start_hook.py
git commit -m "test: #13c hook integration — subprocess driven (5 cases)"
```

---

## Task 10: Final verification + acceptance walkthrough

- [ ] **Step 1: Backend full suite**

```bash
cd /d/code/claude-mnemos
python -m pytest tests/ -k "not slow" --ignore=tests/daemon/integration --tb=line 2>&1 | tail -5
```

Expected: all PASS (1235 baseline + ~30 new tests = ~1265 passing).

- [ ] **Step 2: ruff + mypy clean**

```bash
ruff check claude_mnemos/ tests/ hooks/ 2>&1 | tail -5
mypy claude_mnemos/ 2>&1 | tail -5
```

Expected: no errors.

- [ ] **Step 3: Acceptance criteria walk-through (design §6)**

1. ✅ `hooks/session_start.py` exists and registered in `hooks.json`.
2. ✅ Hook emits `{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: ...}}` on cwd match.
3. ✅ Source-field branching honored (resume/compact/edit skip).
4. ✅ Recursion guard via `MNEMOS_INJECT_RUNNING`.
5. ✅ `build_adaptive_context()` respects `max_chars`.
6. ✅ Scoring algorithm ranks by confidence + flavor + recency + proximity + cwd match.
7. ✅ Graph helper builds undirected adjacency.
8. ✅ Silent skip on cwd not matched, vault empty, exception during build.
9. ✅ ~30 new tests pass.
10. ✅ `ActivityOperationType` extended.
11. ✅ Backend baseline holds.
12. ✅ ruff + mypy clean.
13. ✅ Frontend untouched.
14. ⚠️ Manual smoke test: open new claude session in matched cwd → context appears. Run on user's actual machine; not part of pytest.

- [ ] **Step 4: Branch summary**

```bash
git log --oneline main..HEAD
git status
```

~10 commits, working tree clean.

- [ ] **Step 5: Optional commit if anything dangling**

If any small fix-up emerged during verification, commit. Otherwise verification-only.

---

## Spec coverage map

| Design § | Plan task |
|---|---|
| 2.1 output channel | Tasks 6, 7 (builder produces; hook emits) |
| 2.2 source branching | Task 7 (hook) + Task 9 (hook test) |
| 2.3 algorithm | Tasks 2, 3, 4, 5, 6 (graph → seeds → score → pack) |
| 2.4 hook script | Task 7 |
| 2.5 hooks.json | Task 8 |
| 2.6 activity op_type | Task 1 |
| 2.7 graph helper | Tasks 2, 3 |
| 2.8 budget heuristic | Task 6 |
| §6 ACs | Task 10 |
