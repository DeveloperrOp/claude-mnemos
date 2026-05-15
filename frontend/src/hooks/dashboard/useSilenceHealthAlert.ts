import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postSilenceAlert } from "@/api/health_alerts.api";

export function useSilenceHealthAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, duration_hours }: { id: string; duration_hours: number }) =>
      postSilenceAlert(id, { duration_hours }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["health-alerts"] });
    },
  });
}
