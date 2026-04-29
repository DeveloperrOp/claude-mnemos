import { useTranslation } from "react-i18next";
import { RotateCcw, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { KindBadge, type KindTone } from "./KindBadge";
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
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <span className="break-all font-mono text-xs">{s.name}</span>
          <KindBadge label={t(`snapshots.kind.${s.kind}`)} tone={KIND_TONE[s.kind]} />
        </div>
      </CardHeader>
      <CardContent className="space-y-1 text-xs">
        <div className="text-[hsl(var(--muted-foreground))]">{s.timestamp}</div>
        {s.label && (
          <div>
            <span className="text-[hsl(var(--muted-foreground))]">{t("snapshots.label")}: </span>
            <span>{s.label}</span>
          </div>
        )}
        {s.op_id && (
          <div className="text-[hsl(var(--muted-foreground))]">
            {t("snapshots.op_id")}: <code>{s.op_id}</code>
            {s.op_type && (
              <>
                {" · "}{t("snapshots.op_type")}: <code>{s.op_type}</code>
              </>
            )}
          </div>
        )}
        <div className="text-[hsl(var(--muted-foreground))]">
          {t("snapshots.size")}: {formatBytes(s.size_bytes)}
        </div>
        <div className="flex items-center gap-2 pt-2">
          <Button size="sm" variant="outline" disabled title={t("snapshots.restore_disabled")}>
            <RotateCcw className="mr-1 h-3 w-3" />
            {t("snapshots.restore_disabled")}
          </Button>
          <Button size="sm" variant="outline" disabled title={t("snapshots.delete_disabled")}>
            <Trash2 className="mr-1 h-3 w-3" />
            {t("snapshots.delete_disabled")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
