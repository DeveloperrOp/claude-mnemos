import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { retryDeadLetter } from "@/api/dead_letter.api";
import { extractApiError } from "@/lib/error";

/**
 * Retry a job that landed in the dead-letter queue. Backend exposes retry
 * only for status="dead_letter" — `failed` jobs are auto-retried by the
 * worker until JOB_MAX_ATTEMPTS, after which they become dead_letter.
 */
export function useRetryJob() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (jobId: string) => retryDeadLetter(jobId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      void qc.invalidateQueries({ queryKey: ["dead-letter"] });
      toast.success(t("queue.retry_success"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
