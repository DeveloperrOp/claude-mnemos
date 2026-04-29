import { useQuery } from "@tanstack/react-query";
import { listSuggestions, type ListSuggestionsOptions } from "@/api/suggestions.api";

export function useSuggestions(
  project: string | undefined,
  opts: ListSuggestionsOptions = {},
) {
  return useQuery({
    queryKey: ["suggestions", project, opts.status ?? null],
    queryFn: () => listSuggestions(project!, opts),
    enabled: !!project,
    refetchInterval: 5_000,
  });
}
