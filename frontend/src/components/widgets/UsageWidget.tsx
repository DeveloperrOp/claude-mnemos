import { useTranslation } from "react-i18next";
import { Syringe } from "lucide-react";
import { useUsage } from "@/hooks/useUsage";

function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}K`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

function formatRatio(r: number): string {
  return r.toFixed(1);
}

export function UsageWidget() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useUsage("1d");

  if (isLoading || isError || !data) return null;

  if (data.total_tokens_injected === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-[hsl(var(--muted-foreground))]">
        <Syringe className="h-4 w-4" />
        <span>{t("usage.no_data")}</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 text-sm" title={t("usage.title")}>
      <Syringe className="h-4 w-4 text-[hsl(var(--primary))]" />
      <span>{formatTokens(data.total_tokens_injected)}</span>
      <span className="text-[hsl(var(--muted-foreground))]">·</span>
      <span>{data.sessions_covered}</span>
      <span className="text-[hsl(var(--muted-foreground))]">·</span>
      <span>×{formatRatio(data.avg_compression_ratio)}</span>
    </div>
  );
}
