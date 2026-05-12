import { useMemo } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivity } from "@/hooks/useActivity";
import { ActivityRow } from "@/components/widgets/ActivityRow";
import { EmptyState } from "@/components/widgets/EmptyState";
import { groupByDay, type DayGroupKey } from "@/lib/groupByDay";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

const VISIBLE_GROUPS: DayGroupKey[] = [
  "needs_attention",
  "today",
  "yesterday",
  "earlier_week",
  "older",
];

export function ActivityCenter() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const activityQuery = useActivity(project, { limit: 200 });

  const groups = useMemo(
    () => groupByDay(activityQuery.data?.entries ?? []),
    [activityQuery.data],
  );

  if (!project) return null;

  if (activityQuery.isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12" />
        ))}
      </div>
    );
  }

  const total = activityQuery.data?.total ?? 0;
  if (total === 0) {
    return (
      <EmptyState
        icon="📜"
        title={t("activity.empty.title")}
        body={t("activity.empty.body")}
      />
    );
  }

  return (
    <div className="space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-center justify-between gap-3">
          <EyebrowBreadcrumb section="activity" />
        </div>
        <h1 className="relative mt-2 font-mono text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("activity.title", "Activity")}
        </h1>
      </header>

      {VISIBLE_GROUPS.map((key) => {
        const group = groups.find((g) => g.key === key);
        if (!group || group.entries.length === 0) return null;
        return (
          <section key={key}>
            <div className="section-rail mb-3">
              <span>{t(`activity.groups.${key}`)}</span>
              <span className="ml-auto font-mono tabular-nums text-foreground/70">{group.entries.length}</span>
            </div>
            <div className="stagger divide-y divide-border/50 rounded-md bg-card/40 ring-1 ring-border/60">
              {group.entries.map((e, i) => (
                <div
                  key={e.id}
                  style={{ ["--i" as string]: i }}
                  className="border-l-2 border-l-transparent px-3 py-2 hover:border-l-accent hover:bg-card/60"
                >
                  <ActivityRow project={project} entry={e} />
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
