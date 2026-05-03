import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postScanActive } from "@/api/dashboard.api";

export function useScanActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postScanActive,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dashboard-snapshot"] });
    },
  });
}
