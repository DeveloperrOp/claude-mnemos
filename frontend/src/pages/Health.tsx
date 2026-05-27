import { useState } from "react";
import { Link, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useHealth } from "@/hooks/useHealth";
import { useProjects } from "@/hooks/useProjects";
import { useWatchdogEvents } from "@/hooks/useWatchdogEvents";
import {
  useDismissWatchdogEvent,
  useDismissAllWatchdogEvents,
} from "@/hooks/useDismissWatchdogEvent";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { formatDateTime } from "@/lib/datetime";
import { getProjectDisplayName } from "@/lib/projectDisplayName";
import {
  jobKindLabel,
  parseJobId,
  parseTrigger,
  shortenPath,
  stripTmpSuffix,
  triggerLabel,
} from "@/lib/healthFormat";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

export function Health() {
  const { name: project } = useParams<{ name: string }>();
  const { t, i18n } = useTranslation();
  const healthQuery = useHealth();
  const projectsQuery = useProjects();
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
  const entry = projectsQuery.data?.find((p) => p.name === project);
  const displayName = entry ? getProjectDisplayName(entry) : project;

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
        <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("health.title")}
          <span className="ml-2 text-base font-normal text-muted-foreground">
            · {displayName}
          </span>
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
          <ul className="divide-y divide-border/50">
            {projectSchedulerJobs.map((j) => {
              const { kind } = parseJobId(j.id);
              const triggerInfo = parseTrigger(j.trigger);
              return (
                <li
                  key={j.id}
                  className="grid gap-2 py-3 md:grid-cols-[1fr_auto_auto] md:items-center"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium">
                      {jobKindLabel(kind, t)}
                    </div>
                    <div
                      className="truncate font-mono text-[10px] text-muted-foreground/70"
                      title={j.id}
                    >
                      {j.id}
                    </div>
                  </div>
                  <div className="text-sm tabular-nums">
                    {triggerLabel(triggerInfo, t)}
                  </div>
                  <div
                    className="text-xs text-muted-foreground tabular-nums"
                    title={t("health.col.next_run_time")}
                  >
                    {j.next_run_time
                      ? t("health.jobs.next_run_prefix", {
                          time: formatDateTime(j.next_run_time, i18n.language),
                        })
                      : "—"}
                  </div>
                </li>
              );
            })}
          </ul>
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
                {alerts.map((a, i) => {
                  const tmp = a.path ? stripTmpSuffix(a.path) : null;
                  const shortPath = tmp ? shortenPath(tmp.path) : null;
                  // Known watchdog kinds have a human label that fully
                  // covers the backend message (which is just raw paths).
                  // For unknown kinds we still show the message so we don't
                  // hide context.
                  const KNOWN_KINDS = [
                    "external_create",
                    "external_rename",
                    "lock_timeout",
                    "parse_failed",
                    "handler_error",
                  ];
                  const isKnownKind = KNOWN_KINDS.includes(a.kind);
                  return (
                    <div
                      key={a.id}
                      style={{ ["--i" as string]: i }}
                      className="border-l-2 border-l-transparent px-3 py-2 hover:border-l-accent hover:bg-card/60 flex items-start gap-3"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
                            {t(`health.alerts.kinds.${a.kind}`, {
                              defaultValue: a.kind,
                            })}
                          </span>
                          {tmp?.isTmp && (
                            <span className="rounded bg-warning/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-warning">
                              {t("health.alerts.tmp_badge", "temp")}
                            </span>
                          )}
                          <span className="text-xs text-muted-foreground">
                            {formatDateTime(a.detected_at, i18n.language)}
                          </span>
                        </div>
                        {a.message && !isKnownKind && (
                          <div className="mt-1 break-words text-sm">{a.message}</div>
                        )}
                        {shortPath && (
                          <div
                            className="mt-1 truncate font-mono text-xs text-muted-foreground"
                            title={a.path ?? undefined}
                          >
                            {shortPath}
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
                  );
                })}
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
