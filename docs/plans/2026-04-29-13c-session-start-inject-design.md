# Plan #13c — SessionStart adaptive context inject (design)

**Date:** 2026-04-29
**Status:** Design
**Goal:** Ship a SessionStart hook that, when a Claude Code session starts in a matched CWD, injects relevant vault pages into the model's context. Final feature from spec v0.2 (§5.2 / §9.2 / §15 / §22). Backend-only.

---

## 1. Background

When a user opens `claude code` in a project's working dir, claude has zero memory of prior sessions. The user has to re-explain context every time. Adaptive inject closes this gap: a SessionStart hook resolves the cwd → project, builds a focused page bundle, and emits it as `additionalContext` so claude reads it as part of its system prompt.

### Recon findings

- **Spec §17 hypothesis was wrong** — §17 is "Testing Strategy". The inject material lives in §5.2 (flow), §9.2 (hook code), §15 (metrics), §22 (glossary).
- **Reference impl exists** at `d:/Обсидиан мозги/OBSIDIAN/.shared/hooks/session-start.py` (191 lines, working, in production for the user). Already debugged the Claude Code hook JSON contract.
- **Spec's output shape is wrong**: §9.2 says `print({"context": ...})`. Actual contract: `print({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}})`. Reference impl confirms.
- **No SessionStart in mnemos today.** `hooks.json` registers only `SessionEnd`. `claude_mnemos/core/session_start.py` doesn't exist.
- **Frontmatter model** has `type` / `status` / `confidence` / `flavor` / `related` / `provenance` etc. Pydantic v2 `extra="forbid"`.
- **Wikilinks helpers** exist (`extract_wikilinks`, `find_files_referencing`) but no K-hop graph traversal.
- **Manifest** records each session's `created_pages` — gives "last N sessions' affected pages" for free.
- **CWD resolver** uses `fnmatch.fnmatchcase` with most-specific-wins. Battle-tested in `session_end.py` and MCP server.

### Scope decision

**One plan, ~12 tasks.** The recon recommended a 3-way split (α plumbing / β scoring / γ metrics). I'm collapsing α + β into one plan because shipping "naïve last 10 pages" without scoring isn't really adaptive — it's just a dump. Including smart scoring keeps the feature honest. **§15 compression_ratio metric is deferred** to a follow-up plan (not blocking the inject itself; just the dashboard view).

### Out of scope

- §15 `compression_ratio` metric + `state/inject-metrics.json` + `/metrics/inject` route + dashboard widget. Defer to follow-up.
- Materialized `overview.md` / `index.md` / `hot.md` artifacts that §5.2 mentions — they don't exist in current vaults, and on-the-fly synthesis from the manifest works fine.
- Tokenizer dependency (tiktoken). Use char-count budget with 4 chars ≈ 1 token heuristic; document the approximation.
- MCP-tool pull-mode `get_session_context`. Hook stdout is sufficient.
- Frontend Activity-toast specific to inject. Existing Activity stream picks up the new op_type automatically.

---

## 2. Architecture

### 2.1 Output channel

Hook `hooks/session_start.py` reads stdin payload (`{cwd, session_id, transcript_path, source}`), calls `claude_mnemos.core.session_start.build_adaptive_context(project, cwd, ...)`, prints JSON to stdout:

```json
{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}
```

Hook timeout 15 s (per spec §9.2). On any error: silent skip — emit empty stdout, log to `~/.claude-mnemos/inject.log`. Never break the session.

### 2.2 Source-field branching

Claude Code's SessionStart payload includes `source: "startup" | "resume" | "clear" | "compact" | "edit"`. Behavior:

| `source` | Action |
|---|---|
| `startup` | inject |
| `clear` | inject (treat as new session) |
| `resume` | skip (claude already has the prior context) |
| `compact` | skip (claude just compacted) |
| `edit` | skip |
| (missing) | inject (conservative default) |

### 2.3 build_adaptive_context algorithm

`claude_mnemos.core.session_start.build_adaptive_context(project, cwd, max_chars=40_000) → str`:

1. **Recent sessions' affected pages** — read `Manifest.ingested` for `project`, take last `N=10` `IngestRecord`s, flatten `created_pages`. Set of "seed" page slugs.
2. **K-hop graph expansion** — build forward+backward edges from `frontmatter.related` and body `[[wikilinks]]`. From the seed set, BFS to K=2 hops. Add discovered slugs to the candidate pool.
3. **CWD-aware boost** — for every candidate, scan body for substrings matching `cwd` last-segment (e.g., if cwd is `D:/code/foo`, boost pages mentioning `foo`).
4. **Score** each candidate:
   ```
   score = 1.0 * confidence
         + 0.5 * flavor_weight  # decision/lesson=1.0, pattern=0.7, reference=0.4, mistake=0.5
         + 0.3 * recency_decay  # last_human_edit, exp decay over 30 days
         + 0.4 * graph_proximity  # 1.0 at hop 0, 0.5 at hop 1, 0.2 at hop 2
         + 0.6 * cwd_match  # 1.0 if cwd-segment found in body, 0 otherwise
   - 0.5 * stale_penalty  # if status == "stale" or "archived"
   ```
   Constants are exposed as module-level so they can be tuned.
