# claude-mnemos — project instructions

## Skills (superpowers) — ALWAYS USE

For **every** non-trivial task in this repo, default to the `superpowers` skills. They override the default system behaviour where they conflict.

**Mandatory by task type:**

| Situation | Required skill |
|---|---|
| New feature / change you don't fully understand yet | `superpowers:brainstorming` → produces spec in `docs/superpowers/specs/` |
| Spec exists, need to implement | `superpowers:writing-plans` → produces plan in `docs/superpowers/plans/` |
| Plan exists, executing | `superpowers:subagent-driven-development` (preferred) OR `superpowers:executing-plans` |
| Writing or modifying code | `superpowers:test-driven-development` (TDD: red → green → refactor) |
| Bug report | `superpowers:debugging` (reproduce → isolate → fix → regression test) |
| Frontend UI work | `superpowers:frontend-design` |
| Before declaring "done" | `superpowers:verification-before-completion` |
| Before merging branch | `superpowers:finishing-a-development-branch` |
| Asking for review | `superpowers:requesting-code-review` |

**Even a 1% chance a skill applies → invoke it.** Do not rationalise it away as "this is simple". Apply skills BEFORE writing any code or response.

**Process order when multiple skills could apply:**
1. Process skills first (brainstorming, debugging) — determine HOW
2. Implementation skills second (frontend-design, TDD) — determine execution

**Locations:**
- Specs: `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
- Plans: `docs/superpowers/plans/YYYY-MM-DD-<feature>.md`

User feedback already captured in memory (read `~/.claude/projects/.../memory/MEMORY.md`):
- `feedback_superpowers.md` — superpowers by default
- `feedback_show_findings_before_fixing.md` — after audit show findings, wait for choice
- `feedback_no_pause_between_subagent_tasks.md` — execute lists without pauses
- `feedback_brainstorming_style.md` — design as a single block, one gate

## Stack quick-ref

- Backend: Python 3.12, FastAPI, pytest (asyncio mode), pydantic v2
- Frontend: React 19, Vite, Tailwind v4, shadcn-ui, react-router v7, i18next, Vitest, Zod
- Locales source of truth: `frontend/public/locales/{en,uk,ru}.json` (mirrored into `claude_mnemos/daemon/static/locales/` at build)
- Backend user-facing strings: emit `i18n_key` + `i18n_params`, frontend renders via `t(key, params, { defaultValue: message })`
- Tests: backend via `pipx`-installed Python (`~/pipx/venvs/claude-mnemos/Scripts/python.exe -m pytest`), frontend via `npm test`
- Daemon dev port: 5757
- All API routes under `/api/` prefix (do NOT revert to bare paths)

## Hard rules

1. Never create projects/vaults/persistent artifacts without explicit user consent — diagnose gaps, ask first.
2. Never run destructive git ops (force-push, reset --hard, branch -D) without explicit ask.
3. Never skip hooks (`--no-verify`) or signing.
4. After audit/review: show findings with severity, **wait** for user's "fix what" before applying.
5. Match locale-format dates via `formatDateTime(iso, i18n.language)` — never render raw ISO in user-facing UI.
