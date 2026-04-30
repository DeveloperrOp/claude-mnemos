import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getProjectSettings,
  patchProjectSettings,
} from "@/api/settings.api";
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
  return useMutation({
    mutationFn: (patch: ProjectSettingsPatch) => patchProjectSettings(slug, patch),
    onSuccess: (data) => {
      qc.setQueryData(queryKey(slug), data);
    },
  });
}
