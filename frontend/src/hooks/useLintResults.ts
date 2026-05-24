import { useQuery } from "@tanstack/react-query";
import { getLintResults } from "@/api/lint.api";

export function useLintResults(project: string | undefined) {
  return useQuery({
    queryKey: ["lint", project, "results"],
    queryFn: () => getLintResults(project!),
    enabled: !!project,
    staleTime: 10_000,
  });
}
