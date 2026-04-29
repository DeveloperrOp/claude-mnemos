import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { deleteSnapshot } from "@/api/snapshots.api";
import { extractApiError } from "@/lib/error";

export function useSnapshotDelete(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (name: string) => deleteSnapshot(project, name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["snapshots", project] });
      toast.success(t("snapshots.deleted_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
