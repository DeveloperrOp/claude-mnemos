import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

export interface HookErrorEntry {
  ts: string;
  hook: string;
  kind: string;
  message: string;
  traceback?: string | null;
  context?: Record<string, unknown>;
}

export interface HookErrorsResponse {
  log_path: string;
  count: number;
  entries: HookErrorEntry[];
}

export function useHookErrors(limit = 10) {
  return useQuery<HookErrorsResponse>({
    queryKey: ["hooks", "errors", limit],
    queryFn: async () => {
      const r = await apiClient.get<HookErrorsResponse>(`/hooks/errors?limit=${limit}`);
      return r.data;
    },
    refetchInterval: 30_000,
  });
}
