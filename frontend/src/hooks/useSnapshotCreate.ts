import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { createSnapshot } from "@/api/snapshots.api";
import { extractApiError } from "@/lib/error";

export function useSnapshotCreate(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (label?: string) => createSnapshot(project, label),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["snapshots", project] });
      toast.success(t("snapshots.created_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
