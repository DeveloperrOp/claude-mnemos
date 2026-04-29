import { useQuery } from "@tanstack/react-query";
import { getDeadLetter } from "@/api/dead_letter.api";

export function useDeadLetterEntry(jobId: string | undefined) {
  return useQuery({
    queryKey: ["dead-letter-entry", jobId],
    queryFn: () => getDeadLetter(jobId!),
    enabled: !!jobId,
    refetchInterval: 5_000,
  });
}
