import { useQuery } from "@tanstack/react-query";
import { getSession } from "@/api/sessions.api";

export function useSession(
  project: string | undefined,
  sessionId: string | undefined,
) {
  return useQuery({
    queryKey: ["session", project, sessionId],
    queryFn: () => getSession(project!, sessionId!),
    enabled: !!project && !!sessionId,
    refetchInterval: 5_000,
  });
}
