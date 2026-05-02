import { useQuery } from "@tanstack/react-query";
import { getLostSessionTranscript } from "@/api/lost_sessions.api";

export function useLostSessionTranscript(session_id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["lost-session-transcript", session_id],
    queryFn: () => getLostSessionTranscript(session_id, 100),
    enabled,
    staleTime: 5 * 60_000,
  });
}
