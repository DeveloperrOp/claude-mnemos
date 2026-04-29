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
