import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
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
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <CardTitle className="truncate text-base font-semibold">
          {getProjectDisplayName(project)}
        </CardTitle>
        <HealthBadge vault_health={vault_health} />
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className="truncate text-xs text-muted-foreground"
          title={project.vault_root}
        >
          {project.vault_root}
        </div>

        <div className="grid grid-cols-3 gap-2 text-center">
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
          />
        </div>

        <div className="flex justify-end">
          <Button asChild size="sm">
            <Link to={`/project/${project.name}`}>{t("common.open")}</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  const inner = (
    <div className="space-y-0.5">
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
    </div>
  );
  if (!hint) return inner;
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button type="button" className="cursor-help text-left">
            {inner}
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">{hint}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
