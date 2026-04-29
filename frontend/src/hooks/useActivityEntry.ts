import { useQuery } from "@tanstack/react-query";
import { getActivityEntry } from "@/api/activity.api";

export function useActivityEntry(
  project: string | undefined,
  opId: string | undefined,
) {
  return useQuery({
    queryKey: ["activity-entry", project, opId],
    queryFn: () => getActivityEntry(project!, opId!),
    enabled: !!project && !!opId,
    refetchInterval: 5_000,
  });
}
