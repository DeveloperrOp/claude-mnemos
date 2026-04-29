import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ignoreLostSession, type IgnoreLostSessionBody } from "@/api/lost_sessions.api";
import { extractApiError } from "@/lib/error";

interface IgnoreArgs {
  session_id: string;
  body: IgnoreLostSessionBody;
}

export function useLostSessionIgnore() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ session_id, body }: IgnoreArgs) => ignoreLostSession(session_id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      toast.success(t("lost_sessions.ignored_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
