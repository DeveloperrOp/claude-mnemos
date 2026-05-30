import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, RotateCcw, Trash2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { KindBadge, type KindTone } from "./KindBadge";
import { ConfirmDialog } from "./ConfirmDialog";
import { TypedConfirmDialog } from "./TypedConfirmDialog";
import {
  useSnapshotTrash,
  useTrashPurge,
  useTrashRestore,
} from "@/hooks/useSnapshotTrash";
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

function TrashRow({
  snapshot: s,
  project,
}: {
  snapshot: SnapshotInfo;
  project: string;
}) {
  const { t, i18n } = useTranslation();
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [purgeOpen, setPurgeOpen] = useState(false);
  const restore = useTrashRestore(project);
  const purge = useTrashPurge(project);

  return (
    <>
      <Card className="bg-muted/20">
        <CardContent className="flex flex-wrap items-center justify-between gap-2 py-3 text-xs">
          <div className="min-w-0 space-y-0.5">
            <div className="flex items-center gap-2">
              <span className="break-all font-mono">{s.name}</span>
              <KindBadge label={t(`snapshots.kind.${s.kind}`)} tone={KIND_TONE[s.kind]} />
            </div>
            <div className="text-muted-foreground">
              {formatDateTime(s.timestamp, i18n.language)} · {formatBytes(s.size_bytes)}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={restore.isPending}
              onClick={() => setRestoreOpen(true)}
            >
              <RotateCcw className="mr-1 h-3 w-3" />
              {t("snapshots.trash.restore_button", "Восстановить")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={purge.isPending}
              onClick={() => setPurgeOpen(true)}
            >
              <Trash2 className="mr-1 h-3 w-3" />
              {t("snapshots.trash.purge_button", "Удалить навсегда")}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Restore: recoverable, plain confirm. */}
      <ConfirmDialog
        open={restoreOpen}
        onOpenChange={setRestoreOpen}
        title={t("snapshots.trash.restore_modal_title", "Восстановить снимок?")}
        description={t(
          "snapshots.trash.restore_modal_desc",
          "Снимок вернётся в список снимков. Восстановления самого хранилища это не запускает.",
        )}
        confirmLabel={t("snapshots.trash.restore_button", "Восстановить")}
        onConfirm={() => {
          restore.mutate(s.name, { onSettled: () => setRestoreOpen(false) });
        }}
        isPending={restore.isPending}
      />

      {/* Purge: truly irreversible — typed confirm gates on the name. */}
      <TypedConfirmDialog
        open={purgeOpen}
        onOpenChange={setPurgeOpen}
        title={t("snapshots.trash.purge_modal_title", "Удалить снимок навсегда?")}
        description={t(
          "snapshots.trash.purge_modal_desc",
          "Снимок будет удалён безвозвратно. Восстановить его будет невозможно.",
        )}
        expectedPhrase={s.name}
        phraseLabel={t("snapshots.trash.purge_typed_label", "Введите имя снимка для подтверждения")}
        confirmLabel={t("snapshots.trash.purge_button", "Удалить навсегда")}
        onConfirm={() => {
          purge.mutate(s.name, { onSettled: () => setPurgeOpen(false) });
        }}
        isPending={purge.isPending}
      />
    </>
  );
}

export function SnapshotTrashSection({ project }: { project: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const { data } = useSnapshotTrash(project);

  const items = data ?? [];
  // Keep the page clean when there's nothing deleted.
  if (items.length === 0) return null;

  return (
    <div className="space-y-3 border-t pt-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
      >
        {open ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        {t("snapshots.trash.title", "Корзина снимков")} ({items.length})
      </button>
      {open && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            {t(
              "snapshots.trash.hint",
              "Удалённые снимки хранятся здесь, пока их возраст не превысит срок хранения, после чего удаляются автоматически. Можно восстановить или удалить навсегда вручную.",
            )}
          </p>
          {items.map((s) => (
            <TrashRow key={s.name} snapshot={s} project={project} />
          ))}
        </div>
      )}
    </div>
  );
}
