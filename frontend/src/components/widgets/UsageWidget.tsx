import { useTranslation } from "react-i18next";
import { Syringe } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useUsage } from "@/hooks/useUsage";

function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}K`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

function formatTokensPerByte(r: number): string {
  return r.toFixed(2);
}

interface MetricProps {
  tip: string;
  children: React.ReactNode;
}

function Metric({ tip, children }: MetricProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="cursor-help">{children}</span>
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  );
}

export function UsageWidget() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useUsage("1d");

  if (isLoading || isError || !data) return null;

  if (data.tokens_injected === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Syringe className="h-4 w-4" />
        <span>{t("usage.no_data")}</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-2 text-sm">
        <Syringe className="h-4 w-4 text-primary" />
        <Metric tip={t("usage_widget.tooltip_tokens")}>
          {formatTokens(data.tokens_injected)}
        </Metric>
        <span className="text-muted-foreground">·</span>
        <Metric tip={t("usage_widget.tooltip_sessions")}>
          {data.sessions_covered}
        </Metric>
        {data.tokens_per_byte !== null && (
          <>
            <span className="text-muted-foreground">·</span>
            <Metric tip={t("usage_widget.tooltip_tokens_per_byte")}>
              {formatTokensPerByte(data.tokens_per_byte)} tok/B
            </Metric>
          </>
        )}
      </div>
      <div className="text-xs text-muted-foreground">
        <Metric tip={t("usage_widget.tooltip_inject_events")}>
          {t("metrics.inject_events", { count: data.inject_events_count })}
        </Metric>
        {data.avg_compression_ratio !== null && (
          <>
            {" · "}
            <Metric tip={t("usage_widget.tooltip_avg_compression")}>
              {t("metrics.avg_compression", {
                ratio: data.avg_compression_ratio.toFixed(1),
              })}
            </Metric>
          </>
        )}
      </div>
    </div>
  );
}