5. **Rank** descending. **Trim by char budget**: greedy pack pages until char count ≥ `max_chars * 0.95` or pool exhausted. Each page contributes its title + one-line summary (frontmatter `title` + first 200 chars of body) by default. **Top 3** pages get full body if budget allows.
6. **Format** as a markdown block:
   ```markdown
   # Project context (mnemos)

   Recent sessions touched these pages:
   - [[wiki/concepts/foo]] — short summary

   ## Top relevant
   ### [[wiki/entities/bar]]
   <full body>

   ### ...
   ```

### 2.4 hooks/session_start.py

Skeleton (port from `session_end.py`):

```python
#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

RECURSION_FLAG = "MNEMOS_INJECT_RUNNING"
SKIP_SOURCES = {"resume", "compact", "edit"}


def main() -> int:
    if os.environ.get(RECURSION_FLAG) == "1":
        sys.exit(0)
    os.environ[RECURSION_FLAG] = "1"

    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if payload.get("source") in SKIP_SOURCES:
        sys.exit(0)

    cwd_str = payload.get("cwd")
    if not cwd_str:
        sys.exit(0)

    try:
        from claude_mnemos.mapping.resolver import ProjectResolver
        from claude_mnemos.core.session_start import build_adaptive_context
    except Exception as exc:
        _log(f"import failed: {exc}")
        sys.exit(0)

    cwd = Path(cwd_str)
    try:
        project = ProjectResolver().resolve_by_cwd(cwd)
    except Exception as exc:
        _log(f"resolve failed: {exc}")
        sys.exit(0)

    if project is None:
        sys.exit(0)  # cwd not in any project — silent skip

    try:
        context = build_adaptive_context(project, cwd, max_chars=40_000)
    except Exception as exc:
        _log(f"build failed: {exc}")
        sys.exit(0)

    if not context:
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }))
    return 0


def _log(msg: str) -> None:
    log_path = Path.home() / ".claude-mnemos" / "inject.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"{msg}\n")


if __name__ == "__main__":
    main()
```

### 2.5 hooks.json registration

Append to existing `hooks.json`:

```json
{
  "SessionEnd": "hooks/session_end.py",
  "SessionStart": "hooks/session_start.py"
}
```

(Confirm the actual hooks.json shape first — may use a different structure.)

### 2.6 Activity recording

Add to `claude_mnemos/state/activity.py::ActivityOperationType` the literal `"session_start_inject"`. The hook itself doesn't write an Activity entry directly — it's a one-way emit, and the daemon may not even be running. Instead, the hook **optionally** posts to a new daemon endpoint `POST /sessions/{project}/inject-event` if reachable; otherwise silent skip. This keeps Activity history when daemon is up but doesn't block inject when daemon is down.

For v1 (this plan), **omit the daemon write** entirely. Activity recording can be added later without changing the hook contract. This keeps #13c minimal and fully offline-compatible.

### 2.7 Graph helper

`claude_mnemos/core/graph.py`:

```python
def build_page_graph(vault: Path) -> dict[str, set[str]]:
    """Return slug → set of slugs adjacent (forward + backward via wikilinks).

    Builds an undirected adjacency map. Slug = relative path under wiki/
    without .md suffix.
    """

def pages_within_k_hops(
    graph: dict[str, set[str]],
    seeds: set[str],
    *,
    k: int = 2,
) -> dict[str, int]:
    """BFS from each seed; return slug → min-hop-distance for all reachable
    pages within k hops. Seeds map to 0.
    """
```

The graph is built fresh per inject call. On a 2k-page vault this is ~50 ms. If needed later, daemon can cache and watchdog-invalidate.

### 2.8 Char-budget heuristic

Token approximation: `len(text) / 4`. The 40 000 char default ≈ 10 000 tokens. Documented in module docstring. Real tokenizer dependency (tiktoken / anthropic.count_tokens) deferred — overkill for this approximation.

---

## 3. Data flow

```
Claude Code SessionStart
  ↓ stdin: {cwd, session_id, transcript_path, source}
hooks/session_start.py
  ├─ source filter (skip resume/compact/edit)
  ├─ recursion guard (MNEMOS_INJECT_RUNNING=1)
  └─ ProjectResolver.resolve_by_cwd(cwd)
      ├─ no match → silent skip
      └─ project found
          ↓
core.session_start.build_adaptive_context(project, cwd, max_chars=40000)
  ├─ Manifest.load(vault).ingested → last N sessions' created_pages → seeds
  ├─ build_page_graph(vault)
  ├─ pages_within_k_hops(graph, seeds, k=2) → candidates
  ├─ score each candidate (confidence + flavor + recency + proximity + cwd_match - stale)
  ├─ rank, trim to char budget, format as markdown
  └─ return string
      ↓
print {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}
  ↓
Claude Code prepends to system prompt
```

