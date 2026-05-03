import { useQuery } from "@tanstack/react-query";
import { getInjectPreview } from "@/api/inject_preview.api";

export function useInjectPreview(project: string) {
  return useQuery({
    queryKey: ["inject-preview", project],
    queryFn: () => getInjectPreview(project),
    refetchInterval: 60_000,
    enabled: Boolean(project),
  });
}
