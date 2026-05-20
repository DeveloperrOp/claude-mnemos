import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { postSilenceAlert } from "@/api/health_alerts.api";

export function useSilenceHealthAlert() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ id, duration_hours }: { id: string; duration_hours: number }) =>
      postSilenceAlert(id, { duration_hours }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["health-alerts"] });
    },
    onError: (err: Error) => {
      toast.error(t("health.silence_error", { message: err.message }));
    },
  });
}
