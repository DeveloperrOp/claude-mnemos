import { z } from "zod";

export const ActiveSessionStatusSchema = z.enum(["hot", "cooling"]);
export type ActiveSessionStatus = z.infer<typeof ActiveSessionStatusSchema>;

export const ActiveSessionSchema = z.object({
  session_id: z.string(),
  transcript_path: z.string(),
  sha: z.string(),
  project_name: z.string(),
  cwd: z.string().nullable(),
  preview: z.string().nullable(),
  mtime: z.string(), // ISO datetime
  size_bytes: z.number().int().nonnegative(),
  status: ActiveSessionStatusSchema,
  auto_dump_at: z.string().nullable(),
});
export type ActiveSession = z.infer<typeof ActiveSessionSchema>;

export const RunningJobSchema = z.object({
  id: z.string(),
  kind: z.string(),
  status: z.string(),
  payload: z.record(z.string(), z.unknown()).optional(),
  project_name: z.string(),
  started_at: z.string().nullable().optional(),
});
export type RunningJob = z.infer<typeof RunningJobSchema>;

export const KpiSchema = z.object({
  queue: z.object({
    queued: z.number().int(),
    running: z.number().int(),
    failed: z.number().int(),
  }),
  active: z.object({
    hot: z.number().int(),
    cooling: z.number().int(),
  }),
  today: z.object({
    ingest_count: z.number().int(),
    pages_count: z.number().int(),
  }),
  tokens_today: z.number().int(),
  lost_total: z.number().int(),
});
export type Kpi = z.infer<typeof KpiSchema>;

export const DashboardSnapshotSchema = z.object({
  kpi: KpiSchema,
  active_sessions: z.array(ActiveSessionSchema),
  running_jobs: z.array(RunningJobSchema),
  errors: z.array(z.string()),
});
export type DashboardSnapshot = z.infer<typeof DashboardSnapshotSchema>;
