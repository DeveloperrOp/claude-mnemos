import { useQuery } from "@tanstack/react-query";
import { getSetupStatus } from "@/api/diagnostics.api";

export function useSetupStatus() {
  return useQuery({
    queryKey: ["setup-status"],
    queryFn: getSetupStatus,
    refetchInterval: 30_000,
  });
}
