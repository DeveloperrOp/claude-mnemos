# Frontend foundation + Overview Implementation Plan (Plan #14a)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` syntax for tracking.

**Goal:** Stand up `frontend/` (Vite + React 19 + TS + Tailwind v4 + shadcn/ui) inside `claude-mnemos`; ship the smallest user-visible deliverable: open `http://localhost:5757/` after `mnemos daemon start` and see a working dashboard with project list, health badges, usage widget, language switcher, and ProjectView shell. All other pages are placeholders pointing to future sub-plans.

**Architecture:** New `frontend/` directory at repo root. Vite builds to `claude_mnemos/daemon/static/` (gitignored except `.gitkeep`). FastAPI `create_app` mounts that directory at `/` last with `StaticFiles(html=True)` — JSON API routes win, missing-build is skipped silently. Dev mode: vite `:5173` proxies REST prefixes to daemon `:5757`. State: TanStack Query for server state, Zustand for UI. i18next with UK primary + RU + EN.

**Tech Stack:** React 19, TypeScript 5.7, Vite 6, Tailwind v4, shadcn/ui (Radix UI primitives), react-router 7, @tanstack/react-query 5, Zustand 5, axios, zod, i18next, lucide-react, dayjs, Vitest + Testing Library, ESLint 9 + typescript-eslint 8. Backend changes minimal: `claude_mnemos/daemon/app.py` adds StaticFiles mount.

**Design doc:** `docs/plans/2026-04-29-14a-frontend-foundation-design.md` — read before starting each task.

---

## Files map

**Create (frontend root):**
- `frontend/package.json`
- `frontend/pnpm-lock.yaml` (or `package-lock.json`)
- `frontend/vite.config.ts`
- `frontend/tsconfig.json`
- `frontend/tsconfig.node.json`
- `frontend/tailwind.config.ts`
- `frontend/postcss.config.js`
- `frontend/components.json` (shadcn/ui)
- `frontend/index.html`
- `frontend/eslint.config.js`
- `frontend/vitest.config.ts`
- `frontend/.gitignore`

**Create (frontend src):**
- `frontend/public/favicon.svg`
- `frontend/public/locales/uk.json`
- `frontend/public/locales/ru.json`
- `frontend/public/locales/en.json`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/i18n.ts`
- `frontend/src/setup-tests.ts`
- `frontend/src/styles/globals.css`
- `frontend/src/lib/utils.ts` (`cn()` helper for shadcn/ui)
- `frontend/src/api/client.ts`
- `frontend/src/api/projects.api.ts`
- `frontend/src/api/health.api.ts`
- `frontend/src/api/metrics.api.ts`
- `frontend/src/types/Project.ts`
- `frontend/src/types/Health.ts`
- `frontend/src/types/UsageSummary.ts`
- `frontend/src/hooks/useProjects.ts`
- `frontend/src/hooks/useHealth.ts`
- `frontend/src/hooks/useUsage.ts`
- `frontend/src/hooks/useUsageByProject.ts`
- `frontend/src/stores/ui.store.ts`
- `frontend/src/stores/notifications.store.ts`
- `frontend/src/components/ui/button.tsx` (shadcn)
- `frontend/src/components/ui/card.tsx` (shadcn)
- `frontend/src/components/ui/dropdown-menu.tsx` (shadcn)
- `frontend/src/components/ui/skeleton.tsx` (shadcn)
- `frontend/src/components/ui/badge.tsx` (shadcn)
- `frontend/src/components/ui/sonner.tsx` (shadcn — Toaster)
- `frontend/src/components/layout/Layout.tsx`
- `frontend/src/components/layout/TopBar.tsx`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/components/layout/ProjectSwitcher.tsx`
- `frontend/src/components/widgets/HealthBadge.tsx`
- `frontend/src/components/widgets/UsageWidget.tsx`
- `frontend/src/components/widgets/ProjectCard.tsx`
- `frontend/src/components/widgets/DaemonDownAlert.tsx`
- `frontend/src/components/widgets/NoProjectsCallout.tsx`
- `frontend/src/components/widgets/UnknownProject.tsx`
- `frontend/src/pages/Overview.tsx`
- `frontend/src/pages/ProjectView.tsx`
- `frontend/src/pages/Help.tsx`
- `frontend/src/pages/Placeholder.tsx`
- `frontend/src/__tests__/*` test files (per task)

**Create (backend):**
- `claude_mnemos/daemon/static/.gitkeep`
- `claude_mnemos/daemon/static/.gitignore` (`*` + `!.gitkeep`)
- `tests/daemon/test_app_static.py`

**Modify:**
- `claude_mnemos/daemon/app.py` — add StaticFiles mount at end of `create_app`
- `.gitignore` (root) — add `frontend/node_modules/`, `frontend/dist/`, etc.

---

## Task 1: Frontend project bootstrap

**Files:**
- Create: `frontend/package.json`, `frontend/index.html`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/.gitignore`, `frontend/src/main.tsx`, `frontend/src/App.tsx`

- [ ] **Step 1: Create the directory and run Vite scaffold**

```bash
cd /d/code/claude-mnemos
mkdir -p frontend
cd frontend
# Use the interactive Vite create or generate manually. We do it manually for full control.
```

Write `frontend/package.json`:

```json
{
  "name": "claude-mnemos-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint src",
    "typecheck": "tsc -b --noEmit"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router": "^7.1.1"
  },
  "devDependencies": {
    "@types/react": "^19.0.1",
    "@types/react-dom": "^19.0.1",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "^5.7.2",
    "vite": "^6.0.5"
  }
}
```

Write `frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>claude-mnemos</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Write `frontend/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const DAEMON_URL = "http://127.0.0.1:5757";
const PROXIED_PREFIXES = [
  "/projects", "/sessions", "/snapshots", "/pages", "/trash",
  "/lint", "/ontology", "/activity", "/vault", "/lost-sessions",
  "/jobs", "/dead-letter", "/metrics", "/health", "/version",
  "/alerts", "/settings",
];

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    outDir: "../claude_mnemos/daemon/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      PROXIED_PREFIXES.map((p) => [p, DAEMON_URL]),
    ),
  },
});
```

Write `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Write `frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true
  },
  "include": ["vite.config.ts"]
}
```

Write `frontend/.gitignore`:

```
node_modules
dist
*.log
.vite
```

Write `frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Write `frontend/src/App.tsx`:

```tsx
export default function App() {
  return <h1>claude-mnemos</h1>;
}
```

Add `frontend/public/favicon.svg` (any valid SVG; use a simple one):

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="14" fill="#0ea5e9"/><text x="16" y="22" font-family="sans-serif" font-size="18" fill="white" text-anchor="middle">m</text></svg>
```

- [ ] **Step 2: Install dependencies**

```bash
cd /d/code/claude-mnemos/frontend
pnpm install   # or: npm install
```

If pnpm is not available, fall back to npm. Either way commit the resulting lockfile.

- [ ] **Step 3: Smoke verify**

```bash
pnpm dev   # opens vite on :5173 if free, or auto-pick a port
```

Browser at the printed URL: should show "claude-mnemos" headline. Stop with Ctrl-C.

- [ ] **Step 4: Verify typecheck**

```bash
pnpm typecheck
```

Expected: no errors.

- [ ] **Step 5: Update root `.gitignore`**

Append to `D:/code/claude-mnemos/.gitignore` (or create section):

```
# Frontend
frontend/node_modules/
frontend/dist/
frontend/.vite/

