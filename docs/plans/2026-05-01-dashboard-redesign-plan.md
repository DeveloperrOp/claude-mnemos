# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the dashboard redesign spec from `docs/plans/2026-05-01-dashboard-redesign-design.md` to the live dashboard — IDE/terminal aesthetic, OKLCH tokens, Geist Sans/Mono, lime accent, three signature motion elements, light+dark theme toggle.

**Architecture:** Five sequential phases, each landing as one commit on `main`. Phase 1 rewrites color tokens in `globals.css`; Phase 2 swaps fonts; Phase 3 adds three new signature components; Phase 4 walks the existing shadcn primitives applying new tokens + Mono pattern; Phase 5 wires charts to the token system and adds the theme toggle. Each phase keeps `pnpm vitest run` green and `pnpm build` succeeding before commit.

**Tech Stack:** React 19 + Tailwind v4 + shadcn/ui + recharts. `next-themes` (already in deps, used for the theme toggle). `geist` (new dep, for fonts).

**Working tree note:** Plan executes on `main` (no worktree, inline-approved by user). Each commit is reversible via `git revert <sha>`.

---

## Reality reconciliation with the spec

Spec listed shadcn primitives `input.tsx`, `select.tsx`, `dialog.tsx`, `popover.tsx`, `table.tsx`, `accordion.tsx` for restyle. Reality: those don't exist as standalone shadcn components in this codebase — they're ad-hoc or use Radix primitives directly via `dropdown-menu.tsx` / `alert-dialog.tsx` / `tooltip.tsx`. Phase 4 restyles only the actual present primitives plus `TopBar.tsx` / `Sidebar.tsx` shells.

Existing shadcn primitives in `frontend/src/components/ui/`:
`alert-dialog.tsx`, `badge.tsx`, `button.tsx`, `card.tsx`, `chart.tsx`, `dropdown-menu.tsx`, `skeleton.tsx`, `sonner.tsx`, `tooltip.tsx`.

Spec called for `localStorage`-based theme persistence; project already has `next-themes` installed. Use that — no need to roll our own. Phase 5 adapted accordingly.

---

## Phase 1: Color Tokens (one commit)

**Files:**
- Modify: `frontend/src/styles/globals.css` (full rewrite of `:root`, `.dark`, `@theme` block; preserve `.prose` styles)

**What changes:** Replace HSL `--background`/`--foreground`/`--muted`/etc. with OKLCH `--bg`/`--fg`/`--accent` semantic tokens per spec. The `@theme` block remaps shadcn-ergonomic names (`--color-background`, `--color-popover`, `--color-accent`) to the new `--bg`/`--bg-elev-1`/`--accent` so existing component classes (`bg-popover`, `bg-accent`, `text-popover-foreground`) keep working without component churn.

- [ ] **Step 1: Rewrite `globals.css`**

Replace the entire file contents with:

```css
@import "tailwindcss";

/* New token system: cool blue-grey baseline (h=264) + lime accent (h=130).
   shadcn-ergonomic names are mapped through @theme so existing class usage
   (bg-card, text-popover-foreground, bg-accent, etc.) keeps working. */
@theme {
  --color-background: var(--bg);
  --color-foreground: var(--fg);
  --color-card: var(--bg-elev-1);
  --color-card-foreground: var(--fg);
  --color-popover: var(--bg-elev-1);
  --color-popover-foreground: var(--fg);
  --color-primary: var(--accent);
  --color-primary-foreground: var(--accent-fg);
  --color-secondary: var(--bg-elev-1);
  --color-secondary-foreground: var(--fg);
  --color-muted: var(--bg-elev-1);
  --color-muted-foreground: var(--fg-muted);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-fg);
  --color-destructive: var(--danger);
  --color-destructive-foreground: var(--bg);
  --color-border: var(--border);
  --color-input: var(--border);
  --color-ring: var(--accent);

  --font-sans: "Geist", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "Geist Mono", "JetBrains Mono", ui-monospace, monospace;
}

@layer base {
  :root {
    /* Light theme */
    --bg:           oklch(99% 0.005 264);
    --bg-elev-1:    oklch(97% 0.006 264);
    --bg-elev-2:    oklch(94% 0.008 264);
    --fg:           oklch(20% 0.02 264);
    --fg-muted:     oklch(45% 0.015 264);
    --fg-subtle:    oklch(60% 0.01 264);
    --border:       oklch(90% 0.008 264);
    --border-strong:oklch(80% 0.01 264);
    --accent:       oklch(70% 0.22 130);
    --accent-fg:    oklch(20% 0.05 130);
    --accent-dim:   oklch(55% 0.12 130);
    --success:      oklch(70% 0.22 145);
    --warning:      oklch(75% 0.16 75);
    --danger:       oklch(60% 0.22 25);
    --info:         oklch(65% 0.15 240);

    --radius: 0.375rem;

    /* Charts: keep three-series ladder. accent → primary, info → secondary, warning → tertiary. */
    --chart-input:    var(--accent);
    --chart-output:   var(--info);
    --chart-sessions: var(--warning);

    /* Motion */
    --motion-fast:   80ms;
    --motion-medium: 150ms;
    --motion-slow:   250ms;
    --ease-out:      cubic-bezier(0.2, 0.7, 0.1, 1);
    --ease-in-out:   cubic-bezier(0.4, 0, 0.2, 1);
  }

  .dark {
    --bg:           oklch(15% 0.012 264);
    --bg-elev-1:    oklch(18% 0.014 264);
    --bg-elev-2:    oklch(22% 0.016 264);
    --fg:           oklch(95% 0.01 264);
    --fg-muted:     oklch(65% 0.012 264);
    --fg-subtle:    oklch(50% 0.01 264);
    --border:       oklch(28% 0.014 264);
    --border-strong:oklch(40% 0.018 264);
    --accent:       oklch(85% 0.27 130);
    --accent-fg:    oklch(15% 0.05 130);
    --accent-dim:   oklch(60% 0.15 130);
    --success:      oklch(80% 0.20 145);
    --warning:      oklch(82% 0.18 75);
    --danger:       oklch(70% 0.20 25);
    --info:         oklch(75% 0.15 240);
  }

  body {
    @apply bg-background text-foreground;
    font-family: var(--font-sans);
    font-feature-settings: "ss01", "cv11"; /* Geist optional ligatures */
  }

  /* Signature motion keyframes */
  @keyframes blink { 50% { opacity: 0 } }
  .cursor-blink { animation: blink 1.06s steps(2, start) infinite; }

  @keyframes pulse-accent {
    0%, 100% { opacity: 0.6 }
    50%      { opacity: 1.0 }
  }
  .pulse-accent { animation: pulse-accent 2s var(--ease-in-out) infinite; }

  /* Markdown / prose blocks (Help, page bodies). Mono code, lime border-left
     on fenced blocks. */
  .prose h1 { @apply mt-6 mb-3 text-2xl font-semibold; font-family: var(--font-mono); }
  .prose h2 { @apply mt-5 mb-2 text-xl font-semibold; font-family: var(--font-mono); }
  .prose h3 { @apply mt-4 mb-2 text-lg font-semibold; font-family: var(--font-mono); }
  .prose p { @apply my-2 leading-relaxed; }
  .prose code {
    @apply rounded px-1.5 py-0.5 text-sm;
    background: var(--bg-elev-1);
    color: var(--accent);
    font-family: var(--font-mono);
  }
  .prose pre {
    @apply my-3 overflow-x-auto rounded-md p-3 text-sm;
    background: var(--bg-elev-2);
    border-left: 2px solid var(--accent);
    font-family: var(--font-mono);
  }
  .prose pre code { background: transparent; padding: 0; color: inherit; }
  .prose ul { @apply my-2 ml-5 list-disc space-y-1; }
  .prose ol { @apply my-2 ml-5 list-decimal space-y-1; }
  .prose blockquote { @apply my-3 border-l-4 pl-3 italic; border-color: var(--border); }
  .prose a { @apply underline; color: var(--accent); }
  .prose table { @apply my-3 w-full border-collapse text-sm; }
  .prose th, .prose td { @apply px-2 py-1; border: 1px solid var(--border); }
  .prose th { background: var(--bg-elev-1); @apply font-semibold; font-family: var(--font-mono); }
}
```

