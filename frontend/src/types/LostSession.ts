import { z } from "zod";

export const LostSessionSchema = z.object({
  session_id: z.string(),
  transcript_path: z.string(),
  sha: z.string(),
  size_bytes: z.number().int().nonnegative(),
  mtime: z.string(),
  project_name: z.string(),
  cwd: z.string().nullable().optional(),
  group_root: z.string().nullable().optional(),
  preview: z.string().nullable().optional(),
});
export type LostSession = z.infer<typeof LostSessionSchema>;

export const LostSessionListResponseSchema = z.object({
  sessions: z.array(LostSessionSchema),
  total: z.number().int().nonnegative(),
});

export const IgnoredSessionSchema = z.object({
  sha: z.string(),
  project_name: z.string().optional().default(""),
  transcript_path: z.string().nullable().optional(),
  session_id: z.string().nullable().optional(),
  size_bytes: z.number().int().nonnegative().nullable().optional(),
  mtime: z.string().nullable().optional(),
  preview: z.string().nullable().optional(),
  cwd: z.string().nullable().optional(),
});
export type IgnoredSession = z.infer<typeof IgnoredSessionSchema>;

export const IgnoredSessionListResponseSchema = z.object({
  ignored: z.array(IgnoredSessionSchema),
  total: z.number().int().nonnegative(),
});
export type IgnoredSessionListResponse = z.infer<typeof IgnoredSessionListResponseSchema>;
