import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { MessageSquare, BookOpen, ScrollText, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { type ProjectMapEntry } from "@/types/Project";
import { type VaultHealth } from "@/types/Health";
import { getProjectDisplayName } from "@/lib/projectDisplayName";
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
    <Link
      to={`/project/${project.name}`}
      className="group relative block overflow-hidden rounded-md border border-border/60 bg-card/40 p-4 transition-all hover:border-accent/60 hover:bg-card/70"
    >
      {/* Lime hairline left edge — appears on hover */}
      <span className="pointer-events-none absolute inset-y-0 left-0 w-[2px] bg-accent opacity-0 transition-opacity group-hover:opacity-100" />

      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="eyebrow mb-1">{project.name}</div>
          <h3 className="truncate font-mono text-base font-medium tracking-tight text-foreground">
            {getProjectDisplayName(project)}
          </h3>
        </div>
        <HealthBadge vault_health={vault_health} />
      </div>

      <div
        className="mt-2 truncate font-mono text-[11px] text-muted-foreground"
        title={project.vault_root}
      >
        {project.vault_root}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3">
        <Stat
          label={t("project_view.stats.sessions_covered")}
          value={formatNum(usage?.sessions_covered)}
          hint={t("project_view.stats.sessions_covered_hint")}
        />
        <Stat
          label={t("project_view.stats.jobs_queued")}
          value={formatNum(vault_health?.jobs_queued)}
          hint={t("project_view.stats.jobs_queued_hint")}
        />
        <Stat
          label={t("project_view.stats.jobs_dead_letter")}
          value={formatNum(vault_health?.jobs_dead_letter)}
          hint={t("project_view.stats.jobs_dead_letter_hint")}
          accent={vault_health?.jobs_dead_letter ? "danger" : undefined}
        />
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-border/40 pt-3">
        <div className="flex gap-0.5" onClick={(e) => e.stopPropagation()}>
          <Button asChild size="icon" variant="ghost" title={t("navigation.sessions")} className="h-7 w-7">
            <Link to={`/project/${project.name}/sessions`} aria-label={t("navigation.sessions")}>
              <MessageSquare className="h-3.5 w-3.5" />
            </Link>
          </Button>
          <Button asChild size="icon" variant="ghost" title={t("navigation.pages")} className="h-7 w-7">
            <Link to={`/project/${project.name}/pages`} aria-label={t("navigation.pages")}>
              <BookOpen className="h-3.5 w-3.5" />
            </Link>
          </Button>
          <Button asChild size="icon" variant="ghost" title={t("navigation.activity")} className="h-7 w-7">
            <Link to={`/project/${project.name}/activity`} aria-label={t("navigation.activity")}>
              <ScrollText className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
        <span className="flex items-center gap-1 font-mono text-[11px] uppercase tracking-wider text-muted-foreground transition-colors group-hover:text-accent">
          {t("common.open")}
          <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
        </span>
      </div>
    </Link>
  );
}

function Stat({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: "danger";
}) {
  const valueClass =
    accent === "danger" && value !== "—" && value !== "0"
      ? "text-destructive"
      : "text-foreground";
  const inner = (
    <div className="space-y-0.5">
      <div className={`hero-num text-2xl ${valueClass}`}>{value}</div>
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </div>
    </div>
  );
  if (!hint) return inner;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" className="cursor-help text-left" onClick={(e) => e.preventDefault()}>
          {inner}
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{hint}</TooltipContent>
    </Tooltip>
  );
}
