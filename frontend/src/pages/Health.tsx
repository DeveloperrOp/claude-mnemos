import { useState } from "react";
import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useHealth } from "@/hooks/useHealth";
import { useWatchdogEvents } from "@/hooks/useWatchdogEvents";
import {
  useDismissWatchdogEvent,
  useDismissAllWatchdogEvents,
} from "@/hooks/useDismissWatchdogEvent";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { formatDateTime } from "@/lib/datetime";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

export function Health() {
  const { name: project } = useParams<{ name: string }>();
  const { t, i18n } = useTranslation();
  const healthQuery = useHealth();
  const alertsQuery = useWatchdogEvents();
  const dismiss = useDismissWatchdogEvent();
  const dismissAll = useDismissAllWatchdogEvents();
  const [alertsExpanded, setAlertsExpanded] = useState(false);
  const [clearAllOpen, setClearAllOpen] = useState(false);

  if (!project) return null;
  if (healthQuery.isLoading) return <Skeleton className="h-64" />;
  if (healthQuery.isError) return <DaemonDownAlert error={healthQuery.error} />;

  const health = healthQuery.data;
  const vh = health?.vaults?.[project];

  if (!vh) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("health.vault_not_mounted_title")}</h1>
        <p className="text-muted-foreground">
          {project} — {t("health.vault_not_mounted_hint")}
        </p>
      </div>
    );
  }

  const projectSchedulerJobs =
    health?.scheduler_jobs?.filter((j) => j.id.endsWith(`:${project}`)) ?? [];

  const alerts = alertsQuery.data ?? [];
  const alertsCount = health?.alerts_count ?? alerts.length;

  return (
    <div className="space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="health" />
        </div>
        <h1 className="relative mt-2 font-mono text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("health.title")}
        </h1>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-md border border-border/60 bg-card/40 p-4">
          <div
            className={`text-sm font-semibold ${
              vh.watchdog_running
                ? "text-success"
                : "text-warning"
            }`}
          >
            {vh.watchdog_running
              ? t("health.watchdog_running")
              : t("health.watchdog_down")}
          </div>
        </div>
        <div className="rounded-md border border-border/60 bg-card/40 p-4 space-y-1">
          <div className="hero-num">{vh.jobs_queued}</div>
          <div className="eyebrow text-muted-foreground">
            {t("health.jobs_queued")}
          </div>
        </div>
        <div className="rounded-md border border-border/60 bg-card/40 p-4 space-y-1">
          <div className="hero-num">{vh.jobs_running}</div>
          <div className="eyebrow text-muted-foreground">
            {t("health.jobs_running")}
          </div>
        </div>
        <div className="rounded-md border border-border/60 bg-card/40 p-4 space-y-2">
          <div className="hero-num">{vh.jobs_dead_letter}</div>
          <div className="eyebrow text-muted-foreground">
            {t("health.jobs_dead_letter")}
          </div>
          {vh.jobs_dead_letter > 0 && (
            <Link
              to={`/dead-letter?project=${encodeURIComponent(project)}`}
              className="text-xs text-primary underline inline-block"
            >
              {t("health.view_failed_jobs")}
            </Link>
          )}
        </div>
      </div>

      <div className="rounded-md border border-border/60 bg-card/40 p-4">
        <div className="section-rail mb-4">
          <span>{t("health.scheduler_jobs")}</span>
          <span className="ml-auto font-mono tabular-nums text-foreground/70">{projectSchedulerJobs.length}</span>
        </div>
        {projectSchedulerJobs.length === 0 ? (
          <div className="flex items-center gap-3 rounded-md border border-dashed border-border bg-card/30 px-3 py-3 font-mono text-[11px] text-muted-foreground">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/60" />
            <span className="uppercase tracking-wider">{t("health.empty_label")}</span>
            <span className="ml-auto opacity-60">{t("health.no_scheduler_jobs")}</span>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-2 font-medium text-xs uppercase tracking-wide text-muted-foreground">{t("health.col.id")}</th>
                <th className="py-2 font-medium text-xs uppercase tracking-wide text-muted-foreground">{t("health.col.next_run_time")}</th>
                <th className="py-2 font-medium text-xs uppercase tracking-wide text-muted-foreground">{t("health.col.trigger")}</th>
              </tr>
            </thead>
            <tbody>
              {projectSchedulerJobs.map((j) => (
                <tr key={j.id} className="border-b last:border-0">
                  <td className="py-2 font-mono text-xs">{j.id}</td>
                  <td className="py-2 text-xs">
                    {j.next_run_time ? formatDateTime(j.next_run_time, i18n.language) : "—"}
                  </td>
                  <td className="py-2 text-xs">{j.trigger}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="rounded-md border border-border/60 bg-card/40 p-4">
        <button
          type="button"
          className="w-full text-left"
          onClick={() => setAlertsExpanded((x) => !x)}
          aria-expanded={alertsExpanded}
        >
          <div className="section-rail mb-0">
            <div className="flex items-center gap-2">
              {alertsExpanded ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
              <span>{t("health.alerts_count")}</span>
            </div>
            <span className="ml-auto font-mono tabular-nums text-foreground/70">{alertsCount}</span>
          </div>
        </button>
        {alertsExpanded && (
          <div className="mt-4">
            {alerts.length > 0 && (
              <div className="mb-3">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setClearAllOpen(true)}
                  disabled={dismissAll.isPending}
                >
                  {t("health.alerts.clear_all")}
                </Button>
              </div>
            )}
            {alerts.length === 0 ? (
              <div className="flex items-center gap-3 rounded-md border border-dashed border-border bg-card/30 px-3 py-3 font-mono text-[11px] text-muted-foreground">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/60" />
                <span className="uppercase tracking-wider">{t("health.empty_label")}</span>
                <span className="ml-auto opacity-60">{t("health.alerts.empty")}</span>
              </div>
            ) : (
              <div className="stagger divide-y divide-border/50 rounded-md bg-card/40 ring-1 ring-border/60">
                {alerts.map((a, i) => (
                  <div
                    key={a.id}
                    style={{ ["--i" as string]: i }}
                    className="border-l-2 border-l-transparent px-3 py-2 hover:border-l-accent hover:bg-card/60 flex items-start gap-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                          {a.kind}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {formatDateTime(a.detected_at, i18n.language)}
                        </span>
                      </div>
                      <div className="mt-1 break-words text-sm">{a.message}</div>
                      {a.path && (
                        <div className="mt-1 truncate font-mono text-xs text-muted-foreground">
                          {a.path}
                        </div>
                      )}
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => dismiss.mutate(a.id)}
                      disabled={dismiss.isPending}
                      title={t("health.alerts.dismiss")}
                      aria-label={t("health.alerts.dismiss")}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={clearAllOpen}
        onOpenChange={setClearAllOpen}
        title={t("health.alerts.clear_all")}
        description={t("health.alerts.clear_all_confirm", { count: alerts.length })}
        confirmLabel={t("health.alerts.clear_all")}
        onConfirm={() => {
          dismissAll.mutate(
            alerts.map((a) => a.id),
            { onSettled: () => setClearAllOpen(false) },
          );
        }}
        isPending={dismissAll.isPending}
      />
    </div>
  );
}
