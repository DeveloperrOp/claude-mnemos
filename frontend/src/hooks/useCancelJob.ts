import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { cancelJob } from "@/api/jobs.api";
import { extractApiError } from "@/lib/error";

export function useCancelJob() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (jobId: string) => cancelJob(jobId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      toast.success(t("queue.cancel_success"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
