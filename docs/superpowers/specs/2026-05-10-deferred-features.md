# Deferred / not-yet-implemented features

> **Status:** living document. Created 2026-05-10 alongside v0.0.12, which
> dropped 5 placebo `ProjectSettings` groups. Their schemas had been written
> but no production code path read them — they appeared in the UI as toggles
> that did nothing. Removed from runtime, recorded here as a roadmap.

The decision criterion for each row is **"Does claude-mnemos need this to be
a stable, complete memory for Claude Code?"** If the default behaviour
already covers the core use case, the feature is deferred (not "removed
forever" — just not on the critical path).

---

## 1. Watchdog mode (`watchdog.mode: strict | merge | open`)

### What it was supposed to do

Govern how the watchdog handles external edits to vault page files (i.e.
edits NOT made by mnemos itself, like the user editing a page in Obsidian).

* `strict` — reject external edits, force re-read from disk
* `merge` — let the edit stand, mark `agent_written=False`, log to activity
* `open` — disable tracking entirely; trust the user

### What replaces it now

Hardcoded `merge` mode in `claude_mnemos/daemon/watchdog_handler.py`.
External edits land in the file, get the `agent_written=False` frontmatter
flag, and produce an activity entry of kind `human_edit_detected`. No
blocking, no rejection.

### Needed for core memory?

**No.** The merge mode is the right default for a personal-knowledge
system — users CAN edit their notes, the system records the fact and moves
on. `strict` is only useful for "frozen archive" vaults (rare); `open` is
useful for read-heavy vaults where tracking is overhead (also rare).

### Recommendation

**Defer.** Add back if a user actually requests strict-archive behaviour.
Until then merge handles every realistic case.

---

## 2. Ontology HITL auto-mode (`ontology.auto_mode`, `confidence_min`,
`confidence_auto_apply`)

### What it was supposed to do

Govern the human-in-the-loop ontology pipeline (entity merges, page
renames, page deletions proposed by the LLM). The toggles would let high-
confidence proposals (`confidence >= confidence_auto_apply`, default 0.95)
auto-apply without user review.

### What replaces it now

All ontology operations require **manual approval** through the dashboard's
"Suggestions" page. Each proposal is staged via `StagingTransaction` with a
pre-op snapshot, the user reviews, clicks "Apply" or "Dismiss".

### Needed for core memory?

**No.** Manual review is the safer default — wrong auto-merges would
silently corrupt the vault. The current flow surfaces all proposals to the
user; the only loss is convenience for users who trust the LLM enough to
auto-accept high-confidence ones.

### Recommendation

**Defer.** Auto-mode is risky and only useful after the user has built
trust in their model + prompt configuration. If the use case appears
("I have 200 pending ontology proposals and they're all obviously right"),
revisit.

---

## 3. Lifecycle auto-archive (`lifecycle.auto_stale_days`,
`lifecycle.auto_archive`)

### What it was supposed to do

Detect pages that haven't been read or edited in N days (default 90) and
either flag them as stale or auto-move them into `<vault>/archive/` so the
inject-context pipeline doesn't keep loading them.

### What replaces it now

Nothing. Pages live in `wiki/` forever. The vault grows monotonically.
`SessionStart` adaptive context (Plan #13c) ranks pages by relevance per
session, so stale pages are naturally deprioritized at inject time without
having to physically move them.

### Needed for core memory?

**Not for correctness.** It IS useful for long-term storage hygiene —
after 2+ years of heavy use, a vault may have 5000+ pages, half of which
are obsolete. Auto-archive would keep the active set lean and the
inject-context build faster.

### Recommendation

**Defer until the vault size becomes a measurable problem.** For most
users in the first year or two this is invisible. Worth revisiting when
someone reports slow Overview / slow inject-preview / slow vault scan.

---

## 4. Custom prompts (`prompts.custom_system_path`,
`prompts.custom_extract_user_path`)

### What it was supposed to do

Let a power user override the bundled LLM prompts (system prompt + extract
user prompt) with their own files. E.g. tune the extraction style for a
specific domain or change the language preference at the prompt level
rather than via the `language_hint` flag.

