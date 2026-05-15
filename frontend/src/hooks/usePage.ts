import { useQuery } from "@tanstack/react-query";
import { getPage } from "@/api/pages.api";

export function usePage(
  project: string | undefined,
  pageRef: string | undefined,
) {
  return useQuery({
    queryKey: ["page", project, pageRef],
    queryFn: () => getPage(project!, pageRef!),
    enabled: !!project && !!pageRef,
    refetchInterval: 7 * 60_000,
  });
}
