import { useQuery } from "@tanstack/react-query";
import { getPageBacklinks } from "@/api/pages.api";

export function usePageBacklinks(
  project: string | undefined,
  pageRef: string | undefined,
) {
  return useQuery({
    queryKey: ["page-backlinks", project, pageRef],
    queryFn: () => getPageBacklinks(project!, pageRef!),
    enabled: !!project && !!pageRef,
    refetchInterval: 60_000,
  });
}
