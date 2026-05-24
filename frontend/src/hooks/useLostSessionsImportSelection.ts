import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  importLostSessionsSelection,
  type ImportSelectionResponse,
} from "@/api/lost_sessions.api";
import { extractApiError } from "@/lib/error";
import type { LostSession } from "@/types/LostSession";

export interface ImportSelectionArgs {
  selected: LostSession[];
  extract?: boolean;
}

export interface ImportSelectionAggregate {
  total_queued: number;
  total_skipped: number;
  total_missing: number;
  per_project: { project_name: string; result: ImportSelectionResponse }[];
}

function groupByProject(selected: LostSession[]): Map<string, string[]> {
  const m = new Map<string, string[]>();
  for (const s of selected) {
    const arr = m.get(s.project_name) ?? [];
    arr.push(s.session_id);
    m.set(s.project_name, arr);
  }
  return m;
}

export function useLostSessionsImportSelection() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: async ({
      selected,
      // Default `false` matches backend v0.0.10 contract — extraction (which
      // burns LLM tokens) is opt-in. Bulk-import callers that want extraction
      // must pass `extract: true` explicitly (e.g. via a checkbox).
      extract = false,
    }: ImportSelectionArgs): Promise<ImportSelectionAggregate> => {
      const groups = groupByProject(selected);
      const results = await Promise.all(
        Array.from(groups.entries()).map(async ([project_name, session_ids]) => {
          const r = await importLostSessionsSelection({
            project_name,
            session_ids,
            extract,
          });
          return { project_name, result: r };
        }),
      );
      const total_queued = results.reduce((n, r) => n + r.result.queued, 0);
      const total_skipped = results.reduce((n, r) => n + r.result.skipped, 0);
      const total_missing = results.reduce(
        (n, r) => n + r.result.missing.length,
        0,
      );
      return { total_queued, total_skipped, total_missing, per_project: results };
    },
    onSuccess: (agg) => {
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      void qc.invalidateQueries({ queryKey: ["dead-letter"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
      void qc.invalidateQueries({ queryKey: ["sessions"] });
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      toast.success(
        t("lost_sessions.selection.import_toast", {
          n: agg.total_queued,
        }),
      );
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
