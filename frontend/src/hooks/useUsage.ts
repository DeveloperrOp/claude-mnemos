import { useQuery } from "@tanstack/react-query";
import { getUsage } from "@/api/metrics.api";

export function useUsage(period = "1d") {
  return useQuery({
    queryKey: ["usage", period],
    queryFn: () => getUsage(period),
    refetchInterval: 30_000,
  });
}
