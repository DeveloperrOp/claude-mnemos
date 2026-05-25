import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
  const { t } = useTranslation();
  const locale = useUIStore((s) => s.locale);
  const setLocale = useUIStore((s) => s.setLocale);

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

      {/* Wide screens: inline link row. */}
      <nav className="hidden xl:flex items-center gap-1" aria-label="global">
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

      {/* Narrow screens: collapse into a Menu dropdown so the 5 ru/uk-long
          link labels don't wrap to two rows and break the TopBar layout. */}
      <div className="xl:hidden">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2"
              aria-label={t("topbar.global_menu_label", "Global menu")}
            >
              <Menu className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {GLOBAL_LINKS.map((link) => (
              <DropdownMenuItem key={link.to} asChild>
                <Link to={link.to} className="cursor-pointer font-mono text-xs uppercase tracking-[0.12em]">
                  {t(link.labelKey)}
                </Link>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

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
