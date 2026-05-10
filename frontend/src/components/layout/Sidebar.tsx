import { useTranslation } from "react-i18next";
import { NavLink, useParams } from "react-router";
import { cn } from "@/lib/utils";

interface NavItem {
  to: (project: string) => string;
  label: string;
  icon: string;
}

// All project-scoped. Global navigation lives in TopBar (Task 1 of v0.0.13).
const PROJECT_ITEMS: NavItem[] = [
  { to: (p) => `/project/${p}`,             label: "navigation.project_overview", icon: "📊" },
  { to: (p) => `/project/${p}/pages`,       label: "navigation.pages",            icon: "📚" },
  { to: (p) => `/project/${p}/sessions`,    label: "navigation.sessions",         icon: "💬" },
  { to: (p) => `/project/${p}/queue`,       label: "navigation.queue",            icon: "🌊" },
  { to: (p) => `/project/${p}/activity`,    label: "navigation.activity",         icon: "📜" },
  { to: (p) => `/project/${p}/suggestions`, label: "navigation.suggestions",      icon: "💡" },
  { to: (p) => `/project/${p}/trash`,       label: "navigation.trash",            icon: "🗑️" },
  { to: (p) => `/project/${p}/snapshots`,   label: "navigation.snapshots",        icon: "💾" },
  { to: (p) => `/project/${p}/health`,      label: "navigation.health",           icon: "🩺" },
  { to: (p) => `/project/${p}/settings`,    label: "navigation.settings",         icon: "⚙" },
];

interface SidebarLinkProps {
  to: string;
  icon: string;
  label: string;
  exact?: boolean;
}

function SidebarLink({ to, icon, label, exact }: SidebarLinkProps) {
  return (
    <NavLink
      to={to}
      end={exact}
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

export function Sidebar() {
  const { t } = useTranslation();
  const { name } = useParams<{ name: string }>();
  if (!name) return null; // Sidebar is project-scoped; without a project we render nothing.

  return (
    <nav
      aria-label="primary"
      className="flex flex-col gap-0.5 border-r border-border/60 bg-card/30 py-2"
    >
      {PROJECT_ITEMS.map((item, i) => (
        <SidebarLink
          key={item.label}
          to={item.to(name)}
          icon={item.icon}
          label={t(item.label)}
          exact={i === 0}
        />
      ))}
    </nav>
  );
}
