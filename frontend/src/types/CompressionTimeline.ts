import { z } from "zod";

export const CompressionTimelinePointSchema = z.object({
  date: z.string(),
  events_count: z.number().int().nonnegative(),
  valid_events_count: z.number().int().nonnegative(),
  avg_compression_ratio: z.number().nullable(),
});
export type CompressionTimelinePoint = z.infer<typeof CompressionTimelinePointSchema>;

export const CompressionTimelineResponseSchema = z.object({
  points: z.array(CompressionTimelinePointSchema),
});
