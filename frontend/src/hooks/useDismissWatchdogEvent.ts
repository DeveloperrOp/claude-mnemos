import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  dismissWatchdogEvent,
  dismissAllWatchdogEvents,
} from "@/api/watchdog_events.api";
import { extractApiError } from "@/lib/error";

export function useDismissWatchdogEvent() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (id: string) => dismissWatchdogEvent(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["watchdog-events"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
    },
    onError: (err) => toast.error(extractApiError(err) || t("health.alerts.error")),
  });
}

export function useDismissAllWatchdogEvents() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (ids: string[]) => dismissAllWatchdogEvents(ids),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["watchdog-events"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
      toast.success(t("health.alerts.cleared_all_toast"));
    },
    onError: (err) => toast.error(extractApiError(err) || t("health.alerts.error")),
  });
}
