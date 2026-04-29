import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { approveSuggestion } from "@/api/suggestions.api";
import { extractApiError } from "@/lib/error";

export function useSuggestionApprove(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (id: string) => approveSuggestion(project, id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["suggestions", project] });
      void qc.invalidateQueries({ queryKey: ["pages", project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("suggestions.approved_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
