import { useQuery } from "@tanstack/react-query";
import { listSnapshots } from "@/api/snapshots.api";

export function useSnapshots(project: string | undefined) {
  return useQuery({
    queryKey: ["snapshots", project],
    queryFn: () => listSnapshots(project!),
    enabled: !!project,
    refetchInterval: 30_000,
  });
}