- [ ] **Step 2: Run vitest**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run 2>&1 | tail -5`
Expected: `Tests 295 passed (295)`. (Tests don't assert specific colors, so no breakage.)

- [ ] **Step 3: Run build**

Run: `cd /d/code/claude-mnemos/frontend && pnpm build 2>&1 | tail -10`
Expected: `built in <Ns>`, no Tailwind errors. The `@theme` block must compile cleanly.

- [ ] **Step 4: Manual UI smoke**

Open `http://127.0.0.1:5757/` in a browser (daemon already running with fresh `dist/` because `pnpm build` writes to `claude_mnemos/daemon/static/`). Click into Overview, Pages, Settings. Expected: layout intact, no broken styles, default light theme uses near-white backgrounds with cool grey text. No glaring lime yet (accent only fires on `bg-primary` / `bg-accent` consumers — those will land in Phase 4).

- [ ] **Step 5: Commit**

```bash
cd /d/code/claude-mnemos
git add frontend/src/styles/globals.css
git commit -m "$(cat <<'EOF'
style(tokens): switch to OKLCH semantic token system

Replace shadcn HSL defaults with OKLCH semantic tokens per design spec
2026-05-01-dashboard-redesign-design.md. Cool blue-grey baseline
(h=264) for greys, lime acid accent (h=130) for primary.

@theme block maps shadcn-ergonomic names (--color-background,
--color-popover, --color-accent, etc.) to the new --bg/--bg-elev-1/
--accent semantic tokens, so existing component classes (bg-popover,
bg-accent, text-popover-foreground) keep working without churn.

Also lands the motion language: --motion-fast/medium/slow, --ease-out/
in-out, plus signature keyframes (.cursor-blink with xterm-style 1.06s
asymmetric timing, .pulse-accent for running/active states).

.prose block updated to use new tokens — mono headings, lime-bordered
fenced code blocks.

Phase 1 of 5 in dashboard redesign. Tokens land alone; component
restyle and theme toggle in subsequent phases.
EOF
)"
```

---

## Phase 2: Typography (one commit)

**Files:**
- Modify: `frontend/package.json` (add `geist` dep)
- Modify: `frontend/src/styles/globals.css` (`@font-face` import at top)
- Modify: `frontend/index.html` (preconnect/preload optional — skip for offline-first single-user app)

