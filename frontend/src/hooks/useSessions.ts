import { useQuery } from "@tanstack/react-query";
import { listSessions, type ListSessionsOptions } from "@/api/sessions.api";

export function useSessions(
  project: string | undefined,
  opts: ListSessionsOptions = {},
) {
  return useQuery({
    queryKey: ["sessions", project, opts.status ?? null, opts.limit ?? null],
    queryFn: () => listSessions(project!, opts),
    enabled: !!project,
    refetchInterval: 5_000,
  });
}
