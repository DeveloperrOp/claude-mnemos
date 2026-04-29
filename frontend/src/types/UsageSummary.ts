import { z } from "zod";

export const UsageSummarySchema = z.object({
  period: z.string(),
  total_tokens_injected: z.number().int().nonnegative(),
  tokens_full: z.number().int().nonnegative(),
  sessions_covered: z.number().int().nonnegative(),
  avg_compression_ratio: z.number().nonnegative(),
  events_count: z.number().int().nonnegative(),
});
export type UsageSummary = z.infer<typeof UsageSummarySchema>;

export const UsageByProjectEntrySchema = z.object({
  project: z.string(),
  // The daemon emits a UsageSummary with the same keys minus `period`,
  // plus the project name. Accept extra fields gracefully.
}).passthrough();
export type UsageByProjectEntry = z.infer<typeof UsageByProjectEntrySchema>;

export const UsageByProjectResponseSchema = z.object({
  projects: z.array(UsageByProjectEntrySchema),
});
