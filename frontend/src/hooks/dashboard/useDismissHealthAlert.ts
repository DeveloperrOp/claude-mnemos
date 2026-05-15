import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { postDismissAlert } from "@/api/health_alerts.api";

export function useDismissHealthAlert() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (id: string) => postDismissAlert(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["health-alerts"] });
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(
        t("health.alerts.dismiss_error", {
          defaultValue: "Failed to dismiss alert: {{error}}",
          error: msg,
        }),
      );
    },
  });
}
