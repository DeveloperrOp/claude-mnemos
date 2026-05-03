import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  ignoreLostSessionsSelection,
  type IgnoreSelectionResponse,
} from "@/api/lost_sessions.api";
import { extractApiError } from "@/lib/error";
import type { LostSession } from "@/types/LostSession";

export interface IgnoreSelectionArgs {
  selected: LostSession[];
}

export interface IgnoreSelectionAggregate {
  total_added: number;
  per_project: { project_name: string; result: IgnoreSelectionResponse }[];
}

function groupShasByProject(selected: LostSession[]): Map<string, string[]> {
  const m = new Map<string, string[]>();
  for (const s of selected) {
    const arr = m.get(s.project_name) ?? [];
    arr.push(s.sha);
    m.set(s.project_name, arr);
  }
  return m;
}

export function useLostSessionsIgnoreSelection() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: async ({
      selected,
    }: IgnoreSelectionArgs): Promise<IgnoreSelectionAggregate> => {
      const groups = groupShasByProject(selected);
      const results = await Promise.all(
        Array.from(groups.entries()).map(async ([project_name, shas]) => {
          const r = await ignoreLostSessionsSelection({ project_name, shas });
          return { project_name, result: r };
        }),
      );
      const total_added = results.reduce((n, r) => n + r.result.added, 0);
      return { total_added, per_project: results };
    },
    onSuccess: (agg) => {
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      toast.success(
        t("lost_sessions.selection.ignore_toast", { n: agg.total_added }),
      );
    },
    onError: (err) => toast.error(extractApiError(err)),
  });
}
