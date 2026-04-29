import { z } from "zod";

export const VaultHealthSchema = z.object({
  watchdog_running: z.boolean(),
  jobs_queued: z.number().int().nonnegative(),
  jobs_running: z.number().int().nonnegative(),
  jobs_dead_letter: z.number().int().nonnegative(),
});
export type VaultHealth = z.infer<typeof VaultHealthSchema>;

export const HealthSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  version: z.string(),
  uptime_s: z.number().nonnegative(),
  alerts_count: z.number().int().nonnegative(),
  vaults: z.record(z.string(), VaultHealthSchema),
  jobs_alert: z.boolean(),
  scheduler_jobs: z.array(z.unknown()).optional(),
});
export type Health = z.infer<typeof HealthSchema>;
