import { useTranslation } from "react-i18next";
import { useProjects } from "@/hooks/useProjects";
import { useHealth } from "@/hooks/useHealth";
import { useUsageByProject } from "@/hooks/useUsageByProject";
import { useDashboardSnapshot } from "@/hooks/dashboard/useDashboardSnapshot";
import { ProjectCard } from "@/components/widgets/ProjectCard";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { HookStatusBanner } from "@/components/widgets/HookStatusBanner";
import { NoProjectsCallout } from "@/components/widgets/NoProjectsCallout";
import { KpiBar } from "@/components/widgets/dashboard/KpiBar";
import { RunningJobsLive } from "@/components/widgets/dashboard/RunningJobsLive";
import { ActiveSessionsLive } from "@/components/widgets/dashboard/ActiveSessionsLive";
import { HealthDot } from "@/components/widgets/dashboard/HealthDot";
import { Skeleton } from "@/components/ui/skeleton";

export function Overview() {
  const { t } = useTranslation();
  const projectsQuery = useProjects();
  const healthQuery = useHealth();
  const usageQuery = useUsageByProject("30d");
  const snapshotQuery = useDashboardSnapshot();

  if (projectsQuery.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
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

  const snapshot = snapshotQuery.data;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("overview.title", "Overview")}</h1>
        <HealthDot />
      </div>

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

      {snapshot && snapshot.errors.length > 0 && (
        <div className="rounded border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs">
          {snapshot.errors.join(" · ")}
        </div>
      )}

      {snapshot && (
        <>
          <KpiBar data={snapshot.kpi} />
          <RunningJobsLive jobs={snapshot.running_jobs} />
          <ActiveSessionsLive sessions={snapshot.active_sessions} />
        </>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">
          {t("overview.projects_heading", "Projects")}
        </h2>
        <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
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
      </section>
    </div>
  );
}
