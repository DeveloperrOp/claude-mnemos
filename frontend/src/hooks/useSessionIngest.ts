import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ingestSession } from "@/api/sessions.api";
import { extractApiError } from "@/lib/error";

interface IngestArgs {
  project: string;
  session_id: string;
  transcript_path: string;
  /** Run LLM extraction in addition to raw dump. */
  extract?: boolean;
}

export function useSessionIngest() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({
      project,
      session_id,
      transcript_path,
      extract = false,
    }: IngestArgs) =>
      ingestSession(project, session_id, transcript_path, extract),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["session", vars.project, vars.session_id] });
      void qc.invalidateQueries({ queryKey: ["sessions", vars.project] });
      void qc.invalidateQueries({ queryKey: ["pages", vars.project] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
      toast.success(t("sessions.ingested_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
