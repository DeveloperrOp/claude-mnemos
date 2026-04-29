import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { rejectSuggestion } from "@/api/suggestions.api";
import { extractApiError } from "@/lib/error";

export function useSuggestionReject(project: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (id: string) => rejectSuggestion(project, id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["suggestions", project] });
      toast.success(t("suggestions.rejected_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
