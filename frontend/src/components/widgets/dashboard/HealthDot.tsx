import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { useHealth } from "@/hooks/useHealth";
import { useHealthAlerts } from "@/hooks/dashboard/useHealthAlerts";
import { useProjects } from "@/hooks/useProjects";

/* Top-level frontend has no /health route — Health page lives under
   /project/:name/health. We link to the first registered project's
   Health page when available; otherwise render as static (no link).
   Long-term TODO: build a true cross-vault Health page mounted at /health. */

export function HealthDot() {
  const { t } = useTranslation();
  const q = useHealth();
  const alertsQ = useHealthAlerts();
  const projects = useProjects();
  const firstProject = projects.data?.[0]?.name;

  const status = q.data?.status ?? "ok";
  // Previously this used q.data.alerts_count which is the historical
  // watchdog-notifications counter (grew without bound). The Overview dot
  // should reflect *active* health alerts only — same source HealthAlertsBar
  // uses.
  const alertsCount = alertsQ.data?.alerts.length ?? 0;

  const isOk = status === "ok" && alertsCount === 0;
  const dotColor = isOk
    ? "bg-success"
    : status === "degraded" || alertsCount > 0
      ? "bg-amber-500"
      : "bg-destructive";
  const label = isOk
    ? t("overview.health_dot.ok")
    : alertsCount > 0
      ? t("overview.health_dot.warning")
      : t("overview.health_dot.critical");

  const inner = (
    <>
      <span className="relative flex h-2 w-2">
        <span
          className={`absolute inline-flex h-full w-full rounded-full opacity-60 ${dotColor} ${
            isOk ? "animate-ping" : ""
          }`}
        />
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dotColor}`} />
      </span>
      <span className="font-mono text-[10px] uppercase tracking-wider">
        {label}
      </span>
      {firstProject && (
        <span className="font-mono text-[10px] text-muted-foreground transition-colors group-hover:text-accent">
          {t("overview.health_dot.details_link")}
        </span>
      )}
    </>
  );

  if (!firstProject) {
    return (
      <span className="flex items-center gap-2 rounded-full border border-border/60 bg-card/50 px-2.5 py-1">
        {inner}
      </span>
    );
  }

  return (
    <Link
      to={`/project/${encodeURIComponent(firstProject)}/health`}
      className="group flex items-center gap-2 rounded-full border border-border/60 bg-card/50 px-2.5 py-1 transition-colors hover:border-accent/60"
    >
      {inner}
    </Link>
  );
}
