import { apiClient } from "./client";
import {
  SnapshotListResponseSchema,
  type SnapshotInfo,
} from "@/types/Snapshot";

export async function listSnapshots(
  project: string,
): Promise<SnapshotInfo[]> {
  const r = await apiClient.get(`/snapshots/${encodeURIComponent(project)}`);
  return SnapshotListResponseSchema.parse(r.data).snapshots;
}
