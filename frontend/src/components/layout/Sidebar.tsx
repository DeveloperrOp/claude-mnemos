import type { ComponentType, SVGProps } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useParams } from "react-router";
import {
  Activity,
  BookOpen,
  History,
  LayoutDashboard,
  Lightbulb,
  ListOrdered,
  MessageSquare,
  Save,
  Search,
  Settings,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

interface NavItem {
  to: (project: string) => string;
  label: string;
  Icon: IconComponent;
}

// All project-scoped. Global navigation lives in TopBar (Task 1 of v0.0.13).
// Icons: Lucide monochrome SVG — consistent visual weight, OS-independent
// rendering, matches the rest of the app's iconography (was: emoji).
const PROJECT_ITEMS: NavItem[] = [
  { to: (p) => `/project/${p}`,             label: "navigation.project_overview", Icon: LayoutDashboard },
  { to: (p) => `/project/${p}/pages`,       label: "navigation.pages",            Icon: BookOpen },
  { to: (p) => `/project/${p}/sessions`,    label: "navigation.sessions",         Icon: MessageSquare },
  { to: (p) => `/project/${p}/queue`,       label: "navigation.queue",            Icon: ListOrdered },
  { to: (p) => `/project/${p}/activity`,    label: "navigation.activity",         Icon: History },
  { to: (p) => `/project/${p}/suggestions`, label: "navigation.suggestions",      Icon: Lightbulb },
  { to: (p) => `/project/${p}/trash`,       label: "navigation.trash",            Icon: Trash2 },
  { to: (p) => `/project/${p}/snapshots`,   label: "navigation.snapshots",        Icon: Save },
  { to: (p) => `/project/${p}/lint`,        label: "navigation.lint",             Icon: Search },
  { to: (p) => `/project/${p}/health`,      label: "navigation.health",           Icon: Activity },
  { to: (p) => `/project/${p}/settings`,    label: "navigation.settings",         Icon: Settings },
];

interface SidebarLinkProps {
  to: string;
  Icon: IconComponent;
  label: string;
  exact?: boolean;
}

function SidebarLink({ to, Icon, label, exact }: SidebarLinkProps) {
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
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
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
          Icon={item.Icon}
          label={t(item.label)}
          exact={i === 0}
        />
      ))}
    </nav>
  );
}
