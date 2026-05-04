import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { HookStatus } from "./useHookStatus";

interface InstallResult {
  ok: boolean;
  python: string;
  session_start_script: string;
  session_end_script: string;
  backup_path: string | null;
}

interface InstallResponse {
  install_result: InstallResult;
  status: HookStatus;
}

export function useInstallHooks() {
  const qc = useQueryClient();
  return useMutation<InstallResponse, Error>({
    mutationFn: async () => {
      const r = await apiClient.post<InstallResponse>("/hooks/install");
      return r.data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["hooks", "status"] });
      // SetupChecklist + Diagnostics rely on /api/onboarding/setup-status,
      // which surfaces the same hook-presence detector. Refresh so the row
      // flips to OK as soon as the install succeeds.
      void qc.invalidateQueries({ queryKey: ["setup-status"] });
    },
  });
}
