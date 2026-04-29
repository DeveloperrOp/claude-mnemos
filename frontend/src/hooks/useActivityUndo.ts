import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { undoOperation } from "@/api/activity.api";
import { extractApiError } from "@/lib/error";

interface UndoArgs {
  project: string;
  op_id: string;
}

export function useActivityUndo() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ project, op_id }: UndoArgs) => undoOperation(project, op_id),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["activity"] });
      void qc.invalidateQueries({ queryKey: ["pages", vars.project] });
      void qc.invalidateQueries({ queryKey: ["sessions", vars.project] });
      void qc.invalidateQueries({ queryKey: ["trash", vars.project] });
      toast.success(t("activity.undone_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
