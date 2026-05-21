import { z } from "zod";

export const SnapshotKindSchema = z.enum(["pre-op", "daily", "manual"]);
export type SnapshotKind = z.infer<typeof SnapshotKindSchema>;

export const SnapshotInfoSchema = z.object({
  name: z.string(),
  kind: SnapshotKindSchema,
  timestamp: z.string(),
  op_id: z.string().nullable(),
  op_type: z.string().nullable(),
  label: z.string().nullable(),
  size_bytes: z.number().int().nonnegative(),
  path: z.string(),
});
export type SnapshotInfo = z.infer<typeof SnapshotInfoSchema>;

export const SnapshotListResponseSchema = z.object({
  snapshots: z.array(SnapshotInfoSchema),
});

export const RestorePreviewSchema = z.object({
  snapshot_name: z.string(),
  snapshot_timestamp: z.string(),
  snapshot_kind: z.string(),
  snapshot_file_count: z.number().int().nonnegative(),
  vault_file_count: z.number().int().nonnegative(),
  will_create: z.array(z.string()),
  will_delete: z.array(z.string()),
  will_overwrite: z.array(z.string()),
  unchanged_count: z.number().int().nonnegative(),
  sample_limit: z.number().int().positive(),
  truncated: z.boolean(),
});
export type RestorePreview = z.infer<typeof RestorePreviewSchema>;
