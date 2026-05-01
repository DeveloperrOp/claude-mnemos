import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHealth } from "@/hooks/useHealth";

export function Health() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const healthQuery = useHealth();

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

      <div className="text-xs text-muted-foreground">
        {t("health.alerts_count")}: {health?.alerts_count ?? 0}
      </div>
    </div>
  );
}
