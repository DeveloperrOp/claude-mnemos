import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { restoreSnapshot } from "@/api/snapshots.api";
import { extractApiError } from "@/lib/error";

export function useSnapshotRestore(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (name: string) => restoreSnapshot(project, name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["snapshots", project] });
      void qc.invalidateQueries({ queryKey: ["pages", project] });
      void qc.invalidateQueries({ queryKey: ["sessions", project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("snapshots.restored_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
