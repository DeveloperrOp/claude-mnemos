import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { dismissDeadLetter } from "@/api/dead_letter.api";
import { extractApiError } from "@/lib/error";

export function useDeadLetterDismiss() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (jobId: string) => dismissDeadLetter(jobId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dead-letter"] });
      void qc.invalidateQueries({ queryKey: ["dead-letter-entry"] });
      toast.success(t("dead_letter.dismissed_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
