import { z } from "zod";

export const VaultHealthSchema = z.object({
  watchdog_running: z.boolean(),
  jobs_queued: z.number().int().nonnegative(),
  jobs_running: z.number().int().nonnegative(),
  jobs_dead_letter: z.number().int().nonnegative(),
});
export type VaultHealth = z.infer<typeof VaultHealthSchema>;

export const SchedulerJobInfoSchema = z.object({
  id: z.string(),
  next_run_time: z.string().nullable(),
  trigger: z.string(),
});
export type SchedulerJobInfo = z.infer<typeof SchedulerJobInfoSchema>;

export const HealthSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  version: z.string(),
  uptime_s: z.number().nonnegative(),
  alerts_count: z.number().int().nonnegative(),
  vaults: z.record(z.string(), VaultHealthSchema),
  jobs_alert: z.boolean(),
  scheduler_jobs: z.array(SchedulerJobInfoSchema).default([]),
});
export type Health = z.infer<typeof HealthSchema>;
