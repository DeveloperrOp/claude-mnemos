import { z } from "zod";

export const LostSessionSchema = z.object({
  session_id: z.string(),
  transcript_path: z.string(),
  sha: z.string(),
  size_bytes: z.number().int().nonnegative(),
  mtime: z.string(),
  project_name: z.string(),
  cwd: z.string().nullable().optional(),
  preview: z.string().nullable().optional(),
});
export type LostSession = z.infer<typeof LostSessionSchema>;

export const LostSessionListResponseSchema = z.object({
  sessions: z.array(LostSessionSchema),
  total: z.number().int().nonnegative(),
});
