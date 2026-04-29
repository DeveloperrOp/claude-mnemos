import { useQuery } from "@tanstack/react-query";
import { listDeadLetter, type ListDeadLetterOptions } from "@/api/dead_letter.api";

export function useDeadLetter(opts: ListDeadLetterOptions = {}) {
  return useQuery({
    queryKey: ["dead-letter", opts.limit ?? null, opts.offset ?? null],
    queryFn: () => listDeadLetter(opts),
    refetchInterval: 5_000,
  });
}
