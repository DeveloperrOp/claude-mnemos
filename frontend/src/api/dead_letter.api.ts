import { apiClient } from "./client";
import {
  DeadLetterListResponseSchema,
  JobSchema,
  type Job,
} from "@/types/Job";

export interface ListDeadLetterOptions {
  limit?: number;
  offset?: number;
}

export async function listDeadLetter(
  opts: ListDeadLetterOptions = {},
): Promise<Job[]> {
  const params: Record<string, number> = {};
  if (opts.limit !== undefined) params.limit = opts.limit;
  if (opts.offset !== undefined) params.offset = opts.offset;
  const r = await apiClient.get("/dead-letter", { params });
  return DeadLetterListResponseSchema.parse(r.data).jobs;
}

export async function getDeadLetter(jobId: string): Promise<Job> {
  const r = await apiClient.get(`/dead-letter/${encodeURIComponent(jobId)}`);
  return JobSchema.parse(r.data);
}

export async function retryDeadLetter(jobId: string): Promise<Job> {
  const r = await apiClient.post(`/dead-letter/${encodeURIComponent(jobId)}/retry`);
  return r.data as Job;
}

export async function dismissDeadLetter(jobId: string): Promise<void> {
  await apiClient.delete(`/dead-letter/${encodeURIComponent(jobId)}`);
}
