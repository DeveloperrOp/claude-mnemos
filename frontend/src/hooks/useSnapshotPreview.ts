import { useQuery } from "@tanstack/react-query";
import { previewSnapshot } from "@/api/snapshots.api";

export function useSnapshotPreview(
  project: string | undefined,
  name: string | undefined,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["snapshot-preview", project, name],
    queryFn: () => previewSnapshot(project!, name!),
    enabled: !!project && !!name && enabled,
    staleTime: 30_000,
  });
}
