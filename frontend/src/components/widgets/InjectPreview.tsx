import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useInjectPreview } from "@/hooks/useInjectPreview";

interface Props {
  project: string;
}

function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}K`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

function zoneClass(ratio: number): { bar: string; over: boolean } {
  if (ratio > 1) return { bar: "bg-destructive", over: true };
  if (ratio >= 0.75) return { bar: "bg-amber-500", over: false };
  return { bar: "bg-success", over: false };
}

export function InjectPreview({ project }: Props) {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useInjectPreview(project);
  const [pagesOpen, setPagesOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  if (isLoading) return <Skeleton className="h-32 w-full" />;
  if (isError || !data) return null;

  const { tokens_estimate, limit, ratio, pages, preview_text } = data;
  const { bar, over } = zoneClass(ratio);
  const widthPct = Math.min(100, ratio * 100);

  return (
    <Card
      data-testid="inject-preview"
      className="border-border/60 bg-card/40"
    >
      <CardContent className="space-y-3 py-4">
        <div className="flex items-baseline justify-between gap-3">
          <span className="eyebrow">{t("inject_preview.title")}</span>
          {over && (
            <span
              data-testid="inject-preview-truncated"
              className="rounded bg-destructive/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-destructive"
            >
              {t("inject_preview.truncated")}
            </span>
          )}
        </div>

        <div className="flex items-baseline gap-2">
          <span className="hero-num text-3xl">
            {formatTokens(tokens_estimate)}
          </span>
          <span className="font-mono text-sm text-muted-foreground">
            / {formatTokens(limit)} {t("inject_preview.tokens_label")}
          </span>
        </div>

        <div
          data-testid="inject-preview-bar"
          className="h-1.5 w-full overflow-hidden rounded-full bg-muted/40"
        >
          <div
            data-testid="inject-preview-bar-fill"
            className={`h-full ${bar} transition-[width]`}
            style={{ width: `${widthPct}%` }}
          />
        </div>

        <button
          type="button"
          onClick={() => setPagesOpen((v) => !v)}
          className="flex w-full items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground"
        >
          {pagesOpen ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          {t("inject_preview.pages_count", { count: pages.length })}
        </button>

        {pagesOpen && (
          <ul
            data-testid="inject-preview-pages"
            className="space-y-1 font-mono text-xs"
          >
            {pages.map((p) => (
              <li
                key={p.slug}
                className={`flex items-center justify-between gap-2 ${
                  p.included ? "text-foreground" : "text-muted-foreground/60"
                }`}
              >
                <span className="truncate">
                  {p.included ? "✓ " : "· "}
                  {p.path}
                </span>
                <span className="shrink-0 tabular-nums">
                  {p.score.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        )}

        <button
          type="button"
          onClick={() => setPreviewOpen((v) => !v)}
          className="flex w-full items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground"
        >
          {previewOpen ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          {previewOpen
            ? t("inject_preview.preview_hide")
            : t("inject_preview.preview_show")}
        </button>

        {previewOpen && (
          <pre
            data-testid="inject-preview-text"
            className="max-h-80 overflow-auto rounded-md border border-border/60 bg-bg-elev-1 p-3 font-mono text-xs leading-relaxed"
          >
            {preview_text}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}
