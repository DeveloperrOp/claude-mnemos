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
    onError: (err: Error) => {
      toast.error(t("health.dismiss_error", { message: err.message }));
    },
  });
}
