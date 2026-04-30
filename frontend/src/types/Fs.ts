import { z } from "zod";

export const FsHomeSchema = z.object({
  home: z.string(),
});
export type FsHome = z.infer<typeof FsHomeSchema>;

export const FsEntrySchema = z.object({
  name: z.string(),
  path: z.string(),
  type: z.enum(["directory", "file"]).default("directory"),
});
export type FsEntry = z.infer<typeof FsEntrySchema>;

export const FsBrowseSchema = z.object({
  cwd: z.string(),
  parent: z.string().nullable(),
  entries: z.array(FsEntrySchema),
  truncated: z.boolean().default(false),
});
export type FsBrowse = z.infer<typeof FsBrowseSchema>;

export const FsMkdirResponseSchema = z.object({
  path: z.string(),
});
export type FsMkdirResponse = z.infer<typeof FsMkdirResponseSchema>;

export const FsDriveSchema = z.object({
  name: z.string(),
  path: z.string(),
});
export type FsDrive = z.infer<typeof FsDriveSchema>;

export const FsDrivesSchema = z.object({
  drives: z.array(FsDriveSchema),
});
export type FsDrives = z.infer<typeof FsDrivesSchema>;
