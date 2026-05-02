import { apiClient } from "./client";
import { JobSchema, type Job } from "@/types/Job";
import { z } from "zod";

const JobsResponseSchema = z.object({
  jobs: z.array(JobSchema),
  counts: z.record(z.string(), z.number()),
});

export interface JobsResponse {
  jobs: Job[];
  counts: Record<string, number>;
}

export interface ListJobsOptions {
  project?: string;
  status?: string;
  limit?: number;
}

export async function listJobs(opts: ListJobsOptions = {}): Promise<JobsResponse> {
  const params: Record<string, string | number> = {};
  if (opts.project) params.project = opts.project;
  if (opts.status) params.status = opts.status;
  if (opts.limit !== undefined) params.limit = opts.limit;
  const r = await apiClient.get("/jobs", { params });
  return JobsResponseSchema.parse(r.data);
}

export async function cancelJob(jobId: string): Promise<void> {
  await apiClient.delete(`/jobs/${encodeURIComponent(jobId)}`);
}
