import { useMemo } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivity } from "@/hooks/useActivity";
import { ActivityRow } from "@/components/widgets/ActivityRow";
import { groupByDay, type DayGroupKey } from "@/lib/groupByDay";

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
      <div className="py-12 text-center text-muted-foreground">
        {t("activity.no_activity")}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {VISIBLE_GROUPS.map((key) => {
        const group = groups.find((g) => g.key === key);
        if (!group || group.entries.length === 0) return null;
        return (
          <section key={key}>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              {t(`activity.groups.${key}`)}
              <span className="ml-2 font-normal">({group.entries.length})</span>
            </h2>
            <div className="space-y-2">
              {group.entries.map((e) => (
                <ActivityRow key={e.id} project={project} entry={e} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
