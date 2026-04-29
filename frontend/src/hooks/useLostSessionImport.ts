import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { importLostSession, type ImportLostSessionBody } from "@/api/lost_sessions.api";
import { extractApiError } from "@/lib/error";

interface ImportArgs {
  session_id: string;
  body: ImportLostSessionBody;
}

export function useLostSessionImport() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ session_id, body }: ImportArgs) => importLostSession(session_id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      void qc.invalidateQueries({ queryKey: ["dead-letter"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
      void qc.invalidateQueries({ queryKey: ["sessions"] });
      toast.success(t("lost_sessions.imported_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
