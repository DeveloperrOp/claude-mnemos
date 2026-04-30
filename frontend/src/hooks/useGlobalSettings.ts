import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getGlobalSettings,
  patchGlobalSettings,
} from "@/api/settings.api";
import type { GlobalSettings, GlobalSettingsPatch } from "@/types/Settings";

const queryKey = ["global-settings"];

export function useGlobalSettings() {
  return useQuery<GlobalSettings>({
    queryKey,
    queryFn: getGlobalSettings,
    staleTime: 30_000,
  });
}

export function useGlobalSettingsMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: GlobalSettingsPatch) => patchGlobalSettings(patch),
    onSuccess: (data) => {
      qc.setQueryData(queryKey, data);
    },
  });
}
