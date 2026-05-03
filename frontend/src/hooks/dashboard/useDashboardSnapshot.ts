import { useQuery } from "@tanstack/react-query";
import { getDashboardSnapshot } from "@/api/dashboard.api";

export function useDashboardSnapshot() {
  return useQuery({
    queryKey: ["dashboard-snapshot"],
    queryFn: getDashboardSnapshot,
    refetchInterval: 10_000,
  });
}
