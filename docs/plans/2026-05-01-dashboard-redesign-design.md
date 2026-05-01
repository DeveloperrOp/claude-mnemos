# Dashboard Redesign — Design Spec v0.1

**Date:** 2026-05-01
**Owner:** Yarik (with Claude pair)
**Status:** Approved (inline approval), ready for implementation plan
**Scope:** Visual layer only — IA / routes / feature logic unchanged

---

## Vision

Turn the dashboard from stock-shadcn admin grey into a **terminal/IDE-feeling
instrument**. A programmer opens it and recognizes "their" aesthetic: monospace
labels with section markers, lime accent (familiar from `git diff +`, ESLint
passing, terminal cursors), tactile micro-motions. Anti-generic AI output —
opinionated and recognizable.

Stack stays: React 19 + Tailwind v4 + shadcn/ui + recharts. We change tokens,
typography, three signature components — not the framework.

---

## Color tokens (oklch)

All colors expressed in OKLCH for perceptual uniformity and dark/light parity.
Tailwind v4 native — no HSL fallback needed.

Cool blue-grey hue baseline `264` (so dark theme doesn't drift sepia).

| Token | Light | Dark | Purpose |
|---|---|---|---|
| `--bg` | `oklch(99% 0.005 264)` | `oklch(15% 0.012 264)` | primary background |
| `--bg-elev-1` | `oklch(97% 0.006 264)` | `oklch(18% 0.014 264)` | cards, popovers |
| `--bg-elev-2` | `oklch(94% 0.008 264)` | `oklch(22% 0.016 264)` | nested cards, hover |
| `--fg` | `oklch(20% 0.02 264)` | `oklch(95% 0.01 264)` | primary text |
| `--fg-muted` | `oklch(45% 0.015 264)` | `oklch(65% 0.012 264)` | secondary text, labels |
| `--fg-subtle` | `oklch(60% 0.01 264)` | `oklch(50% 0.01 264)` | hint, placeholder |
| `--border` | `oklch(90% 0.008 264)` | `oklch(28% 0.014 264)` | dividers |
| `--border-strong` | `oklch(80% 0.01 264)` | `oklch(40% 0.018 264)` | active focus, selection |
| `--accent` | `oklch(70% 0.22 130)` | `oklch(85% 0.27 130)` | **lime — primary accent** |
| `--accent-fg` | `oklch(20% 0.05 130)` | `oklch(15% 0.05 130)` | text on accent fill |
| `--accent-dim` | `oklch(55% 0.12 130)` | `oklch(60% 0.15 130)` | accent muted state |
| `--success` | `oklch(70% 0.22 145)` | `oklch(80% 0.20 145)` | green-positive (distinct from accent) |
| `--warning` | `oklch(75% 0.16 75)` | `oklch(82% 0.18 75)` | amber |
| `--danger` | `oklch(60% 0.22 25)` | `oklch(70% 0.20 25)` | red |
| `--info` | `oklch(65% 0.15 240)` | `oklch(75% 0.15 240)` | cyan-ish |

Accent intensity in light mode (`oklch(70% 0.22 130)`) may need a step down
to `oklch(65% 0.18 130)` if it visually pierces during testing — track this
during Phase 4 visual check.

---

## Typography

**Families** (via `geist` npm package, served as `@font-face`):

- **Geist Sans** — body, prose, UI controls. Variable axis, weights 400–700.
- **Geist Mono** — headings, labels, metrics, code, file paths, IDs. Variable
  axis, weights 400–600.

**Scale (rem, base 16px):**

| Token | Value | Use |
|---|---|---|
| `--text-xs` | 0.75 | uppercase labels, badges |
| `--text-sm` | 0.875 | secondary body, table cells |
| `--text-base` | 1 | primary body |
| `--text-lg` | 1.125 | sub-headings |
| `--text-xl` | 1.25 | card-level headings |
| `--text-2xl` | 1.5 | page section headings |
| `--text-3xl` | 1.875 | page titles |

**Pattern «SECTION ▸ VALUE»** — used wherever metrics/status appear:

```
JOBS ▸ 03 queued   01 running   00 dead-letter
```

- Label: uppercase mono, `text-xs`, `tracking-wider`, `text-fg-muted`.
- Value: bold mono, `text-base`, `text-fg` (or `text-accent` for highlighted).
- Separator `▸` (`U+25B8`) in `text-fg-subtle`.

**Headings:**

- Page titles, section headings, card titles → Mono, weight 600.
- Long prose (Help workflows/troubleshooting bodies, About) → Sans.

---

## Spacing & layout

- 4px base scale (Tailwind default).
- Container max-width `1280px`.
- Sidebar `220px` (unchanged).
- Card padding `p-4` (16px). Nested card padding `p-3` (12px).
- Section gap `space-y-6` (24px) — feels denser than current `space-y-10`.

---

## Motion language

**Durations** (CSS variables in `:root`):

- `--motion-fast` 80ms — colour-only transitions (hover bg/fg).
- `--motion-medium` 150ms — transform/opacity (modals, popovers, accordion).
- `--motion-slow` 250ms — page entry, tab switching.

**Easings:**

- `--ease-out` `cubic-bezier(0.2, 0.7, 0.1, 1)` — default for entry/expand.
- `--ease-in-out` `cubic-bezier(0.4, 0, 0.2, 1)` — bidirectional state changes.

**Signature elements (exactly three, no more):**

1. **Blink cursor** `▌` (`U+258C`) — placed in active job counter (sidebar)
   or page header context. CSS keyframe:
   ```css
   @keyframes blink { 50% { opacity: 0 } }
   .cursor-blink { animation: blink 1.06s steps(2, start) infinite; }
   ```
   1.06s asymmetric duration mirrors xterm/VS Code defaults — not a
   symmetric 1s flash.

2. **Status pulse** — for `running` jobs and `active` watchdog states. Lime
   gradient pulse:
   ```css
   @keyframes pulse-accent {
     0%, 100% { opacity: 0.6 }
     50%      { opacity: 1.0 }
   }
   .pulse-accent { animation: pulse-accent 2s ease-in-out infinite; }
   ```

3. **Hover lift** on cards — `border-color: var(--border-strong)` + a 1px
   subtle box-shadow, transitioning over `--motion-fast`. **No translate, no
   scale** (cinematic hover-lift is overkill for an instrument).

**Anti-list (do NOT do):**

- Cinematic page transitions, parallax, scroll-triggered animations,
  hover-tilt, color transitions longer than 250ms, spring physics, FLIP
  reordering, hero scroll narratives.

---

## Component patterns

### Cards (`<Card>` shadcn)

- Border 1px `--border`. Hover → `--border-strong` + subtle shadow.
- Padding `p-4`. Radius `rounded-md` (6px — not softer; sharper feels
  technical).
- `<CardTitle>`: Mono, uppercase, `text-xs`, `tracking-wider`, `text-fg-muted`.
- For "real" headings outside the card frame, use a sans `<h2>` above the card.

### Buttons

- `primary` (default): `bg-accent text-accent-fg`, hover `bg-accent-dim`,
  Mono uppercase letter-spacing.
- `secondary`: `bg-bg-elev-1 border border-border text-fg`, hover `bg-bg-elev-2`.
- `ghost`: `text-fg-muted`, hover `bg-bg-elev-1 text-fg`.
- `danger`: outline-style — `border-danger text-danger`, hover `bg-danger
  text-bg`.

### Badges / status pills

- Tiny mono uppercase: `text-[10px] tracking-widest`, `px-2 py-0.5`.
- `running` → `bg-accent/20 text-accent` + `pulse-accent` animation.
- `queued` → `bg-info/20 text-info`.
- `failed` / `dead-letter` → `bg-danger/20 text-danger`.
- `done` / `extracted` → `bg-success/20 text-success`.
- `archived` / `dismissed` → `bg-fg-muted/20 text-fg-muted`.

### Inputs / selects

- Body inputs: Sans.
- Numeric inputs, file paths, IDs, slug fields: **Mono**.
- Border `--border`, focus → 1px `--accent` ring (no glow blur — keep crisp).
- Background `--bg-elev-1`.

### Dropdowns / popovers

(Already opaque after `8f7c3f1`. Add):

- Border 1px `--border-strong`.
- Focused item: 2px left border `--accent`, otherwise no fill change.
- `bg-bg-elev-1`.

### Tables

- Zebra: even rows `bg-bg`, odd rows `bg-bg-elev-1`.
- Header row: Mono uppercase `text-xs tracking-wider text-fg-muted`.
- Numeric columns: Mono right-align.
- Hover row: `bg-bg-elev-2`.

### Code blocks (Help quickstart, workflows)

- Block: `bg-bg-elev-2`, Mono, `p-3`, **`border-l-2 border-accent`**.
- Inline `<code>`: `bg-bg-elev-1 text-accent`, `px-1.5 py-0.5`, Mono,
  `rounded-sm`.

(This implies adding a minimal markdown pass to `MultiPara` — see Open
questions below.)

### Charts (recharts)

- Grid lines: `--border` (very dim).
- Axes labels: Mono, `text-fg-muted`, `text-xs`.
- Series colors:
  - Primary → `--accent`.
  - Secondary → `--info`.
  - Tertiary → `--warning`.
  - **Not a rainbow.** Three-series ladder maximum; if more, dim the rest
    to `--fg-muted` shades.
- Tooltip: `bg-bg-elev-1 border-border`, mono numbers.

---

## Theme toggle

- UI: Sun/Moon icon (Lucide) in `Header.tsx`, next to the language selector.
- State: `localStorage` key `mnemos-theme` ∈ `"light" | "dark" | "system"`.
- Default: `"system"` (CSS `prefers-color-scheme`).
- CSS class `.dark` toggled on `<html>`. All tokens defined twice (`:root`
  and `.dark`).

---

## Iconography

Lucide (already used). Single stroke weight `1.5`. Default size `16px`.
Line icons pair naturally with Mono typography. No icon redesign needed.

---

## Migration plan (5 phases — each its own commit)

1. **Phase 1 — Tokens.** Rewrite `globals.css`: all `--*` variables for
   light + dark, `@theme` block mapping to Tailwind v4 semantic colors. Drop
   leftover shadcn defaults. **~1 file.**

2. **Phase 2 — Typography.** Install `geist` npm package. Load via
   `@font-face` (preferred) or `<link>` in `index.html`. Set body default
   to Geist Sans. Mono utility class works via Tailwind `font-mono` now
   pointing at Geist Mono. **~2 files.**

3. **Phase 3 — Signature components.** Add three new tiny components in
   `frontend/src/components/signature/`:
   - `BlinkCursor.tsx` — renders `▌` with `cursor-blink` class.
   - `MetricLabel.tsx` — renders `LABEL ▸ value` pattern; takes `label`
     and `children` props.
   - `StatusPill.tsx` — renders status string with appropriate
     bg/fg/animation lookup. Replaces ad-hoc badges in
     `JobStatusBadge` / `PageStatusBadge` if they exist.

   **~3 new files + 1-2 call-site touches.**

4. **Phase 4 — Component restyle.** Walk through shadcn primitives and
   apply new tokens + Mono pattern:
   `button.tsx`, `card.tsx`, `badge.tsx`, `input.tsx`, `select.tsx`,
   `dropdown-menu.tsx`, `dialog.tsx`, `popover.tsx`, `table.tsx`,
   `accordion.tsx`. Plus the `Header.tsx` and `Sidebar.tsx` shells.
   **~12 files.**

5. **Phase 5 — Charts + Theme toggle.** Rewire recharts color tokens
   through CSS variables (or Tailwind `text-*` utilities passed to recharts
   `<Cell>`/`<Line>` via inline style). Add `<ThemeToggle>` in `Header.tsx`
   with `localStorage` persistence and `system` default.
   **~3 files.**

Each phase: green vitest, manual UI smoke check at `127.0.0.1:5757`,
single commit. No phase deferred to a later PR — full pass in one
implementation session.

---

## Out of scope

- Information architecture (sidebar items, route structure).
- Feature behavior of any page.
- New components beyond shadcn primitives + 3 signature elements.
- Storybook / visual regression tests.
- Markdown rendering richness in `MultiPara` (kept as plain text — this
  redesign only adds **fenced code block** styling for sections that already
  use indented code; no new parsing logic).
- Custom icon pack.
- Animation library (Framer Motion etc.) — stay on CSS keyframes.

---

## Risks & open questions

- **Mono headings in long prose** (Help workflows, troubleshooting bodies)
  may visually fight readability. Mitigation: prose-body inside Help
  cards stays Sans; Mono is reserved for the card titles, section labels,
  and inline code.
- **Lime accent intensity in light mode** may pierce eyes (oklch 70% / 0.22
  chroma is high-saturation). If visual check during Phase 4 confirms it,
  step down to `oklch(65% 0.18 130)`. Track in implementation plan as a
  decision-point at end of Phase 4.
- **Theme toggle persistence** is local-only via `localStorage`. Future
  user-settings rollout (when multi-user lands) could migrate to
  server-stored preference; not a blocker now.
- **`MultiPara` fenced-code-block styling** requires either a regex pass
  for triple-backtick blocks or accepting that current Help bodies render
  flat. Decision: regex pass for ` ``` ` fences only (no inline backticks
  to `<code>` parsing — avoids escaping conflicts). This is a 5-line
  helper, fits inside Phase 5.

---

## Approval

Inline approval received from Yarik on 2026-05-01. Proceeding to
implementation plan via the `writing-plans` skill.
