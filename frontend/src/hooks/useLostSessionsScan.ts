import { useMutation, useQueryClient } from "@tanstack/react-query";
import { scanLostSessions } from "@/api/lost_sessions.api";

export function useLostSessionsScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: scanLostSessions,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
    },
  });
}
