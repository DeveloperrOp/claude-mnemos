import { useTranslation } from "react-i18next";
import { NavLink, useParams } from "react-router";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface NavItem {
  to: (project?: string) => string;
  label: string;
  icon: string;
  requiresProject: boolean;
}

const PROJECT_ITEMS: NavItem[] = [
  { to: (p) => `/project/${p}/pages`, label: "navigation.pages", icon: "📚", requiresProject: true },
  { to: (p) => `/project/${p}/sessions`, label: "navigation.sessions", icon: "💬", requiresProject: true },
  { to: (p) => `/project/${p}/queue`, label: "navigation.queue", icon: "🌊", requiresProject: true },
  { to: (p) => `/project/${p}/activity`, label: "navigation.activity", icon: "📜", requiresProject: true },
  { to: (p) => `/project/${p}/suggestions`, label: "navigation.suggestions", icon: "💡", requiresProject: true },
  { to: () => "/lost-sessions", label: "navigation.lost_sessions", icon: "🔍", requiresProject: false },
  { to: (p) => `/project/${p}/trash`, label: "navigation.trash", icon: "🗑️", requiresProject: true },
  { to: (p) => `/project/${p}/snapshots`, label: "navigation.snapshots", icon: "💾", requiresProject: true },
  { to: (p) => `/project/${p}/health`, label: "navigation.health", icon: "🩺", requiresProject: true },
  { to: (p) => `/project/${p}/settings`, label: "navigation.settings", icon: "⚙", requiresProject: true },
];

const GLOBAL_ITEMS: NavItem[] = [
  { to: () => "/dead-letter", label: "navigation.failed_jobs", icon: "⚠", requiresProject: false },
  { to: () => "/metrics", label: "navigation.metrics", icon: "📈", requiresProject: false },
  { to: () => "/help", label: "navigation.help", icon: "📖", requiresProject: false },
  { to: () => "/settings/global", label: "navigation.global_settings", icon: "⚙", requiresProject: false },
];

interface SidebarLinkProps {
  to: string;
  icon: string;
  label: string;
  disabled?: boolean;
}

function SidebarLink({ to, icon, label, disabled }: SidebarLinkProps) {
  const { t } = useTranslation();
  if (disabled) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            data-disabled
            className="flex cursor-not-allowed items-center gap-2.5 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground/50"
          >
            <span className="w-4 text-center text-[13px] grayscale opacity-60">{icon}</span>
            <span>{label}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent side="right">
          {t("navigation.disabled_hint")}
        </TooltipContent>
      </Tooltip>
    );
  }
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        cn(
          "relative flex items-center gap-2.5 px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em] transition-all duration-[var(--motion-fast)]",
          isActive
            ? "text-foreground bg-accent/5 before:absolute before:left-0 before:top-1 before:bottom-1 before:w-[2px] before:bg-accent"
            : "text-muted-foreground hover:text-foreground hover:bg-card/60",
        )
      }
    >
      <span className="w-4 text-center text-[13px]">{icon}</span>
      <span>{label}</span>
    </NavLink>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 pt-3 pb-1 font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground/60">
      {children}
    </div>
  );
}

export function Sidebar() {
  const { t } = useTranslation();
  const { name } = useParams<{ name: string }>();
  const hasProject = Boolean(name);

  return (
    <nav
      aria-label="primary"
      className="flex flex-col gap-0.5 border-r border-border/60 bg-card/30 py-2"
    >
      <SidebarLink to="/" icon="📊" label={t("navigation.overview")} />

      <SectionLabel>{t("navigation.section_project", "Project")}</SectionLabel>

      {PROJECT_ITEMS.map((item) => (
        <SidebarLink
          key={item.label}
          to={item.requiresProject && name ? item.to(name) : item.to()}
          icon={item.icon}
          label={t(item.label)}
          disabled={item.requiresProject && !hasProject}
        />
      ))}

      <SectionLabel>{t("navigation.section_global", "Global")}</SectionLabel>

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
