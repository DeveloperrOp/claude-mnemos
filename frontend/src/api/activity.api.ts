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