### What replaces it now

Bundled prompts in `claude_mnemos/ingest/prompts/` apply to every project.
The `language_hint` setting (still present, in `IngestOverrides` — also
deferred, see §6) was meant to let you steer language without overriding
the entire prompt.

### Needed for core memory?

**No.** Bundled prompts work for the three locales (en/uk/ru). Custom
prompts are a power-user feature for niche tuning needs.

### Recommendation

**Defer indefinitely** — until at least one user complains that bundled
prompts don't fit their domain. Risk of opening this is high: bad custom
prompts produce malformed LLM output that breaks the ingest pipeline. If
revisited, also need a "validate prompt schema" step.

---

## 5. Telemetry opt-in (`telemetry.opt_in`)

### What it was supposed to do

Toggle anonymous usage statistics — what features users use, ingest
volumes, error rates — sent to a backend the maintainer would set up.

### What replaces it now

Nothing. There is no backend, no collection, and no opt-in toggle
required because there is nothing to opt in to. Local logs in
`~/.claude-mnemos/` are all that exists.

### Needed for core memory?

**No.** Privacy is a feature here, not a missing one. claude-mnemos is a
single-user tool that runs locally — telemetry would only matter if it
became a multi-user product or a hosted service.

### Recommendation

**Drop entirely** unless the project becomes a hosted product. The setting
was vestigial from when claude-mnemos was scoped as a possible cloud tool.

---

## 6. Per-project ingest overrides (`ingest.model`, `ingest.language_hint`,
`ingest.max_input_tokens`, `ingest.context_limit`)

### What it was supposed to do

Let each project override the global ingest defaults. Use cases:
* a Russian-only project pinning `language_hint: ru` instead of `auto`
* a research project using a more capable model than the default
* a noisy chat-log project capping `max_input_tokens` to keep ingest cheap

### What replaces it now

Every project uses `GlobalSettings.{default_model, default_language_hint,
default_max_input_tokens}`. `language_hint: auto` works for most multi-
language users via per-session detection. `default_model: claude-sonnet-4-6`
is sensible across domains.

### Needed for core memory?

**No, for single-user single-domain workflows.** Yes, for users with
multiple distinct projects (different languages, different LLM budgets per
project). Ярик's use case (claude-mnemos-dev + perviy + future projects
all in Russian/Ukrainian) is single-domain enough that the global default
is fine.

### Recommendation

**Defer** until a multi-domain user complains. The wiring is
straightforward when revisited — the ingest pipeline already accepts
these as kwargs; the only missing step is reading them out of
`ProjectSettings.ingest` (which doesn't exist anymore) and threading
through.

---

## Summary table

| Feature | Replaces it | Needed for core memory? | Recommendation |
|---|---|---|---|
| Watchdog mode | hardcoded `merge` | No | Defer |
| Ontology auto-mode | manual review of all proposals | No | Defer |
| Lifecycle auto-archive | nothing (pages live forever) | Not yet | Revisit when vaults get >5000 pages |
| Custom prompts | bundled prompts | No | Defer indefinitely |
| Telemetry opt-in | nothing (no backend) | No | Drop |
| Per-project ingest overrides | global defaults | Not for single-domain users | Defer until needed |

## Conclusion

claude-mnemos is **complete and stable as a Claude Code memory system
without any of these six features**. They each add either:

* **Safety hardening** (Watchdog strict mode, Ontology HITL auto-apply)
  for niche use cases that aren't the default workflow
* **Operational convenience** (Lifecycle auto-archive, Per-project ingest
  overrides) that only matters at scale or with multiple distinct projects
* **Power-user customization** (Custom prompts) that introduces risk
  without clear value for the typical user
* **Cloud-product features** (Telemetry) that don't fit the local single-
  user model

The bar for re-implementing any of them: **a real user complaint that the
default behaviour is broken, not just less convenient**. Until then the
v0.0.12 surface area is the right one — six accordion sections that all do
something real, no toggles that lie about what they do.
