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
