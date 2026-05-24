import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { updateProject, type UpdateProjectBody } from "@/api/projects.api";
import { extractApiError } from "@/lib/error";

export function useProjectUpdate(slug: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (patch: UpdateProjectBody) => updateProject(slug, patch),
    onSuccess: () => {
      // Invalidate both the list (sidebar/switcher) and the per-project query
      // (settings page, project detail header).
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["project", slug] });
      toast.success(t("settings.saved_toast"));
    },
    onError: (err) =>
      toast.error(
        t("settings.save_error_toast", { message: extractApiError(err) }),
      ),
  });
}
