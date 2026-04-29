import { z } from "zod";

// Shape matches GET /metrics/usage from claude_mnemos/daemon/routes/metrics.py::usage_route
export const UsageSummarySchema = z.object({
  period: z.string(),
  period_days: z.number().int().nonnegative(),
  sessions_covered: z.number().int().nonnegative(),
  tokens_input: z.number().int().nonnegative(),
  tokens_output: z.number().int().nonnegative(),
  tokens_injected: z.number().int().nonnegative(),
  raw_bytes_total: z.number().int().nonnegative(),
  tokens_per_byte: z.number().nullable(),
});
export type UsageSummary = z.infer<typeof UsageSummarySchema>;

// The daemon emits a UsageSummary with the same keys minus `period`, plus
// the project name (see daemon/routes/metrics.py::by_project_route). Declare
// the fields explicitly so widgets can consume them with full typing.
export const UsageByProjectEntrySchema = z.object({
  project: z.string(),
  period_days: z.number().int().nonnegative(),
  sessions_covered: z.number().int().nonnegative(),
  tokens_input: z.number().int().nonnegative(),
  tokens_output: z.number().int().nonnegative(),
  tokens_injected: z.number().int().nonnegative(),
  raw_bytes_total: z.number().int().nonnegative(),
  tokens_per_byte: z.number().nullable(),
}).passthrough();
export type UsageByProjectEntry = z.infer<typeof UsageByProjectEntrySchema>;

export const UsageByProjectResponseSchema = z.object({
  projects: z.array(UsageByProjectEntrySchema),
});
