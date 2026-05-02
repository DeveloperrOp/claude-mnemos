import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { deleteTrash } from "@/api/trash.api";
import { extractApiError } from "@/lib/error";

export function useDismissTrashBulk(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: async (trashIds: string[]) => {
      for (const id of trashIds) {
        await deleteTrash(project, id);
      }
    },
    onSuccess: (_data, trashIds) => {
      void qc.invalidateQueries({ queryKey: ["trash", project] });
      toast.success(
        t("trash.bulk.cleanup_success_toast", { count: trashIds.length }),
      );
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
