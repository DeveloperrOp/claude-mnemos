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
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(t("lost_sessions.scan_error", { defaultValue: "Scan failed: {{error}}", error: msg }));
    },
  });
}
