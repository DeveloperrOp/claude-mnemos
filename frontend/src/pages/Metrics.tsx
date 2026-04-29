import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useUsageTimeline } from "@/hooks/useUsageTimeline";
import { useUsageByProject } from "@/hooks/useUsageByProject";
import { useTopSessions } from "@/hooks/useTopSessions";
import { UsageTimelineChart } from "@/components/widgets/UsageTimelineChart";
import { UsageByProjectTable } from "@/components/widgets/UsageByProjectTable";
import { TopSessionsTable } from "@/components/widgets/TopSessionsTable";
import { cn } from "@/lib/utils";

const PERIODS = ["7d", "30d", "90d", "1y"] as const;
type Period = (typeof PERIODS)[number];

function Metrics() {
  const { t } = useTranslation();
  const [period, setPeriod] = useState<Period>("30d");
  const timeline = useUsageTimeline(period);
  const byProject = useUsageByProject(period);
  const top = useTopSessions(10);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("metrics.title")}</h1>
        <div className="flex items-center gap-2">
          <span className="text-xs text-[hsl(var(--muted-foreground))]">
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
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("metrics.timeline_title")}</CardTitle>
        </CardHeader>
        <CardContent>
          {timeline.isLoading ? (
            <Skeleton className="h-72" />
          ) : (
            <UsageTimelineChart points={timeline.data ?? []} />
          )}
        </CardContent>
      </Card>

      <div className={cn("grid gap-4", "xl:grid-cols-2")}>
        {byProject.isLoading ? (
          <Skeleton className="h-48" />
        ) : (
          <UsageByProjectTable rows={byProject.data ?? []} />
        )}
        {top.isLoading ? (
          <Skeleton className="h-48" />
        ) : (
          <TopSessionsTable rows={top.data ?? []} />
        )}
      </div>
    </div>
  );
}

export { Metrics };
export default Metrics;
