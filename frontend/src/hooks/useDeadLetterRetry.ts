import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { retryDeadLetter } from "@/api/dead_letter.api";
import { extractApiError } from "@/lib/error";

export function useDeadLetterRetry() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (jobId: string) => retryDeadLetter(jobId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dead-letter"] });
      void qc.invalidateQueries({ queryKey: ["dead-letter-entry"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
      toast.success(t("dead_letter.retried_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
