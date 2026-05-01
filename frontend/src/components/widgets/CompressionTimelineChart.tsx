import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, Legend, CartesianGrid,
} from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import type { CompressionTimelinePoint } from "@/types/CompressionTimeline";

interface Props {
  points: CompressionTimelinePoint[];
}

export function CompressionTimelineChart({ points }: Props) {
  const { t } = useTranslation();

  const isEmpty = useMemo(() => {
    if (points.length === 0) return true;
    return points.every((p) => p.events_count === 0);
  }, [points]);

  if (isEmpty) {
    return (
      <div className="flex h-72 items-center justify-center rounded-md border bg-muted text-sm text-muted-foreground">
        {t("metrics.compression_timeline_empty")}
      </div>
    );
  }

  return (
    <>
      <span className="sr-only">{t("metrics.compression_timeline_legend_events")}</span>
      <span className="sr-only">{t("metrics.compression_timeline_legend_ratio")}</span>
      <ChartContainer height={320}>
        <ComposedChart data={points} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey="date" fontSize={11} />
          <YAxis yAxisId="events" fontSize={11} />
          <YAxis yAxisId="ratio" orientation="right" fontSize={11} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar
            yAxisId="events"
            dataKey="events_count"
            name={t("metrics.compression_timeline_legend_events")}
            fill="var(--chart-input)"
          />
          <Line
            yAxisId="ratio"
            type="monotone"
            dataKey="avg_compression_ratio"
            name={t("metrics.compression_timeline_legend_ratio")}
            stroke="var(--chart-sessions)"
            strokeWidth={2}
            connectNulls={false}
          />
        </ComposedChart>
      </ChartContainer>
    </>
  );
}
