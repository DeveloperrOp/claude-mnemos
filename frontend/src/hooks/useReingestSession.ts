import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ingestSession } from "@/api/sessions.api";
import { extractApiError } from "@/lib/error";

interface ReingestArgs {
  project: string;
  session_id: string;
  transcript_path: string;
  /** Run LLM extraction in addition to raw dump (burns tokens). */
  extract?: boolean;
  /** Override the per-extract input-token cap. */
  maxInputTokens?: number;
  /** Split a large transcript into chunks for extraction. */
  chunked?: boolean;
}

/**
 * Re-queue an existing session for ingest. Same backend endpoint as
 * useSessionIngest but with a re-ingest-flavored toast pointing the user
 * to the Queue page.
 */
export function useReingestSession() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: ({
      project,
      session_id,
      transcript_path,
      extract = false,
      maxInputTokens,
      chunked,
    }: ReingestArgs) =>
      ingestSession(project, session_id, transcript_path, extract, {
        maxInputTokens,
        chunked,
      }),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["session", vars.project, vars.session_id] });
      void qc.invalidateQueries({ queryKey: ["sessions", vars.project] });
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success(t("sessions.reingest_toast"));
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
