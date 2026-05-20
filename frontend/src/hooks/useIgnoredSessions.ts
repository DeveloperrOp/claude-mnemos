import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  listIgnoredSessions,
  unIgnoreLostSessionsSelection,
} from "@/api/lost_sessions.api";

export function useIgnoredSessions() {
  return useQuery({
    queryKey: ["ignored-sessions"],
    queryFn: listIgnoredSessions,
  });
}

export function useUnIgnoreLostSessions() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: unIgnoreLostSessionsSelection,
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ["ignored-sessions"] });
      void qc.invalidateQueries({ queryKey: ["lost-sessions"] });
      toast.success(
        t("ignored_sessions.unignored_toast", { count: data.removed }),
      );
    },
    onError: (err: Error) => {
      toast.error(t("ignored_sessions.unignore_error", { message: err.message }));
    },
  });
}