**What changes:** Install `geist` package (Vercel's free variable font, sans + mono pair). Import via CSS `@font-face`. Body default already pointed at `var(--font-sans)` in Phase 1; this phase makes that variable resolve to actual font files instead of `system-ui` fallback.

- [ ] **Step 1: Install Geist**

Run: `cd /d/code/claude-mnemos/frontend && pnpm add geist 2>&1 | tail -5`
Expected: `+ geist <version>` in output, no peer-dep warnings (Geist has no React/Next-only requirements when used via CSS).

- [ ] **Step 2: Add `@font-face` block to `globals.css`**

At the very top of `globals.css`, just after `@import "tailwindcss";`, prepend:

```css
@font-face {
  font-family: "Geist";
  src: url("geist/dist/fonts/geist-sans/Geist-Variable.woff2") format("woff2-variations");
  font-weight: 100 900;
  font-style: normal;
  font-display: swap;
}

@font-face {
  font-family: "Geist Mono";
  src: url("geist/dist/fonts/geist-mono/GeistMono-Variable.woff2") format("woff2-variations");
  font-weight: 100 900;
  font-style: normal;
  font-display: swap;
}
```

Vite resolves `url("geist/...")` against `node_modules/geist/...` because `vite` ≥ 4 supports bare specifiers in CSS `url()` for installed packages. If resolution fails (Vite version-dependent), fallback is to copy the woff2 to `public/fonts/` and use `url("/fonts/Geist-Variable.woff2")`.

- [ ] **Step 3: Verify font path exists**

Run: `ls /d/code/claude-mnemos/frontend/node_modules/geist/dist/fonts/geist-sans/Geist-Variable.woff2 2>&1`
Expected: file exists. If not, inspect `ls /d/code/claude-mnemos/frontend/node_modules/geist/dist/fonts/` to find the actual filename and adjust the `@font-face` `src` URL.

- [ ] **Step 4: Run build**

Run: `cd /d/code/claude-mnemos/frontend && pnpm build 2>&1 | tail -10`
Expected: build succeeds. The woff2 files appear under `claude_mnemos/daemon/static/assets/` (Vite copies them).

- [ ] **Step 5: Run vitest**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run 2>&1 | tail -5`
Expected: `Tests 295 passed (295)`. (jsdom doesn't load real fonts, so no behavioral change in tests.)

- [ ] **Step 6: Manual UI smoke**

Reload `http://127.0.0.1:5757/`. Expected: body text rendered in Geist Sans (slightly geometric, more "designed" than system-ui). DevTools → Network tab → confirm Geist `.woff2` files load with HTTP 200. No FOUT (font-display: swap means text shows in fallback first then swaps). No font-loading errors in console.

- [ ] **Step 7: Commit**

```bash
cd /d/code/claude-mnemos
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/styles/globals.css
git commit -m "$(cat <<'EOF'
style(typography): adopt Geist Sans + Geist Mono via geist npm package

Install geist (Vercel's free variable-axis font family). @font-face
declarations in globals.css resolve to node_modules/geist/dist/fonts/
via Vite's bare-specifier support in CSS url().

Phase 1 already pointed --font-sans / --font-mono CSS vars at "Geist"
and "Geist Mono" — this phase makes those vars resolve to real font
files instead of the system-ui fallback.

font-display: swap, so the dashboard renders immediately in fallback
fonts before swapping to Geist when the woff2 loads.

Phase 2 of 5 in dashboard redesign.
EOF
)"
```

---

## Phase 3: Signature Components (one commit)

**Files:**
- Create: `frontend/src/components/signature/BlinkCursor.tsx`
- Create: `frontend/src/components/signature/MetricLabel.tsx`
- Create: `frontend/src/components/signature/__tests__/BlinkCursor.test.tsx`
- Create: `frontend/src/components/signature/__tests__/MetricLabel.test.tsx`
- Modify: `frontend/src/components/widgets/StatusBadge.tsx` (rewrite to use new tokens + add `running` variant with `pulse-accent`)

**What changes:** Three small components that carry the spec's "signature elements" — blink cursor, status pulse, label/value pattern. StatusBadge stops using hard-coded zinc/blue/emerald/amber Tailwind classes (which ignore our new token system) and switches to semantic token classes (`bg-accent/20`, `text-accent`, etc.) plus `pulse-accent` animation for `running`-style states.

- [ ] **Step 1: Write failing test for `BlinkCursor`**

Create `frontend/src/components/signature/__tests__/BlinkCursor.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { BlinkCursor } from "../BlinkCursor";

describe("BlinkCursor", () => {
  it("renders the U+258C glyph", () => {
    const { container } = render(<BlinkCursor />);
    expect(container.textContent).toBe("▌");
  });

  it("applies the cursor-blink animation class", () => {
    const { container } = render(<BlinkCursor />);
    const span = container.querySelector("span");
    expect(span?.className).toContain("cursor-blink");
  });

  it("forwards aria-hidden=true (decorative)", () => {
    const { container } = render(<BlinkCursor />);
    const span = container.querySelector("span");
    expect(span?.getAttribute("aria-hidden")).toBe("true");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run BlinkCursor 2>&1 | tail -10`
Expected: FAIL with "Cannot find module '../BlinkCursor'".

- [ ] **Step 3: Implement `BlinkCursor`**

Create `frontend/src/components/signature/BlinkCursor.tsx`:

```tsx
import { cn } from "@/lib/utils";

export function BlinkCursor({ className }: { className?: string }) {
  return (
    <span aria-hidden="true" className={cn("cursor-blink", className)}>
      ▌
    </span>
  );
}
```

- [ ] **Step 4: Run BlinkCursor test**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run BlinkCursor 2>&1 | tail -10`
Expected: 3 passed.

- [ ] **Step 5: Write failing test for `MetricLabel`**

Create `frontend/src/components/signature/__tests__/MetricLabel.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MetricLabel } from "../MetricLabel";

