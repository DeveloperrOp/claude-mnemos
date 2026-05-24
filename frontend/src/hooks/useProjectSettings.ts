import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  getProjectSettings,
  patchProjectSettings,
} from "@/api/settings.api";
import { extractApiError } from "@/lib/error";
import type { ProjectSettings, ProjectSettingsPatch } from "@/types/Settings";

const queryKey = (slug: string) => ["project-settings", slug];

export function useProjectSettings(slug: string) {
  return useQuery<ProjectSettings>({
    queryKey: queryKey(slug),
    queryFn: () => getProjectSettings(slug),
    staleTime: 30_000,
  });
}

export function useProjectSettingsMutation(slug: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (patch: ProjectSettingsPatch) => patchProjectSettings(slug, patch),
    onSuccess: (data) => {
      qc.setQueryData(queryKey(slug), data);
      toast.success(t("settings.saved_toast"));
    },
    onError: (err) =>
      toast.error(
        t("settings.save_error_toast", { message: extractApiError(err) }),
      ),
  });
}
