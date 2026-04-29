import { z } from "zod";

// ── ActivityOperationType ───────────────────────────────────────────────────────
// Verified against claude_mnemos/state/activity.py::ActivityOperationType.
// Current backend literals: "ingest_extracted" | "ingest_raw_only" | "manual_restore" |
//   "ontology_apply" | "human_edit_detected" | "lint_fix" | "manual_edit" |
//   "manual_delete" | "manual_restore_trash" | "trash_dismissed" | "trash_emptied"
// Using z.string() for forward-compatibility — the list will grow as new operations
// are added, and a strict enum would reject unknown values from a newer daemon.

export const ActivityOperationTypeSchema = z.string();
export type ActivityOperationType = string;

// ── ActivityStatus ──────────────────────────────────────────────────────────────
// Verified against claude_mnemos/state/activity.py::ActivityStatus.
// Backend: Literal["success"] — only one value currently.
// NOTE: Plan design doc listed "partial" and "failed" as well — these do NOT exist
// in the backend. Schema fixed to match the real Literal["success"].

export const ActivityStatusSchema = z.enum(["success"]);
export type ActivityStatus = z.infer<typeof ActivityStatusSchema>;

// ── ActivityEntry ───────────────────────────────────────────────────────────────
// Verified against claude_mnemos/state/activity.py::ActivityEntry.

export const ActivityEntrySchema = z.object({
  id: z.string(),
  timestamp: z.string(),
  operation_type: ActivityOperationTypeSchema,
  status: ActivityStatusSchema,
  snapshot_path: z.string().nullable(),
  can_undo: z.boolean(),
  undone: z.boolean(),
  undone_at: z.string().nullable(),
  undone_by_id: z.string().nullable(),
  affected_pages: z.array(z.string()),
  metadata: z.record(z.string(), z.unknown()),
});
export type ActivityEntry = z.infer<typeof ActivityEntrySchema>;

// ── Response schemas ────────────────────────────────────────────────────────────

export const ActivityListResponseSchema = z.object({
  entries: z.array(ActivityEntrySchema),
  total: z.number().int().nonnegative(),
});