---

## 4. New / changed files

**New:**
- `claude_mnemos/core/session_start.py` — `build_adaptive_context()` + scoring constants
- `claude_mnemos/core/graph.py` — `build_page_graph()`, `pages_within_k_hops()`
- `hooks/session_start.py` — hook entry point
- `tests/test_graph.py`
- `tests/test_session_start.py`
- `tests/integration/test_session_start_hook.py` (or wherever hook tests live)

**Modified:**
- `claude_mnemos/state/activity.py` — add `"session_start_inject"` literal to `ActivityOperationType`
- `hooks/hooks.json` — register SessionStart hook

---

## 5. Testing strategy

- **`test_graph.py`** unit tests:
  - empty vault → empty graph
  - single page no links → graph contains slug with empty neighbors
  - bidirectional wikilink → both slugs neighbors
  - frontmatter `related` produces edges
  - `pages_within_k_hops` k=0/1/2 boundaries
- **`test_session_start.py`** unit tests on synthetic vault:
  - cwd-pattern matched + seeds present → builds non-empty context
  - confidence/flavor/recency weights produce expected ranking on hand-crafted fixture
  - char budget trim respected (assert `len(context) ≤ max_chars`)
  - empty vault → empty string returned
  - graph proximity priority: hop-0 > hop-1 > hop-2
- **Hook integration test** (subprocess):
  - feed JSON stdin; assert stdout JSON shape
  - assert recursion guard: re-invocation with `MNEMOS_INJECT_RUNNING=1` exits with empty stdout
  - assert source-field skip: `source=resume` → empty stdout
  - assert silent fail on bad input

Total: ~25-30 new pytest tests. Frontend Vitest unchanged.

---

## 6. Acceptance criteria

1. ✅ `hooks/session_start.py` exists and is registered in `hooks.json`.
2. ✅ Hook emits `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}` on cwd match.
3. ✅ Source-field branching honored (resume/compact/edit skip).
4. ✅ Recursion guard via `MNEMOS_INJECT_RUNNING`.
5. ✅ `build_adaptive_context()` respects `max_chars` budget.
6. ✅ Scoring algorithm ranks pages by confidence + flavor + recency + graph proximity + cwd match.
7. ✅ Graph helper builds undirected adjacency from frontmatter `related` + body wikilinks.
8. ✅ Silent skip on: cwd not matched, daemon down, vault empty, exception in scoring.
9. ✅ ~25-30 new pytest tests; all pass.
10. ✅ `ActivityOperationType` enum extended with `"session_start_inject"` (consumed by future #13c follow-up).
11. ✅ Backend pytest baseline holds (1235 → 1260+ passing).
12. ✅ ruff + mypy clean.
13. ✅ Frontend untouched.
14. ✅ Manual smoke test: open new claude session in a matched cwd → context appears in claude's response (verify by asking claude "what's in your system context?" or similar).

---

## 7. Risks

- **Hook JSON shape — `additionalContext`, not `context`.** Verified against working LLM Wiki impl. If a future Claude Code version changes contract, we break silently. Mitigate: log on emit so we can verify in a real session.
- **Graph build performance.** 2k-page vault ≈ 50 ms per inject (acceptable). 20k-page vault would be 500 ms — still inside the 15 s timeout but worth a cache. Defer cache to follow-up.
- **Scoring constants drift.** Initial weights are heuristic; will need tuning. Module-level constants make this easy.
- **Char budget overshoot.** Greedy packing; document that the trim is char-based and approximate. Real-world overshoot ≤ 1 page worth.
- **Seed set empty for fresh project.** First-ever session in a new project has no manifest entries. Algorithm degrades: seeds = empty → graph expansion produces nothing → return empty string → silent skip. User sees no inject. Acceptable. Could fall back to "list all pages with confidence ≥ 0.8" — defer.
- **Frontmatter `related` validity.** If user puts a non-existent slug in `related`, graph builder must not crash. Test for this.
- **Stale ingest records.** Manifest may reference deleted pages. Score them in `created_pages` but skip in graph if file missing. Already protected by file-existence check.

---

## 8. Decomposition map

| Design § | Plan task |
|---|---|
| 2.1 output channel | Tasks 1-3 (graph + scoring + format) feed into Task 4 (hook) which produces the channel |
| 2.2 source branching | Task 5 |
| 2.3 algorithm | Tasks 1-3 (graph, scoring, format) |
| 2.4 hook script | Task 6 |
| 2.5 hooks.json | Task 7 |
| 2.6 activity op_type | Task 8 |
| 2.7 graph helper | Task 1 |
| 2.8 budget heuristic | Task 3 |
| §6 ACs | Task 11 (final verification) |

Roughly 11 tasks. Backend-heavy, no frontend.

---

(end of design)
