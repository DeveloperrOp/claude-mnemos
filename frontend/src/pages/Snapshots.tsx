import { useState, useMemo } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import { useSnapshots } from "@/hooks/useSnapshots";
import { useSnapshotCreate } from "@/hooks/useSnapshotCreate";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { SnapshotCard } from "@/components/widgets/SnapshotCard";
import { EmptyState } from "@/components/widgets/EmptyState";
import { DaemonDownAlert } from "@/components/widgets/DaemonDownAlert";
import { SnapshotFilters, type KindFilter } from "@/components/filters/SnapshotFilters";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";

export function Snapshots() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const [kind, setKind] = useState<KindFilter>("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [label, setLabel] = useState("");
  const snapshotsQuery = useSnapshots(project);
  const create = useSnapshotCreate(project ?? "");

  const filtered = useMemo(() => {
    const all = snapshotsQuery.data ?? [];
    if (kind === "all") return all;
    return all.filter((s) => s.kind === kind);
  }, [snapshotsQuery.data, kind]);

  if (!project) return null;
  if (snapshotsQuery.isError) {
    return <DaemonDownAlert error={snapshotsQuery.error} />;
  }

  const headerControls = (
    <div className="flex items-center gap-3">
      <SnapshotFilters value={kind} onChange={setKind} />
      <Button
        size="sm"
        variant="outline"
        onClick={() => setCreateOpen(true)}
        disabled={create.isPending}
      >
        <Plus className="mr-1 h-3 w-3" />
        {t("snapshots.create_button")}
      </Button>
    </div>
  );

  if (snapshotsQuery.isLoading) {
    return (
      <div className="space-y-6">
        <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
          <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
          <div className="relative flex items-baseline gap-3">
            <EyebrowBreadcrumb section="snapshots" />
          </div>
          <h1 className="relative mt-2 font-mono text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
            {t("snapshots.title")}
          </h1>
        </header>
        <div className="space-y-3">
          {headerControls}
          <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}
          </div>
        </div>
      </div>
    );
  }

  const empty = (snapshotsQuery.data ?? []).length === 0;

  return (
    <div className="space-y-6">
      <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
        <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative flex items-baseline gap-3">
          <EyebrowBreadcrumb section="snapshots" />
        </div>
        <h1 className="relative mt-2 font-mono text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
          {t("snapshots.title")}
        </h1>
      </header>
      <div className="space-y-3">
        {headerControls}
        {empty ? (
          <EmptyState
            icon="💾"
            title={t("snapshots.empty.title")}
            body={t("snapshots.empty.body")}
            actions={
              <Button
                size="sm"
                variant="default"
                onClick={() => setCreateOpen(true)}
                disabled={create.isPending}
              >
                <Plus className="mr-1 h-3 w-3" />
                {t("snapshots.create_button")}
              </Button>
            }
          />
        ) : (
          <>
            <div className="text-xs text-muted-foreground">
              {t("snapshots.showing_n", { count: filtered.length })}
            </div>
            <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
              {filtered.map((s) => <SnapshotCard key={s.name} snapshot={s} />)}
            </div>
          </>
        )}
      </div>

      <AlertDialog
        open={createOpen}
        onOpenChange={(next) => {
          if (!next) setLabel("");
          setCreateOpen(next);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("snapshots.create_modal_title")}</AlertDialogTitle>
            <AlertDialogDescription>&nbsp;</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2">
            <label className="text-sm font-medium">{t("snapshots.create_label_label")}</label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              maxLength={128}
              disabled={create.isPending}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              placeholder={t("snapshots.create_label_placeholder")}
              autoFocus
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={create.isPending}>
              {t("confirm.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                create.mutate(label || undefined, {
                  onSettled: () => {
                    setCreateOpen(false);
                    setLabel("");
                  },
                })
              }
              disabled={create.isPending}
            >
              {create.isPending ? t("confirm.working") : t("snapshots.create_submit")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
