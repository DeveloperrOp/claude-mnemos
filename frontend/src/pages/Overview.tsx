import { useTranslation } from "react-i18next";
import { useProjects } from "@/hooks/useProjects";
import { useHealth } from "@/hooks/useHealth";
import { useUsageByProject } from "@/hooks/useUsageByProject";
import { ProjectCard } from "@/components/widgets/ProjectCard";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { HookStatusBanner } from "@/components/widgets/HookStatusBanner";
import { NoProjectsCallout } from "@/components/widgets/NoProjectsCallout";
import { Skeleton } from "@/components/ui/skeleton";

export function Overview() {
  const { t } = useTranslation();
  const projectsQuery = useProjects();
  const healthQuery = useHealth();
  const usageQuery = useUsageByProject("30d");

  if (projectsQuery.isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-48 w-full" />
        ))}
      </div>
    );
  }

  if (projectsQuery.isError) {
    return <DaemonDownAlert error={projectsQuery.error} />;
  }

  const projects = projectsQuery.data ?? [];
  if (projects.length === 0) {
    return <NoProjectsCallout />;
  }

  const usageByName = new Map(
    (usageQuery.data ?? []).map((u) => [u.project as string, u]),
  );

  const pausedUntil = healthQuery.data?.queue_paused_until ?? null;
  const showRateLimitBanner =
    pausedUntil !== null && new Date(pausedUntil) > new Date();

  return (
    <div className="space-y-4">
      <HookStatusBanner />
      {showRateLimitBanner && (
        <div
          role="status"
          className="rounded-md border border-warning bg-warning/10 p-2 text-sm"
        >
          {t("overview.rate_limited_until", {
            time: new Date(pausedUntil!).toLocaleTimeString(),
          })}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {projects.map((p) => (
          <ProjectCard
            key={p.name}
            project={p}
            vault_health={healthQuery.data?.vaults?.[p.name]}
            usage={usageByName.get(p.name) as
              | { sessions_covered?: number; avg_compression_ratio?: number }
              | undefined}
          />
        ))}
      </div>
    </div>
  );
}
