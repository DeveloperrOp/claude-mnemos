import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { scanLostSessions } from "@/api/lost_sessions.api";

export function useLostSessionsScan() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: scanLostSessions,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
    },
    onError: (err: Error) => {
      toast.error(t("lost_sessions.scan_error", { message: err.message }));
    },
  });
}
