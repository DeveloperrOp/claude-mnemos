import { useState } from "react";
import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHealth } from "@/hooks/useHealth";
import { useAlerts } from "@/hooks/useAlerts";
import { useDismissAlert, useDismissAllAlerts } from "@/hooks/useDismissAlert";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { formatDateTime } from "@/lib/datetime";

export function Health() {
  const { name: project } = useParams<{ name: string }>();
  const { t, i18n } = useTranslation();
  const healthQuery = useHealth();
  const alertsQuery = useAlerts();
  const dismiss = useDismissAlert();
  const dismissAll = useDismissAllAlerts();
  const [alertsExpanded, setAlertsExpanded] = useState(false);
  const [clearAllOpen, setClearAllOpen] = useState(false);

  if (!project) return null;
  if (healthQuery.isLoading) return <Skeleton className="h-64" />;

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
      <h1 className="text-xl font-semibold">{t("health.title")}</h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card>
          <CardContent className="py-3">
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
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 py-3">
            <div className="text-2xl font-semibold">{vh.jobs_queued}</div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              {t("health.jobs_queued")}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 py-3">
            <div className="text-2xl font-semibold">{vh.jobs_running}</div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              {t("health.jobs_running")}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 py-3">
            <div className="text-2xl font-semibold">{vh.jobs_dead_letter}</div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              {t("health.jobs_dead_letter")}
            </div>
            {vh.jobs_dead_letter > 0 && (
              <Link
                to={`/dead-letter?project=${encodeURIComponent(project)}`}
                className="text-xs text-primary underline"
              >
                {t("health.view_failed_jobs")}
              </Link>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("health.scheduler_jobs")}</CardTitle>
        </CardHeader>
        <CardContent>
          {projectSchedulerJobs.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              {t("health.no_scheduler_jobs")}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="py-1 font-medium">id</th>
                  <th className="py-1 font-medium">next_run_time</th>
                  <th className="py-1 font-medium">trigger</th>
                </tr>
              </thead>
              <tbody>
                {projectSchedulerJobs.map((j) => (
                  <tr key={j.id} className="border-b last:border-0">
                    <td className="py-1 font-mono text-xs">{j.id}</td>
                    <td className="py-1 text-xs">{j.next_run_time ?? "—"}</td>
                    <td className="py-1 text-xs">{j.trigger}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <button
            type="button"
            className="flex w-full items-center justify-between text-left"
            onClick={() => setAlertsExpanded((x) => !x)}
            aria-expanded={alertsExpanded}
          >
            <CardTitle className="flex items-center gap-2 text-base">
              {alertsExpanded ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
              {t("health.alerts_count")}: {alertsCount}
            </CardTitle>
            {alertsExpanded && alerts.length > 0 && (
              <Button
                size="sm"
                variant="outline"
                onClick={(e) => {
                  e.stopPropagation();
                  setClearAllOpen(true);
                }}
                disabled={dismissAll.isPending}
              >
                {t("health.alerts.clear_all")}
              </Button>
            )}
          </button>
        </CardHeader>
        {alertsExpanded && (
          <CardContent>
            {alerts.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                {t("health.alerts.empty")}
              </div>
            ) : (
              <div className="space-y-2">
                {alerts.map((a) => (
                  <div
                    key={a.id}
                    className="flex items-start gap-3 rounded-md border bg-background px-3 py-2 text-sm"
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
                      <div className="mt-1 break-words">{a.message}</div>
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
          </CardContent>
        )}
      </Card>

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