# Built frontend artefacts (only .gitkeep is tracked)
claude_mnemos/daemon/static/*
!claude_mnemos/daemon/static/.gitkeep
```

- [ ] **Step 6: Commit**

```bash
cd /d/code/claude-mnemos
git add frontend/ .gitignore
git commit -m "feat(frontend): bootstrap Vite + React 19 + TypeScript scaffold"
```

---

## Task 2: Tailwind v4 + shadcn/ui base

**Files:**
- Create: `frontend/tailwind.config.ts`, `frontend/postcss.config.js`, `frontend/src/styles/globals.css`, `frontend/components.json`, `frontend/src/lib/utils.ts`
- Modify: `frontend/src/main.tsx` (import globals.css), `frontend/src/App.tsx` (Tailwind smoke), `frontend/package.json` (deps)

- [ ] **Step 1: Install Tailwind v4 + shadcn deps**

```bash
cd frontend
pnpm add tailwindcss @tailwindcss/postcss class-variance-authority clsx tailwind-merge lucide-react
pnpm add -D postcss autoprefixer
```

- [ ] **Step 2: Tailwind config**

Write `frontend/postcss.config.js`:

```js
export default {
  plugins: {
    "@tailwindcss/postcss": {},
    autoprefixer: {},
  },
};
```

Write `frontend/tailwind.config.ts` (Tailwind v4 still reads it for theme/content):

```ts
import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
} satisfies Config;
```

Write `frontend/src/styles/globals.css`:

```css
@import "tailwindcss";

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222 47% 11%;
    --primary: 199 89% 48%;
    --primary-foreground: 210 20% 98%;
    --muted: 210 16% 95%;
    --muted-foreground: 215 16% 47%;
    --border: 220 13% 91%;
    --card: 0 0% 100%;
    --card-foreground: 222 47% 11%;
    --destructive: 0 84% 60%;
    --destructive-foreground: 210 20% 98%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 222 47% 11%;
    --foreground: 210 20% 98%;
    --primary: 199 89% 48%;
    --primary-foreground: 222 47% 11%;
    --muted: 217 19% 27%;
    --muted-foreground: 215 14% 71%;
    --border: 217 19% 27%;
    --card: 222 47% 11%;
    --card-foreground: 210 20% 98%;
    --destructive: 0 84% 60%;
    --destructive-foreground: 210 20% 98%;
  }

  body {
    @apply bg-[hsl(var(--background))] text-[hsl(var(--foreground))];
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }
}
```

Write `frontend/src/lib/utils.ts`:

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

Write `frontend/components.json`:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/styles/globals.css",
    "baseColor": "slate",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

- [ ] **Step 3: Wire CSS in main.tsx**

Edit `frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./styles/globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Edit `frontend/src/App.tsx` for a Tailwind smoke:

```tsx
export default function App() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[hsl(var(--background))]">
      <h1 className="text-3xl font-bold text-[hsl(var(--primary))]">
        claude-mnemos
      </h1>
    </div>
  );
}
```

- [ ] **Step 4: Smoke verify**

```bash
pnpm dev
```

Browser: title should now be centered, large, and primary-color (sky-blue). Ctrl-C.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Tailwind v4 + shadcn baseline (cn helper, theme tokens)"
```

---

## Task 3: shadcn/ui components install + sonner toaster

**Files:**
- Create: `frontend/src/components/ui/{button,card,dropdown-menu,skeleton,badge,sonner,tooltip}.tsx`
- Modify: `frontend/package.json` (Radix peer deps)

- [ ] **Step 1: Install shadcn components**

```bash
cd frontend
pnpm dlx shadcn@latest init -y --tailwind v4 --typescript --jsx --rsc=false
# Then individually:
pnpm dlx shadcn@latest add button card dropdown-menu skeleton badge sonner tooltip
```

If `pnpm dlx` is unavailable use `npx shadcn@latest`.

This auto-installs `@radix-ui/react-dropdown-menu`, `@radix-ui/react-slot`, `@radix-ui/react-tooltip`, `sonner`, etc., and writes the component files to `frontend/src/components/ui/`.

- [ ] **Step 2: Verify install**

Files exist:
- `frontend/src/components/ui/button.tsx`
- `frontend/src/components/ui/card.tsx`
- `frontend/src/components/ui/dropdown-menu.tsx`
- `frontend/src/components/ui/skeleton.tsx`
- `frontend/src/components/ui/badge.tsx`
- `frontend/src/components/ui/sonner.tsx`
- `frontend/src/components/ui/tooltip.tsx`

```bash
pnpm typecheck
```

- [ ] **Step 3: Smoke check the Button**

Edit `frontend/src/App.tsx`:

```tsx
import { Button } from "@/components/ui/button";

export default function App() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[hsl(var(--background))]">
      <Button>Hello</Button>
    </div>
  );
}
```

```bash
pnpm dev
```

Should render a styled shadcn Button. Ctrl-C.

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): shadcn/ui components (button, card, dropdown-menu, skeleton, badge, sonner, tooltip)"
```

---

## Task 4: ESLint v9 + Vitest + RTL setup

**Files:**
- Create: `frontend/eslint.config.js`, `frontend/vitest.config.ts`, `frontend/src/setup-tests.ts`, `frontend/src/__tests__/smoke.test.tsx`
- Modify: `frontend/package.json` (deps + scripts)

- [ ] **Step 1: Install dev deps**

```bash
cd frontend
pnpm add -D vitest @vitest/ui jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
pnpm add -D eslint typescript-eslint @eslint/js eslint-plugin-react-hooks eslint-plugin-react-refresh globals
```

- [ ] **Step 2: ESLint config**

Write `frontend/eslint.config.js`:

```js
import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
);
```

- [ ] **Step 3: Vitest config**

Write `frontend/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setup-tests.ts"],
    css: false,
  },
});
```

Write `frontend/src/setup-tests.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 4: Write a smoke test**

Write `frontend/src/__tests__/smoke.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "../App";

describe("App smoke", () => {
  it("renders the Hello button", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: /hello/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Run + verify**

```bash
pnpm test
pnpm lint
pnpm typecheck
```

All green.

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): ESLint 9 + Vitest + RTL setup with smoke test"
```

---

## Task 5: i18next + locale skeletons

**Files:**
- Create: `frontend/src/i18n.ts`, `frontend/public/locales/{uk,ru,en}.json`, `frontend/src/__tests__/i18n.test.tsx`
- Modify: `frontend/package.json` (deps), `frontend/src/main.tsx` (import i18n), `frontend/src/App.tsx` (use t())

- [ ] **Step 1: Install i18next**

```bash
pnpm add i18next react-i18next i18next-http-backend i18next-browser-languagedetector
```

- [ ] **Step 2: Locale files**

Write `frontend/public/locales/uk.json`:

```json
{
  "common": {
    "loading": "Завантаження...",
    "save": "Зберегти",
    "cancel": "Скасувати",
    "open": "Відкрити",
    "retry": "Повторити"
  },
  "navigation": {
    "overview": "Огляд",
    "pages": "Сторінки",
    "sessions": "Чати",
    "queue": "Черга",
    "activity": "Історія",
    "suggestions": "Пропозиції",
    "lost_sessions": "Втрачені",
    "trash": "Кошик",
    "snapshots": "Знімки",
    "health": "Здоров'я",
    "settings": "Налаштування",
    "metrics": "Метрики",
    "help": "Допомога"
  },
  "topbar": {
    "all_projects": "Всі проєкти",
    "alerts": "Сповіщення",
    "settings": "Налаштування",
    "help": "Допомога",
    "locale": "Мова"
  },
  "overview": {
    "no_projects_title": "Мозок проєкту з'явиться тут",
    "no_projects_hint_cmd": "Зареєструйте перший проєкт:",
    "no_projects_hint_command": "mnemos project add NAME --vault PATH",
    "daemon_down_title": "Демон недоступний",
    "daemon_down_hint_cmd": "Запустіть демон:",
    "daemon_down_hint_command": "mnemos daemon start",
    "daemon_down_reconnect": "Дашборд автоматично перепідключиться."
  },
  "project_view": {
    "open_in_obsidian": "Відкрити в Obsidian",
    "watchdog_running": "Watchdog працює",
    "watchdog_down": "Watchdog зупинено",
    "stats": {
      "sessions_covered": "Сесії з контекстом",
      "jobs_queued": "В черзі",
      "jobs_running": "Виконуються",
      "jobs_dead_letter": "Помилки"
    },
    "unknown_title": "Проєкт не знайдено",
    "unknown_hint": "Цей проєкт не зареєстровано. Поверніться до Огляду.",
    "coming_in": "З'явиться в плані {{plan}}"
  },
  "health": {
    "ok": "Добре",
    "degraded": "Деградовано",
    "down": "Недоступний"
  },
  "usage": {
    "title": "Використання",
    "tokens_short": "{{count}} токенів",
    "sessions_short": "{{count}} сесій",
    "ratio_short": "стиснення ×{{ratio}}",
    "no_data": "Поки без даних"
  },
  "placeholder": {
    "title": "{{section}}",
    "body": "Цей розділ з'явиться в плані {{plan}}.",
    "back_link": "Повернутись до Огляду"
  }
}
```

Write `frontend/public/locales/ru.json` — same keys, Russian:

```json
{
  "common": {
    "loading": "Загрузка...",
    "save": "Сохранить",
    "cancel": "Отменить",
    "open": "Открыть",
    "retry": "Повторить"
  },
  "navigation": {
    "overview": "Обзор",
    "pages": "Страницы",
    "sessions": "Чаты",
    "queue": "Очередь",
    "activity": "История",
    "suggestions": "Предложения",
    "lost_sessions": "Потерянные",
    "trash": "Корзина",
    "snapshots": "Снимки",
    "health": "Здоровье",
    "settings": "Настройки",
    "metrics": "Метрики",
    "help": "Помощь"
  },
  "topbar": {
    "all_projects": "Все проекты",
    "alerts": "Уведомления",
    "settings": "Настройки",
    "help": "Помощь",
    "locale": "Язык"
  },
  "overview": {
    "no_projects_title": "Мозг проекта появится здесь",
    "no_projects_hint_cmd": "Зарегистрируйте первый проект:",
    "no_projects_hint_command": "mnemos project add NAME --vault PATH",
    "daemon_down_title": "Daemon недоступен",
    "daemon_down_hint_cmd": "Запустите daemon:",
    "daemon_down_hint_command": "mnemos daemon start",
    "daemon_down_reconnect": "Дашборд переподключится автоматически."
  },
  "project_view": {
    "open_in_obsidian": "Открыть в Obsidian",
    "watchdog_running": "Watchdog работает",
    "watchdog_down": "Watchdog остановлен",
    "stats": {
      "sessions_covered": "Сессий с контекстом",
      "jobs_queued": "В очереди",
      "jobs_running": "Выполняются",
      "jobs_dead_letter": "Ошибки"
    },
    "unknown_title": "Проект не найден",
    "unknown_hint": "Этот проект не зарегистрирован. Вернитесь в Обзор.",
    "coming_in": "Появится в плане {{plan}}"
  },
  "health": {
    "ok": "Хорошо",
    "degraded": "Деградировано",
    "down": "Недоступно"
  },
  "usage": {
    "title": "Использование",
    "tokens_short": "{{count}} токенов",
    "sessions_short": "{{count}} сессий",
    "ratio_short": "сжатие ×{{ratio}}",
    "no_data": "Пока без данных"
  },
  "placeholder": {
    "title": "{{section}}",
    "body": "Этот раздел появится в плане {{plan}}.",
    "back_link": "Вернуться в Обзор"
  }
}
```

Write `frontend/public/locales/en.json`:

```json
{
  "common": {
    "loading": "Loading...",
    "save": "Save",
    "cancel": "Cancel",
    "open": "Open",
    "retry": "Retry"
  },
  "navigation": {
    "overview": "Overview",
    "pages": "Pages",
    "sessions": "Sessions",
    "queue": "Queue",
    "activity": "Activity",
    "suggestions": "Suggestions",
    "lost_sessions": "Lost",
    "trash": "Trash",
    "snapshots": "Snapshots",
    "health": "Health",
    "settings": "Settings",
    "metrics": "Metrics",
    "help": "Help"
  },
  "topbar": {
    "all_projects": "All projects",
    "alerts": "Alerts",
    "settings": "Settings",
    "help": "Help",
    "locale": "Language"
  },
  "overview": {
    "no_projects_title": "Project brains appear here",
    "no_projects_hint_cmd": "Register your first project:",
    "no_projects_hint_command": "mnemos project add NAME --vault PATH",
    "daemon_down_title": "Daemon unavailable",
    "daemon_down_hint_cmd": "Start the daemon:",
    "daemon_down_hint_command": "mnemos daemon start",
    "daemon_down_reconnect": "The dashboard will reconnect automatically."
  },
  "project_view": {
    "open_in_obsidian": "Open in Obsidian",
    "watchdog_running": "Watchdog running",
    "watchdog_down": "Watchdog stopped",
    "stats": {
      "sessions_covered": "Sessions covered",
      "jobs_queued": "Queued",
      "jobs_running": "Running",
      "jobs_dead_letter": "Failed"
    },
    "unknown_title": "Project not found",
    "unknown_hint": "This project is not registered. Return to Overview.",
    "coming_in": "Coming in plan {{plan}}"
  },
  "health": {
    "ok": "OK",
    "degraded": "Degraded",
    "down": "Down"
  },
  "usage": {
    "title": "Usage",
    "tokens_short": "{{count}} tokens",
    "sessions_short": "{{count}} sessions",
    "ratio_short": "compression ×{{ratio}}",
    "no_data": "No data yet"
  },
  "placeholder": {
    "title": "{{section}}",
    "body": "This section is coming in plan {{plan}}.",
    "back_link": "Back to Overview"
  }
}
```

- [ ] **Step 3: i18n setup**

Write `frontend/src/i18n.ts`:

```ts
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import HttpBackend from "i18next-http-backend";

void i18n
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: "en",
    supportedLngs: ["uk", "ru", "en"],
    backend: { loadPath: "/locales/{{lng}}.json" },
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    },
  });

export default i18n;
```

Edit `frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./styles/globals.css";
import "./i18n";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Edit `frontend/src/App.tsx` to use translations:

```tsx
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

export default function App() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Button>{t("common.open")}</Button>
    </div>
  );
}
```

- [ ] **Step 4: Tests**

Write `frontend/src/__tests__/i18n.test.tsx`:

```tsx
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import i18n from "../i18n";
import App from "../App";

beforeAll(async () => {
  // Stub the http backend with inline resources for tests.
  i18n.removeResourceBundle("uk", "translation");
  i18n.removeResourceBundle("ru", "translation");
  i18n.removeResourceBundle("en", "translation");
  i18n.addResources("uk", "translation", { common: { open: "Відкрити" } });
  i18n.addResources("ru", "translation", { common: { open: "Открыть" } });
  i18n.addResources("en", "translation", { common: { open: "Open" } });
});

describe("i18n", () => {
  it("renders Ukrainian by default after detection", async () => {
    await i18n.changeLanguage("uk");
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("button")).toHaveTextContent("Відкрити"),
    );
  });

  it("switches language at runtime", async () => {
    await i18n.changeLanguage("en");
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("button")).toHaveTextContent("Open"),
    );
  });
});
```

- [ ] **Step 5: Run + verify**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): i18next setup with UK/RU/EN locales (skeleton)"
```

---

## Task 6: Backend StaticFiles mount

**Files:**
- Modify: `claude_mnemos/daemon/app.py`
- Create: `claude_mnemos/daemon/static/.gitkeep`, `claude_mnemos/daemon/static/.gitignore`, `tests/daemon/test_app_static.py`

- [ ] **Step 1: Create static dir guards**

```bash
mkdir -p claude_mnemos/daemon/static
touch claude_mnemos/daemon/static/.gitkeep
```

Write `claude_mnemos/daemon/static/.gitignore`:

```
*
!.gitkeep
!.gitignore
```

- [ ] **Step 2: Write failing tests**

Write `tests/daemon/test_app_static.py`:

```python
from __future__ import annotations
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_mnemos.daemon.app import create_app


def test_static_mount_skipped_when_no_index_html(tmp_path, monkeypatch):
    """When daemon/static/index.html does not exist, the mount is skipped
    silently and the daemon serves only its JSON API."""
    # Patch the static_dir resolution by clearing index.html if it exists.
    static_dir = (
        Path(__file__).resolve().parents[2]
        / "claude_mnemos"
        / "daemon"
        / "static"
    )
    index = static_dir / "index.html"
    if index.exists():
        index.unlink()

    app = create_app()
    client = TestClient(app)

    # Health works (REST API).
    r = client.get("/health")
    assert r.status_code == 200
    # Without a built frontend, requesting "/" returns 404 from FastAPI
    # (no route, no static fallback) — the route table itself doesn't
    # define GET /, so the response is 404.
    r = client.get("/")
    assert r.status_code == 404


def test_static_mount_active_when_index_html_exists(tmp_path):
    """When daemon/static/index.html exists, GET / returns its bytes."""
    static_dir = (
        Path(__file__).resolve().parents[2]
        / "claude_mnemos"
        / "daemon"
        / "static"
    )
    static_dir.mkdir(parents=True, exist_ok=True)
    index = static_dir / "index.html"
    index.write_text("<!doctype html><html><body>fake spa</body></html>", encoding="utf-8")

    try:
        app = create_app()
        client = TestClient(app)

        r = client.get("/")
        assert r.status_code == 200
        assert b"fake spa" in r.content
        # API still wins.
        r = client.get("/health")
        assert r.status_code == 200
    finally:
        index.unlink()
```

- [ ] **Step 3: Run** → FAIL.

```bash
python -m pytest tests/daemon/test_app_static.py -v
```

Expected: `test_static_mount_active_when_index_html_exists` fails (no static mount yet).

- [ ] **Step 4: Implement the mount**

Edit `claude_mnemos/daemon/app.py`. Add `from pathlib import Path` and `from fastapi.staticfiles import StaticFiles` at the top. At the end of `create_app`, after all routers and exception handlers, add:

```python
    # Mount frontend static files (built by `frontend/`).
    # html=True provides SPA fallback: any path not matching a file → index.html.
    # Mounted last so REST routers take precedence on overlapping paths.
    static_dir = Path(__file__).parent / "static"
    if (static_dir / "index.html").is_file():
        app.mount(
            "/",
            StaticFiles(directory=static_dir, html=True),
            name="frontend",
        )

    return app
```

- [ ] **Step 5: Run** → PASS.

```bash
python -m pytest tests/daemon/test_app_static.py -v
```

- [ ] **Step 6: Run full daemon suite for regressions**

```bash
python -m pytest tests/daemon/ -q --ignore=tests/daemon/integration -k "not slow" 2>&1 | tail -10
```

- [ ] **Step 7: ruff + mypy**

```bash
ruff check claude_mnemos/daemon/app.py tests/daemon/test_app_static.py
mypy --strict claude_mnemos/daemon/app.py
```

- [ ] **Step 8: Commit**

```bash
git add claude_mnemos/daemon/app.py claude_mnemos/daemon/static/ tests/daemon/test_app_static.py
git commit -m "feat(daemon): mount frontend static at / with SPA fallback (skip when missing)"
```

---

## Task 7: API client + types + zod schemas

**Files:**
- Create: `frontend/src/api/client.ts`, `frontend/src/api/projects.api.ts`, `frontend/src/api/health.api.ts`, `frontend/src/api/metrics.api.ts`, `frontend/src/types/{Project,Health,UsageSummary}.ts`, `frontend/src/__tests__/api.test.ts`
- Modify: `frontend/package.json` (deps)

- [ ] **Step 1: Install deps**

```bash
pnpm add axios zod
```

- [ ] **Step 2: Write the api module + types**

Write `frontend/src/api/client.ts`:

```ts
import axios from "axios";

const baseURL = (import.meta.env.VITE_DAEMON_BASE_URL ?? "") as string;

export const apiClient = axios.create({
  baseURL,
  timeout: 5000,
});
```

Write `frontend/src/types/Project.ts`:

```ts
import { z } from "zod";

export const ProjectMapEntrySchema = z.object({
  name: z.string(),
  vault_root: z.string(),
  cwd_patterns: z.array(z.string()),
});
export type ProjectMapEntry = z.infer<typeof ProjectMapEntrySchema>;
```

Write `frontend/src/types/Health.ts`:

```ts
import { z } from "zod";

export const VaultHealthSchema = z.object({
  watchdog_running: z.boolean(),
  jobs_queued: z.number().int().nonnegative(),
  jobs_running: z.number().int().nonnegative(),
  jobs_dead_letter: z.number().int().nonnegative(),
});
export type VaultHealth = z.infer<typeof VaultHealthSchema>;

export const HealthSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  version: z.string(),
  uptime_s: z.number().nonnegative(),
  alerts_count: z.number().int().nonnegative(),
  vaults: z.record(z.string(), VaultHealthSchema),
  jobs_alert: z.boolean(),
  scheduler_jobs: z.array(z.unknown()).optional(),
});
export type Health = z.infer<typeof HealthSchema>;
```

Write `frontend/src/types/UsageSummary.ts`:

```ts
import { z } from "zod";

export const UsageSummarySchema = z.object({
  period: z.string(),
  total_tokens_injected: z.number().int().nonnegative(),
  tokens_full: z.number().int().nonnegative(),
  sessions_covered: z.number().int().nonnegative(),
  avg_compression_ratio: z.number().nonnegative(),
  events_count: z.number().int().nonnegative(),
});
export type UsageSummary = z.infer<typeof UsageSummarySchema>;

export const UsageByProjectEntrySchema = z.object({
  project: z.string(),
  // The daemon emits a UsageSummary with the same keys minus `period`,
  // plus the project name. Accept extra fields gracefully.
}).passthrough();
export type UsageByProjectEntry = z.infer<typeof UsageByProjectEntrySchema>;

export const UsageByProjectResponseSchema = z.object({
  projects: z.array(UsageByProjectEntrySchema),
});
```

Write `frontend/src/api/projects.api.ts`:

```ts
import { apiClient } from "./client";
import { ProjectMapEntrySchema, type ProjectMapEntry } from "@/types/Project";
import { z } from "zod";

const ProjectsListSchema = z.array(ProjectMapEntrySchema);

export async function listProjects(): Promise<ProjectMapEntry[]> {
  const r = await apiClient.get("/projects");
  return ProjectsListSchema.parse(r.data);
}
```

Write `frontend/src/api/health.api.ts`:

```ts
import { apiClient } from "./client";
import { HealthSchema, type Health } from "@/types/Health";

export async function getHealth(): Promise<Health> {
  const r = await apiClient.get("/health");
  return HealthSchema.parse(r.data);
}
```

Write `frontend/src/api/metrics.api.ts`:

```ts
import { apiClient } from "./client";
import {
  UsageSummarySchema,
  UsageByProjectResponseSchema,
  type UsageSummary,
  type UsageByProjectEntry,
} from "@/types/UsageSummary";

export async function getUsage(period = "30d"): Promise<UsageSummary> {
  const r = await apiClient.get("/metrics/usage", { params: { period } });
  return UsageSummarySchema.parse(r.data);
}

export async function getUsageByProject(
  period = "30d",
): Promise<UsageByProjectEntry[]> {
  const r = await apiClient.get("/metrics/usage/by-project", { params: { period } });
  return UsageByProjectResponseSchema.parse(r.data).projects;
}
```

- [ ] **Step 3: Test**

Write `frontend/src/__tests__/api.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "../api/client";
import { listProjects } from "../api/projects.api";
import { getHealth } from "../api/health.api";
import { getUsage } from "../api/metrics.api";

describe("api", () => {
  beforeEach(() => {
    vi.spyOn(apiClient, "get");
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("listProjects parses an array of ProjectMapEntry", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: [{ name: "alpha", vault_root: "/a", cwd_patterns: [] }],
    });
    const list = await listProjects();
    expect(list).toHaveLength(1);
    expect(list[0]?.name).toBe("alpha");
  });

  it("listProjects rejects malformed payload", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: [{ wrong: 1 }] });
    await expect(listProjects()).rejects.toThrow();
  });

  it("getHealth parses the per-vault dict shape", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        status: "ok",
        version: "0.1",
        uptime_s: 12,
        alerts_count: 0,
        vaults: {
          alpha: {
            watchdog_running: true,
            jobs_queued: 0,
            jobs_running: 0,
            jobs_dead_letter: 0,
          },
        },
        jobs_alert: false,
        scheduler_jobs: [],
      },
    });
    const h = await getHealth();
    expect(h.status).toBe("ok");
    expect(h.vaults.alpha?.watchdog_running).toBe(true);
  });

  it("getUsage parses summary shape", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        period: "30d",
        total_tokens_injected: 1000,
        tokens_full: 5000,
        sessions_covered: 10,
        avg_compression_ratio: 5,
        events_count: 10,
      },
    });
    const u = await getUsage("30d");
    expect(u.sessions_covered).toBe(10);
  });
});
```

- [ ] **Step 4: Run + verify**

```bash
pnpm test
pnpm lint
pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): typed API client (axios + zod) for /projects, /health, /metrics"
```

---

## Task 8: TanStack Query + hooks

**Files:**
- Create: `frontend/src/hooks/useProjects.ts`, `frontend/src/hooks/useHealth.ts`, `frontend/src/hooks/useUsage.ts`, `frontend/src/hooks/useUsageByProject.ts`, `frontend/src/lib/query-client.ts`, `frontend/src/__tests__/hooks.test.tsx`
- Modify: `frontend/src/main.tsx` (wrap with QueryClientProvider), `frontend/package.json` (deps)

- [ ] **Step 1: Install deps**

```bash
pnpm add @tanstack/react-query
pnpm add -D @tanstack/react-query-devtools
```

- [ ] **Step 2: Query client + hooks**

Write `frontend/src/lib/query-client.ts`:

```ts
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
```

Write `frontend/src/hooks/useProjects.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { listProjects } from "@/api/projects.api";

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    refetchInterval: 5_000,
  });
}
```

Write `frontend/src/hooks/useHealth.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/api/health.api";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 5_000,
  });
}
```

Write `frontend/src/hooks/useUsage.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { getUsage } from "@/api/metrics.api";

export function useUsage(period = "1d") {
  return useQuery({
    queryKey: ["metrics", "usage", period],
    queryFn: () => getUsage(period),
    refetchInterval: 30_000,
  });
}
```

Write `frontend/src/hooks/useUsageByProject.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { getUsageByProject } from "@/api/metrics.api";

export function useUsageByProject(period = "30d") {
  return useQuery({
    queryKey: ["metrics", "usage", "by-project", period],
    queryFn: () => getUsageByProject(period),
    refetchInterval: 30_000,
  });
}
```

- [ ] **Step 3: Wrap App**

Edit `frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import App from "./App.tsx";
import "./styles/globals.css";
import "./i18n";
import { queryClient } from "./lib/query-client";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
```

- [ ] **Step 4: Test the hook**

Write `frontend/src/__tests__/hooks.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode } from "react";

import { apiClient } from "../api/client";
import { useProjects } from "../hooks/useProjects";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useProjects", () => {
  beforeEach(() => {
    vi.spyOn(apiClient, "get");
  });

  it("returns the parsed list", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: [{ name: "alpha", vault_root: "/a", cwd_patterns: [] }],
    });
    const { result } = renderHook(() => useProjects(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0]?.name).toBe("alpha");
  });

  it("exposes error state on failure", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error("daemon down"));
    const { result } = renderHook(() => useProjects(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
```

- [ ] **Step 5: Run + verify**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): TanStack Query setup + useProjects/useHealth/useUsage hooks"
```

---

## Task 9: Zustand UI + notifications stores

**Files:**
- Create: `frontend/src/stores/ui.store.ts`, `frontend/src/stores/notifications.store.ts`, `frontend/src/__tests__/stores.test.ts`
- Modify: `frontend/package.json` (deps)

- [ ] **Step 1: Install zustand**

```bash
pnpm add zustand
```

- [ ] **Step 2: ui.store**

Write `frontend/src/stores/ui.store.ts`:

```ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

type Locale = "uk" | "ru" | "en";
type Theme = "light" | "dark";

interface UIState {
  sidebarCollapsed: boolean;
  locale: Locale;
  theme: Theme;
  toggleSidebar: () => void;
  setLocale: (l: Locale) => void;
  setTheme: (t: Theme) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      locale: "uk",
      theme: "light",
      toggleSidebar: () =>
        set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setLocale: (locale) => set({ locale }),
      setTheme: (theme) => set({ theme }),
    }),
    { name: "claude-mnemos:ui" },
  ),
);
```

- [ ] **Step 3: notifications.store**

Write `frontend/src/stores/notifications.store.ts`:

```ts
import { create } from "zustand";

export type ToastKind = "info" | "success" | "warning" | "error";

export interface Toast {
  id: string;
  kind: ToastKind;
  title: string;
  description?: string;
}

interface NotificationsState {
  toasts: Toast[];
  push: (toast: Omit<Toast, "id">) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

export const useNotifications = create<NotificationsState>((set) => ({
  toasts: [],
  push: (toast) => {
    const id = crypto.randomUUID();
    set((s) => ({ toasts: [...s.toasts, { ...toast, id }] }));
    return id;
  },
  dismiss: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  clear: () => set({ toasts: [] }),
}));
```

- [ ] **Step 4: Tests**

Write `frontend/src/__tests__/stores.test.ts`:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore } from "../stores/ui.store";
import { useNotifications } from "../stores/notifications.store";

describe("ui.store", () => {
  beforeEach(() => {
    useUIStore.setState({
      sidebarCollapsed: false,
      locale: "uk",
      theme: "light",
    });
  });

  it("toggles sidebar", () => {
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
  });

  it("sets locale", () => {
    useUIStore.getState().setLocale("en");
    expect(useUIStore.getState().locale).toBe("en");
  });
});

describe("notifications.store", () => {
  beforeEach(() => useNotifications.getState().clear());

  it("push returns id and stores toast", () => {
    const id = useNotifications.getState().push({
      kind: "info",
      title: "Hello",
    });
    expect(typeof id).toBe("string");
    expect(useNotifications.getState().toasts).toHaveLength(1);
  });

  it("dismiss removes the toast", () => {
    const id = useNotifications.getState().push({
      kind: "warning",
      title: "Test",
    });
    useNotifications.getState().dismiss(id);
    expect(useNotifications.getState().toasts).toHaveLength(0);
  });
});
```

- [ ] **Step 5: Run + verify**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Zustand ui + notifications stores"
```

---

## Task 10: Layout shell

**Files:**
- Create: `frontend/src/components/layout/Layout.tsx`, `frontend/src/__tests__/Layout.test.tsx`
- Modify: `frontend/src/App.tsx` (use BrowserRouter + Outlet placeholder)

- [ ] **Step 1: Test first**

Write `frontend/src/__tests__/Layout.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { Layout } from "../components/layout/Layout";

describe("Layout", () => {
  it("renders TopBar slot, Sidebar slot, and Outlet content", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<div>page-body</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole("banner")).toBeInTheDocument(); // TopBar = <header>
    expect(screen.getByRole("navigation")).toBeInTheDocument(); // Sidebar = <nav>
    expect(screen.getByText("page-body")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement Layout (with stubs for TopBar/Sidebar — concrete components in next tasks)**

Write `frontend/src/components/layout/Layout.tsx`:

```tsx
import { Outlet } from "react-router";

export function Layout() {
  return (
    <div className="grid h-screen grid-rows-[auto_1fr] overflow-hidden">
      <header className="border-b bg-[hsl(var(--background))] px-4 py-3">
        <span className="font-semibold">claude-mnemos</span>
      </header>
      <div className="grid grid-cols-[16rem_1fr] overflow-hidden">
        <nav aria-label="primary" className="border-r bg-[hsl(var(--muted))] p-4">
          <span className="text-sm text-[hsl(var(--muted-foreground))]">nav</span>
        </nav>
        <main className="overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Run + verify**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Layout shell with TopBar/Sidebar/Outlet skeleton"
```

---

## Task 11: Routing + Placeholder + App.tsx

**Files:**
- Create: `frontend/src/pages/Placeholder.tsx`, `frontend/src/pages/{Overview,ProjectView,Help}.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Stub pages**

Write `frontend/src/pages/Placeholder.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

interface Props {
  section: string;
  plan: string;
}

export function Placeholder({ section, plan }: Props) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-xl space-y-3 py-12 text-center">
      <h1 className="text-2xl font-semibold">{section}</h1>
      <p className="text-[hsl(var(--muted-foreground))]">
        {t("placeholder.body", { plan })}
      </p>
      <Link to="/" className="text-[hsl(var(--primary))] underline">
        {t("placeholder.back_link")}
      </Link>
    </div>
  );
}
```

Write `frontend/src/pages/Overview.tsx` (stub for now, full impl in Task 17):

```tsx
export function Overview() {
  return <div>Overview (Task 17)</div>;
}
```

Write `frontend/src/pages/ProjectView.tsx` (stub for now, Task 18):

```tsx
export function ProjectView() {
  return <div>ProjectView (Task 18)</div>;
}
```

Write `frontend/src/pages/Help.tsx` (lightweight stub):

```tsx
import { useTranslation } from "react-i18next";

export function Help() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-2xl space-y-4 py-8">
      <h1 className="text-2xl font-semibold">{t("navigation.help")}</h1>
      <p className="text-[hsl(var(--muted-foreground))]">
        {t("placeholder.body", { plan: "#14d" })}
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Update App.tsx with full router**

Write `frontend/src/App.tsx`:

```tsx
import { createBrowserRouter, RouterProvider } from "react-router";
import { Layout } from "./components/layout/Layout";
import { Overview } from "./pages/Overview";
import { ProjectView } from "./pages/ProjectView";
import { Help } from "./pages/Help";
import { Placeholder } from "./pages/Placeholder";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "onboarding", element: <Placeholder section="Onboarding" plan="#14d" /> },
      {
        path: "project/:name",
        children: [
          { index: true, element: <ProjectView /> },
          { path: "pages", element: <Placeholder section="Pages" plan="#14b" /> },
          { path: "pages/:pageId", element: <Placeholder section="Page detail" plan="#14b" /> },
          { path: "sessions", element: <Placeholder section="Sessions" plan="#14b" /> },
          { path: "activity", element: <Placeholder section="Activity Center" plan="#14b" /> },
          { path: "suggestions", element: <Placeholder section="Suggestions" plan="#14b" /> },
          { path: "trash", element: <Placeholder section="Trash" plan="#14b" /> },
          { path: "snapshots", element: <Placeholder section="Snapshots" plan="#14b" /> },
          { path: "health", element: <Placeholder section="Health" plan="#14b" /> },
          { path: "settings", element: <Placeholder section="Settings" plan="#14c" /> },
        ],
      },
      { path: "lost-sessions", element: <Placeholder section="Lost Sessions" plan="#14b" /> },
      { path: "help", element: <Help /> },
      { path: "metrics", element: <Placeholder section="Metrics" plan="#14d" /> },
      { path: "settings/global", element: <Placeholder section="Global Settings" plan="#14c" /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
```

- [ ] **Step 3: Test routing**

Add to existing `frontend/src/__tests__/Layout.test.tsx` (or new file `routing.test.tsx`):

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { Placeholder } from "../pages/Placeholder";

describe("Placeholder", () => {
  it("renders section title and plan reference", () => {
    render(
      <MemoryRouter>
        <Placeholder section="Pages" plan="#14b" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: /pages/i })).toBeInTheDocument();
    // Note: t() returns the key when bundle missing; smoke check that the
    // body contains the plan number once locale loads — for unit test, the
    // key fallback is acceptable.
  });
});
```

- [ ] **Step 4: Run + verify**

```bash
pnpm test
pnpm typecheck
pnpm lint
```

- [ ] **Step 5: Smoke verify in browser**

```bash
pnpm dev
```

Visit `http://localhost:5173/`. Should see "Overview (Task 17)". Try `/help` — Help page. Try `/lost-sessions` — Placeholder. Ctrl-C.

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): full router + Placeholder stubs for #14b/#14c/#14d sections"
```

---

## Task 12: TopBar — minimal (logo + locale switcher)

**Files:**
- Create: `frontend/src/components/layout/TopBar.tsx`, `frontend/src/__tests__/TopBar.test.tsx`
- Modify: `frontend/src/components/layout/Layout.tsx` (use TopBar)

- [ ] **Step 1: Test**

Write `frontend/src/__tests__/TopBar.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TopBar } from "../components/layout/TopBar";
import { useUIStore } from "../stores/ui.store";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("TopBar", () => {
  it("renders the brand", () => {
    render(wrap(<TopBar />));
    expect(screen.getByText("claude-mnemos")).toBeInTheDocument();
  });

  it("locale switcher cycles uk → ru → en → uk", async () => {
    const user = userEvent.setup();
    useUIStore.setState({ locale: "uk", sidebarCollapsed: false, theme: "light" });
    render(wrap(<TopBar />));
    const btn = screen.getByRole("button", { name: /uk/i });
    await user.click(btn);
    expect(useUIStore.getState().locale).toBe("ru");
    await user.click(screen.getByRole("button", { name: /ru/i }));
    expect(useUIStore.getState().locale).toBe("en");
    await user.click(screen.getByRole("button", { name: /en/i }));
    expect(useUIStore.getState().locale).toBe("uk");
  });
});
```

- [ ] **Step 2: Implement**

Write `frontend/src/components/layout/TopBar.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { useEffect } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/stores/ui.store";

const LOCALE_CYCLE = ["uk", "ru", "en"] as const;
type Locale = (typeof LOCALE_CYCLE)[number];

function nextLocale(l: Locale): Locale {
  const i = LOCALE_CYCLE.indexOf(l);
  return LOCALE_CYCLE[(i + 1) % LOCALE_CYCLE.length]!;
}

export function TopBar() {
  const { i18n } = useTranslation();
  const locale = useUIStore((s) => s.locale);
  const setLocale = useUIStore((s) => s.setLocale);

  useEffect(() => {
    if (i18n.language !== locale) void i18n.changeLanguage(locale);
  }, [i18n, locale]);

  return (
    <header className="flex items-center justify-between border-b bg-[hsl(var(--background))] px-4 py-2">
      <div className="flex items-center gap-3">
        <Link to="/" className="font-semibold">
          claude-mnemos
        </Link>
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setLocale(nextLocale(locale))}
        >
          {locale.toUpperCase()}
        </Button>
      </div>
    </header>
  );
}
```

- [ ] **Step 3: Wire into Layout**

Edit `frontend/src/components/layout/Layout.tsx`:

```tsx
import { Outlet } from "react-router";
import { TopBar } from "./TopBar";

export function Layout() {
  return (
    <div className="grid h-screen grid-rows-[auto_1fr] overflow-hidden">
      <TopBar />
      <div className="grid grid-cols-[16rem_1fr] overflow-hidden">
        <nav aria-label="primary" className="border-r bg-[hsl(var(--muted))] p-4">
          <span className="text-sm text-[hsl(var(--muted-foreground))]">
            (Sidebar — Task 14)
          </span>
        </nav>
        <main className="overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run + verify**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): TopBar with brand + locale cycle button"
```

---

## Task 13: ProjectSwitcher in TopBar

**Files:**
- Create: `frontend/src/components/layout/ProjectSwitcher.tsx`, `frontend/src/__tests__/ProjectSwitcher.test.tsx`
- Modify: `frontend/src/components/layout/TopBar.tsx`

- [ ] **Step 1: Test**

Write `frontend/src/__tests__/ProjectSwitcher.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { ProjectSwitcher } from "../components/layout/ProjectSwitcher";

function wrap(ui: React.ReactNode, path = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/" element={ui} />
          <Route path="/project/:name" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("ProjectSwitcher", () => {
  it("renders 'all projects' label when on /", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: [{ name: "alpha", vault_root: "/a", cwd_patterns: [] }],
    });
    render(wrap(<ProjectSwitcher />));
    await waitFor(() => {
      expect(screen.getByRole("button")).toBeInTheDocument();
    });
  });

  it("opens menu and lists projects", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: [
        { name: "alpha", vault_root: "/a", cwd_patterns: [] },
        { name: "beta", vault_root: "/b", cwd_patterns: [] },
      ],
    });
    const user = userEvent.setup();
    render(wrap(<ProjectSwitcher />));
    await waitFor(() => screen.getByRole("button"));
    await user.click(screen.getByRole("button"));
    expect(await screen.findByText("alpha")).toBeInTheDocument();
    expect(await screen.findByText("beta")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement**

Write `frontend/src/components/layout/ProjectSwitcher.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";
import { ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useProjects } from "@/hooks/useProjects";

export function ProjectSwitcher() {
  const { t } = useTranslation();
  const { name: currentName } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { data: projects, isLoading } = useProjects();

  const label =
    currentName ?? (isLoading ? t("common.loading") : t("topbar.all_projects"));

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1">
          {label}
          <ChevronDown className="h-3 w-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-48">
        <DropdownMenuItem onClick={() => navigate("/")}>
          {t("topbar.all_projects")}
        </DropdownMenuItem>
        {projects?.map((p) => (
          <DropdownMenuItem
            key={p.name}
            onClick={() => navigate(`/project/${p.name}`)}
          >
            {p.name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

- [ ] **Step 3: Wire into TopBar**

Edit `frontend/src/components/layout/TopBar.tsx` — add ProjectSwitcher next to the brand:

```tsx
import { useTranslation } from "react-i18next";
import { useEffect } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/stores/ui.store";
import { ProjectSwitcher } from "./ProjectSwitcher";

const LOCALE_CYCLE = ["uk", "ru", "en"] as const;
type Locale = (typeof LOCALE_CYCLE)[number];

function nextLocale(l: Locale): Locale {
  const i = LOCALE_CYCLE.indexOf(l);
  return LOCALE_CYCLE[(i + 1) % LOCALE_CYCLE.length]!;
}

export function TopBar() {
  const { i18n } = useTranslation();
  const locale = useUIStore((s) => s.locale);
  const setLocale = useUIStore((s) => s.setLocale);

  useEffect(() => {
    if (i18n.language !== locale) void i18n.changeLanguage(locale);
  }, [i18n, locale]);

  return (
    <header className="flex items-center justify-between border-b bg-[hsl(var(--background))] px-4 py-2">
      <div className="flex items-center gap-3">
        <Link to="/" className="font-semibold">
          claude-mnemos
        </Link>
        <ProjectSwitcher />
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setLocale(nextLocale(locale))}
        >
          {locale.toUpperCase()}
        </Button>
      </div>
    </header>
  );
}
```

- [ ] **Step 4: Run + verify**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): ProjectSwitcher dropdown in TopBar"
```

---

## Task 14: UsageWidget in TopBar

**Files:**
- Create: `frontend/src/components/widgets/UsageWidget.tsx`, `frontend/src/__tests__/UsageWidget.test.tsx`
- Modify: `frontend/src/components/layout/TopBar.tsx`

- [ ] **Step 1: Test**

Write `frontend/src/__tests__/UsageWidget.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { UsageWidget } from "../components/widgets/UsageWidget";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe("UsageWidget", () => {
  it("formats tokens injected and ratio", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        period: "1d",
        total_tokens_injected: 8234,
        tokens_full: 47356,
        sessions_covered: 5,
        avg_compression_ratio: 5.75,
        events_count: 5,
      },
    });
    render(wrap(<UsageWidget />));
    await waitFor(() => expect(screen.getByText(/8\.2K/)).toBeInTheDocument());
    expect(screen.getByText(/×5\.8/)).toBeInTheDocument();
    expect(screen.getByText(/5/)).toBeInTheDocument();
  });

  it("shows 'no data' when usage is empty", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        period: "1d",
        total_tokens_injected: 0,
        tokens_full: 0,
        sessions_covered: 0,
        avg_compression_ratio: 0,
        events_count: 0,
      },
    });
    render(wrap(<UsageWidget />));
    await waitFor(() =>
      expect(screen.getByText(/no_data|no data/i)).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 2: Implement**

Write `frontend/src/components/widgets/UsageWidget.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { Syringe } from "lucide-react";
import { useUsage } from "@/hooks/useUsage";

function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}K`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

function formatRatio(r: number): string {
  return r.toFixed(1);
}

export function UsageWidget() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useUsage("1d");

  if (isLoading || isError || !data) return null;

  if (data.total_tokens_injected === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-[hsl(var(--muted-foreground))]">
        <Syringe className="h-4 w-4" />
        <span>{t("usage.no_data")}</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 text-sm" title={t("usage.title")}>
      <Syringe className="h-4 w-4 text-[hsl(var(--primary))]" />
      <span>{formatTokens(data.total_tokens_injected)}</span>
      <span className="text-[hsl(var(--muted-foreground))]">·</span>
      <span>{data.sessions_covered}</span>
      <span className="text-[hsl(var(--muted-foreground))]">·</span>
      <span>×{formatRatio(data.avg_compression_ratio)}</span>
    </div>
  );
}
```

- [ ] **Step 3: Wire into TopBar**

Edit `frontend/src/components/layout/TopBar.tsx`:

```tsx
// imports …
import { UsageWidget } from "@/components/widgets/UsageWidget";

// inside <header>:
<header className="flex items-center justify-between border-b bg-[hsl(var(--background))] px-4 py-2">
  <div className="flex items-center gap-3">
    <Link to="/" className="font-semibold">claude-mnemos</Link>
    <ProjectSwitcher />
  </div>
  <div className="flex items-center gap-4">
    <UsageWidget />
    <Button variant="ghost" size="sm" onClick={() => setLocale(nextLocale(locale))}>
      {locale.toUpperCase()}
    </Button>
  </div>
</header>
```

- [ ] **Step 4: Run + verify**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): UsageWidget in TopBar (tokens·sessions·ratio)"
```

---

## Task 15: Sidebar with navigation

**Files:**
- Create: `frontend/src/components/layout/Sidebar.tsx`, `frontend/src/__tests__/Sidebar.test.tsx`
- Modify: `frontend/src/components/layout/Layout.tsx`

- [ ] **Step 1: Test**

Write `frontend/src/__tests__/Sidebar.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { Sidebar } from "../components/layout/Sidebar";

describe("Sidebar", () => {
  it("highlights Overview on /", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<Sidebar />} />
        </Routes>
      </MemoryRouter>,
    );
    const overview = screen.getByRole("link", { name: /overview|огляд|обзор/i });
    expect(overview).toHaveAttribute("aria-current", "page");
  });

  it("shows project section disabled when no project active", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<Sidebar />} />
        </Routes>
      </MemoryRouter>,
    );
    // Per-project nav links are present but render as disabled (data-disabled).
    const pages = screen.queryByText(/pages|сторінки|страницы/i);
    expect(pages).toBeInTheDocument();
  });

  it("activates project links when on /project/:name", () => {
    render(
      <MemoryRouter initialEntries={["/project/alpha/pages"]}>
        <Routes>
          <Route path="/project/:name/*" element={<Sidebar />} />
        </Routes>
      </MemoryRouter>,
    );
    const pages = screen.getByRole("link", { name: /pages|сторінки|страницы/i });
    expect(pages).toHaveAttribute("aria-current", "page");
  });
});
```

- [ ] **Step 2: Implement**

Write `frontend/src/components/layout/Sidebar.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { NavLink, useParams } from "react-router";
import { cn } from "@/lib/utils";

interface NavItem {
  to: (project?: string) => string;
  label: string;
  icon: string;
  requiresProject: boolean;
}

const PROJECT_ITEMS: NavItem[] = [
  { to: (p) => `/project/${p}/pages`, label: "navigation.pages", icon: "📚", requiresProject: true },
  { to: (p) => `/project/${p}/sessions`, label: "navigation.sessions", icon: "💬", requiresProject: true },
  { to: (p) => `/project/${p}`, label: "navigation.queue", icon: "🌊", requiresProject: true },
  { to: (p) => `/project/${p}/activity`, label: "navigation.activity", icon: "📜", requiresProject: true },
  { to: (p) => `/project/${p}/suggestions`, label: "navigation.suggestions", icon: "💡", requiresProject: true },
  { to: () => "/lost-sessions", label: "navigation.lost_sessions", icon: "🔍", requiresProject: false },
  { to: (p) => `/project/${p}/trash`, label: "navigation.trash", icon: "🗑️", requiresProject: true },
  { to: (p) => `/project/${p}/snapshots`, label: "navigation.snapshots", icon: "💾", requiresProject: true },
  { to: (p) => `/project/${p}/health`, label: "navigation.health", icon: "🩺", requiresProject: true },
  { to: (p) => `/project/${p}/settings`, label: "navigation.settings", icon: "⚙", requiresProject: true },
];

const GLOBAL_ITEMS: NavItem[] = [
  { to: () => "/metrics", label: "navigation.metrics", icon: "📈", requiresProject: false },
  { to: () => "/help", label: "navigation.help", icon: "📖", requiresProject: false },
];

interface SidebarLinkProps {
  to: string;
  icon: string;
  label: string;
  disabled?: boolean;
}

function SidebarLink({ to, icon, label, disabled }: SidebarLinkProps) {
  if (disabled) {
    return (
      <span
        data-disabled
        className="flex cursor-not-allowed items-center gap-2 rounded-md px-3 py-1.5 text-sm text-[hsl(var(--muted-foreground))] opacity-60"
      >
        <span className="w-5 text-center">{icon}</span>
        <span>{label}</span>
      </span>
    );
  }
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
          isActive
            ? "bg-[hsl(var(--primary))]/10 font-medium text-[hsl(var(--primary))]"
            : "text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]",
        )
      }
    >
      <span className="w-5 text-center">{icon}</span>
      <span>{label}</span>
    </NavLink>
  );
}

export function Sidebar() {
  const { t } = useTranslation();
  const { name } = useParams<{ name: string }>();
  const hasProject = Boolean(name);

  return (
    <nav
      aria-label="primary"
      className="flex flex-col gap-1 border-r bg-[hsl(var(--muted))] p-3"
    >
      <SidebarLink to="/" icon="📊" label={t("navigation.overview")} />

      <div className="my-2 border-t" />

      {PROJECT_ITEMS.map((item) => (
        <SidebarLink
          key={item.label}
          to={item.requiresProject && name ? item.to(name) : item.to()}
          icon={item.icon}
          label={t(item.label)}
          disabled={item.requiresProject && !hasProject}
        />
      ))}

      <div className="my-2 border-t" />

      {GLOBAL_ITEMS.map((item) => (
        <SidebarLink
          key={item.label}
          to={item.to()}
          icon={item.icon}
          label={t(item.label)}
        />
      ))}
    </nav>
  );
}
```

- [ ] **Step 3: Wire into Layout**

Edit `frontend/src/components/layout/Layout.tsx`:

```tsx
import { Outlet } from "react-router";
import { TopBar } from "./TopBar";
import { Sidebar } from "./Sidebar";

export function Layout() {
  return (
    <div className="grid h-screen grid-rows-[auto_1fr] overflow-hidden">
      <TopBar />
      <div className="grid grid-cols-[16rem_1fr] overflow-hidden">
        <Sidebar />
        <main className="overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run + verify**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Sidebar with 11 nav links + active state + project-aware disable"
```

---

## Task 16: HealthBadge widget

**Files:**
- Create: `frontend/src/components/widgets/HealthBadge.tsx`, `frontend/src/__tests__/HealthBadge.test.tsx`

- [ ] **Step 1: Test**

Write `frontend/src/__tests__/HealthBadge.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { HealthBadge } from "../components/widgets/HealthBadge";

describe("HealthBadge", () => {
  it("renders green when watchdog up and dead-letter clean", () => {
    render(
      <HealthBadge
        vault_health={{
          watchdog_running: true,
          jobs_queued: 0,
          jobs_running: 0,
          jobs_dead_letter: 0,
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveAttribute("data-level", "ok");
  });

  it("renders yellow when watchdog down", () => {
    render(
      <HealthBadge
        vault_health={{
          watchdog_running: false,
          jobs_queued: 0,
          jobs_running: 0,
          jobs_dead_letter: 0,
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveAttribute("data-level", "warn");
  });

  it("renders red when watchdog down AND dead-letter overflow", () => {
    render(
      <HealthBadge
        vault_health={{
          watchdog_running: false,
          jobs_queued: 0,
          jobs_running: 0,
          jobs_dead_letter: 11,
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveAttribute("data-level", "danger");
  });

  it("renders 'down' when no health data", () => {
    render(<HealthBadge vault_health={undefined} />);
    expect(screen.getByRole("status")).toHaveAttribute("data-level", "down");
  });
});
```

- [ ] **Step 2: Implement**

Write `frontend/src/components/widgets/HealthBadge.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { type VaultHealth } from "@/types/Health";
import { cn } from "@/lib/utils";

type Level = "ok" | "warn" | "danger" | "down";

function levelOf(vh: VaultHealth | undefined): Level {
  if (!vh) return "down";
  const watchdog = vh.watchdog_running;
  const dlQ = vh.jobs_dead_letter > 10;
  if (!watchdog && dlQ) return "danger";
  if (!watchdog || dlQ) return "warn";
  return "ok";
}

const STYLES: Record<Level, { dot: string; text: string }> = {
  ok: {
    dot: "bg-emerald-500",
    text: "text-emerald-700 dark:text-emerald-400",
  },
  warn: {
    dot: "bg-amber-500",
    text: "text-amber-700 dark:text-amber-400",
  },
  danger: {
    dot: "bg-red-500",
    text: "text-red-700 dark:text-red-400",
  },
  down: {
    dot: "bg-zinc-400",
    text: "text-zinc-600 dark:text-zinc-400",
  },
};

interface Props {
  vault_health: VaultHealth | undefined;
}

export function HealthBadge({ vault_health }: Props) {
  const { t } = useTranslation();
  const level = levelOf(vault_health);
  const styles = STYLES[level];
  const labelKey = level === "ok" ? "health.ok"
    : level === "warn" ? "health.degraded"
    : level === "danger" ? "health.degraded"
    : "health.down";
  return (
    <span
      role="status"
      data-level={level}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium",
        styles.text,
      )}
    >
      <span className={cn("h-2 w-2 rounded-full", styles.dot)} />
      <span>{t(labelKey)}</span>
    </span>
  );
}
```

- [ ] **Step 3: Run + verify**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): HealthBadge widget (ok/warn/danger/down)"
```

---

## Task 17: ProjectCard + Overview page

**Files:**
- Create: `frontend/src/components/widgets/ProjectCard.tsx`, `frontend/src/components/widgets/DaemonDownAlert.tsx`, `frontend/src/components/widgets/NoProjectsCallout.tsx`, `frontend/src/__tests__/Overview.test.tsx`
- Modify: `frontend/src/pages/Overview.tsx`

- [ ] **Step 1: ProjectCard**

Write `frontend/src/components/widgets/ProjectCard.tsx`:

```tsx
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { type ProjectMapEntry } from "@/types/Project";
import { type VaultHealth } from "@/types/Health";
import { HealthBadge } from "./HealthBadge";

interface Props {
  project: ProjectMapEntry;
  vault_health: VaultHealth | undefined;
  usage:
    | { tokens_injected?: number; sessions_covered?: number; avg_compression_ratio?: number }
    | undefined;
}

function formatNum(n: number | undefined): string {
  if (n === undefined) return "—";
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}K`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

export function ProjectCard({ project, vault_health, usage }: Props) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <CardTitle className="truncate text-base font-semibold">
          {project.name}
        </CardTitle>
        <HealthBadge vault_health={vault_health} />
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className="truncate text-xs text-[hsl(var(--muted-foreground))]"
          title={project.vault_root}
        >
          {project.vault_root}
        </div>

        <div className="grid grid-cols-3 gap-2 text-center">
          <Stat label={t("project_view.stats.sessions_covered")} value={formatNum(usage?.sessions_covered)} />
          <Stat label={t("project_view.stats.jobs_queued")} value={formatNum(vault_health?.jobs_queued)} />
          <Stat label={t("project_view.stats.jobs_dead_letter")} value={formatNum(vault_health?.jobs_dead_letter)} />
        </div>

        <div className="flex justify-end">
          <Button asChild size="sm" variant="outline">
            <Link to={`/project/${project.name}`}>{t("common.open")}</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-0.5">
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
        {label}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: DaemonDownAlert + NoProjectsCallout**

Write `frontend/src/components/widgets/DaemonDownAlert.tsx`:

```tsx
import { useTranslation } from "react-i18next";

export function DaemonDownAlert({ error }: { error: unknown }) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-2xl rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-900 dark:bg-red-950">
      <h2 className="mb-2 text-lg font-semibold text-red-700 dark:text-red-300">
        ⚠ {t("overview.daemon_down_title")}
      </h2>
      <p className="mb-2 text-sm">{t("overview.daemon_down_hint_cmd")}</p>
      <pre className="mb-2 rounded bg-[hsl(var(--muted))] p-2 text-xs">
        {t("overview.daemon_down_hint_command")}
      </pre>
      <p className="text-sm text-[hsl(var(--muted-foreground))]">
        {t("overview.daemon_down_reconnect")}
      </p>
      {error instanceof Error && (
        <p className="mt-2 text-xs text-[hsl(var(--muted-foreground))]">
          {error.message}
        </p>
      )}
    </div>
  );
}
```

Write `frontend/src/components/widgets/NoProjectsCallout.tsx`:

```tsx
import { useTranslation } from "react-i18next";

export function NoProjectsCallout() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-2xl rounded-lg border bg-[hsl(var(--muted))] p-6 text-center">
      <h2 className="mb-3 text-lg font-semibold">
        🧠 {t("overview.no_projects_title")}
      </h2>
      <p className="mb-2 text-sm">{t("overview.no_projects_hint_cmd")}</p>
      <pre className="rounded bg-[hsl(var(--background))] p-2 text-xs">
        {t("overview.no_projects_hint_command")}
      </pre>
    </div>
  );
}
```

- [ ] **Step 3: Overview page**

Edit `frontend/src/pages/Overview.tsx`:

```tsx
import { useProjects } from "@/hooks/useProjects";
import { useHealth } from "@/hooks/useHealth";
import { useUsageByProject } from "@/hooks/useUsageByProject";
import { ProjectCard } from "@/components/widgets/ProjectCard";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { NoProjectsCallout } from "@/components/widgets/NoProjectsCallout";
import { Skeleton } from "@/components/ui/skeleton";

export function Overview() {
  const projectsQuery = useProjects();
  const healthQuery = useHealth();
  const usageQuery = useUsageByProject("30d");

  if (projectsQuery.isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-48 w-full" />
        ))}
      </div>
    );
  }

  if (projectsQuery.isError) {
    return <DaemonDownAlert error={projectsQuery.error} />;
  }

  const projects = projectsQuery.data ?? [];
  if (projects.length === 0) {
    return <NoProjectsCallout />;
  }

  const usageByName = new Map(
    (usageQuery.data ?? []).map((u) => [u.project as string, u]),
  );

  return (
    <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
      {projects.map((p) => (
        <ProjectCard
          key={p.name}
          project={p}
          vault_health={healthQuery.data?.vaults?.[p.name]}
          usage={usageByName.get(p.name) as
            | { sessions_covered?: number; avg_compression_ratio?: number }
            | undefined}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Test**

Write `frontend/src/__tests__/Overview.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { Overview } from "../pages/Overview";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("Overview", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders skeleton while loading", () => {
    vi.spyOn(apiClient, "get").mockImplementation(() => new Promise(() => {}));
    render(wrap(<Overview />));
    // Skeleton has no semantic role; check at least a placeholder is present.
    expect(screen.queryByRole("link", { name: /open/i })).not.toBeInTheDocument();
  });

  it("renders DaemonDownAlert on /projects failure", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("ECONNREFUSED"));
    render(wrap(<Overview />));
    await waitFor(() =>
      expect(screen.getByText(/daemon|демон/i)).toBeInTheDocument(),
    );
  });

  it("renders NoProjectsCallout when project list empty", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/projects") return { data: [] };
      if (url === "/health")
        return {
          data: {
            status: "ok",
            version: "0.1",
            uptime_s: 0,
            alerts_count: 0,
            vaults: {},
            jobs_alert: false,
            scheduler_jobs: [],
          },
        };
      return { data: { projects: [] } };
    });
    render(wrap(<Overview />));
    await waitFor(() =>
      expect(screen.getByText(/no_projects|brain|мозок|мозг/i)).toBeInTheDocument(),
    );
  });

  it("renders project cards when list is populated", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/projects")
        return {
          data: [{ name: "alpha", vault_root: "/a", cwd_patterns: [] }],
        };
      if (url === "/health")
        return {
          data: {
            status: "ok",
            version: "0.1",
            uptime_s: 0,
            alerts_count: 0,
            vaults: {
              alpha: {
                watchdog_running: true,
                jobs_queued: 0,
                jobs_running: 0,
                jobs_dead_letter: 0,
              },
            },
            jobs_alert: false,
            scheduler_jobs: [],
          },
        };
      return { data: { projects: [] } };
    });
    render(wrap(<Overview />));
    await waitFor(() =>
      expect(screen.getByText("alpha")).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 5: Run + verify**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Overview page with project cards + loading/error/empty states"
```

---

## Task 18: ProjectView shell

**Files:**
- Create: `frontend/src/components/widgets/UnknownProject.tsx`, `frontend/src/__tests__/ProjectView.test.tsx`
- Modify: `frontend/src/pages/ProjectView.tsx`

- [ ] **Step 1: UnknownProject component**

Write `frontend/src/components/widgets/UnknownProject.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

export function UnknownProject({ name }: { name: string }) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-xl space-y-3 py-12 text-center">
      <h1 className="text-2xl font-semibold">
        {t("project_view.unknown_title")}
      </h1>
      <p className="text-[hsl(var(--muted-foreground))]">
        <code className="rounded bg-[hsl(var(--muted))] px-1.5">{name}</code>
        {" — "}
        {t("project_view.unknown_hint")}
      </p>
      <Link to="/" className="text-[hsl(var(--primary))] underline">
        {t("placeholder.back_link")}
      </Link>
    </div>
  );
}
```

- [ ] **Step 2: ProjectView**

Write `frontend/src/pages/ProjectView.tsx`:

```tsx
import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { ExternalLink } from "lucide-react";
import { useProjects } from "@/hooks/useProjects";
import { useHealth } from "@/hooks/useHealth";
import { useUsageByProject } from "@/hooks/useUsageByProject";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { HealthBadge } from "@/components/widgets/HealthBadge";
import { UnknownProject } from "@/components/widgets/UnknownProject";

const TILES: Array<{ key: string; emoji: string; path: string; plan: string }> = [
  { key: "navigation.pages",        emoji: "📚", path: "pages",        plan: "#14b" },
  { key: "navigation.sessions",     emoji: "💬", path: "sessions",     plan: "#14b" },
  { key: "navigation.activity",     emoji: "📜", path: "activity",     plan: "#14b" },
  { key: "navigation.suggestions",  emoji: "💡", path: "suggestions",  plan: "#14b" },
  { key: "navigation.trash",        emoji: "🗑️", path: "trash",        plan: "#14b" },
  { key: "navigation.snapshots",    emoji: "💾", path: "snapshots",    plan: "#14b" },
  { key: "navigation.health",       emoji: "🩺", path: "health",       plan: "#14b" },
  { key: "navigation.settings",     emoji: "⚙",  path: "settings",     plan: "#14c" },
];

export function ProjectView() {
  const { name } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const { data: projects, isLoading } = useProjects();
  const { data: health } = useHealth();
  const { data: usage } = useUsageByProject("30d");

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  const project = projects?.find((p) => p.name === name);
  if (!project) return <UnknownProject name={name ?? ""} />;
  const vh = health?.vaults?.[name!];
  const u = usage?.find((x) => (x.project as string) === name);

  const obsidianUrl = `obsidian://open?vault=${encodeURIComponent(project.vault_root)}`;

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold">{project.name}</h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            {project.vault_root}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <HealthBadge vault_health={vh} />
          <Button variant="outline" size="sm" asChild>
            <a href={obsidianUrl}>
              {t("project_view.open_in_obsidian")}
              <ExternalLink className="ml-1 h-3 w-3" />
            </a>
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label={t("project_view.stats.sessions_covered")}
          value={(u?.sessions_covered as number | undefined) ?? "—"}
        />
        <StatCard
          label={t("project_view.stats.jobs_queued")}
          value={vh?.jobs_queued ?? "—"}
        />
        <StatCard
          label={t("project_view.stats.jobs_running")}
          value={vh?.jobs_running ?? "—"}
        />
        <StatCard
          label={t("project_view.stats.jobs_dead_letter")}
          value={vh?.jobs_dead_letter ?? "—"}
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {TILES.map((tile) => (
          <Card key={tile.path} className="transition-colors hover:bg-[hsl(var(--muted))]">
            <Link to={`/project/${name}/${tile.path}`}>
              <CardHeader>
                <CardTitle className="text-base">
                  {tile.emoji} {t(tile.key)}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-[hsl(var(--muted-foreground))]">
                  {t("project_view.coming_in", { plan: tile.plan })}
                </div>
              </CardContent>
            </Link>
          </Card>
        ))}
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <Card>
      <CardContent className="space-y-1 py-3">
        <div className="text-2xl font-semibold">{value}</div>
        <div className="text-xs uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
          {label}
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: Test**

Write `frontend/src/__tests__/ProjectView.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { ProjectView } from "../pages/ProjectView";

function wrap(ui: React.ReactNode, path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/project/:name" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const FAKE_PROJECTS_RESP = {
  data: [{ name: "alpha", vault_root: "D:/v/alpha", cwd_patterns: [] }],
};
const FAKE_HEALTH_RESP = {
  data: {
    status: "ok",
    version: "0.1",
    uptime_s: 0,
    alerts_count: 0,
    vaults: {
      alpha: {
        watchdog_running: true,
        jobs_queued: 1,
        jobs_running: 0,
        jobs_dead_letter: 0,
      },
    },
    jobs_alert: false,
    scheduler_jobs: [],
  },
};

describe("ProjectView", () => {
  it("renders header + stats + tiles for known project", async () => {
    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      if (url === "/projects") return FAKE_PROJECTS_RESP;
      if (url === "/health") return FAKE_HEALTH_RESP;
      return { data: { projects: [] } };
    });
    render(wrap(<ProjectView />, "/project/alpha"));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "alpha" })).toBeInTheDocument(),
    );
    // Vault path visible
    expect(screen.getByText(/D:\/v\/alpha/)).toBeInTheDocument();
    // 8 navigation tiles
    expect(
      screen.getAllByRole("link").filter((l) =>
        l.getAttribute("href")?.startsWith("/project/alpha/"),
      ),
    ).toHaveLength(8);
  });

  it("renders UnknownProject when name is not in /projects", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: [] });
    render(wrap(<ProjectView />, "/project/ghost"));
    await waitFor(() =>
      expect(screen.getByText(/unknown_title|not found|не найден|не знайдено/i))
        .toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 4: Run + verify**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): ProjectView shell with stats grid + 8 navigation tiles"
```

---

## Task 19: Build + serve smoke test

**Files:** none new — verifies the integration works end-to-end.

- [ ] **Step 1: Build the frontend**

```bash
cd /d/code/claude-mnemos/frontend
pnpm build
```

Expected output: dist successfully written to `../claude_mnemos/daemon/static/`. Check:

```bash
ls /d/code/claude-mnemos/claude_mnemos/daemon/static/
# Should contain: index.html, assets/, favicon.svg, locales/
```

- [ ] **Step 2: Run the daemon and curl /**

In one terminal:

```bash
cd /d/code/claude-mnemos
mnemos daemon start
```

In another:

```bash
curl -s http://127.0.0.1:5757/ | head -20
```

Expected: `<!doctype html>...` containing the React mount-point. Stop daemon: `mnemos daemon stop`.

- [ ] **Step 3: Run all backend tests once more**

```bash
python -m pytest -q --ignore=tests/daemon/integration -k "not slow" 2>&1 | tail -10
ruff check claude_mnemos
mypy --strict claude_mnemos
```

All clean.

- [ ] **Step 4: Run all frontend tests once more**

```bash
cd frontend
pnpm test
pnpm lint
pnpm typecheck
```

All clean.

- [ ] **Step 5: Manual smoke (browser)**

```bash
mnemos daemon start --all
```

Open `http://127.0.0.1:5757/` in a browser. Verify:
- Brand "claude-mnemos" visible in TopBar.
- ProjectSwitcher dropdown lists registered projects.
- UsageWidget shows tokens / sessions / ratio (or "no data" callout).
- Locale switch works (UK→RU→EN→UK).
- Sidebar lists 11 entries; per-project items disabled until a project is selected.
- Click a project → ProjectView shell with stats and tiles.
- Stop daemon: dashboard shows DaemonDownAlert. Restart daemon: page recovers on next poll.

If everything checks out, this task is done — no commit needed (verification only).

- [ ] **Step 6: Optional commit (lockfile / minor follow-ups)**

If `pnpm build` produced a `pnpm-lock.yaml` change (unlikely), or any small cleanup is needed, commit that:

```bash
git add frontend/pnpm-lock.yaml claude_mnemos/daemon/static/.gitignore
git commit -m "chore(frontend): final build smoke + lockfile sync"
```

---

## Task 20: Final verification

- [ ] **Step 1: Hard-cuts grep**

```bash
cd /d/code/claude-mnemos
grep -rn "TODO" frontend/src 2>&1 | head -10  # Any leftover TODOs in source? Investigate each.
grep -rn "TBD\|FIXME" frontend/src 2>&1 | head -10
```

If any results — review and either resolve or document why they're acceptable for #14a.

- [ ] **Step 2: Acceptance criteria walk-through (design §6)**

For each AC #1–#15 from `docs/plans/2026-04-29-14a-frontend-foundation-design.md`, verify and note:
1. ✅ `frontend/` directory exists with full scaffold.
2. ✅ `pnpm build` succeeds.
3. ✅ `claude_mnemos/daemon/app.py` mounts static; tested.
4. ✅ Daemon serves index.html on `/` after build.
5. ✅ Browser shows TopBar/Sidebar/Overview.
6. ✅ Cards display real data.
7. ✅ Locale cycle works.
8. ✅ DaemonDownAlert on failure.
9. ✅ NoProjectsCallout on empty map.
10. ✅ ProjectView shell with stats + 8 tiles.
11. ✅ Unknown project → friendly page.
12. ✅ Vitest suite green.
13. ✅ Static-mount Python tests green.
14. ✅ ruff + mypy clean.
15. ✅ ESLint clean.

- [ ] **Step 3: Branch summary**

```bash
git log --oneline main..HEAD
git status
```

Working tree clean; commit count ~20.

---

## Spec coverage map

| Design §   | Plan task(s) |
|------------|--------------|
| 1.x background/goals | All tasks |
| 2.1 layout | Task 1 |
| 2.2 build flow | Tasks 1, 19 |
| 2.3 FastAPI mount | Task 6 |
| 2.4 stack pinning | Tasks 1–9 (deps installed across tasks) |
| 2.5 routing | Task 11 |
| 2.6 API client | Task 7 |
| 2.7 layout components | Tasks 10, 12, 13, 14, 15 |
| 2.8 Overview | Task 17 |
| 2.9 ProjectView shell | Task 18 |
| 2.10 i18n | Task 5 |
| 2.11 notifications | Task 9 (store), wired in #14c (deferred) |
| 2.12 tests | Tasks 4, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18 |
| 3 backend changes | Task 6 |
| 4 vite proxy | Task 1 |
| 5 risks | n/a operational |
| 6 acceptance criteria | Task 19 step 5, Task 20 step 2 |
| 7 open questions | n/a (decisions baked in) |
| 8 out of scope | n/a (deferred to #14b/#14c/#14d) |

No uncovered spec requirements.
