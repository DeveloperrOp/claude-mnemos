import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { dismissAlert, dismissAllAlerts } from "@/api/alerts.api";
import { extractApiError } from "@/lib/error";

export function useDismissAlert() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (id: string) => dismissAlert(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["alerts"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
    },
    onError: (err) => toast.error(extractApiError(err) || t("health.alerts.error")),
  });
}

export function useDismissAllAlerts() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (ids: string[]) => dismissAllAlerts(ids),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["alerts"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
      toast.success(t("health.alerts.cleared_all_toast"));
    },
    onError: (err) => toast.error(extractApiError(err) || t("health.alerts.error")),
  });
}
