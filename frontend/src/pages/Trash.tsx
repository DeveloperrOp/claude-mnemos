import { useState } from "react";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
import { useTrash } from "@/hooks/useTrash";
import { useDismissTrashBulk } from "@/hooks/useDismissTrashBulk";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TrashRow } from "@/components/widgets/TrashRow";
import { EmptyState } from "@/components/widgets/EmptyState";
import { ConfirmDialog } from "@/components/widgets/ConfirmDialog";

export function Trash() {
  const { name: project } = useParams<{ name: string }>();
  const { t } = useTranslation();
  const trashQuery = useTrash(project);
  const bulkDismiss = useDismissTrashBulk(project ?? "");
  const [bulkOpen, setBulkOpen] = useState(false);

  if (!project) return null;
  if (trashQuery.isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    );
  }

  const entries = trashQuery.data?.entries ?? [];
  if (entries.length === 0) {
    return (
      <EmptyState
        icon="🗑️"
        title={t("trash.empty.title")}
        body={t("trash.empty.body")}
      />
    );
  }

  const blockedEntries = entries.filter((e) => e.restorable === false);
  const blockedIds = blockedEntries.map((e) => e.trash_id);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          {t("trash.showing_n", { count: entries.length })}
        </div>
        {blockedEntries.length > 0 && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setBulkOpen(true)}
            disabled={bulkDismiss.isPending}
          >
            <Trash2 className="mr-1 h-3 w-3" />
            {t("trash.bulk.cleanup_blocked_button", { n: blockedEntries.length })}
          </Button>
        )}
      </div>
      {entries.map((e) => (
        <TrashRow key={e.trash_id} entry={e} />
      ))}

      <ConfirmDialog
        open={bulkOpen}
        onOpenChange={setBulkOpen}
        title={t("trash.bulk.cleanup_blocked_confirm_title")}
        description={t("trash.bulk.cleanup_blocked_confirm_body", {
          n: blockedEntries.length,
        })}
        confirmLabel={t("trash.bulk.cleanup_blocked_button", {
          n: blockedEntries.length,
        })}
        destructive
        isPending={bulkDismiss.isPending}
        onConfirm={() => {
          bulkDismiss.mutate(blockedIds, {
            onSettled: () => setBulkOpen(false),
          });
        }}
      />
    </div>
  );
}
