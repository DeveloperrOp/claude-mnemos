import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { restoreTrash } from "@/api/trash.api";
import { extractApiError } from "@/lib/error";

export function useTrashRestore(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (trash_id: string) => restoreTrash(project, trash_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["trash", project] });
      void qc.invalidateQueries({ queryKey: ["pages", project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("trash.restored_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
