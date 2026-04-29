import { useQuery } from "@tanstack/react-query";
import { listActivity, type ListActivityOptions } from "@/api/activity.api";

export function useActivity(
  project: string | undefined,
  opts: ListActivityOptions = {},
) {
  return useQuery({
    queryKey: ["activity", project, opts.limit ?? null, opts.offset ?? null],
    queryFn: () => listActivity(project!, opts),
    enabled: !!project,
    refetchInterval: 5_000,
  });
}
