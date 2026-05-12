import { useTranslation } from "react-i18next";
import { useProjects } from "@/hooks/useProjects";
import { useHealth } from "@/hooks/useHealth";
import { useUsageByProject } from "@/hooks/useUsageByProject";
import { useDashboardSnapshot } from "@/hooks/dashboard/useDashboardSnapshot";
import { useFirstSessionCelebration } from "@/hooks/useFirstSessionCelebration";
import { ProjectCard } from "@/components/widgets/ProjectCard";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { HookStatusBanner } from "@/components/widgets/HookStatusBanner";
import { UpdateBanner } from "@/components/widgets/dashboard/UpdateBanner";
import { HealthAlertsBar } from "@/components/widgets/dashboard/HealthAlertsBar";
import { SetupChecklist } from "@/components/widgets/dashboard/SetupChecklist";
import { NoProjectsCallout } from "@/components/widgets/NoProjectsCallout";
import { KpiBar } from "@/components/widgets/dashboard/KpiBar";
import { RunningJobsLive } from "@/components/widgets/dashboard/RunningJobsLive";
import { ActiveSessionsLive } from "@/components/widgets/dashboard/ActiveSessionsLive";
import { HealthDot } from "@/components/widgets/dashboard/HealthDot";
import { Skeleton } from "@/components/ui/skeleton";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

export function Overview() {
  const { t } = useTranslation();
  const projectsQuery = useProjects();
  const healthQuery = useHealth();
  const usageQuery = useUsageByProject("30d");
  const snapshotQuery = useDashboardSnapshot();
  useFirstSessionCelebration(snapshotQuery.data);

  if (projectsQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-14 w-full" />
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

  // Local time string for "operational" vibe in header meta-line.
  const nowStr = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  return (
    <div className="space-y-6">
      {/* ── Operational header ─────────────────────────────────── */}
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-baseline gap-3">
            <EyebrowBreadcrumb section="ops" />
          </div>
          <HealthDot />
        </div>
        <div className="relative mt-2 flex items-end justify-between gap-3">
          <h1 className="font-mono text-[clamp(1.75rem,4vw,2.75rem)] font-medium tracking-tight">
            {t("overview.title", "Overview")}
            <span className="cursor-blink text-accent">_</span>
          </h1>
          <div className="hidden font-mono text-[10px] tabular-nums uppercase tracking-wider text-muted-foreground sm:flex sm:flex-col sm:items-end">
            <span>{t("overview.header.local_time", { time: nowStr })}</span>
            <span>{t("overview.header.refresh_rate")}</span>
          </div>
        </div>
      </header>

      <UpdateBanner />

      <HookStatusBanner />

      <HealthAlertsBar />

      <section>
        <div className="section-rail mb-3">
          <span>{t("overview.projects_heading", "Projects")}</span>
          <span className="ml-auto font-mono tabular-nums text-foreground/70">
            {projects.length}
          </span>
        </div>
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

      <SetupChecklist />

      {showRateLimitBanner && (
        <div
          role="status"
          className="rounded-md border border-warning/60 bg-warning/10 px-3 py-2 font-mono text-xs"
        >
          ⚠ {t("overview.rate_limited_until", {
            time: new Date(pausedUntil!).toLocaleTimeString(),
          })}
        </div>
      )}

      {snapshot && snapshot.errors.length > 0 && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 font-mono text-[11px] text-amber-600 dark:text-amber-400">
          ⚠ {snapshot.errors.join(" · ")}
        </div>
      )}

      {snapshot && (
        <>
          <KpiBar data={snapshot.kpi} />
          <RunningJobsLive jobs={snapshot.running_jobs} />
          <ActiveSessionsLive sessions={snapshot.active_sessions} />
        </>
      )}
    </div>
  );
}
