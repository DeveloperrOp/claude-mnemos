import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { useHealth } from "@/hooks/useHealth";

export function HealthDot() {
  const { t } = useTranslation();
  const q = useHealth();
  const status = q.data?.status ?? "ok";
  const alertsCount = q.data?.alerts_count ?? 0;

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

  return (
    <Link
      to="/health"
      className="group flex items-center gap-2 rounded-full border border-border/60 bg-card/50 px-2.5 py-1 transition-colors hover:border-accent/60"
    >
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
      <span className="font-mono text-[10px] text-muted-foreground transition-colors group-hover:text-accent">
        {t("overview.health_dot.details_link")}
      </span>
    </Link>
  );
}
