import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postDismissAlert } from "@/api/health_alerts.api";

export function useDismissHealthAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => postDismissAlert(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["health-alerts"] });
    },
  });
}
