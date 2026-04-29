import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { createProject, type CreateProjectBody } from "@/api/projects.api";
import { extractApiError } from "@/lib/error";

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
    onError: (err) => toast.error(extractApiError(err)),
  });
}
