import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useUsageTimeline } from "@/hooks/useUsageTimeline";
import { useUsageByProject } from "@/hooks/useUsageByProject";
import { useTopSessions } from "@/hooks/useTopSessions";
import { useCompressionTimeline } from "@/hooks/useCompressionTimeline";
import { UsageTimelineChart } from "@/components/widgets/UsageTimelineChart";
import { UsageByProjectTable } from "@/components/widgets/UsageByProjectTable";
import { TopSessionsTable } from "@/components/widgets/TopSessionsTable";
import { CompressionTimelineChart } from "@/components/widgets/CompressionTimelineChart";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";
import { cn } from "@/lib/utils";

const PERIODS = ["7d", "30d", "90d", "1y"] as const;
type Period = (typeof PERIODS)[number];

function Metrics() {
  const { t } = useTranslation();
  const [period, setPeriod] = useState<Period>("30d");
  const timeline = useUsageTimeline(period);
  const compressionTimeline = useCompressionTimeline(period);
  const byProject = useUsageByProject(period);
  const top = useTopSessions(10);

  const allFailed =
    timeline.isError &&
    compressionTimeline.isError &&
    byProject.isError &&
    top.isError;

  if (allFailed) return <DaemonDownAlert error={timeline.error} />;

  return (
    <div className="space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="metrics" />
        </div>
        <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("metrics.title")}
        </h1>
      </header>

      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        <span className="text-xs text-muted-foreground whitespace-nowrap">
          {t("metrics.period_filter_label")}:
        </span>
        {PERIODS.map((p) => (
          <Button
            key={p}
            size="sm"
            variant={period === p ? "default" : "outline"}
            onClick={() => setPeriod(p)}
          >
            {t(`metrics.period_${p}`)}
          </Button>
        ))}
      </div>

      <div className="rounded-md border border-border/60 bg-card/40 p-4">
        <div className="section-rail mb-4">
          <span>{t("metrics.timeline_title")}</span>
        </div>
        {timeline.isLoading ? (
          <Skeleton className="h-72" />
        ) : (
          <UsageTimelineChart points={timeline.data ?? []} />
        )}
      </div>

      <div className="rounded-md border border-border/60 bg-card/40 p-4">
        <div className="section-rail mb-4">
          <span>{t("metrics.compression_timeline_title")}</span>
        </div>
        {compressionTimeline.isLoading ? (
          <Skeleton className="h-72" />
        ) : (
          <CompressionTimelineChart points={compressionTimeline.data ?? []} />
        )}
      </div>

      <div className={cn("grid gap-4", "xl:grid-cols-2")}>
        <div className="rounded-md border border-border/60 bg-card/40 p-4">
          {byProject.isLoading ? (
            <Skeleton className="h-48" />
          ) : (
            <UsageByProjectTable rows={byProject.data ?? []} />
          )}
        </div>
        <div className="rounded-md border border-border/60 bg-card/40 p-4">
          {top.isLoading ? (
            <Skeleton className="h-48" />
          ) : (
            <TopSessionsTable rows={top.data ?? []} />
          )}
        </div>
      </div>
    </div>
  );
}

export { Metrics };
export default Metrics;
