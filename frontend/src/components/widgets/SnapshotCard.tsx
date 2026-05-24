import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { RotateCcw, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { KindBadge, type KindTone } from "./KindBadge";
import { ConfirmDialog } from "./ConfirmDialog";
import { TypedConfirmDialog } from "./TypedConfirmDialog";
import { SnapshotRestorePreview } from "./SnapshotRestorePreview";
import { useSnapshotDelete } from "@/hooks/useSnapshotDelete";
import { useSnapshotRestore } from "@/hooks/useSnapshotRestore";
import { formatDateTime } from "@/lib/datetime";
import type { SnapshotInfo, SnapshotKind } from "@/types/Snapshot";

const KIND_TONE: Record<SnapshotKind, KindTone> = {
  "pre-op": "amber",
  daily: "blue",
  manual: "emerald",
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function SnapshotCard({ snapshot: s }: { snapshot: SnapshotInfo }) {
  const { t, i18n } = useTranslation();
  const { name: project } = useParams<{ name: string }>();
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const restore = useSnapshotRestore(project ?? "");
  const remove = useSnapshotDelete(project ?? "");

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <span className="break-all font-mono text-xs">{s.name}</span>
            <KindBadge label={t(`snapshots.kind.${s.kind}`)} tone={KIND_TONE[s.kind]} />
          </div>
        </CardHeader>
        <CardContent className="space-y-1 text-xs">
          <div className="text-muted-foreground">{formatDateTime(s.timestamp, i18n.language)}</div>
          {s.label && (
            <div>
              <span className="text-muted-foreground">{t("snapshots.label")}: </span>
              <span>{s.label}</span>
            </div>
          )}
          {s.op_id && (
            <div className="text-muted-foreground">
              {t("snapshots.op_id")}: <code>{s.op_id}</code>
              {s.op_type && (
                <>
                  {" · "}{t("snapshots.op_type")}: <code>{s.op_type}</code>
                </>
              )}
            </div>
          )}
          <div className="text-muted-foreground">
            {t("snapshots.size")}: {formatBytes(s.size_bytes)}
          </div>
          <div className="flex items-center gap-2 pt-2">
            <Button
              size="sm"
              variant="outline"
              disabled={restore.isPending}
              onClick={() => setRestoreOpen(true)}
              title={t("snapshots.restore_button")}
            >
              <RotateCcw className="mr-1 h-3 w-3" />
              {t("snapshots.restore_button")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={remove.isPending}
              onClick={() => setDeleteOpen(true)}
              title={t("snapshots.delete_button")}
            >
              <Trash2 className="mr-1 h-3 w-3" />
              {t("snapshots.delete_button")}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Restore: recoverable (vault file changes only; other snapshots exist
          to re-restore from). Visual safety = preview of file diff. Plain
          confirm — no typed input gate. */}
      <ConfirmDialog
        open={restoreOpen}
        onOpenChange={setRestoreOpen}
        title={t("snapshots.restore_modal_title")}
        description={t("snapshots.restore_modal_desc")}
        confirmLabel={t("snapshots.restore_button")}
        destructive
        extraContent={
          project ? (
            <SnapshotRestorePreview
              project={project}
              name={s.name}
              enabled={restoreOpen}
            />
          ) : null
        }
        onConfirm={() => {
          restore.mutate(s.name, { onSettled: () => setRestoreOpen(false) });
        }}
        isPending={restore.isPending}
      />

      {/* Delete: truly irreversible (snapshot is gone forever, no other
          backup to restore from). TypedConfirmDialog gates on the snapshot
          name to force the user to look at what they're about to lose. */}
      <TypedConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("snapshots.delete_modal_title")}
        description={t("snapshots.delete_modal_desc")}
        expectedPhrase={s.name}
        phraseLabel={t("snapshots.delete_typed_label")}
        confirmLabel={t("snapshots.delete_button")}
        onConfirm={() => {
          remove.mutate(s.name, { onSettled: () => setDeleteOpen(false) });
        }}
        isPending={remove.isPending}
      />
    </>
  );
}
