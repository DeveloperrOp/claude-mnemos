import { useTranslation } from "react-i18next";
import { useEffect } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/stores/ui.store";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { ThemeToggle } from "./ThemeToggle";
import { UsageWidget } from "@/components/widgets/UsageWidget";

const LOCALE_CYCLE = ["uk", "ru", "en"] as const;
type Locale = (typeof LOCALE_CYCLE)[number];

function nextLocale(l: Locale): Locale {
  const i = LOCALE_CYCLE.indexOf(l);
  return LOCALE_CYCLE[(i + 1) % LOCALE_CYCLE.length]!;
}

const GLOBAL_LINKS = [
  { to: "/lost-sessions", labelKey: "topbar.global_links.lost_sessions" },
  { to: "/dead-letter", labelKey: "topbar.global_links.failed_jobs" },
  { to: "/metrics", labelKey: "topbar.global_links.metrics" },
  { to: "/help", labelKey: "topbar.global_links.help" },
  { to: "/settings/global", labelKey: "topbar.global_links.global_settings" },
] as const;

export function TopBar() {
  const { t, i18n } = useTranslation();
  const locale = useUIStore((s) => s.locale);
  const setLocale = useUIStore((s) => s.setLocale);

  useEffect(() => {
    if (i18n.language !== locale) void i18n.changeLanguage(locale);
  }, [i18n, locale]);

  return (
    <header className="relative flex items-center justify-between border-b border-border/60 bg-card/40 px-4 py-2.5">
      {/* Lime hairline bottom edge — operational signature */}
      <span className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-accent/40 to-transparent" />

      <div className="flex items-center gap-4">
        <Link
          to="/"
          className="group flex items-baseline gap-1.5 font-mono text-sm font-medium uppercase tracking-[0.16em]"
        >
          <span className="text-foreground transition-colors group-hover:text-accent">
            claude
          </span>
          <span className="text-accent">/</span>
          <span className="text-muted-foreground transition-colors group-hover:text-foreground">
            mnemos
          </span>
        </Link>
        <span className="h-4 w-px bg-border" />
        <ProjectSwitcher />
      </div>

      <nav className="flex items-center gap-1" aria-label="global">
        {GLOBAL_LINKS.map((link) => (
          <Link
            key={link.to}
            to={link.to}
            className="rounded-md px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground transition-colors hover:bg-card/60 hover:text-foreground"
          >
            {t(link.labelKey)}
          </Link>
        ))}
      </nav>

      <div className="flex items-center gap-3">
        <UsageWidget />
        <span className="h-4 w-px bg-border" />
        <ThemeToggle />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setLocale(nextLocale(locale))}
          className="h-7 px-2 font-mono text-[10px] tracking-[0.14em]"
        >
          {locale.toUpperCase()}
        </Button>
      </div>
    </header>
  );
}
