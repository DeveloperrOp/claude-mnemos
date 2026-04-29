import { useQuery } from "@tanstack/react-query";
import { listPages } from "@/api/pages.api";

export function usePages(project: string | undefined) {
  return useQuery({
    queryKey: ["pages", project],
    queryFn: () => listPages(project!),
    enabled: !!project,
    refetchInterval: 30_000,
  });
}
