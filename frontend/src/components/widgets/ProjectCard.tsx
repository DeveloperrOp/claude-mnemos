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
