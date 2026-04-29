import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import axios from "axios";
import { createProject, type CreateProjectBody } from "@/api/projects.api";
import { extractApiError } from "@/lib/error";

// 409 (name conflict) and 500 (mount failure) are surfaced inline by the
// Onboarding form, so we skip the redundant toast for them.
const INLINE_HANDLED_STATUSES = new Set([409, 500]);

export function useProjectCreate() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (body: CreateProjectBody) => createProject(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["health"] });
      toast.success(t("onboarding.success_toast"));
    },
    onError: (err) => {
      if (axios.isAxiosError(err)) {
        const status = err.response?.status;
        if (status !== undefined && INLINE_HANDLED_STATUSES.has(status)) return;
      }
      toast.error(extractApiError(err));
    },
  });
}
