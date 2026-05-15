import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  listIgnoredSessions,
  unIgnoreLostSessionsSelection,
  type UnIgnoreSelectionBody,
} from "@/api/lost_sessions.api";
import type { IgnoredSession } from "@/types/LostSession";

export function useIgnoredSessions() {
  return useQuery({
    queryKey: ["ignored-sessions"],
    queryFn: listIgnoredSessions,
    staleTime: 30_000,
  });
}

export function useUnIgnoreLostSessions() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (input: {
      selected: Array<Pick<IgnoredSession, "sha" | "project_name">>;
    }) => {
      const byProject = new Map<string, string[]>();
      for (const s of input.selected) {
        const arr = byProject.get(s.project_name) ?? [];
        arr.push(s.sha);
        byProject.set(s.project_name, arr);
      }
      const calls: Promise<unknown>[] = [];
      for (const [project_name, shas] of byProject) {
        const body: UnIgnoreSelectionBody = { project_name, shas };
        calls.push(unIgnoreLostSessionsSelection(body));
      }
      return Promise.all(calls);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ignored-sessions"] });
      qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      toast.success(t("ignored_sessions.restored_toast"));
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(t("ignored_sessions.restore_error", { error: msg }));
    },
  });
}
