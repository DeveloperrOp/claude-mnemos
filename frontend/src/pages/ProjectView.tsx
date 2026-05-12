import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { ExternalLink } from "lucide-react";
import { useProjects } from "@/hooks/useProjects";
import { useHealth } from "@/hooks/useHealth";
import { useUsageByProject } from "@/hooks/useUsageByProject";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { HealthBadge } from "@/components/widgets/HealthBadge";
import { InjectPreview } from "@/components/widgets/InjectPreview";
import { UnknownProject } from "@/components/widgets/UnknownProject";
import { getProjectDisplayName } from "@/lib/projectDisplayName";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

export function ProjectView() {
  const { name } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const projectsQuery = useProjects();
  const { data: health } = useHealth();
  const { data: usage } = useUsageByProject("30d");

  if (projectsQuery.isLoading) return <Skeleton className="h-64 w-full" />;
  if (projectsQuery.isError) return <DaemonDownAlert error={projectsQuery.error} />;
  const project = projectsQuery.data?.find((p) => p.name === name);
  if (!project) return <UnknownProject name={name ?? ""} />;
  const vh = health?.vaults?.[name!];
  const u = usage?.find((x) => (x.project as string) === name);

  const obsidianUrl = `obsidian://open?vault=${encodeURIComponent(project.vault_root)}`;

  return (
    <div className="space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="project" />
          <div className="flex items-center gap-2">
            <HealthBadge vault_health={vh} />
          </div>
        </div>
        <div className="relative mt-3 flex items-end justify-between gap-3">
          <div>
            <h1 className="font-mono text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
              {getProjectDisplayName(project)}
            </h1>
            <p className="mt-1 font-mono text-[10px] text-muted-foreground">
              {project.vault_root}
            </p>
          </div>
          <Button variant="outline" size="sm" asChild className="shrink-0">
            <a href={obsidianUrl}>
              {t("project_view.open_in_obsidian")}
              <ExternalLink className="ml-1 h-3 w-3" />
            </a>
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label={t("project_view.stats.sessions_covered")}
          value={(u?.sessions_covered as number | undefined) ?? "—"}
        />
        <StatCard
          label={t("project_view.stats.jobs_queued")}
          value={vh?.jobs_queued ?? "—"}
        />
        <StatCard
          label={t("project_view.stats.jobs_running")}
          value={vh?.jobs_running ?? "—"}
        />
        <StatCard
          label={t("project_view.stats.jobs_dead_letter")}
          value={vh?.jobs_dead_letter ?? "—"}
        />
      </div>

      <InjectPreview project={name!} />
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <Card className="border-border/60 bg-card/40 hover:bg-card/60 transition-colors">
      <CardContent className="space-y-2 py-3">
        <div className="hero-num text-3xl">
          {value}
        </div>
        <div className="eyebrow text-[10px]">
          {label}
        </div>
      </CardContent>
    </Card>
  );
}
