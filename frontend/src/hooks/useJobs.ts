import { useQuery } from "@tanstack/react-query";
import { listJobs, type ListJobsOptions } from "@/api/jobs.api";

export function useJobs(opts: ListJobsOptions = {}) {
  return useQuery({
    queryKey: ["jobs", opts.project ?? null, opts.status ?? null, opts.limit ?? null],
    queryFn: () => listJobs(opts),
    refetchInterval: 5_000,
  });
}
