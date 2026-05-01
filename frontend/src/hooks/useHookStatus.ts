import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

export interface HookEventStatus {
  installed: boolean;
  mnemos_commands: string[];
  other_commands: string[];
}

export interface HookStatus {
  settings_path: string;
  settings_exists: boolean;
  session_start: HookEventStatus;
  session_end: HookEventStatus;
  all_installed: boolean;
}

export function useHookStatus() {
  return useQuery<HookStatus>({
    queryKey: ["hooks", "status"],
    queryFn: async () => {
      const r = await apiClient.get<HookStatus>("/hooks/status");
      return r.data;
    },
    refetchInterval: 30_000, // re-check every 30s (cheap, file-system poll)
  });
}
