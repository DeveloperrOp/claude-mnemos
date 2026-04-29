import { z } from "zod";

export const JobKindSchema = z.string();
export type JobKind = z.infer<typeof JobKindSchema>;

export const JobStatusSchema = z.enum([
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "dead_letter",
]);
export type JobStatus = z.infer<typeof JobStatusSchema>;

export const JobSchema = z.object({
  id: z.string(),
  kind: JobKindSchema,
  payload: z.record(z.string(), z.unknown()),
  status: JobStatusSchema,
  attempt: z.number().int().nonnegative(),
  next_attempt_at: z.string(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  error: z.string().nullable(),
  error_traceback: z.string().nullable(),
  project_name: z.string(),
});
export type Job = z.infer<typeof JobSchema>;

export const DeadLetterListResponseSchema = z.object({
  jobs: z.array(JobSchema),
});
