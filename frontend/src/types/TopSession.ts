import { z } from "zod";

export const TopSessionSchema = z.object({
  project: z.string(),
  session_id: z.string(),
  ingested_at: z.string(),
  tokens_input: z.number().int().nonnegative(),
  tokens_output: z.number().int().nonnegative(),
  tokens_total: z.number().int().nonnegative(),
  raw_bytes: z.number().int().nonnegative(),
});
export type TopSession = z.infer<typeof TopSessionSchema>;

export const TopSessionsResponseSchema = z.object({
  sessions: z.array(TopSessionSchema),
});
