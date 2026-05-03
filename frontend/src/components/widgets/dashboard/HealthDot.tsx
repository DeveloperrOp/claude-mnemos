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
    ? "bg-emerald-500"
    : status === "degraded" || alertsCount > 0
      ? "bg-amber-500"
      : "bg-rose-500";
  const label = isOk
    ? t("overview.health_dot.ok")
    : alertsCount > 0
      ? t("overview.health_dot.warning")
      : t("overview.health_dot.critical");

  return (
    <Link
      to="/health"
      className="flex items-center gap-2 text-xs hover:underline"
    >
      <span className={`inline-block h-2 w-2 rounded-full ${dotColor}`} />
      <span>{label}</span>
      <span className="text-muted-foreground">
        {t("overview.health_dot.details_link")}
      </span>
    </Link>
  );
}
