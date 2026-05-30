import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { listTrash, purgeFromTrash, restoreFromTrash } from "@/api/snapshots.api";
import { extractApiError } from "@/lib/error";

/** Soft-deleted snapshots (the `_trash-*` dirs) for a project. */
export function useSnapshotTrash(project: string | undefined) {
  return useQuery({
    queryKey: ["snapshots-trash", project],
    queryFn: () => listTrash(project!),
    enabled: !!project,
    refetchInterval: 30_000,
  });
}

export function useTrashRestore(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (name: string) => restoreFromTrash(project, name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["snapshots", project] });
      void qc.invalidateQueries({ queryKey: ["snapshots-trash", project] });
      toast.success(t("snapshots.trash.restored_toast", "Снимок восстановлен"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}

export function useTrashPurge(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (name: string) => purgeFromTrash(project, name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["snapshots-trash", project] });
      toast.success(t("snapshots.trash.purged_toast", "Снимок удалён навсегда"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
