import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { deleteTrash } from "@/api/trash.api";
import { extractApiError } from "@/lib/error";

export function useTrashDelete(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (trash_id: string) => deleteTrash(project, trash_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["trash", project] });
      toast.success(t("trash.permanently_deleted_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
