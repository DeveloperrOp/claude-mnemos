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
