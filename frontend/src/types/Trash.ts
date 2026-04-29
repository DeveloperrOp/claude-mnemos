import { z } from "zod";

export const TrashEntrySchema = z.object({
  trash_id: z.string(),
  deleted_at: z.string(),
  original_path: z.string().nullable(),
  operation_type: z.string().nullable(),
  page_basename: z.string().nullable(),
  restorable: z.boolean(),
  restore_blocked_reason: z.string().nullable(),
});
export type TrashEntry = z.infer<typeof TrashEntrySchema>;

export const TrashListResponseSchema = z.object({
  entries: z.array(TrashEntrySchema),
  total: z.number().int().nonnegative(),
});
