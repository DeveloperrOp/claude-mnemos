import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { apiClient } from "@/api/client";
import { extractApiError } from "@/lib/error";

export interface ImportBulkBody {
  project_name: string;
  extract?: boolean;
  limit?: number;
}

export interface ImportBulkResponse {
  queued: number;
  skipped: number;
  session_ids: string[];
}

export function useImportBulkLostSessions() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation<ImportBulkResponse, Error, ImportBulkBody>({
    mutationFn: async (body) => {
      const r = await apiClient.post<ImportBulkResponse>(
        "/lost-sessions/import-bulk",
        body,
      );
      return r.data;
    },
    onSuccess: (data, vars) => {
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      void qc.invalidateQueries({ queryKey: ["jobs", vars.project_name] });
      void qc.invalidateQueries({ queryKey: ["sessions", vars.project_name] });
      toast.success(
        t("sessions.bulk_import.success", { queued: data.queued }),
      );
      if (data.skipped > 0) {
        toast.warning(
          t("sessions.bulk_import.skipped", { skipped: data.skipped }),
        );
      }
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
