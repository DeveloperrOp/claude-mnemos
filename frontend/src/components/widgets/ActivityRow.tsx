import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { AlertTriangle, CheckCircle2, ChevronRight, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "./ConfirmDialog";
import { useActivityUndo } from "@/hooks/useActivityUndo";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/datetime";
import type { ActivityEntry } from "@/types/Activity";

interface Props {
  project: string;
  entry: ActivityEntry;
}

// NOTE: ActivityStatus is Literal["success"] only — "partial"/"failed" do not exist.
// The icon and color map therefore only needs "success". A quarantine flag in
// metadata is surfaced via a separate AlertTriangle icon so the UI can still
// signal problems without relying on non-existent status values.
const STATUS_COLOR: Record<"success", string> = {
  success: "text-success",
};

function EntryIcon({ entry }: { entry: ActivityEntry }) {
  // Quarantined entries get a warning triangle regardless of status.
  const quarantined =
    typeof entry.metadata["quarantined"] === "boolean" &&
    entry.metadata["quarantined"] === true;
  if (quarantined) {
    return <AlertTriangle className="h-4 w-4 shrink-0 text-warning" />;
  }
  return (
    <CheckCircle2
      className={cn("h-4 w-4 shrink-0", STATUS_COLOR[entry.status])}
    />
  );
}

export function ActivityRow({ project, entry: e }: Props) {
  const { t, i18n } = useTranslation();
  const [undoOpen, setUndoOpen] = useState(false);
  const undo = useActivityUndo();
  const canUndo = e.can_undo && !e.undone;

  return (
    <>
      <div className="flex items-center gap-3 rounded-md border bg-background px-3 py-2">
        <EntryIcon entry={e} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-medium">
              {t(`activity.op.${e.operation_type}`, e.operation_type)}
            </span>
            <span className="text-xs text-muted-foreground">
              {formatDateTime(e.timestamp, i18n.language)}
            </span>
          </div>
          {e.affected_pages.length > 0 && (
            <div className="text-xs text-muted-foreground">
              {t("activity.affected_pages", { count: e.affected_pages.length })}
            </div>
          )}
        </div>
        <Button asChild size="sm" variant="ghost">
          <Link to={`/project/${project}/activity/${e.id}`}>
            {t("activity.detail")}
            <ChevronRight className="ml-1 h-3 w-3" />
          </Link>
        </Button>
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

      <ConfirmDialog
        open={undoOpen}
        onOpenChange={setUndoOpen}
        title={t("activity.undo_modal_title")}
        description={t("activity.undo_modal_desc")}
        confirmLabel={t("activity.undo_button")}
        destructive
        onConfirm={() => undo.mutate(
          { project, op_id: e.id },
          { onSettled: () => setUndoOpen(false) },
        )}
        isPending={undo.isPending}
      />
    </>
  );
}
