import { useQuery } from "@tanstack/react-query";
import { getTimeline } from "@/api/metrics.api";

export function useUsageTimeline(period = "30d") {
  return useQuery({
    queryKey: ["usage-timeline", period],
    queryFn: () => getTimeline(period),
    refetchInterval: 60_000,
  });
}
