import { useTranslation } from "react-i18next";
import { useSnapshotPreview } from "@/hooks/useSnapshotPreview";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/datetime";

interface Props {
  project: string;
  name: string;
  /** Only fetch when the dialog is open. */
  enabled: boolean;
}

function FileList({ label, paths, tone }: { label: string; paths: string[]; tone: string }) {
  if (paths.length === 0) return null;
  return (
    <div className="space-y-1">
      <div className={`text-xs font-medium ${tone}`}>{label} ({paths.length})</div>
      <ul className="max-h-24 overflow-y-auto rounded border border-border/40 bg-background/60 px-2 py-1 font-mono text-[11px]">
        {paths.map((p) => (
          <li key={p} className="truncate text-muted-foreground">{p}</li>
        ))}
      </ul>
    </div>
  );
}

export function SnapshotRestorePreview({ project, name, enabled }: Props) {
  const { t, i18n } = useTranslation();
  const q = useSnapshotPreview(project, name, enabled);

  if (!enabled) return null;
  if (q.isLoading) return <Skeleton className="h-32 w-full" />;
  if (q.isError || !q.data) {
    return (
      <div className="rounded border border-rose-500/40 bg-rose-500/5 px-3 py-2 text-xs text-rose-500">
        {t("snapshots.preview.error")}
      </div>
    );
  }

  const p = q.data;
  const totalChanges = p.will_create.length + p.will_delete.length + p.will_overwrite.length;

  return (
    <div className="space-y-3 rounded-md border border-border/60 bg-card/40 p-3 text-sm">
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <div className="text-muted-foreground">{t("snapshots.preview.created")}</div>
          <div className="font-mono">{formatDateTime(p.snapshot_timestamp, i18n.language)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">{t("snapshots.preview.files_in_snapshot")}</div>
          <div className="font-mono">{p.snapshot_file_count}</div>
        </div>
        <div>
          <div className="text-muted-foreground">{t("snapshots.preview.files_in_vault")}</div>
          <div className="font-mono">{p.vault_file_count}</div>
        </div>
        <div>
          <div className="text-muted-foreground">{t("snapshots.preview.unchanged")}</div>
          <div className="font-mono">{p.unchanged_count}</div>
        </div>
      </div>

      {totalChanges === 0 ? (
        <div className="rounded border border-emerald-500/40 bg-emerald-500/5 px-2 py-1.5 text-xs text-emerald-600 dark:text-emerald-400">
          {t("snapshots.preview.no_changes")}
        </div>
      ) : (
        <div className="space-y-2">
          <FileList
            label={t("snapshots.preview.will_create")}
            paths={p.will_create}
            tone="text-emerald-600 dark:text-emerald-400"
          />
          <FileList
            label={t("snapshots.preview.will_overwrite")}
            paths={p.will_overwrite}
            tone="text-amber-600 dark:text-amber-400"
          />
          <FileList
            label={t("snapshots.preview.will_delete")}
            paths={p.will_delete}
            tone="text-rose-600 dark:text-rose-400"
          />
          {p.truncated && (
            <div className="text-[11px] text-muted-foreground">
              {t("snapshots.preview.truncated", { limit: p.sample_limit })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
