import { useTranslation } from "react-i18next";
import { useSnapshotPreview } from "@/hooks/useSnapshotPreview";

interface Props {
  project: string;
  name: string;
  enabled: boolean;
}

function FileList({ title, files }: { title: string; files: string[] }) {
  if (files.length === 0) return null;
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      <ul className="space-y-0.5">
        {files.map((f) => (
          <li key={f} className="text-xs font-mono text-foreground truncate">
            {f}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SnapshotRestorePreview({ project, name, enabled }: Props) {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useSnapshotPreview(project, name, enabled);

  if (!enabled) return null;
  if (isLoading) return <p className="text-xs text-muted-foreground">{t("common.loading")}</p>;
  if (isError || !data) return <p className="text-xs text-destructive">{t("snapshots.preview.error")}</p>;

  const hasChanges =
    data.will_create.length > 0 ||
    data.will_overwrite.length > 0 ||
    data.will_delete.length > 0;

  return (
    <div className="mt-3 space-y-3 text-sm">
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-muted-foreground">{t("snapshots.preview.files_in_snapshot")}: </span>
          <span>{data.snapshot_file_count}</span>
        </div>
        <div>
          <span className="text-muted-foreground">{t("snapshots.preview.files_in_vault")}: </span>
          <span>{data.vault_file_count}</span>
        </div>
        {data.unchanged_count > 0 && (
          <div>
            <span className="text-muted-foreground">{t("snapshots.preview.unchanged")}: </span>
            <span>{data.unchanged_count}</span>
          </div>
        )}
      </div>

      {!hasChanges && (
        <p className="text-xs text-muted-foreground">{t("snapshots.preview.no_changes")}</p>
      )}

      <FileList title={t("snapshots.preview.will_create")} files={data.will_create} />
      <FileList title={t("snapshots.preview.will_overwrite")} files={data.will_overwrite} />
      <FileList title={t("snapshots.preview.will_delete")} files={data.will_delete} />

      {data.truncated && (
        <p className="text-xs text-amber-500">{t("snapshots.preview.truncated")}</p>
      )}
    </div>
  );
}
