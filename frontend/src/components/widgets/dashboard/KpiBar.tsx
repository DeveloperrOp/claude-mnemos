import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import type { Kpi } from "@/types/ActiveSession";

interface KpiTileProps {
  label: string;
  value: string;
  accent?: "default" | "destructive" | "warning";
  href?: string;
  testId?: string;
}

function KpiTile({ label, value, accent = "default", href, testId }: KpiTileProps) {
  const accentClass =
    accent === "destructive"
      ? "border-destructive/50 bg-destructive/5"
      : accent === "warning"
      ? "border-amber-500/50 bg-amber-500/5"
      : "border-border";

  const content = (
    <div
      data-testid={testId}
      className={`rounded-md border ${accentClass} p-3 text-sm`}
    >
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono">{value}</div>
    </div>
  );

  return href ? <Link to={href}>{content}</Link> : content;
}

export function KpiBar({ data }: { data: Kpi }) {
  const { t } = useTranslation();
  const queueAccent = data.queue.failed > 0 ? "destructive" : "default";
  const activeAccent = data.active.cooling > 0 ? "warning" : "default";

  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
      <KpiTile
        label={t("overview.kpi.queue_label")}
        value={t("overview.kpi.queue_format", {
          queued: data.queue.queued,
          running: data.queue.running,
          failed: data.queue.failed,
        })}
        accent={queueAccent}
        testId="kpi-queue"
      />
      <KpiTile
        label={t("overview.kpi.active_label")}
        value={t("overview.kpi.active_format", {
          hot: data.active.hot,
          cooling: data.active.cooling,
        })}
        accent={activeAccent}
        testId="kpi-active"
      />
      <KpiTile
        label={t("overview.kpi.today_label")}
        value={t("overview.kpi.today_format", {
          ingest: data.today.ingest_count,
          pages: data.today.pages_count,
        })}
        testId="kpi-today"
      />
      <KpiTile
        label={t("overview.kpi.tokens_label")}
        value={`${(data.tokens_today / 1000).toFixed(1)}K`}
        testId="kpi-tokens"
      />
      <KpiTile
        label={t("overview.kpi.lost_label")}
        value={`${data.lost_total} ${t("overview.kpi.lost_link")}`}
        href="/lost-sessions"
        testId="kpi-lost"
      />
    </div>
  );
}
