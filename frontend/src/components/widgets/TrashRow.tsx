import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { Trash2, RotateCcw, AlertTriangle, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "./ConfirmDialog";
import { TypedConfirmDialog } from "./TypedConfirmDialog";
import { useTrashRestore } from "@/hooks/useTrashRestore";
import { useTrashDelete } from "@/hooks/useTrashDelete";
import { pageBasename } from "@/lib/pageBasename";
import { formatDateTime } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import type { TrashEntry } from "@/types/Trash";

export function TrashRow({ entry: e }: { entry: TrashEntry }) {
  const { t, i18n } = useTranslation();
  const { name: project } = useParams<{ name: string }>();
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const restore = useTrashRestore(project ?? "");
  const remove = useTrashDelete(project ?? "");

  const displayName = e.page_basename ?? (e.original_path ? pageBasename(e.original_path) : e.trash_id);

  return (
    <>
      <div className="flex items-center gap-3 rounded-md border bg-[hsl(var(--background))] px-3 py-2 text-sm">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono">
              {e.page_basename ?? e.original_path ?? e.trash_id}
            </span>
            {e.operation_type && (
              <span className="rounded bg-[hsl(var(--muted))] px-1.5 py-0.5 text-xs text-[hsl(var(--muted-foreground))]">
                {e.operation_type}
              </span>
            )}
          </div>
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            {t("trash.deleted_at")}: {formatDateTime(e.deleted_at, i18n.language)}
          </div>
          {!e.restorable && e.restore_blocked_reason && (
            <div className="mt-1 flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400">
              <AlertTriangle className="h-3 w-3" />
              <span>{t("trash.blocked")}: {e.restore_blocked_reason}</span>
            </div>
          )}
        </div>
        <div
          className={cn(
            "flex items-center gap-1 text-xs",
            e.restorable ? "text-emerald-600" : "text-zinc-500",
          )}
        >
          {e.restorable ? <Check className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
          <span>{t("trash.restorable")}</span>
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={!e.restorable || restore.isPending}
          onClick={() => setRestoreOpen(true)}
          title={e.restorable ? t("trash.restore_button") : t("trash.blocked")}
        >
          <RotateCcw className="mr-1 h-3 w-3" />
          {t("trash.restore_button")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={remove.isPending}
          onClick={() => setDeleteOpen(true)}
          title={t("trash.delete_permanent_button")}
        >
          <Trash2 className="mr-1 h-3 w-3" />
          {t("trash.delete_permanent_button")}
        </Button>
      </div>

      <ConfirmDialog
        open={restoreOpen}
        onOpenChange={setRestoreOpen}
        title={t("trash.restore_modal_title")}
        description={t("trash.restore_modal_desc", { name: displayName })}
        confirmLabel={t("trash.restore_button")}
        onConfirm={() => {
          restore.mutate(e.trash_id, { onSettled: () => setRestoreOpen(false) });
        }}
        isPending={restore.isPending}
      />

      <TypedConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("trash.delete_permanent_modal_title")}
        description={t("trash.delete_permanent_modal_desc")}
        expectedPhrase={displayName}
        phraseLabel={t("trash.delete_permanent_typed_label")}
        confirmLabel={t("trash.delete_permanent_button")}
        onConfirm={() => {
          remove.mutate(e.trash_id, { onSettled: () => setDeleteOpen(false) });
        }}
        isPending={remove.isPending}
      />
    </>
  );
}
