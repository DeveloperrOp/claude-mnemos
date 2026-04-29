import { useQuery } from "@tanstack/react-query";
import { getUsageByProject } from "@/api/metrics.api";

export function useUsageByProject(period = "30d") {
  return useQuery({
    queryKey: ["usage-by-project", period],
    queryFn: () => getUsageByProject(period),
    refetchInterval: 30_000,
  });
}
