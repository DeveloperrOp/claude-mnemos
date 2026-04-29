import { useQuery } from "@tanstack/react-query";
import { listTrash } from "@/api/trash.api";

export function useTrash(project: string | undefined) {
  return useQuery({
    queryKey: ["trash", project],
    queryFn: () => listTrash(project!),
    enabled: !!project,
    refetchInterval: 5_000,
  });
}
