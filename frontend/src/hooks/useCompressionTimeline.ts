import { useQuery } from "@tanstack/react-query";
import { getCompressionTimeline } from "@/api/metrics.api";

export function useCompressionTimeline(period = "30d") {
  return useQuery({
    queryKey: ["compression-timeline", period],
    queryFn: () => getCompressionTimeline(period),
    refetchInterval: 60_000,
  });
}
