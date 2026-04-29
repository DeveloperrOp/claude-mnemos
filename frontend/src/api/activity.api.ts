import { apiClient } from "./client";
import {
  ActivityEntrySchema,
  ActivityListResponseSchema,
  type ActivityEntry,
} from "@/types/Activity";

export interface ListActivityOptions {
  limit?: number;
  offset?: number;
}

export async function listActivity(
  project: string,
  opts: ListActivityOptions = {},
): Promise<{ entries: ActivityEntry[]; total: number }> {
  const params: Record<string, number> = {};
  if (opts.limit !== undefined) params.limit = opts.limit;
  if (opts.offset !== undefined) params.offset = opts.offset;
  const r = await apiClient.get(
    `/activity/${encodeURIComponent(project)}`,
    { params },
  );
  return ActivityListResponseSchema.parse(r.data);
}

export async function getActivityEntry(
  project: string,
  opId: string,
): Promise<ActivityEntry> {
  const r = await apiClient.get(
    `/activity/${encodeURIComponent(project)}/${encodeURIComponent(opId)}`,
  );
  return ActivityEntrySchema.parse(r.data);
}

export interface UndoApiResult {
  success: boolean;
  op_id: string;
  restored_pages: string[];
  new_entry_id: string;
}

export async function undoOperation(
  project: string, op_id: string,
): Promise<UndoApiResult> {
  const r = await apiClient.post(
    `/activity/${encodeURIComponent(project)}/${encodeURIComponent(op_id)}/undo`,
  );
  return r.data as UndoApiResult;
}
