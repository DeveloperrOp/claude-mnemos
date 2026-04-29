import { apiClient } from "./client";
import {
  TrashListResponseSchema,
  type TrashEntry,
} from "@/types/Trash";

export async function listTrash(
  project: string,
): Promise<{ entries: TrashEntry[]; total: number }> {
  const r = await apiClient.get(`/trash/${encodeURIComponent(project)}`);
  return TrashListResponseSchema.parse(r.data);
}

export interface RestoreTrashResult {
  success: boolean;
  snapshot_path: string | null;
  activity_id: string;
  restored_path: string;
}

export async function restoreTrash(
  project: string,
  trash_id: string,
): Promise<RestoreTrashResult> {
  const r = await apiClient.post(
    `/trash/${encodeURIComponent(project)}/${encodeURIComponent(trash_id)}/restore`,
  );
  return r.data as RestoreTrashResult;
}

export async function deleteTrash(project: string, trash_id: string): Promise<void> {
  await apiClient.delete(
    `/trash/${encodeURIComponent(project)}/${encodeURIComponent(trash_id)}`,
  );
}
