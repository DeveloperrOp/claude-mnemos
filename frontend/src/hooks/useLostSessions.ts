import { useQuery } from "@tanstack/react-query";
import { listLostSessions } from "@/api/lost_sessions.api";

export function useLostSessions() {
  return useQuery({
    queryKey: ["lost-sessions"],
    queryFn: listLostSessions,
    refetchInterval: 30_000,
  });
}
