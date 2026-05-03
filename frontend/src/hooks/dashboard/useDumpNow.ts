import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { postDumpNow, type DumpNowBody } from "@/api/dashboard.api";
import { extractApiError } from "@/lib/error";

interface Args {
  sessionId: string;
  body: DumpNowBody;
}

export function useDumpNow() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({ sessionId, body }: Args) => postDumpNow(sessionId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dashboard-snapshot"] });
      void qc.invalidateQueries({ queryKey: ["sessions"] });
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      toast.success(t("overview.dump_now.toast_success"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
