import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, Legend, CartesianGrid,
} from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import type { UsageTimelinePoint } from "@/types/UsageTimeline";

interface Props {
  points: UsageTimelinePoint[];
}

export function UsageTimelineChart({ points }: Props) {
  const { t } = useTranslation();

  const isEmpty = useMemo(() => {
    if (points.length === 0) return true;
    return points.every(
      (p) => p.sessions === 0 && p.tokens_input === 0 && p.tokens_output === 0,
    );
  }, [points]);

  if (isEmpty) {
    return (
      <div className="flex h-72 items-center justify-center rounded-md border bg-[hsl(var(--muted))] text-sm text-[hsl(var(--muted-foreground))]">
        {t("metrics.timeline_empty")}
      </div>
    );
  }

  return (
    <>
      <span className="sr-only">{t("metrics.timeline_legend_input")}</span>
      <span className="sr-only">{t("metrics.timeline_legend_output")}</span>
      <span className="sr-only">{t("metrics.timeline_legend_sessions")}</span>
      <ChartContainer height={320}>
        <ComposedChart data={points} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey="date" fontSize={11} />
          <YAxis yAxisId="tokens" fontSize={11} />
          <YAxis yAxisId="sessions" orientation="right" fontSize={11} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar yAxisId="tokens" dataKey="tokens_input" stackId="t" name={t("metrics.timeline_legend_input")} fill="#3b82f6" />
          <Bar yAxisId="tokens" dataKey="tokens_output" stackId="t" name={t("metrics.timeline_legend_output")} fill="#10b981" />
          <Line yAxisId="sessions" type="monotone" dataKey="sessions" name={t("metrics.timeline_legend_sessions")} stroke="#f59e0b" strokeWidth={2} />
        </ComposedChart>
      </ChartContainer>
    </>
  );
}
