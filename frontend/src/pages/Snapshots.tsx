import { useState, useMemo } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { useSnapshots } from "@/hooks/useSnapshots";
import { Skeleton } from "@/components/ui/skeleton";
import { SnapshotCard } from "@/components/widgets/SnapshotCard";
import { SnapshotFilters, type KindFilter } from "@/components/filters/SnapshotFilters";

export function Snapshots() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const [kind, setKind] = useState<KindFilter>("all");
  const snapshotsQuery = useSnapshots(project);

  const filtered = useMemo(() => {
    const all = snapshotsQuery.data ?? [];
    if (kind === "all") return all;
    return all.filter((s) => s.kind === kind);
  }, [snapshotsQuery.data, kind]);

  if (!project) return null;
  if (snapshotsQuery.isLoading) {
    return (
      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}
      </div>
    );
  }

  if ((snapshotsQuery.data ?? []).length === 0) {
    return (
      <div className="space-y-3">
        <SnapshotFilters value={kind} onChange={setKind} />
        <div className="py-12 text-center text-[hsl(var(--muted-foreground))]">
          {t("snapshots.no_snapshots")}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <SnapshotFilters value={kind} onChange={setKind} />
      <div className="text-xs text-[hsl(var(--muted-foreground))]">
        {t("snapshots.showing_n", { count: filtered.length })}
      </div>
      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
        {filtered.map((s) => <SnapshotCard key={s.name} snapshot={s} />)}
      </div>
    </div>
  );
}
