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
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(
        t("health.alerts.silence_error", {
          defaultValue: "Failed to snooze alert: {{error}}",
          error: msg,
        }),
      );
    },
  });
}