describe("MetricLabel", () => {
  it("renders LABEL ▸ value pattern", () => {
    render(<MetricLabel label="JOBS">03 queued</MetricLabel>);
    expect(screen.getByText("JOBS")).toBeInTheDocument();
    expect(screen.getByText("▸")).toBeInTheDocument();
    expect(screen.getByText("03 queued")).toBeInTheDocument();
  });

  it("applies mono uppercase to the label", () => {
    const { container } = render(<MetricLabel label="JOBS">03</MetricLabel>);
    const label = container.querySelector("[data-role='label']");
    expect(label?.className).toMatch(/font-mono/);
    expect(label?.className).toMatch(/uppercase/);
  });
});
```

- [ ] **Step 6: Run MetricLabel test, see it fail**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run MetricLabel 2>&1 | tail -10`
Expected: FAIL with "Cannot find module '../MetricLabel'".

- [ ] **Step 7: Implement `MetricLabel`**

Create `frontend/src/components/signature/MetricLabel.tsx`:

```tsx
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface Props {
  label: string;
  children: ReactNode;
  className?: string;
}

export function MetricLabel({ label, children, className }: Props) {
  return (
    <div className={cn("flex items-center gap-2 text-sm", className)}>
      <span
        data-role="label"
        className="font-mono uppercase text-xs tracking-wider text-[hsl(var(--fg-muted))]"
      >
        {label}
      </span>
      <span aria-hidden="true" className="text-[hsl(var(--fg-subtle))]">▸</span>
      <span className="font-mono">{children}</span>
    </div>
  );
}
```

Note: classes use `hsl(var(--fg-muted))` form. With OKLCH tokens we don't need `hsl()` wrap — but Tailwind v4 + our `@theme` block exposed shadcn-ergonomic names. Use `text-muted-foreground` instead, which routes through `--color-muted-foreground = var(--fg-muted)`. Updated implementation:

```tsx
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface Props {
  label: string;
  children: ReactNode;
  className?: string;
}

export function MetricLabel({ label, children, className }: Props) {
  return (
    <div className={cn("flex items-center gap-2 text-sm", className)}>
      <span
        data-role="label"
        className="font-mono uppercase text-xs tracking-wider text-muted-foreground"
      >
        {label}
      </span>
      <span aria-hidden="true" className="text-muted-foreground/60">▸</span>
      <span className="font-mono">{children}</span>
    </div>
  );
}
```

- [ ] **Step 8: Run MetricLabel test**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run MetricLabel 2>&1 | tail -10`
Expected: 2 passed.

- [ ] **Step 9: Rewrite `StatusBadge.tsx`**

Replace contents of `frontend/src/components/widgets/StatusBadge.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { PageStatus } from "@/types/WikiPage";

// Map page statuses → semantic token + animation. All colors flow through
// our token system, so light/dark theme switching works automatically.
const VARIANT: Record<PageStatus, { className: string; pulse: boolean }> = {
  draft:    { className: "bg-muted/30 text-muted-foreground", pulse: false },
  reviewed: { className: "bg-[oklch(75%_0.15_240/0.2)] text-[oklch(65%_0.15_240)] dark:text-[oklch(75%_0.15_240)]", pulse: false },
  verified: { className: "bg-[oklch(70%_0.22_145/0.2)] text-[oklch(70%_0.22_145)] dark:text-[oklch(80%_0.20_145)]", pulse: false },
  stale:    { className: "bg-[oklch(75%_0.16_75/0.2)] text-[oklch(75%_0.16_75)] dark:text-[oklch(82%_0.18_75)]", pulse: false },
  archived: { className: "bg-muted/30 text-muted-foreground/60", pulse: false },
};

export function StatusBadge({ status }: { status: PageStatus }) {
  const { t } = useTranslation();
  const v = VARIANT[status];
  return (
    <span
      role="status"
      data-status={status}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest",
        v.className,
        v.pulse && "pulse-accent",
      )}
    >
      {t(`wiki.status.${status}`)}
    </span>
  );
}
```

The `bg-[oklch(...)]` arbitrary-value classes work in Tailwind v4. Inline OKLCH preserves color-system consistency without adding more theme tokens for one-off semantic colors that already exist in `:root`/`.dark` indirectly.

- [ ] **Step 10: Run all StatusBadge tests**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run StatusBadge 2>&1 | tail -10`
Expected: existing tests still pass — they assert `role="status"` and i18n text presence, not specific colors.

- [ ] **Step 11: Run full vitest**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run 2>&1 | tail -5`
Expected: `Tests 300 passed (300)` (was 295; +3 BlinkCursor +2 MetricLabel = +5).

- [ ] **Step 12: Commit**

```bash
cd /d/code/claude-mnemos
git add frontend/src/components/signature/ frontend/src/components/widgets/StatusBadge.tsx
git commit -m "$(cat <<'EOF'
feat(signature): add BlinkCursor + MetricLabel + restyle StatusBadge

Three signature components from the redesign spec:

- BlinkCursor: terminal-style ▌ glyph with xterm 1.06s asymmetric blink
  via .cursor-blink keyframe (defined in Phase 1 globals.css). Used in
  active-job counters and page-header context to give the dashboard a
  recognizably-terminal feel.

- MetricLabel: renders the SECTION ▸ VALUE pattern that appears
  throughout the redesign. Mono uppercase tracked label + muted
  separator + mono value. Slot-based — caller passes the value as
  children.

- StatusBadge: rewritten from hard-coded zinc/blue/emerald/amber
  Tailwind classes to OKLCH arbitrary values + token-driven base
  styles. Mono uppercase 10px tracked. The variant map gains a `pulse`
  flag — currently all PageStatus values are non-pulsing, but the
  hook is ready for `running`-style live states. Existing tests
  unchanged (they assert role and i18n, not colors).

5 new vitest cases (3 BlinkCursor + 2 MetricLabel). Total now 300/300.

