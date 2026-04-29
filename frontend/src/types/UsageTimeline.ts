import { z } from "zod";

export const UsageTimelinePointSchema = z.object({
  date: z.string(),
  sessions: z.number().int().nonnegative(),
  tokens_input: z.number().int().nonnegative(),
  tokens_output: z.number().int().nonnegative(),
});
export type UsageTimelinePoint = z.infer<typeof UsageTimelinePointSchema>;

export const UsageTimelineResponseSchema = z.object({
  points: z.array(UsageTimelinePointSchema),
});
