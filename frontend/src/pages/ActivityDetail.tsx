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

export function ActivityDetail() {
  const { name: project, opId } = useParams<{ name: string; opId: string }>();
  const { t } = useTranslation();
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
      <article className="mx-auto max-w-2xl space-y-4">
        <div className="flex items-center justify-between">
          <Link
            to={`/project/${project}/activity`}
            className="text-sm text-primary underline"
          >
            ← {t("navigation.activity")}
          </Link>
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

        <header className="space-y-2 border-b pb-4">
          <h1 className="text-xl font-semibold">
            {t(`activity.op.${e.operation_type}`, e.operation_type)}
          </h1>
          <p className="text-xs text-muted-foreground">
            {e.id} · {e.timestamp}
          </p>
        </header>

        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted-foreground">status</dt>
          <dd>{e.status}</dd>

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

          <dt className="text-muted-foreground">undo</dt>
          <dd>
            {e.undone
              ? `${t("activity.undone")} ${e.undone_at ?? ""}`
              : canUndo
                ? t("activity.can_undo")
                : t("activity.cannot_undo")}
          </dd>
        </dl>

        {e.affected_pages.length > 0 && (
          <section>
            <h2 className="mb-2 text-sm font-semibold">
              {t("activity.affected_pages", { count: e.affected_pages.length })}
            </h2>
            <ul className="space-y-1 text-sm">
              {e.affected_pages.map((p) => (
                <li key={p}>
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

        <section>
          <h2 className="mb-2 text-sm font-semibold">{t("activity.metadata")}</h2>
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
