import { useTranslation } from "react-i18next";
import { useEffect } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/stores/ui.store";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { UsageWidget } from "@/components/widgets/UsageWidget";

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
    <header className="flex items-center justify-between border-b bg-background px-4 py-2">
      <div className="flex items-center gap-3">
        <Link
          to="/"
          className="font-mono text-base font-semibold uppercase tracking-widest text-foreground hover:text-primary transition-colors duration-[var(--motion-fast)]"
        >
          claude-mnemos
        </Link>
        <ProjectSwitcher />
      </div>
      <div className="flex items-center gap-4">
        <UsageWidget />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setLocale(nextLocale(locale))}
        >
          {locale.toUpperCase()}
        </Button>
        {/* Slot reserved for ThemeToggle (Phase 5) */}
      </div>
    </header>
  );
}