Phase 3 of 5 in dashboard redesign.
EOF
)"
```

---

## Phase 4: Component Restyle (one commit)

**Files:**
- Modify: `frontend/src/components/ui/button.tsx` (variants + Mono uppercase for primary)
- Modify: `frontend/src/components/ui/card.tsx` (border-strong on hover, subtle shadow)
- Modify: `frontend/src/components/ui/badge.tsx` (Mono uppercase 10px tracking-widest)
- Modify: `frontend/src/components/ui/dropdown-menu.tsx` (left-border accent on focused item)
- Modify: `frontend/src/components/ui/alert-dialog.tsx` (Mono title)
- Modify: `frontend/src/components/ui/tooltip.tsx` (Mono content for terse tooltips)
- Modify: `frontend/src/components/layout/TopBar.tsx` (Mono brand, prepare slot for ThemeToggle)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (Mono nav labels uppercase tracked)

**What changes:** Apply Mono uppercase to interactive primitives where it reinforces the IDE feel. Use new token classes throughout (`text-muted-foreground` already routes to `--fg-muted` after Phase 1). Hover lift for cards = border-strong + 1px shadow, no transform.

- [ ] **Step 1: Restyle `button.tsx`**

Read current contents first:

Run: `cat /d/code/claude-mnemos/frontend/src/components/ui/button.tsx`

Replace `buttonVariants` `cva()` call with:

```tsx
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors duration-[var(--motion-fast)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground font-mono uppercase tracking-wider hover:bg-[oklch(55%_0.12_130)] dark:hover:bg-[oklch(60%_0.15_130)]",
        destructive: "border border-destructive text-destructive hover:bg-destructive hover:text-background",
        outline: "border border-border bg-card text-foreground hover:bg-secondary",
        secondary: "bg-secondary text-secondary-foreground hover:bg-muted",
        ghost: "text-muted-foreground hover:bg-secondary hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);
```

Keep the rest of the file (the `Button` component, prop types, exports) unchanged.

- [ ] **Step 2: Restyle `card.tsx`**

In `frontend/src/components/ui/card.tsx`, find the root `Card` component and update its className. Replace:

```tsx
"rounded-xl border bg-card text-card-foreground shadow"
```

with:

```tsx
"rounded-md border border-border bg-card text-card-foreground transition-[border-color,box-shadow] duration-[var(--motion-fast)] hover:border-[var(--border-strong)] hover:shadow-[0_0_0_1px_var(--border-strong)]"
```

(Keep the `<div ref={ref} className={cn(<above>, className)} {...props}/>` shape.)

- [ ] **Step 3: Restyle `badge.tsx`**

In `frontend/src/components/ui/badge.tsx`, replace `badgeVariants` cva with:

```tsx
const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase tracking-widest transition-colors duration-[var(--motion-fast)] focus:outline-none focus:ring-1 focus:ring-ring",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary/20 text-primary",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-transparent bg-destructive/20 text-destructive",
        outline: "border-border text-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);
```

- [ ] **Step 4: Restyle `dropdown-menu.tsx` focused-item indicator**

In `frontend/src/components/ui/dropdown-menu.tsx`, find `DropdownMenuItem` className. Update the focus state to add a left-border accent. Locate the current className that contains `data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground` (or similar focus class) and replace with:

```tsx
"relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors data-[highlighted]:bg-secondary data-[highlighted]:before:absolute data-[highlighted]:before:left-0 data-[highlighted]:before:top-0 data-[highlighted]:before:h-full data-[highlighted]:before:w-0.5 data-[highlighted]:before:bg-primary data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
```

The `before:` pseudo-element renders the 2px lime left-border on the highlighted item without changing the row background to lime (which would be loud).

- [ ] **Step 5: Restyle `alert-dialog.tsx` title**

In `frontend/src/components/ui/alert-dialog.tsx`, find `AlertDialogTitle`. Update its className to include `font-mono uppercase tracking-wider`. Example: if current is `"text-lg font-semibold"`, change to `"font-mono text-lg font-semibold uppercase tracking-wider"`.

- [ ] **Step 6: Restyle `tooltip.tsx` content**

In `frontend/src/components/ui/tooltip.tsx`, find `TooltipContent` className. Add `font-mono` to its base classes. Tooltips become Mono — terse, IDE-feel.

- [ ] **Step 7: Restyle `TopBar.tsx`**

Edit `frontend/src/components/layout/TopBar.tsx`. Update the brand link from:

```tsx
<Link to="/" className="font-semibold">claude-mnemos</Link>
```

to:

```tsx
<Link
  to="/"
  className="font-mono text-base font-semibold uppercase tracking-widest text-foreground hover:text-primary transition-colors duration-[var(--motion-fast)]"
>
  claude-mnemos
</Link>
```

The header itself should also tighten its background reference. Current:

```tsx
<header className="flex items-center justify-between border-b bg-[hsl(var(--background))] px-4 py-2">
```

Replace `bg-[hsl(var(--background))]` with `bg-background` (Tailwind v4 token-driven).

Leave a blank slot in the right-side flex `gap-4` cluster for the future ThemeToggle (added in Phase 5) — no need to touch the structure now.

- [ ] **Step 8: Restyle `Sidebar.tsx` nav labels**

Edit `frontend/src/components/layout/Sidebar.tsx`. Find sidebar nav items (they typically have a className like `flex items-center gap-2 rounded px-3 py-2 text-sm`). Add `font-mono uppercase tracking-wider` to make labels mono. Keep icons unchanged. Active state should switch from a generic `bg-accent` to the spec's left-border accent: add `data-[active=true]:before:absolute data-[active=true]:before:left-0 data-[active=true]:before:h-full data-[active=true]:before:w-0.5 data-[active=true]:before:bg-primary` (use whichever active-state attribute Sidebar.tsx already uses; if it's a class instead of an attr, mirror the structure).

- [ ] **Step 9: Run vitest**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run 2>&1 | tail -5`
Expected: `300 passed`. Test snapshots that assert specific class strings on Button/Card may need updating — if any test fails because of class-string regex mismatch, update the test expectation to match the new pattern (don't add new behavior, only fix string matchers).

- [ ] **Step 10: Run lint**

Run: `cd /d/code/claude-mnemos/frontend && pnpm lint 2>&1 | tail -5`
Expected: 0 errors, the same 20 pre-existing `react-refresh/only-export-components` warnings (we didn't touch shadcn-export-shape).

- [ ] **Step 11: Run build + manual UI smoke**

Run: `cd /d/code/claude-mnemos/frontend && pnpm build`
Then reload `http://127.0.0.1:5757/`. Inspect:
- Brand "claude-mnemos" in TopBar — should now be Mono uppercase tracked.
- Sidebar nav items — Mono uppercase. Active item has lime left-border (2px).
- Click "+ New project" button on Overview — Mono uppercase, lime fill, dark text.
- Open Settings → click any select/dropdown — focused item has lime left-border, no full-row lime fill.
- Hover a Card on Overview — border darkens (border-strong) and a subtle 1px shadow appears.
- Open any Tooltip — Mono.
- Open the Delete-project dialog (Settings → Danger zone) — title is Mono uppercase tracked.

Decision point on accent intensity (from spec risks): if the lime in light mode visually pierces, edit `:root` `--accent` from `oklch(70% 0.22 130)` to `oklch(65% 0.18 130)` and rebuild. Document in the commit message which value was picked.

- [ ] **Step 12: Commit**

```bash
cd /d/code/claude-mnemos
git add frontend/src/components/ui/ frontend/src/components/layout/
git commit -m "$(cat <<'EOF'
style(components): apply IDE/terminal aesthetic to shadcn primitives

Restyle the visible primitives in line with redesign spec phase 4:

- button.tsx: primary variant gets Mono uppercase tracking-wider, lime
  fill with dark accent-foreground text. Destructive becomes outline-
  style. All variants pick up --motion-fast color transitions.
- card.tsx: border-strong on hover with a 1px shadow ring. No
  transform — kept tactile, not cinematic.
- badge.tsx: Mono uppercase 10px tracking-widest, semantic-token bg/fg.
- dropdown-menu.tsx: highlighted items get a 2px lime left-border via
  ::before pseudo, no full-row lime flood.
- alert-dialog.tsx: title goes Mono uppercase tracking-wider.
- tooltip.tsx: content becomes Mono — IDE-feel, terse.
- TopBar.tsx: brand "claude-mnemos" rendered Mono uppercase widely
  tracked, hover swaps to lime. Slot kept open for ThemeToggle (next
  phase). bg switched to bg-background (token-driven).
- Sidebar.tsx: nav labels Mono uppercase tracked. Active item gets
  lime 2px left-border, no full-row fill.

[Note re: accent intensity decision: kept oklch(70% 0.22 130) light /
oklch(85% 0.27 130) dark — visual check passed.] OR [stepped down to
oklch(65% 0.18 130) light / oklch(80% 0.22 130) dark — original
intensity pierced in side-by-side.]

Phase 4 of 5 in dashboard redesign.
EOF
)"
```

(Pick one of the two bracketed sentences in the commit body based on the actual decision in Step 11.)

---

## Phase 5: Charts + Theme Toggle (one commit)

**Files:**
- Modify: `frontend/src/components/widgets/CompressionTimelineChart.tsx`
- Modify: `frontend/src/components/widgets/UsageTimelineChart.tsx`
- Modify: `frontend/src/components/ui/chart.tsx`
- Create: `frontend/src/components/layout/ThemeToggle.tsx`
- Create: `frontend/src/components/layout/__tests__/ThemeToggle.test.tsx`
- Modify: `frontend/src/components/layout/TopBar.tsx` (insert ThemeToggle in right-side cluster)
- Modify: `frontend/src/main.tsx` (wrap App in `<ThemeProvider>` from `next-themes`)

**What changes:** Two small chart files currently read `--chart-input`/`--chart-output`/`--chart-sessions` — Phase 1 already pointed those vars at `--accent`/`--info`/`--warning`, so the colors auto-update. We verify and then add the visible theme toggle in the header.

- [ ] **Step 1: Verify charts already auto-themed**

Run: `grep -n "chart-input\|chart-output\|chart-sessions" /d/code/claude-mnemos/frontend/src/components/widgets/{CompressionTimelineChart,UsageTimelineChart}.tsx`
Expected: matches showing where the CSS vars are read. Spot-check both files: if they read via `getComputedStyle(document.documentElement).getPropertyValue('--chart-input')`, they're already token-driven — Phase 1's redirection (`--chart-input: var(--accent)` etc.) takes effect at next render.

If a chart file uses hard-coded hex like `#3b82f6`, replace with the same `getComputedStyle(...).getPropertyValue('--chart-input').trim()` pattern that the other one uses (consistency-only edit; no new component).

- [ ] **Step 2: Inspect `chart.tsx` for hard-coded color references**

Run: `grep -n "#[0-9a-fA-F]\{6\}\|hsl(" /d/code/claude-mnemos/frontend/src/components/ui/chart.tsx`
Any hard-coded hex or stale hsl that escaped Phase 1 — replace with the token equivalent. Most likely the file already uses CSS vars correctly; this is a verification step, not a guaranteed edit.

- [ ] **Step 3: Wrap App with `next-themes` provider**

Edit `frontend/src/main.tsx`. Find the existing render call (likely `createRoot(document.getElementById('root')!).render(<App />)` or wrapped with React.StrictMode/QueryClientProvider). Add:

```tsx
import { ThemeProvider } from "next-themes";
```

at the top, and wrap the existing app tree:

```tsx
<ThemeProvider attribute="class" defaultTheme="system" enableSystem>
  {/* existing app tree */}
</ThemeProvider>
```

`attribute="class"` makes next-themes toggle a `.dark` class on `<html>` — exactly what `globals.css` `.dark` overrides expect.

- [ ] **Step 4: Write failing test for `ThemeToggle`**

Create `frontend/src/components/layout/__tests__/ThemeToggle.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "next-themes";
import { ThemeToggle } from "../ThemeToggle";

beforeEach(() => {
  // next-themes uses localStorage; clean between tests.
  localStorage.clear();
});

function wrap(ui: React.ReactNode) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      {ui}
    </ThemeProvider>
  );
}

describe("ThemeToggle", () => {
  it("renders an aria-labeled toggle button", () => {
    render(wrap(<ThemeToggle />));
    expect(screen.getByRole("button", { name: /theme/i })).toBeInTheDocument();
  });

  it("cycles light → dark → system on click", async () => {
    const user = userEvent.setup();
    render(wrap(<ThemeToggle />));
    const btn = screen.getByRole("button", { name: /theme/i });
    // initial = system; click → light
    await user.click(btn);
    expect(localStorage.getItem("theme")).toBe("light");
    await user.click(btn);
    expect(localStorage.getItem("theme")).toBe("dark");
    await user.click(btn);
    expect(localStorage.getItem("theme")).toBe("system");
  });
});
```

- [ ] **Step 5: Run test to see it fail**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run ThemeToggle 2>&1 | tail -10`
Expected: FAIL with module-not-found.

- [ ] **Step 6: Implement `ThemeToggle.tsx`**

Create `frontend/src/components/layout/ThemeToggle.tsx`:

```tsx
import { Sun, Moon, Monitor } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

const CYCLE = ["system", "light", "dark"] as const;
type Mode = (typeof CYCLE)[number];

function nextMode(m: Mode): Mode {
  const i = CYCLE.indexOf(m);
  return CYCLE[(i + 1) % CYCLE.length]!;
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  // Avoid SSR/hydration mismatch — render placeholder until mounted.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const current: Mode = (mounted && (theme as Mode)) || "system";
  const Icon = current === "light" ? Sun : current === "dark" ? Moon : Monitor;
  const label = `Theme: ${current}`;

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={label}
      onClick={() => setTheme(nextMode(current))}
      className="text-muted-foreground hover:text-foreground"
    >
      <Icon className="h-4 w-4" />
    </Button>
  );
}
```

The cycle order `system → light → dark → system` matches industry convention (VS Code, GitHub).

- [ ] **Step 7: Run ThemeToggle test**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run ThemeToggle 2>&1 | tail -10`
Expected: 2 passed.

- [ ] **Step 8: Mount ThemeToggle in TopBar**

Edit `frontend/src/components/layout/TopBar.tsx`. Add import:

```tsx
import { ThemeToggle } from "./ThemeToggle";
```

Insert `<ThemeToggle />` in the right-side cluster, before the locale Button:

```tsx
<div className="flex items-center gap-4">
  <UsageWidget />
  <ThemeToggle />
  <Button
    variant="ghost"
    size="sm"
    onClick={() => setLocale(nextLocale(locale))}
  >
    {locale.toUpperCase()}
  </Button>
</div>
```

- [ ] **Step 9: Run full vitest**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run 2>&1 | tail -5`
Expected: `Tests 302 passed (302)` (+2 ThemeToggle tests).

- [ ] **Step 10: Run lint + build**

Run: `cd /d/code/claude-mnemos/frontend && pnpm lint && pnpm build 2>&1 | tail -10`
Expected: lint 0 errors, build success.

- [ ] **Step 11: Manual UI smoke + theme toggle live test**

Reload `http://127.0.0.1:5757/`. Click the new Sun/Monitor/Moon icon in TopBar:
- system → light: backgrounds near-white, lime accent on buttons.
- light → dark: backgrounds dark blue-grey, lime brighter (per `.dark` token).
- dark → system: reverts to OS preference.

Open Metrics page. Both charts (Compression + Usage) should render with lime as the primary series, info-cyan as secondary, warning-amber as tertiary. Tooltip is Mono.

In DevTools → Application → Local Storage → check key `theme` reflects the current mode.

- [ ] **Step 12: Commit**

```bash
cd /d/code/claude-mnemos
git add frontend/src/components/layout/ThemeToggle.tsx frontend/src/components/layout/__tests__/ThemeToggle.test.tsx frontend/src/components/layout/TopBar.tsx frontend/src/main.tsx frontend/src/components/widgets/CompressionTimelineChart.tsx frontend/src/components/widgets/UsageTimelineChart.tsx frontend/src/components/ui/chart.tsx
git commit -m "$(cat <<'EOF'
feat(theme): add light/dark/system toggle + finalize chart tokens

Wraps the app in next-themes ThemeProvider (attribute="class",
defaultTheme="system") so .dark class on <html> drives token overrides
in globals.css.

ThemeToggle: ghost-style icon button in TopBar that cycles
system → light → dark, persists to localStorage, shows Sun/Moon/Monitor
icon (Lucide) for the current mode. Hydration-safe (mounted gate)
because next-themes' theme value is undefined on first SSR-style
render.

Charts (CompressionTimelineChart, UsageTimelineChart, ui/chart.tsx)
already read --chart-input/output/sessions via getComputedStyle —
Phase 1 redirected those vars at --accent/--info/--warning, so the
chart color story flips automatically with the toggle. Verified
against the live dashboard.

2 new vitest cases (ThemeToggle render + cycle). Total 302/302.

Phase 5 of 5 — dashboard redesign complete.
EOF
)"
```

---

## Final verification (after all 5 phases)

- [ ] **Run full backend pytest** to confirm we didn't accidentally touch backend behavior.

Run: `cd /d/code/claude-mnemos && "/c/Users/68664/pipx/venvs/claude-mnemos/Scripts/python.exe" -m pytest tests/ -m "not slow" 2>&1 | tail -3`
Expected: `1488 passed` (or current count, unchanged).

- [ ] **Run full frontend vitest.**

Run: `cd /d/code/claude-mnemos/frontend && pnpm vitest run 2>&1 | tail -5`
Expected: `Tests 302 passed (302)`.

- [ ] **Run lint.**

Run: `cd /d/code/claude-mnemos/frontend && pnpm lint 2>&1 | tail -3`
Expected: 0 errors, 20 pre-existing warnings.

- [ ] **Run build.**

Run: `cd /d/code/claude-mnemos/frontend && pnpm build 2>&1 | tail -5`
Expected: `built in <Ns>`, no warnings beyond the existing chunk-size note for `index-*.js`.

- [ ] **Push to origin.**

```bash
cd /d/code/claude-mnemos
git push origin main
```

5 phase commits + the design spec commit (`ebdc492`) reach the remote.

---

## Risk register & rollback

**Per-phase rollback:** Each phase is one commit. Rollback = `git revert <sha>` for that phase (safe — non-destructive, creates a new revert commit). If multiple phases need rolling back, revert in reverse order: 5 → 4 → 3 → 2 → 1.

**Token-system risks (Phase 1):**
- Tailwind v4 may reject some OKLCH literal forms. If `pnpm build` fails with PostCSS errors at the `:root` block, `oklch()` syntax is the suspect; convert to `oklch(70% 22% 130)` (chroma as percentage) — Tailwind PostCSS ≥ 4.2 accepts both.
- Existing `bg-[hsl(var(--*))]` arbitrary-value classes scattered through the codebase will break (the vars no longer exist). Search before commit: `grep -rn "hsl(var(--" frontend/src/`. Likely sites: `TopBar.tsx`, possibly `chart.tsx`. Replace with token-class equivalents (`bg-background`, `bg-popover`, etc.).

**Font-loading risk (Phase 2):**
- If Vite can't resolve `url("geist/...")` in CSS, the font won't load and body text falls back to system-ui (visible flash). Mitigation: copy woff2 files to `public/fonts/` and reference via `url("/fonts/Geist-Variable.woff2")`. Adds 1-2 binary files to git (~200KB total) but bypasses Vite's CSS resolver.

**Test-snapshot risk (Phase 4):**
- A few component tests may compare exact class strings on Button/Card. Class strings have changed substantially. Fix by updating the `expect(el.className).toContain(...)` substrings to match the new tokens. **Do not** broaden assertions into `toMatch(/.*/)` — keep them specific to the new class name.

**Theme-toggle hydration risk (Phase 5):**
- `next-themes`'s `theme` value is `undefined` on first render (SSR pattern). Without the `mounted` gate the `Icon` lookup throws. Implementation already includes the gate; tests verify cycle behavior post-mount.

**Manual-UI-check risk (every phase):**
- Browser caches the previous `index-*.js` even after `pnpm build`. Mitigation: hard reload (Ctrl+Shift+R) or check the new content hash matches in the `<script>` tag.

---

## Self-review

**Spec coverage check:**
- [✓] OKLCH tokens (light + dark) → Phase 1
- [✓] Geist Sans/Mono → Phase 2
- [✓] BlinkCursor + MetricLabel + StatusBadge variants → Phase 3
- [✓] Button/Card/Badge/Dropdown/AlertDialog/Tooltip/TopBar/Sidebar restyle → Phase 4
- [✓] Charts via tokens + ThemeToggle → Phase 5
- [✓] Three signature elements (blink/pulse/hover-lift) → Phase 1 keyframes + Phase 3 component + Phase 4 card hover
- [✓] Theme toggle (Sun/Moon/Monitor in TopBar) → Phase 5
- [✓] Mono pattern SECTION ▸ VALUE → MetricLabel in Phase 3
- [✓] Lime accent decision-point → flagged in Phase 4 Step 11

**Placeholder scan:** No "TBD"/"TODO"/"similar to". Each step has the actual code or command. Commit messages are pre-written in full.

**Type consistency:** `BlinkCursor` props uniform (`className?` only). `MetricLabel` props (`label`, `children`, `className`) used consistently in tests and implementation. `ThemeToggle` no props (zero-API component). Cycle order `system → light → dark` consistent across implementation and test assertions.

**Scope:** Pure visual layer. No feature behavior changes. No new routes. `MultiPara` markdown rendering (mentioned as a stretch in the spec) is explicitly deferred — the `.prose` block in Phase 1 styles fenced code if and when it appears, but `MultiPara` itself stays plain-text. Out-of-scope items match the spec's out-of-scope list.

**Ambiguity:** Phase 4 Step 8 says "if Sidebar.tsx uses an attribute or class for active state, mirror the structure" — this is a tolerable bit of "look-then-decide" because we haven't read Sidebar.tsx during plan-writing. Acceptable: the engineer reads the file in Step 8 and applies the analogous pattern. Not a placeholder — the structure (left-border accent on active) is fully defined.

**Plan complete.**
