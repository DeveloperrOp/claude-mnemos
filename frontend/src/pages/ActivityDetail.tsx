import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";
import { useActivityEntry } from "@/hooks/useActivityEntry";
import { useActivityUndo } from "@/hooks/useActivityUndo";
import { pageHref } from "@/lib/pageHref";
import { EyebrowBreadcrumb } from "@/components/EyebrowBreadcrumb";
import { formatDateTime } from "@/lib/datetime";

export function ActivityDetail() {
  const { name: project, opId } = useParams<{ name: string; opId: string }>();
  const { t, i18n } = useTranslation();
  const entryQuery = useActivityEntry(project, opId);
  const [undoOpen, setUndoOpen] = useState(false);
  const undo = useActivityUndo();

  if (entryQuery.isLoading) return <Skeleton className="h-64" />;
  if (entryQuery.isError) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t("activity.not_found_title")}</h1>
        <p className="text-muted-foreground">{opId}</p>
        <Link
          to={`/project/${project}/activity`}
          className="text-primary underline"
        >
          {t("activity.not_found_hint")}
        </Link>
      </div>
    );
  }

  const e = entryQuery.data!;
  const canUndo = e.can_undo && !e.undone;

  return (
    <>
      <article className="mx-auto max-w-3xl space-y-6">
        <header className="relative overflow-hidden rounded-lg border border-border/60 bg-card/40 px-5 py-4">
          <div className="grid-bg pointer-events-none absolute inset-0 opacity-30" />
          <div className="relative flex items-center justify-between gap-3">
            <EyebrowBreadcrumb section="activity" />
            <Link
              to={`/project/${project}/activity`}
              className="text-xs text-primary underline"
            >
              {t("common.back_arrow")}
            </Link>
          </div>
          <h1 className="relative mt-2 text-[clamp(1.5rem,3vw,2.25rem)] font-medium tracking-tight">
            {t(`activity.op.${e.operation_type}`, e.operation_type)}
          </h1>
          <p className="relative mt-2 text-xs text-muted-foreground">
            {e.id} · {formatDateTime(e.timestamp, i18n.language)}
          </p>
        </header>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!canUndo || undo.isPending}
            onClick={() => setUndoOpen(true)}
            title={t("activity.undo_button")}
          >
            <Undo2 className="mr-1 h-3 w-3" />
            {t("activity.undo_button")}
          </Button>
        </div>

        <div className="rounded-md border border-border/60 bg-card/40 p-4">
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground">{t("activity.field.status")}</dt>
            <dd>{t(`activity.status.${e.status}`, e.status)}</dd>

            {e.snapshot_path && (
              <>
                <dt className="text-muted-foreground">
                  {t("activity.snapshot")}
                </dt>
                <dd className="break-all">
                  <code>{e.snapshot_path}</code>
                </dd>
              </>
            )}

            <dt className="text-muted-foreground">{t("activity.field.undo")}</dt>
            <dd>
              {e.undone
                ? `${t("activity.undone")} ${e.undone_at ?? ""}`
                : canUndo
                  ? t("activity.can_undo")
                  : t("activity.cannot_undo")}
            </dd>
          </dl>
        </div>

        {e.affected_pages.length > 0 && (
          <section className="rounded-md border border-border/60 bg-card/40 p-4">
            <div className="section-rail mb-3">
              <span>{t("activity.affected_pages", { count: e.affected_pages.length })}</span>
              <span className="ml-auto font-mono tabular-nums text-foreground/70">{e.affected_pages.length}</span>
            </div>
            <ul className="stagger divide-y divide-border/50">
              {e.affected_pages.map((p, i) => (
                <li key={p} style={{ ["--i" as string]: i }} className="py-2 text-sm">
                  <Link
                    to={pageHref(project!, p)}
                    className="text-primary hover:underline"
                  >
                    {p}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="rounded-md border border-border/60 bg-card/40 p-4">
          <div className="section-rail mb-3">
            <span>{t("activity.metadata")}</span>
          </div>
          <pre className="overflow-x-auto rounded bg-muted p-3 text-xs">
            {JSON.stringify(e.metadata, null, 2)}
          </pre>
        </section>
      </article>

      <ConfirmDialog
        open={undoOpen}
        onOpenChange={setUndoOpen}
        title={t("activity.undo_modal_title")}
        description={t("activity.undo_modal_desc")}
        confirmLabel={t("activity.undo_button")}
        destructive
        onConfirm={() => {
          if (!project) return;
          undo.mutate(
            { project, op_id: e.id },
            { onSettled: () => setUndoOpen(false) },
          );
        }}
        isPending={undo.isPending}
      />
    </>
  );
}
