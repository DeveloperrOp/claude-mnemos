import { useQuery } from "@tanstack/react-query";
import { getTopSessions } from "@/api/metrics.api";

export function useTopSessions(limit = 10) {
  return useQuery({
    queryKey: ["top-sessions", limit],
    queryFn: () => getTopSessions(limit),
    refetchInterval: 60_000,
  });
}
