import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import type { Kpi } from "@/types/ActiveSession";

/* ──────────────────────────────────────────────────────────────────
   KpiBar — operational hero strip.

   Layout (lg+):  [    HERO ACTIVE     ] [Queue][Today][Tokens][Lost]
                  └ 2/5 width, oversized └ 1/5 each, compact
   On mobile: stacked.

   Hero is "active sessions" because that's the most operationally
   meaningful: how many things are alive RIGHT NOW. The compact tiles
   are auxiliary readings.
   ──────────────────────────────────────────────────────────────── */

interface CompactProps {
  label: string;
  primary: string;
  secondary?: string;
  accent?: "default" | "destructive" | "warning";
  href?: string;
  testId?: string;
}

function CompactTile({
  label,
  primary,
  secondary,
  accent = "default",
  href,
  testId,
}: CompactProps) {
  const ring =
    accent === "destructive"
      ? "border-destructive/60 bg-destructive/5"
      : accent === "warning"
        ? "border-amber-500/50 bg-amber-500/[0.04]"
        : "border-border";

  const inner = (
    <div
      data-testid={testId}
      className={`group relative h-full rounded-md border ${ring} bg-card/60 px-3 py-2.5 transition-colors hover:border-accent/60`}
    >
      <div className="eyebrow">{label}</div>
      <div className="mt-1.5 font-mono text-base tabular-nums leading-tight">
        {primary}
      </div>
      {secondary && (
        <div className="mt-0.5 font-mono text-[10px] tabular-nums text-muted-foreground">
          {secondary}
        </div>
      )}
    </div>
  );

  return href ? (
    <Link to={href} className="block h-full">
      {inner}
    </Link>
  ) : (
    inner
  );
}

interface HeroProps {
  hot: number;
  cooling: number;
  totalLabel: string;
  hotLabel: string;
  coolingLabel: string;
}

function ActiveHero({ hot, cooling, totalLabel, hotLabel, coolingLabel }: HeroProps) {
  const total = hot + cooling;
  const hotPct = total > 0 ? Math.round((hot / total) * 100) : 0;
  return (
    <div
      data-testid="kpi-active"
      className="relative h-full overflow-hidden rounded-md border border-border bg-card/60"
    >
      {/* dot-matrix backdrop for hero feel */}
      <div className="dot-bg pointer-events-none absolute inset-0 opacity-40" />

      <div className="relative flex h-full flex-col justify-between p-4">
        <div className="flex items-baseline justify-between gap-3">
          <span className="eyebrow">{totalLabel}</span>
          <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
            {total > 0 ? `${hotPct}% hot` : "—"}
          </span>
        </div>

        <div className="flex items-end gap-3">
          <div className="hero-num text-[clamp(2.75rem,7vw,4.5rem)]">
            {total}
          </div>
          <div className="mb-2 flex flex-col gap-0.5 font-mono text-[11px] leading-tight tabular-nums">
            <span className="flex items-center gap-1.5">
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full bg-accent ${
                  hot > 0 ? "heartbeat" : "opacity-40"
                }`}
              />
              <span className="text-foreground">{hot}</span>
              <span className="text-muted-foreground">{hotLabel}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-500" />
              <span className="text-foreground">{cooling}</span>
              <span className="text-muted-foreground">{coolingLabel}</span>
            </span>
          </div>
        </div>

        {/* Composition meter — single thin bar, lime / amber */}
        {total > 0 && (
          <div className="mt-3 flex h-1 overflow-hidden rounded-full bg-border/60">
            <span
              className="h-full bg-accent"
              style={{ width: `${(hot / total) * 100}%` }}
            />
            <span
              className="h-full bg-amber-500"
              style={{ width: `${(cooling / total) * 100}%` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export function KpiBar({ data }: { data: Kpi }) {
  const { t } = useTranslation();
  const queueAccent = data.queue.failed > 0 ? "destructive" : "default";

  return (
    <div className="grid gap-2 lg:grid-cols-6">
      {/* Hero spans 2 of 6 cols on lg */}
      <div className="lg:col-span-2">
        <ActiveHero
          hot={data.active.hot}
          cooling={data.active.cooling}
          totalLabel={t("overview.kpi.active_label")}
          hotLabel="hot"
          coolingLabel="cooling"
        />
      </div>

      <CompactTile
        label={t("overview.kpi.queue_label")}
        primary={`${data.queue.queued}/${data.queue.running}/${data.queue.failed}`}
        secondary="queued · run · fail"
        accent={queueAccent}
        testId="kpi-queue"
      />

      <CompactTile
        label={t("overview.kpi.today_label")}
        primary={`${data.today.ingest_count}`}
        secondary={`${data.today.pages_count} pages`}
        testId="kpi-today"
      />

      <CompactTile
        label={t("overview.kpi.tokens_label")}
        primary={`${(data.tokens_today / 1000).toFixed(1)}K`}
        secondary="today"
        testId="kpi-tokens"
      />

      <CompactTile
        label={t("overview.kpi.lost_label")}
        primary={`${data.lost_total}`}
        secondary={t("overview.kpi.lost_link")}
        href="/lost-sessions"
        testId="kpi-lost"
      />
    </div>
  );
}
