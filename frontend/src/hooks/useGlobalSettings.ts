import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  getGlobalSettings,
  patchGlobalSettings,
} from "@/api/settings.api";
import { extractApiError } from "@/lib/error";
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
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (patch: GlobalSettingsPatch) => patchGlobalSettings(patch),
    onSuccess: (data) => {
      qc.setQueryData(queryKey, data);
      toast.success(t("settings.saved_toast"));
    },
    onError: (err) =>
      toast.error(
        t("settings.save_error_toast", { message: extractApiError(err) }),
      ),
  });
}
